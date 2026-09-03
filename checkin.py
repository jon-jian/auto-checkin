#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeBuddy 每日自动签到脚本
适用于 GitHub Actions 定时运行，纯标准库实现，零第三方依赖。

环境变量:
  CODEBUDDY_TOKEN  CodeBuddy / WorkBuddy 的 accessToken（必填）
  SC_KEY            Server 酱推送 sendkey（可选，留空则不推送）
  WEBHOOK_URL       通用 Webhook 推送地址（可选，POST JSON {content: "..."}）

GitHub Secrets 中配置同名变量即可。
"""

import os
import sys
import json
import time
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
# CodeBuddy (WorkBuddy) 签到
# ============================================================

CB_API_HOST = "https://www.codebuddy.cn"
CB_STATUS_URL = f"{CB_API_HOST}/v2/billing/meter/checkin-activity-status"
CB_CHECKIN_URL = f"{CB_API_HOST}/v2/billing/meter/daily-checkin"


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
    log("CodeBuddy 自动签到")
    log("=" * 60)

    cb_token = os.environ.get("CODEBUDDY_TOKEN", "").strip()
    sc_key = os.environ.get("SC_KEY", "").strip()
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()

    if not cb_token:
        log("[错误] 未配置 CODEBUDDY_TOKEN，请设置环境变量")
        sys.exit(1)

    need_push = False

    try:
        success, msg, already = codebuddy_checkin(cb_token)
        result = f"CodeBuddy: {'✅' if success else '❌'} {msg}"
        if not already:
            need_push = True
            title = f"{'✅' if success else '❌'} CodeBuddy 签到{'成功' if success else '失败'}"
    except Exception as e:
        log(f"[CodeBuddy] 异常: {e}")
        result = f"CodeBuddy: ❌ 异常: {e}"
        need_push = True
        title = "❌ CodeBuddy 签到异常"

    log("=" * 60)
    log("签到结果汇总:")
    log(result)
    log("=" * 60)

    if need_push and (sc_key or webhook_url):
        log("检测到需要通知的事件，正在推送...")
        push_notification(title, result, sc_key, webhook_url)
    else:
        log("今日已签到，无需推送通知")


if __name__ == "__main__":
    main()
