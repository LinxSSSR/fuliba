# 福利吧论坛自动签到 - 青龙面板部署指南

基于 [wnflb-checkin](https://github.com/fmdxx1991/wnflb-checkin) 改造，适配青龙面板（qinglong）运行。**纯 Cookie 签到，无需账号密码、无需 ddddocr。**

## 功能

- 纯 Cookie 签到，直接复用浏览器登录态
- 使用青龙**内置通知系统**（notify.py），无需额外配置推送渠道
- 依赖极简（仅 `requests`），Alpine 环境零障碍安装

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

青龙面板 Web →「依赖管理」→ 选择「Python3」→ 添加：

```
requests
```

### 配置环境变量

青龙面板 Web →「环境变量」→ 新建变量：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `FORUM_COOKIE` | 是* | 论坛登录后的 Cookie 字符串 |
| `COOKIE_FILE` | 否 | Cookie 文件路径（与 FORUM_COOKIE 二选一） |

> \* 如何获取 Cookie：浏览器登录 `https://www.wnflb2023.com/` → F12 → Application → Cookies → 复制全部 cookie，拼接成 `xxx=aaa; yyy=bbb; ...` 一行字符串填入 `FORUM_COOKIE`。

### 创建定时任务（仅手动上传需要，订阅方式自动创建）

青龙面板 Web →「定时任务」→ 新建任务：

| 字段 | 值 |
|------|-----|
| 名称 | 福利吧论坛签到 |
| 命令 | `task wnflb_checkin_ql.py` |
| 定时规则 | `0 9,22 * * *`（每天 9:00 和 22:00） |

### 手动运行测试

在「定时任务」列表中找到任务，点击「运行」按钮手动执行一次，确认日志输出正常。

## 通知配置

脚本优先使用青龙内置 `notify.py` 的 `send()` 函数，只需在青龙面板「系统设置 → 通知设置」中配置好推送渠道即可，**无需在脚本里额外设置**。

青龙内置通知自动退回到以下环境变量方式（当 notify.py 不可用时）：
- `PUSHPLUS_TOKEN`：PushPlus 推送
- `SERVERCHAN_KEY`：Server 酱推送

## 为什么不用账号密码登录 / ddddocr？

账号密码登录依赖 `ddddocr` 识别 Discuz 验证码，而 `ddddocr` 依赖的 `onnxruntime` 官方**不提供 Alpine（musl libc）的 wheel 文件**（只有 glibc 的 manylinux 版本）。青龙默认容器是 Alpine，因此：

- 换任何 pip 镜像源都装不上 `onnxruntime`（不是镜像同步问题，是包本身不支持）
- 纯 Cookie 方式彻底绕开验证码识别，依赖只剩 `requests`，Alpine 直接可装

## 常见问题

**Q: Cookie 会过期吗？**
A: 会，一般有效期几个月。过期后脚本会报「Cookie 已失效」，重新从浏览器复制最新 Cookie 填入即可。

**Q: 如何获取 Cookie？**
A: 浏览器登录论坛后，F12 → Application → Cookies → 复制所有 cookie，拼接成字符串填入 `FORUM_COOKIE` 环境变量。

**Q: Cookie 字符串太长或含特殊字符？**
A: 也可把 cookie 存成文件，用 `COOKIE_FILE` 指向文件路径。文件内容可以是 JSON 对象 `{"key":"value",...}` 或纯 cookie 字符串。
