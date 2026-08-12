# 福利吧论坛自动签到（青龙面板版）

基于 [wnflb-checkin](https://github.com/fmdxx1991/wnflb-checkin) 改造，适配**青龙面板（qinglong）**运行。

## 功能

- 支持**账号密码自动登录**（含 ddddocr 验证码识别）
- 支持**Cookie 直传**（兼容旧方式）
- Cookie 自动缓存复用，过期自动重新登录
- 使用青龙内置 `notify.py` 推送通知

## 青龙面板部署

### 1. 上传脚本

将 `wnflb_checkin_ql.py` 上传到青龙面板 `/ql/scripts/` 目录。

### 2. 安装依赖

青龙面板「依赖管理 → Python3」添加：

```
requests
ddddocr
Pillow
```

### 3. 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `FORUM_USERNAME` | 是* | 论坛账号 |
| `FORUM_PASSWORD` | 是* | 论坛密码 |
| `FORUM_COOKIE` | 否 | Cookie 字符串（优先级更高） |

### 4. 定时任务

- 命令：`task wnflb_checkin_ql.py`
- 规则：`0 9,22 * * *`（每天 9:00 / 22:00）

---

[原项目](https://github.com/fmdxx1991/wnflb-checkin) | 论坛：https://www.wnflb2023.com/
