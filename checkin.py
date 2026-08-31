#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TraeWork + CodeBuddy 每日自动签到脚本
适用于 GitHub Actions 定时运行，纯标准库实现，零第三方依赖。

环境变量:
  TRAE_TOKEN      TraeWork (TRAE SOLO CN) 的 JWT Token（必填，如需签到 TraeWork）
  CODEBUDDY_TOKEN CodeBuddy / WorkBuddy 的 accessToken（必填，如需签到 CodeBuddy）
  SC_KEY          Server 酱推送 sendkey（可选，留空则不推送）
  WEBHOOK_URL     通用 Webhook 推送地址（可选，POST JSON {content: "..."}）

GitHub Secrets 中配置同名变量即可。
"""

import os
import sys
import json
import time
import uuid
import hashlib
import datetime
import urllib.request
import urllib.error

# ============================================================
# 通用工具
# ============================================================

def log(msg):
    """带时间戳的日志输出"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def post_json(url, headers, data=None, timeout=30):
    """发送 POST JSON 请求，返回 (status_code, json_body)"""
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return e.code, {"raw": raw, "error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def push_notification(title, content, sc_key="", webhook_url=""):
    """通过 Server 酱或通用 Webhook 推送通知"""
    text = f"{title}\n{content}"

    if sc_key:
        try:
            url = f"https://sctapi.ftqq.com/{sc_key}.send"
            data = {"title": title, "desp": content}
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15).read()
            log(f"[通知] Server 酱推送成功")
        except Exception as e:
            log(f"[通知] Server 酱推送失败: {e}")

    if webhook_url:
        try:
            data = {"content": text, "text": text}
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                webhook_url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15).read()
            log(f"[通知] Webhook 推送成功")
        except Exception as e:
            log(f"[通知] Webhook 推送失败: {e}")


# ============================================================
# TraeWork (TRAE SOLO CN) 签到
# ============================================================

# 从 TRAE SOLO CN 的 product.json 中确认的 ugApi host
TRAE_API_HOST = "https://api.trae.cn"
TRAE_STATUS_URL = f"{TRAE_API_HOST}/trae/api/v2/ug/checkin_credits/status"
TRAE_CLAIM_URL = f"{TRAE_API_HOST}/trae/api/v2/ug/checkin_credits/claim"


def trae_checkin(token):
    """TraeWork 每日签到"""
    log("=" * 50)
    log("开始 TraeWork 签到")

    # 生成设备标识
    device_id = hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]

    headers = {
        "Authorization": f"Cloud-IDE-JWT {token}",
        "X-Cloudide-Token": token,
        "x-device-id": device_id,
        "x-device-type": "windows",
        "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    }

    # 1. 查询签到状态
    log("查询签到状态...")
    status_code, resp = post_json(TRAE_STATUS_URL, headers)
    log(f"状态查询响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if status_code != 200:
        log(f"[TraeWork] 状态查询失败: HTTP {status_code}")
        return False, f"状态查询失败 (HTTP {status_code})"

    data = resp.get("data", resp)

    if not data.get("enable", False):
        log("[TraeWork] 签到功能未开启或不可用")
        return False, "签到功能未开启"

    if data.get("checked_in", False):
        credits = data.get("credits", "未知")
        log(f"[TraeWork] 今日已签到，当前积分: {credits}")
        return True, f"今日已签到，当前积分: {credits}"

    # 2. 领取签到积分
    log("今日未签到，正在领取...")
    status_code, resp = post_json(TRAE_CLAIM_URL, headers)
    log(f"签到领取响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if status_code != 200:
        log(f"[TraeWork] 签到失败: HTTP {status_code}")
        return False, f"签到失败 (HTTP {status_code})"

    # 3. 二次确认
    time.sleep(2)
    status_code2, resp2 = post_json(TRAE_STATUS_URL, headers)
    data2 = resp2.get("data", resp2) if status_code2 == 200 else {}

    if data2.get("checked_in", False):
        credits = data2.get("credits", "未知")
        log(f"[TraeWork] 签到成功! 当前积分: {credits}")
        return True, f"签到成功! 当前积分: {credits}"
    else:
        # claim 接口可能直接返回成功信息
        claim_credits = resp.get("credits", resp.get("data", {}).get("credits", ""))
        if resp.get("code") == 0 or resp.get("code") == 200:
            log(f"[TraeWork] 签到可能成功（接口返回 code=0），当前积分: {claim_credits}")
            return True, f"签到成功! 当前积分: {claim_credits}"
        log(f"[TraeWork] 签到后未确认，返回: {json.dumps(resp, ensure_ascii=False)[:200]}")
        return False, "签到后未确认，请手动检查"


# ============================================================
# CodeBuddy (WorkBuddy) 签到
# ============================================================

CB_API_HOST = "https://www.codebuddy.cn"
CB_STATUS_URL = f"{CB_API_HOST}/v2/billing/meter/checkin-activity-status"
CB_CHECKIN_URL = f"{CB_API_HOST}/v2/billing/meter/daily-checkin"


def codebuddy_checkin(token):
    """CodeBuddy / WorkBuddy 每日签到"""
    log("=" * 50)
    log("开始 CodeBuddy 签到")

    headers = {
        "Authorization": f"Bearer {token}",
    }

    # 1. 查询签到状态
    log("查询签到状态...")
    status_code, resp = post_json(CB_STATUS_URL, headers)
    log(f"状态查询响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if status_code != 200:
        log(f"[CodeBuddy] 状态查询失败: HTTP {status_code}")
        return False, f"状态查询失败 (HTTP {status_code})"

    data = resp.get("data", resp)
    today = datetime.date.today().isoformat()
    checkin_dates = data.get("checkin_dates", [])

    if data.get("today_checked_in", False) or today in checkin_dates:
        streak = data.get("streak_days", "未知")
        log(f"[CodeBuddy] 今日已签到，连续 {streak} 天")
        return True, f"今日已签到，连续 {streak} 天"

    # 2. 执行签到
    log("今日未签到，正在签到...")
    status_code, resp = post_json(CB_CHECKIN_URL, headers)
    log(f"签到响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if status_code != 200:
        log(f"[CodeBuddy] 签到失败: HTTP {status_code}")
        return False, f"签到失败 (HTTP {status_code})"

    # 3. 二次确认
    time.sleep(2)
    status_code2, resp2 = post_json(CB_STATUS_URL, headers)
    data2 = resp2.get("data", resp2) if status_code2 == 200 else {}
    checkin_dates2 = data2.get("checkin_dates", [])

    if data2.get("today_checked_in", False) or today in checkin_dates2:
        streak = data2.get("streak_days", "未知")
        log(f"[CodeBuddy] 签到成功! 连续 {streak} 天")
        return True, f"签到成功! 连续 {streak} 天"
    else:
        log(f"[CodeBuddy] 签到后未确认，返回: {json.dumps(resp, ensure_ascii=False)[:200]}")
        return False, "签到后未确认，请手动检查"


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 60)
    log("TraeWork + CodeBuddy 自动签到")
    log("=" * 60)

    trae_token = os.environ.get("TRAE_TOKEN", "").strip()
    cb_token = os.environ.get("CODEBUDDY_TOKEN", "").strip()
    sc_key = os.environ.get("SC_KEY", "").strip()
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()

    if not trae_token and not cb_token:
        log("[错误] 未配置任何 token，请设置 TRAE_TOKEN 和/或 CODEBUDDY_TOKEN 环境变量")
        sys.exit(1)

    results = []

    if trae_token:
        try:
            success, msg = trae_checkin(trae_token)
            results.append(f"TraeWork: {'✅' if success else '❌'} {msg}")
        except Exception as e:
            log(f"[TraeWork] 异常: {e}")
            results.append(f"TraeWork: ❌ 异常: {e}")

    if cb_token:
        try:
            success, msg = codebuddy_checkin(cb_token)
            results.append(f"CodeBuddy: {'✅' if success else '❌'} {msg}")
        except Exception as e:
            log(f"[CodeBuddy] 异常: {e}")
            results.append(f"CodeBuddy: ❌ 异常: {e}")

    # 汇总
    summary = "\n".join(results)
    log("=" * 60)
    log("签到结果汇总:")
    log(summary)
    log("=" * 60)

    # 推送通知
    if sc_key or webhook_url:
        push_notification("自动签到结果", summary, sc_key, webhook_url)


if __name__ == "__main__":
    main()
