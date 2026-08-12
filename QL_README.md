# 福利吧论坛自动签到 - 青龙面板部署指南

基于 [wnflb-checkin](https://github.com/fmdxx1991/wnflb-checkin) 改造，适配青龙面板（qinglong）运行。

## 功能

- 支持**账号密码登录**（自动处理 Discuz 验证码，ddddocr 识别）
- 支持**Cookie 直传**（兼容旧方式）
- Cookie 自动缓存复用，过期自动重新登录
- 使用青龙**内置通知系统**（notify.py），无需额外配置推送渠道

## 部署步骤

### 方式一：订阅自动部署（推荐）

青龙面板 →「订阅管理」→ 新建订阅：

| 字段 | 值 |
|------|-----|
| 名称 | 福利吧论坛签到 |
| 类型 | public-repo |
| URL | `https://github.com/LinxSSSR/fuliba.git` |
| 分支 | `main` |
| 白名单 | `wnflb_checkin_ql.py` |
| 依赖文件 | `requirements_ql.txt` |

添加后青龙自动拉取脚本、创建定时任务（每天 9:00 / 22:00），后续脚本有更新也会自动同步。

### 方式二：手动上传

将 `wnflb_checkin_ql.py` 上传到青龙面板的脚本目录：

- 方式一：青龙面板 Web →「脚本管理」→ 上传或新建文件，粘贴脚本内容
- 方式二：复制到容器内 `/ql/scripts/` 目录

### 安装依赖（两种方式都需要）

青龙面板 Web →「依赖管理」→ 选择「Python3」→ 逐个添加：

```
requests
ddddocr
Pillow
```

> ⚠️ 注意：ddddocr 体积较大，首次安装可能需要几分钟。如果安装失败，检查「系统设置」中的 Python 镜像源是否正确。

### 配置环境变量

青龙面板 Web →「环境变量」→ 新建变量：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `FORUM_USERNAME` | 是* | 论坛账号 |
| `FORUM_PASSWORD` | 是* | 论坛密码 |
| `FORUM_COOKIE` | 否 | 直接传入 Cookie 字符串（优先级高于账号密码） |
| `COOKIE_FILE` | 否 | Cookie 缓存路径，默认 `/ql/data/cookies_wnflb.json` |

> \* `FORUM_USERNAME` + `FORUM_PASSWORD` 和 `FORUM_COOKIE` 二选一即可

### 创建定时任务（仅手动上传需要，订阅方式自动创建）

青龙面板 Web →「定时任务」→ 新建任务：

| 字段 | 值 |
|------|-----|
| 名称 | 福利吧论坛签到 |
| 命令 | `task wnflb_checkin_ql.py` |
| 定时规则 | `0 9,22 * * *`（每天 9:00 和 22:00） |

> 建议每天运行 1-2 次即可，签到是幂等的（已签到不会重复计算）。

### 手动运行测试

在「定时任务」列表中找到刚创建的任务，点击「运行」按钮手动执行一次，确认日志输出正常。

## 通知配置

脚本优先使用青龙内置 `notify.py` 的 `send()` 函数，只需在青龙面板「系统设置 → 通知设置」中配置好推送渠道即可，**无需在脚本里额外设置**。

青龙内置通知自动退回到以下环境变量方式（当 notify.py 不可用时）：
- `PUSHPLUS_TOKEN`：PushPlus 推送
- `SERVERCHAN_KEY`：Server 酱推送

## Cookie 说明

- 首次运行走账号密码登录（可能触发验证码识别），登录成功后 Cookie 自动保存到 `/ql/data/cookies_wnflb.json`
- 之后运行自动从缓存加载 Cookie，跳过登录步骤直接签到
- Cookie 失效后自动重新登录并更新缓存
- 如果青龙容器重启导致 `/ql/data/` 丢失，重新执行一次账号密码登录即可

## 与原始版本的差异

| 原始版 (GitHub Actions) | 青龙面板版 |
|--------------------------|------------|
| 环境变量通过 GitHub Secrets | 环境变量通过青龙面板配置 |
| argparse CLI 参数 | 纯环境变量读取 |
| GITHUB_OUTPUT 写缓存刷新标记 | 不需要（直接本地文件） |
| 自建 PushPlus/Server 酱通知 | 优先青龙内置 notify.send() |
| Cookie 默认 `cookies.json` | Cookie 默认 `/ql/data/cookies_wnflb.json` |
| GitHub Actions 定时 | 青龙面板 cron 定时 |

## 常见问题

**Q: 日志报 "未安装 ddddocr"？**
A: 在「依赖管理 → Python3」中添加 `ddddocr`，然后重新运行任务。

**Q: 验证码识别失败怎么办？**
A: 脚本会重试 3 次（每次换新图），仍失败则退出。可以尝试用 `FORUM_COOKIE` 直接从浏览器复制 Cookie 绕过验证码。

**Q: 如何获取 Cookie？**
A: 浏览器登录论坛后，F12 → Application → Cookies → 复制所有 cookie，拼接成字符串填入 `FORUM_COOKIE` 环境变量。

**Q: 容器重启后 Cookie 丢失？**
A: 默认路径 `/ql/data/` 在容器重启后如果路径改变，可设置 `COOKIE_FILE` 环境变量指向持久化目录。
