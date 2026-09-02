#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TraeWork + CodeBuddy 每日自动签到脚本
适用于 GitHub Actions 定时运行，纯标准库实现，零第三方依赖。

环境变量:
  TRAE_TOKEN      TraeWork (TRAE SOLO CN) 的 JWT Token（必填，如需签到 TraeWork）
  TRAE_DEVICE_ID  TraeWork 持久化设备 ID（可选，不填则基于 Token 自动生成确定性 ID）
  CODEBUDDY_TOKEN CodeBuddy / WorkBuddy 的 accessToken（必填，如需签到 CodeBuddy）
  SC_KEY          Server 酱推送 sendkey（可选，留空则不推送）
  WEBHOOK_URL     通用 Webhook 推送地址（可选，POST JSON {content: "..."}）

GitHub Secrets 中配置同名变量即可。
"""

import os
import sys
import json
import time
import random
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


# TraeWork 客户端 User-Agent（模拟 Electron/Chromium 网络栈）
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"


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


def _is_token_expired(status_code, resp):
    """检测 Token 是否过期/失效"""
    if status_code in (401, 403):
        return True
    if isinstance(resp, dict):
        code = resp.get("code", resp.get("Code", 0))
        msg = str(resp.get("msg", resp.get("message", "")))
        if code in (401, 403, 4001, 4003) or "token" in msg.lower() or "unauthorized" in msg.lower():
            return True
    return False


def trae_checkin(token):
    """TraeWork 每日签到，返回 (success, msg, already_checked_in)"""
    log("=" * 50)
    log("开始 TraeWork 签到")

    # 使用持久化设备 ID：优先从环境变量读取，否则基于 token 生成确定性 ID
    device_id = os.environ.get("TRAE_DEVICE_ID", "").strip()
    if not device_id:
        device_id = hashlib.sha256(token.encode()).hexdigest()[:32]

    # 模拟 TraeWork 客户端 (Electron/Chromium) 的请求头
    # 源码分析：bb() 方法构造 auth headers，fb() 方法追加 device headers
    # TTNet c() 方法追加 x-rust-request-timeout
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Cloud-IDE-JWT {token}",
        "X-User-Region": "CN",
        "x-device-id": device_id,
        "x-device-type": "windows",
        "x-device-brand": "Windows",
        "x-rust-request-timeout": "30000",
    }

    # 模拟用户行为：首次请求前随机等待 2-5 秒
    initial_delay = random.uniform(2, 5)
    log(f"等待 {initial_delay:.1f} 秒后开始签到...")
    time.sleep(initial_delay)

    # 直接签到，不预先查询状态（避免被检测为自动化行为）
    # 限流时快速重试，不长时间等待（靠 10 点兜底任务补签）
    max_retries = 3
    retry_intervals = [10, 20]
    resp = None
    rate_limited = False
    for attempt in range(max_retries):
        log(f"正在签到... (第 {attempt + 1}/{max_retries} 次)")
        status_code, resp = post_json(TRAE_CLAIM_URL, headers)
        log(f"签到响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

        if _is_token_expired(status_code, resp):
            log("[TraeWork] Token 已过期或失效，请重新提取")
            return False, "Token 已过期，请重新提取并更新 Secrets", False

        if status_code != 200:
            log(f"[TraeWork] 签到失败: HTTP {status_code}")
            return False, f"签到失败 (HTTP {status_code})", False

        # code=9074 是服务端限流，快速重试
        if resp.get("code") == 9074:
            rate_limited = True
            if attempt < max_retries - 1:
                wait = retry_intervals[attempt]
                log(f"[TraeWork] 服务端限流，{wait} 秒后重试...")
                time.sleep(wait)
                continue
            break

        rate_limited = False
        break

    # 重试耗尽仍然被限流，直接返回失败
    if rate_limited:
        log("[TraeWork] 限流重试失败，等待兜底任务补签")
        return False, f"签到失败: {resp.get('message', '服务端限流')}", False

    # 签到接口返回成功
    if resp.get("code") == 0 or resp.get("code") == 200:
        credits = resp.get("credits", resp.get("data", {}).get("credits", "未知"))
        log(f"[TraeWork] 签到成功! 当前积分: {credits}")
        return True, f"签到成功! 当前积分: {credits}", False

    # 其他非成功响应，查一次状态判断是否今日已签
    log("[TraeWork] 签到返回非成功，查询状态确认...")
    time.sleep(2)
    status_code2, resp2 = post_json(TRAE_STATUS_URL, headers)
    if status_code2 == 200:
        data2 = resp2.get("data", resp2)
        if data2.get("checked_in", False):
            credits = data2.get("credits", "未知")
            log(f"[TraeWork] 今日已签到，当前积分: {credits}")
            return True, f"今日已签到，当前积分: {credits}", True

    log(f"[TraeWork] 签到失败，返回: {json.dumps(resp, ensure_ascii=False)[:200]}")
    return False, f"签到失败: {resp.get('message', '未知错误')}", False


# ============================================================
# CodeBuddy (WorkBuddy) 签到
# ============================================================

CB_API_HOST = "https://www.codebuddy.cn"
CB_STATUS_URL = f"{CB_API_HOST}/v2/billing/meter/checkin-activity-status"
CB_CHECKIN_URL = f"{CB_API_HOST}/v2/billing/meter/daily-checkin"


def codebuddy_checkin(token):
    """CodeBuddy / WorkBuddy 每日签到，返回 (success, msg, already_checked_in)"""
    log("=" * 50)
    log("开始 CodeBuddy 签到")

    headers = {
        "Authorization": f"Bearer {token}",
    }

    # 1. 查询签到状态
    log("查询签到状态...")
    status_code, resp = post_json(CB_STATUS_URL, headers)
    log(f"状态查询响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if _is_token_expired(status_code, resp):
        log("[CodeBuddy] Token 已过期或失效，请重新提取")
        return False, "Token 已过期，请重新提取并更新 Secrets", False

    if status_code != 200:
        log(f"[CodeBuddy] 状态查询失败: HTTP {status_code}")
        return False, f"状态查询失败 (HTTP {status_code})", False

    data = resp.get("data", resp)
    today = datetime.date.today().isoformat()
    checkin_dates = data.get("checkin_dates", [])

    if data.get("today_checked_in", False) or today in checkin_dates:
        streak = data.get("streak_days", "未知")
        log(f"[CodeBuddy] 今日已签到，连续 {streak} 天")
        return True, f"今日已签到，连续 {streak} 天", True

    # 2. 执行签到
    log("今日未签到，正在签到...")
    status_code, resp = post_json(CB_CHECKIN_URL, headers)
    log(f"签到响应: HTTP {status_code} - {json.dumps(resp, ensure_ascii=False)[:300]}")

    if _is_token_expired(status_code, resp):
        log("[CodeBuddy] Token 已过期或失效，请重新提取")
        return False, "Token 已过期，请重新提取并更新 Secrets", False

    if status_code != 200:
        log(f"[CodeBuddy] 签到失败: HTTP {status_code}")
        return False, f"签到失败 (HTTP {status_code})", False

    # 3. 二次确认
    time.sleep(2)
    status_code2, resp2 = post_json(CB_STATUS_URL, headers)
    data2 = resp2.get("data", resp2) if status_code2 == 200 else {}
    checkin_dates2 = data2.get("checkin_dates", [])

    if data2.get("today_checked_in", False) or today in checkin_dates2:
        streak = data2.get("streak_days", "未知")
        log(f"[CodeBuddy] 签到成功! 连续 {streak} 天")
        return True, f"签到成功! 连续 {streak} 天", False
    else:
        log(f"[CodeBuddy] 签到后未确认，返回: {json.dumps(resp, ensure_ascii=False)[:200]}")
        return False, "签到后未确认，请手动检查", False


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
    need_push = False  # 是否需要推送通知

    # 先签到 CodeBuddy，再签到 TraeWork
    if cb_token:
        try:
            success, msg, already = codebuddy_checkin(cb_token)
            results.append(f"CodeBuddy: {'✅' if success else '❌'} {msg}")
            if not already:
                need_push = True
        except Exception as e:
            log(f"[CodeBuddy] 异常: {e}")
            results.append(f"CodeBuddy: ❌ 异常: {e}")
            need_push = True

    if trae_token:
        try:
            success, msg, already = trae_checkin(trae_token)
            results.append(f"TraeWork: {'✅' if success else '❌'} {msg}")
            if not already:
                need_push = True
        except Exception as e:
            log(f"[TraeWork] 异常: {e}")
            results.append(f"TraeWork: ❌ 异常: {e}")
            need_push = True

    # 汇总（CodeBuddy 在前，TraeWork 在后）
    summary = "\n".join(results)
    log("=" * 60)
    log("签到结果汇总:")
    log(summary)
    log("=" * 60)

    # 推送通知：仅在首次签到成功、签到失败、Token 过期时推送
    # 今日已签到的重复执行不推送
    if need_push and (sc_key or webhook_url):
        log("检测到需要通知的事件，正在推送...")
        push_notification("自动签到结果", summary, sc_key, webhook_url)
    else:
        log("今日已签到，无需推送通知")


if __name__ == "__main__":
    main()
