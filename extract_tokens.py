#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Token 提取脚本
从已登录的 CodeBuddy 客户端中提取签到所需的 Token。

使用方法:
  python extract_tokens.py

提取结果会直接打印，请将对应的值填入 GitHub Secrets:
  CODEBUDDY_TOKEN -> CodeBuddy 的 accessToken
"""

import os
import sys
import json
from pathlib import Path


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
    print("CodeBuddy Token 提取工具")
    print("=" * 60)
    print()
    print("请确保已登录 CodeBuddy 客户端后再运行此脚本。")
    print()

    cb_token = extract_codebuddy_token()

    print()
    print("=" * 60)
    print("提取结果")
    print("=" * 60)

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
