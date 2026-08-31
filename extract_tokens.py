#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Token 提取脚本
从已登录的 TraeWork 和 CodeBuddy 客户端中提取签到所需的 Token。

使用方法:
  pip install pycryptodome
  python extract_tokens.py

提取结果会直接打印，请将对应的值填入 GitHub Secrets:
  TRAE_TOKEN      -> TraeWork 的 JWT Token
  CODEBUDDY_TOKEN -> CodeBuddy 的 accessToken
"""

import os
import sys
import json
import hashlib
import base64
from pathlib import Path

try:
    from Crypto.Cipher import AES
except ImportError:
    print("[错误] 缺少 pycryptodome 依赖，请先运行: pip install pycryptodome")
    sys.exit(1)


# ============================================================
# TraeWork (TRAE SOLO CN) Token 解密
# ============================================================

# 硬编码盐值，来自 Trae CN 前端 JS 源码
SALT_A = bytes([
    82, 9, 106, 213, 48, 54, 165, 56, 191, 64, 163, 158, 129, 243, 215, 251,
    124, 227, 57, 130, 155, 47, 255, 135, 52, 142, 67, 68, 196, 222, 233, 203,
    84, 123, 148, 50, 166, 194, 35, 61, 238, 76, 149, 11, 66, 250, 195, 78,
    8, 46, 161, 102, 40, 217, 36, 178, 118, 91, 162, 73, 109, 139, 209, 37,
])
SALT_B = bytes([
    31, 221, 168, 51, 136, 7, 199, 49, 177, 18, 16, 89, 39, 128, 236, 95,
    96, 81, 127, 169, 25, 181, 74, 13, 45, 229, 122, 159, 147, 201, 156, 239,
    160, 224, 59, 77, 174, 42, 245, 176, 200, 235, 187, 60, 131, 83, 153, 97,
    23, 43, 4, 126, 186, 119, 214, 38, 225, 105, 20, 99, 85, 33, 12, 125,
])
SALT_C = bytes([
    191, 192, 216, 250, 122, 246, 220, 97, 31, 254, 98, 27, 8, 72, 71, 176,
    135, 99, 96, 18, 127, 101, 203, 104, 211, 102, 191, 125, 37, 72, 150, 156,
    51, 229, 121, 35, 17, 153, 141, 177, 110, 131, 150, 128, 172, 255, 254, 6,
    18, 140, 55, 62, 236, 249, 135, 64, 135, 12, 117, 4, 89, 149, 168, 209,
])
SALT_D = bytes([
    246, 204, 26, 232, 232, 70, 129, 109, 223, 146, 169, 242, 23, 241, 105, 145,
    50, 196, 165, 42, 254, 120, 3, 54, 244, 207, 209, 85, 53, 6, 138, 106,
    175, 148, 31, 204, 186, 186, 165, 182, 87, 142, 49, 10, 39, 110, 26, 154,
    86, 56, 173, 125, 18, 64, 198, 225, 99, 99, 83, 82, 191, 134, 76, 170,
])


def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def detect_enc_type(header):
    """检测加密类型: AES 或 AES_PRIVATE"""
    if (header[0] == 0x74 and header[1] == 0x63 and
            header[2] == 0x05 and header[3] == 0x10 and
            header[4] == 0x00 and header[5] == 0x00):
        return "AES"
    if (header[0] == 18 and header[1] == 57 and
            header[2] == 32 and header[3] == 32 and
            header[4] == 2 and header[5] == 3):
        return "AES_PRIVATE"
    return "UNKNOWN"


def derive_key_iv(random_bytes, enc_type):
    """从随机字节和盐值推导 AES 密钥和 IV"""
    if enc_type == "AES_PRIVATE":
        salt = xor_bytes(SALT_C, SALT_D)
    else:
        salt = xor_bytes(SALT_A, SALT_B)

    hash_of_random = hashlib.sha512(random_bytes).digest()
    combined = hash_of_random + salt
    final_hash = hashlib.sha512(combined).digest()

    aes_key = final_hash[:16]
    iv = final_hash[16:32]
    return aes_key, iv


def aes_cbc_decrypt(key, iv, data):
    """AES-128-CBC 解密，自动去除 PKCS7 填充"""
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(data)
    # 去除 PKCS7 填充
    pad_len = decrypted[-1]
    if pad_len < 1 or pad_len > 16:
        return decrypted
    return decrypted[:-pad_len]


def decrypt_storage_value(encrypted_value):
    """解密 storage.json 中的加密值"""
    raw = base64.b64decode(encrypted_value)
    header = raw[:6]
    random_bytes = raw[6:38]
    encrypted_data = raw[38:]

    enc_type = detect_enc_type(header)
    if enc_type == "UNKNOWN":
        raise ValueError(f"未知的加密类型，header: {header.hex()}")

    aes_key, iv = derive_key_iv(random_bytes, enc_type)
    decrypted = aes_cbc_decrypt(aes_key, iv, encrypted_data)

    # 前 64 字节是 SHA-512 校验哈希，后面是明文
    stored_hash = decrypted[:64]
    plaintext = decrypted[64:]

    computed_hash = hashlib.sha512(plaintext).digest()
    if stored_hash != computed_hash:
        print("[警告] 哈希校验未通过，解密结果可能不正确")

    return plaintext.decode("utf-8")


def extract_trae_token():
    """从本地 TraeWork 客户端提取 JWT Token"""
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))

    # 按优先级尝试不同版本的路径
    candidates = [
        ("TRAE SOLO CN", Path(appdata) / "TRAE SOLO CN" / "User"),
        ("Trae CN", Path(appdata) / "Trae CN" / "User"),
        ("TRAE SOLO", Path(appdata) / "TRAE SOLO" / "User"),
        ("Trae", Path(appdata) / "Trae" / "User"),
    ]

    for name, data_dir in candidates:
        storage_path = data_dir / "globalStorage" / "storage.json"
        if not storage_path.exists():
            continue

        print(f"\n[{name}] 找到 storage.json: {storage_path}")

        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                storage = json.load(f)
        except Exception as e:
            print(f"  读取失败: {e}")
            continue

        auth_key = "iCubeAuthInfo://icube.cloudide"
        encrypted_auth = storage.get(auth_key)
        if not encrypted_auth:
            print(f"  未找到认证数据 (key: {auth_key})")
            continue

        # 如果是明文 JSON（国际版）
        if isinstance(encrypted_auth, str) and encrypted_auth.strip().startswith("{"):
            auth_data = json.loads(encrypted_auth)
        else:
            try:
                decrypted = decrypt_storage_value(encrypted_auth)
                auth_data = json.loads(decrypted)
            except Exception as e:
                print(f"  解密失败: {e}")
                continue

        # 尝试多种可能的字段名
        token = None
        for key in ("token", "Token", "accessToken", "access_token"):
            if key in auth_data:
                token = auth_data[key]
                break
            if "Result" in auth_data and key in auth_data["Result"]:
                token = auth_data["Result"][key]
                break

        if token:
            # 截取显示
            display = token[:50] + "..." if len(token) > 50 else token
            print(f"  ✅ 成功提取 Token: {display}")
            return token
        else:
            print(f"  解密成功但未找到 token 字段，可用字段: {list(auth_data.keys())}")
            # 打印所有字段帮助排查
            for k, v in auth_data.items():
                if isinstance(v, str) and len(v) > 20:
                    print(f"    {k}: {v[:40]}...")
                elif not isinstance(v, (dict, list)):
                    print(f"    {k}: {v}")

    return None


# ============================================================
# CodeBuddy (WorkBuddy) Token 提取
# ============================================================

def extract_codebuddy_token():
    """从本地 CodeBuddy / WorkBuddy 客户端提取 accessToken"""
    localappdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    auth_path = Path(localappdata) / "CodeBuddyExtension" / "Data" / "Public" / "auth" / "workbuddy-desktop.info"

    if not auth_path.exists():
        print(f"\n[CodeBuddy] 未找到认证文件: {auth_path}")
        return None

    print(f"\n[CodeBuddy] 找到认证文件: {auth_path}")

    try:
        with open(auth_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  读取失败: {e}")
        return None

    # 尝试多种字段路径
    token = None

    # 路径1: auth.accessToken
    auth = data.get("auth", {})
    for key in ("accessToken", "token", "authToken"):
        if key in auth:
            token = auth[key]
            break

    # 路径2: 顶层 accessToken
    if not token:
        for key in ("accessToken", "token", "authToken"):
            if key in data:
                token = data[key]
                break

    if token:
        display = token[:50] + "..." if len(token) > 50 else token
        print(f"  ✅ 成功提取 accessToken: {display}")

        # 同时提取 UID（可选，用于多账号配置）
        uid = None
        accounts = auth.get("accounts", data.get("accounts", []))
        if accounts and isinstance(accounts, list) and len(accounts) > 0:
            uid = accounts[0].get("uid", "")
        if uid:
            print(f"  UID: {uid}")

        return token
    else:
        print(f"  未找到 token 字段，可用字段: {list(data.keys())}")
        if auth:
            print(f"  auth 字段内: {list(auth.keys())}")

    return None


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("TraeWork + CodeBuddy Token 提取工具")
    print("=" * 60)
    print()
    print("请确保已登录对应的客户端后再运行此脚本。")
    print()

    trae_token = extract_trae_token()
    cb_token = extract_codebuddy_token()

    print()
    print("=" * 60)
    print("提取结果")
    print("=" * 60)

    if trae_token:
        print(f"\n✅ TraeWork Token 提取成功!")
        print(f"   GitHub Secret 名: TRAE_TOKEN")
        print(f"   值: {trae_token}")
    else:
        print("\n❌ TraeWork Token 提取失败")
        print("   请确认已安装并登录 TraeWork / TRAE SOLO CN 客户端")

    if cb_token:
        print(f"\n✅ CodeBuddy Token 提取成功!")
        print(f"   GitHub Secret 名: CODEBUDDY_TOKEN")
        print(f"   值: {cb_token}")
    else:
        print("\n❌ CodeBuddy Token 提取失败")
        print("   请确认已安装并登录 CodeBuddy / WorkBuddy 客户端")

    print()
    print("提示: Token 有效期约 60 天，过期后需重新提取。")
    print("请将上面的值复制到 GitHub 仓库的 Settings → Secrets and variables → Actions 中。")


if __name__ == "__main__":
    main()
