# 福利吧论坛自动签到（青龙面板版）

基于 [wnflb-checkin](https://github.com/fmdxx1991/wnflb-checkin) 改造，适配**青龙面板（qinglong）**运行。

## 功能

- 支持**账号密码自动登录**（含 ddddocr 验证码识别）
- 支持**Cookie 直传**（兼容旧方式）
- Cookie 自动缓存复用，过期自动重新登录
- 使用青龙内置 `notify.py` 推送通知

## 青龙面板部署（订阅方式，推荐）

### 1. 添加订阅

青龙面板 →「订阅管理」→ 新建订阅：

| 字段 | 值 |
|------|-----|
| 名称 | 福利吧论坛签到 |
| 类型 | public-repo |
| URL | `https://github.com/LinxSSSR/fuliba.git` |
| 分支 | `main` |
| 白名单 | `wnflb_checkin_ql.py` |
| 依赖文件 | `requirements_ql.txt` |

### 2. 安装依赖

青龙面板「依赖管理 → Python3」添加：

```
requests
ddddocr
Pillow
```

### 3. 配置环境变量

青龙面板「环境变量」添加：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `FORUM_USERNAME` | 是* | 论坛账号 |
| `FORUM_PASSWORD` | 是* | 论坛密码 |
| `FORUM_COOKIE` | 否 | Cookie 字符串（优先级更高） |

> \* 二选一即可

### 4. 运行订阅

添加后青龙会自动拉取脚本并创建定时任务（每天 9:00 / 22:00）。也可以手动点「运行」拉取最新版本。

---

[原项目](https://github.com/fmdxx1991/wnflb-checkin) | 仓库地址：https://github.com/LinxSSSR/fuliba
