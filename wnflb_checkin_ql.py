#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
福利吧论坛自动签到 - 青龙面板版（纯 Cookie）
==============================================
基于 wnflb_checkin 改造，专为青龙面板（qinglong）设计。
本版本仅支持 Cookie 直传方式，无需账号密码、无需验证码识别（ddddocr）。

青龙面板订阅后自动创建定时任务，无需手动配置：
  ql repo https://github.com/LinxSSSR/fuliba.git "" "wnflb_checkin_ql.py"

new Env('福利吧论坛签到')
cron: 0 9,22 * * *

环境变量（在青龙面板「环境变量」页面添加）：
  FORUM_COOKIE   （必填）论坛登录后的 Cookie 字符串，形如 "xxx=aaa; yyy=bbb"
  COOKIE_FILE    （可选）Cookie 文件路径；与 FORUM_COOKIE 二选一

通知：使用青龙内置 notify.py 的 send() 函数，自动读取面板中配置的通知渠道。
  notify.py 不可用时自动退回到 PUSHPLUS_TOKEN / SERVERCHAN_KEY 环境变量方式。

依赖安装（在青龙面板「依赖管理 → Python3」中添加）：
  requests
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

# ========================= 青龙面板通知（优先用内置 notify.py） =========================
_notify_send = None

try:
    # 青龙面板 /ql/scripts/ 目录下自带 notify.py，Python 进程会自动找到同目录模块
    from notify import send as _ql_send
    _notify_send = _ql_send
except ImportError:
    pass


def ql_notify(title, content):
    """发送通知：优先使用青龙内置 notify.send，否则退回到环境变量方式。"""
    if _notify_send:
        try:
            _notify_send(title, content)
            return
        except Exception as e:
            print(f"  [通知] 青龙内置通知异常: {e}，退回环境变量方式")

    # ---- 退回原始的环境变量推送方式 ----
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if token:
        try:
            resp = requests.post(
                "http://www.pushplus.plus/send",
                json={"token": token, "title": title, "content": content, "template": "txt"},
                timeout=10,
            )
            print(f"  [PushPlus] {resp.json().get('msg', 'unknown')}")
        except Exception as e:
            print(f"  [PushPlus] 发送失败: {e}")

    key = os.environ.get("SERVERCHAN_KEY", "")
    if key:
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            print(f"  [Server酱] {resp.json().get('message', 'unknown')}")
        except Exception as e:
            print(f"  [Server酱] 发送失败: {e}")

    if not token and not key and not _notify_send:
        print("  (未配置任何推送通知)")


# ========================= 配置 =========================
BASE_URL = "https://www.wnflb2023.com"
FORUM_URL = BASE_URL + "/forum.php"
TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ========================= 工具函数 =========================

def get_cst_time():
    utc_now = datetime.now(timezone.utc)
    return (utc_now + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_cookies(raw):
    """Cookie 字符串 -> 字典"""
    cookies = {}
    for item in raw.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def get_page_text(resp):
    """优先按 GBK 解码（论坛是 GBK）"""
    if resp.encoding and resp.encoding.lower() in ("gbk", "gb2312", "gb18030"):
        return resp.text
    try:
        return resp.content.decode("gbk")
    except (UnicodeDecodeError, LookupError):
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text


def fetch_forum(session):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(FORUM_URL, timeout=TIMEOUT)
            return resp
        except requests.RequestException as e:
            print(f"  [网络] 第 {attempt}/{MAX_RETRIES} 次请求失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None


# ========================= Cookie 载入 =========================

def load_cookies(session, raw_cookie, cookie_file):
    """把 cookie 载入 session。返回是否成功载入。"""
    if raw_cookie:
        session.cookies.update(parse_cookies(raw_cookie))
        return True
    if cookie_file and os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            # 兼容两种格式：JSON 对象 或 纯 cookie 字符串
            if content.startswith("{"):
                data = json.loads(content)
                if isinstance(data, dict) and data:
                    session.cookies.update(data)
                    return True
            elif content:
                session.cookies.update(parse_cookies(content))
                return True
        except Exception as e:
            print(f"  [Cookie] 读取文件失败: {e}")
    return False


# ========================= 登录态校验 =========================

def verify_login(session):
    """访问论坛首页，判断是否已登录。返回 (bool, html)"""
    resp = fetch_forum(session)
    if resp is None:
        return False, ""
    html = get_page_text(resp)
    logged = check_logged_in(html)
    return logged, html


def check_logged_in(html):
    """
    检测页面是否处于登录态。
    最可靠信号：页面 JS 里的 discuz_uid（游客为 '0'，登录后为真实 UID）。
    """
    m = re.search(r"discuz_uid\s*=\s*'(\d+)'", html)
    if m:
        return m.group(1) != "0"
    if 'class="logout"' in html or "mod=logging&action=logout" in html:
        return True
    if 'name="username"' in html and 'name="password"' in html:
        return False
    return False


# ========================= 签到 =========================

def check_already_signed(html):
    m = re.search(r"fx_chk_menu\s*=\s*(true|false)", html)
    if m:
        return m.group(1) == "true"
    return False


def extract_formhash(html):
    m = re.search(r"fx_checkin:checkin&formhash=([a-f0-9]+)&([a-f0-9]+)", html)
    if m:
        return m.group(1), m.group(2)
    return None, None


def do_checkin(session, formhash, fx_formhash):
    url = (
        f"{BASE_URL}/plugin.php?id=fx_checkin:checkin"
        f"&formhash={formhash}&{fx_formhash}&inajax=1"
    )
    headers = {
        "Referer": FORUM_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT, headers=headers)
            return resp.text
        except requests.RequestException as e:
            print(f"  [签到] 第 {attempt}/{MAX_RETRIES} 次请求失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None


def parse_result(text):
    if text is None:
        return False, "网络请求失败"
    cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", text, re.DOTALL)
    content = cdata.group(1) if cdata else text
    clean = re.sub(r"<[^>]+>", " ", content).strip()
    clean = re.sub(r"\s+", " ", clean)

    if "签到成功" in clean:
        rank = re.search(r"第\s*(\d+)\s*个", clean)
        if rank:
            return True, f"签到成功！今日第 {rank.group(1)} 个签到"
        return True, "签到成功！"
    if "已经签到" in clean or "已签到" in clean:
        return True, "今日已签到（重复签到）"
    if "先登录" in clean or "请登录" in clean:
        return False, "Cookie 已过期，请重新获取"
    if "补签" in clean and "成功" in clean:
        return True, "补签成功"
    return False, f"未知响应: {clean[:200]}"


# ========================= 主流程 =========================

def main():
    now = get_cst_time()
    print("=" * 50)
    print("  福利吧论坛自动签到 (青龙面板版 - 纯 Cookie)")
    print(f"  时间: {now}")
    print("=" * 50)

    # ---- 读取配置 ----
    raw_cookie = os.environ.get("FORUM_COOKIE", "").strip()
    cookie_file = os.environ.get("COOKIE_FILE", "").strip()

    if not raw_cookie and not cookie_file:
        msg = (
            "未配置 Cookie！请在青龙面板「环境变量」中设置：\n"
            "  FORUM_COOKIE = 论坛登录后的 Cookie 字符串\n"
            "  （浏览器登录后 F12 → Application → Cookies 复制全部）"
        )
        print(f"[FAIL] {msg}")
        ql_notify("[签到失败] 未配置 Cookie", f"时间:{now}\n错误:{msg}")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(HEADERS)

    # 1) 载入 Cookie 并校验登录态
    if load_cookies(session, raw_cookie, cookie_file):
        print("[1] 已载入 Cookie，校验登录态 ...")
        logged, html = verify_login(session)
        if not logged:
            msg = "Cookie 已失效或过期，请重新从浏览器复制最新 Cookie"
            print(f"[FAIL] {msg}")
            ql_notify("[签到失败] Cookie 失效", f"时间:{now}\n错误:{msg}")
            sys.exit(1)
        print("  -> Cookie 有效")
    else:
        msg = "未能载入 Cookie"
        print(f"[FAIL] {msg}")
        ql_notify("[签到失败] Cookie 载入失败", f"时间:{now}\n错误:{msg}")
        sys.exit(1)

    # 2) 签到
    print("[2] 检查签到状态 ...")
    if check_already_signed(html):
        print("[OK] 今日已签到，无需重复操作")
        ql_notify("[签到结果] WNFLB", f"时间:{now}\n状态:今日已签到")
        return

    print("  -> 今日尚未签到，执行签到 ...")

    formhash, fx_formhash = extract_formhash(html)
    if not formhash:
        msg = "无法提取 formhash，页面结构可能已变化"
        print(f"[FAIL] {msg}")
        ql_notify("[签到失败] WNFLB", f"时间:{now}\n错误:{msg}")
        sys.exit(1)

    text = do_checkin(session, formhash, fx_formhash)
    success, message = parse_result(text)
    if success:
        print(f"[OK] {message}")
        ql_notify("[签到成功] WNFLB", f"时间:{now}\n结果:{message}")
    else:
        print(f"[FAIL] {message}")
        ql_notify("[签到失败] WNFLB", f"时间:{now}\n结果:{message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
