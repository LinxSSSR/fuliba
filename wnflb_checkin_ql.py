#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
福利吧论坛自动签到 - 青龙面板版
================================
基于 wnflb_checkin 改造，专为青龙面板（qinglong）设计。

青龙面板订阅后自动创建定时任务，无需手动配置：
  ql repo https://github.com/LinxSSSR/fuliba.git "" "wnflb_checkin_ql.py"

new Env('福利吧论坛签到')
cron: 0 9,22 * * *
"""

环境变量（在青龙面板「环境变量」页面添加）：
  FORUM_USERNAME   论坛账号
  FORUM_PASSWORD   论坛密码
  FORUM_COOKIE     （可选）直接传入 Cookie 字符串，优先级高于账号密码登录
  COOKIE_FILE      Cookie 缓存路径，默认 /ql/data/cookies_wnflb.json

通知：使用青龙内置 notify.py 的 send() 函数，自动读取面板中配置的通知渠道。
  notify.py 不可用时自动退回到 PUSHPLUS_TOKEN / SERVERCHAN_KEY 环境变量方式。

依赖安装（在青龙面板「依赖管理 → Python3」中逐个添加）：
  requests
  ddddocr
  Pillow
"""

import json
import os
import re
import sys
import time
import urllib.parse
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
LOGIN_PAGE_URL = BASE_URL + "/member.php?mod=logging&action=login"
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

# Cookie 缓存路径：优先环境变量，其次青龙默认路径，最后当前目录
DEFAULT_COOKIE_FILE = "/ql/data/cookies_wnflb.json"
if not os.path.isdir(os.path.dirname(DEFAULT_COOKIE_FILE)):
    DEFAULT_COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies_wnflb.json")


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


# ========================= Cookie 读写 =========================

def load_cookies(session, raw_cookie, cookie_file):
    """把 cookie 载入 session。返回是否成功载入。"""
    if raw_cookie:
        session.cookies.update(parse_cookies(raw_cookie))
        return True
    if cookie_file and os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                session.cookies.update(data)
                return True
        except Exception as e:
            print(f"  [Cookie] 读取缓存失败: {e}")
    return False


def save_cookies(session, cookie_file):
    if not cookie_file:
        return
    try:
        # 确保目录存在
        d = os.path.dirname(cookie_file)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        data = {c.name: c.value for c in session.cookies}
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [Cookie] 已保存到 {cookie_file}")
    except Exception as e:
        print(f"  [Cookie] 保存失败: {e}")


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


def extract_message(html):
    """提取 Discuz 提示信息页的正文"""
    m = re.search(r'id="messagetext"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    m = re.search(r'class="alert_(?:right|error|info)"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


# ========================= 登录（账号密码） =========================

def fetch_login_page(session):
    """GET 登录页，返回 (html, formhash, loginhash)"""
    resp = session.get(LOGIN_PAGE_URL, timeout=TIMEOUT)
    html = get_page_text(resp)
    formhash_m = re.search(r'name="formhash"\s+value="([a-f0-9]+)"', html)
    formhash = formhash_m.group(1) if formhash_m else None
    lh_m = re.search(r"loginhash=([A-Za-z0-9]+)", html)
    loginhash = lh_m.group(1) if lh_m else None
    return html, formhash, loginhash


def detect_captcha(html):
    """
    识别登录页/挑战页是否需要验证码，并提取关键参数。
    返回 dict: {needed, idhash, update, seccodehash, auth}
    """
    res = {
        "needed": False,
        "idhash": "",
        "update": str(int(time.time() * 1000)),
        "seccodehash": "",
        "auth": "",
    }

    am = re.search(r'name="auth"\s+value="([A-Za-z0-9%_./=+]+)"', html)
    if am:
        res["auth"] = am.group(1)

    ih = re.search(r"updateseccode\(\s*['\"]([A-Za-z0-9]+)['\"]", html)
    if not ih:
        ih = re.search(r'id="seccode_([A-Za-z0-9]+)"', html)
    if not ih:
        sm = re.search(
            r"misc\.php\?mod=seccode&update=([^&\"']+)&idhash=([A-Za-z0-9]+)", html
        )
        if sm:
            res["idhash"] = sm.group(2)
            res["update"] = sm.group(1)
    if ih and not res["idhash"]:
        res["idhash"] = ih.group(1)

    if not res["idhash"]:
        sid = re.search(r'id="seccodeverify_([A-Za-z0-9]+)"', html)
        if sid:
            res["idhash"] = sid.group(1)
    if not res["idhash"]:
        sh = re.search(r'name="seccodehash"\s+value="([A-Za-z0-9]+)"', html)
        if sh:
            res["idhash"] = sh.group(1)

    if not res["idhash"] and re.search(r'name="seccodeverify"', html):
        res["idhash"] = "SkyV"

    if res["idhash"] or res["auth"]:
        res["needed"] = True

    if res["idhash"]:
        sh = re.search(r'name="seccodehash"\s+value="([A-Za-z0-9]+)"', html)
        res["seccodehash"] = sh.group(1) if sh else res["idhash"]

    return res


def extract_login_fields(html):
    """从登录/挑战页提取 formhash、loginhash、auth"""
    fh = re.search(r'name="formhash"\s+value="([a-f0-9]+)"', html)
    lh = re.search(r"loginhash=([A-Za-z0-9]+)", html)
    auth = re.search(r'name="auth"\s+value="([A-Za-z0-9%_]+)"', html)
    return (
        fh.group(1) if fh else None,
        lh.group(1) if lh else None,
        auth.group(1) if auth else None,
    )


def solve_captcha(session, cap):
    """
    拉取验证码图片并用 ddddocr 识别。
    多次重试（每次换一张新图），提高识别率。
    """
    try:
        import ddddocr
    except ImportError:
        print("  [验证码] 未安装 ddddocr，请在青龙「依赖管理→Python3」中添加 ddddocr")
        return None

    ocr = ddddocr.DdddOcr(show_ad=False)
    headers = {"Referer": LOGIN_PAGE_URL}
    for attempt in range(1, 4):
        try:
            update = str(int(time.time() * 1000))
            img_url = (
                f"{BASE_URL}/misc.php?mod=seccode"
                f"&update={update}&idhash={cap['idhash']}"
            )
            r = session.get(img_url, timeout=TIMEOUT, headers=headers)
            if r.status_code != 200 or len(r.content) < 100:
                print(f"  [验证码] 第 {attempt} 次拉取图片失败(status={r.status_code}, len={len(r.content)})")
                continue
            if r.content[:4] not in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):
                print(f"  [验证码] 第 {attempt} 次返回非图片(可能被拦截), len={len(r.content)}")
                continue
            code = ocr.classification(r.content).strip()
            if code:
                return code
        except Exception as e:
            print(f"  [验证码] 第 {attempt} 次识别异常: {e}")
    return None


def verify_captcha_code(session, cap, code):
    """调用 Discuz 验证码校验接口（action=check）"""
    url = (
        f"{BASE_URL}/misc.php?mod=seccode&action=check&inajax=1"
        f"&modid=member::logging&idhash={cap['idhash']}&secverify={code}"
    )
    try:
        r = session.get(
            url,
            timeout=TIMEOUT,
            headers={
                "Referer": LOGIN_PAGE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        txt = get_page_text(r)
        ok = "succeed" in txt
        return ok
    except Exception as e:
        print(f"  [验证码] 校验接口异常: {e}")
        return False


def _submit_login(session, formhash, loginhash, username="", password="",
                  seccode="", auth="", seccodehash="", challenge=False):
    """执行一次登录 POST。返回 (ok, msg, resp_html)"""
    if challenge:
        data = {
            "formhash": formhash,
            "referer": BASE_URL + "/",
            "auth": auth,
            "questionid": "0",
            "answer": "",
            "seccodehash": seccodehash or "",
            "seccodemodid": "member::logging",
            "seccodeverify": seccode,
        }
    else:
        data = {
            "formhash": formhash,
            "referer": BASE_URL + "/",
            "loginfield": "username",
            "username": username,
            "password": password,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
        }
        if seccode:
            data["seccodeverify"] = seccode
            if seccodehash:
                data["seccodehash"] = seccodehash

    login_url = (
        f"{BASE_URL}/member.php?mod=logging&action=login"
        f"&loginsubmit=yes&loginhash={loginhash}"
    )
    if challenge:
        login_url += "&inajax=1"
    try:
        r = session.post(
            login_url,
            data=data,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={"Referer": LOGIN_PAGE_URL},
        )
    except requests.RequestException as e:
        return False, f"登录请求异常: {e}", ""

    txt = get_page_text(r)
    msg = extract_message(txt)
    if not msg:
        cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", txt, re.DOTALL)
        if cdata:
            msg = re.sub(r"<[^>]+>", "", cdata.group(1)).strip()

    if "请输入验证码" in txt and "auth=" in txt:
        return False, (msg or "验证码不正确，请重试"), txt

    logged, _ = verify_login(session)
    if logged:
        return True, "登录成功", txt
    if msg and ("密码" in msg or "用户名" in msg):
        return False, f"登录失败: {msg}", txt
    return False, (msg or "登录失败（未进入登录态）"), txt


def do_login(session, username, password):
    """
    账号密码登录（含新 IP 二次验证码挑战）。
    成功返回 (True, 消息)，失败返回 (False, 消息)。
    """
    print("  [登录] 获取登录页 ...")
    html, formhash, loginhash = fetch_login_page(session)
    if not formhash or not loginhash:
        return False, "无法解析登录页(formhash/loginhash 缺失)"

    ok, msg, resp_html = _submit_login(
        session, formhash, loginhash, username, password, None, None
    )
    if ok:
        return True, "登录成功"

    chtml = resp_html or ""
    c_fh, c_lh, auth = extract_login_fields(chtml)
    auth = urllib.parse.unquote(auth) if auth else None
    if not auth:
        am = re.search(r"auth=([A-Za-z0-9%_./=+]+)", chtml)
        auth = urllib.parse.unquote(am.group(1)) if am else None
    if not auth:
        return False, msg

    cap = detect_captcha(chtml)
    if not (c_fh and c_lh and cap["needed"] and cap["idhash"]):
        print("  [登录] 触发验证码挑战，重新获取挑战页 ...")
        try:
            r = session.get(
                f"{BASE_URL}/member.php",
                params={"mod": "logging", "action": "login", "auth": auth},
                timeout=TIMEOUT,
                headers={"Referer": LOGIN_PAGE_URL},
            )
            chtml = get_page_text(r)
            c_fh, c_lh, c_auth = extract_login_fields(chtml)
            auth = urllib.parse.unquote(c_auth) if c_auth else auth
            cap = detect_captcha(chtml)
        except requests.RequestException as e:
            return False, f"获取挑战页异常: {e}"

    if not (c_fh and c_lh):
        return False, "验证码挑战页未解析出 formhash/loginhash"
    if not cap["needed"] or not cap["idhash"]:
        return False, f"验证码挑战页未解析出验证码(idhash 缺失): {msg}"

    last_msg = "验证码识别失败"
    for attempt in range(1, 4):
        print(f"  [登录] 验证码 idhash={cap['idhash']}，ddddocr 识别中(第{attempt}次) ...")
        code = solve_captcha(session, cap)
        if not code:
            return False, "验证码识别失败，请检查 ddddocr 或手动处理"

        if not verify_captcha_code(session, cap, code):
            print(f"  [登录] 第 {attempt} 次验证码校验未通过，换新图重试 ...")
            continue

        ok2, last_msg, _ = _submit_login(
            session, c_fh, c_lh, username, password, code, auth,
            cap["seccodehash"], challenge=True,
        )
        if ok2:
            return True, "登录成功(已通过验证码)"
        if "验证码" in last_msg and ("不正确" in last_msg or "错误" in last_msg):
            print(f"  [登录] 第 {attempt} 次验证码不正确，换新图重试 ...")
            continue
        if "密码" in last_msg or "用户名" in last_msg:
            print(f"  [登录] 第 {attempt} 次疑似凭据缺失，重拉挑战页重试 ...")
            try:
                r = session.get(
                    f"{BASE_URL}/member.php",
                    params={"mod": "logging", "action": "login", "auth": auth},
                    timeout=TIMEOUT, headers={"Referer": LOGIN_PAGE_URL},
                )
                chtml = get_page_text(r)
                c_fh, c_lh, c_auth = extract_login_fields(chtml)
                auth = urllib.parse.unquote(c_auth) if c_auth else auth
                cap = detect_captcha(chtml)
            except requests.RequestException:
                pass
            continue
        return False, last_msg
    return False, last_msg


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
    print("  福利吧论坛自动签到 (青龙面板版)")
    print(f"  时间: {now}")
    print("=" * 50)

    # ---- 读取配置 ----
    username = os.environ.get("FORUM_USERNAME", "").strip()
    password = os.environ.get("FORUM_PASSWORD", "").strip()
    raw_cookie = os.environ.get("FORUM_COOKIE", "").strip()
    cookie_file = os.environ.get("COOKIE_FILE", "").strip() or DEFAULT_COOKIE_FILE

    if not raw_cookie and not (username and password):
        msg = (
            "未配置任何登录凭据！请在青龙面板「环境变量」中设置：\n"
            "  FORUM_USERNAME + FORUM_PASSWORD（账号密码登录）\n"
            "  或 FORUM_COOKIE（直接传入 Cookie）"
        )
        print(f"[FAIL] {msg}")
        ql_notify("[签到失败] 未配置凭据", f"时间:{now}\n错误:{msg}")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(HEADERS)

    html = None

    # 1) 尝试用缓存/Cookie 直接登录
    if load_cookies(session, raw_cookie, cookie_file):
        print("[1] 已载入 Cookie，校验登录态 ...")
        logged, html = verify_login(session)
        if logged:
            print("  -> Cookie 有效，直接签到")
        else:
            print("  -> Cookie 已过期")
            html = None
    else:
        print("[1] 未找到可用 Cookie")

    # 2) Cookie 不可用 -> 账号密码登录
    if html is None:
        if not (username and password):
            msg = "Cookie 无效，且未提供 FORUM_USERNAME / FORUM_PASSWORD"
            print(f"[FAIL] {msg}")
            ql_notify("[签到失败] 需登录", f"时间:{now}\n错误:{msg}")
            sys.exit(1)
        print("[2] 使用账号密码登录 ...")
        ok, msg = do_login(session, username, password)
        if not ok:
            print(f"[FAIL] 登录失败: {msg}")
            ql_notify("[签到失败] 登录失败", f"时间:{now}\n错误:{msg}")
            sys.exit(1)
        print(f"  -> {msg}")
        save_cookies(session, cookie_file)
        logged, html = verify_login(session)
        if not logged:
            print("[FAIL] 登录后首页校验未通过")
            sys.exit(1)

    # 3) 签到
    print("[3] 检查签到状态 ...")
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
