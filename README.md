# CodeBuddy 自动签到

在 GitHub Actions 上自动完成 CodeBuddy (WorkBuddy) 的每日签到，无需服务器、无需付费。

## 签到收益

| 平台 | 每日积分 | 说明 |
|------|---------|------|
| CodeBuddy | 100 积分/天 | Buddy 加油站通用积分，连续签到有额外奖励 |

## 原理

通过逆向分析客户端源码，直接用 HTTP API 调用完成签到，无需启动桌面客户端。

- **CodeBuddy**: `POST https://www.codebuddy.cn/v2/billing/meter/daily-checkin`

签到脚本纯 Python 标准库实现，GitHub Actions 直接运行，零依赖。

## 部署步骤

### 1. Fork 或创建仓库

将本项目文件推送到你的 GitHub 仓库，目录结构：

```
.
├── .github/workflows/checkin.yml   # GitHub Actions 定时任务
├── checkin.py                       # 签到主脚本
└── README.md
```

### 2. 获取凭证（二选一）

> **重要**：新版客户端把 Token 用 AES-128-GCM 加密后存在本地（`$wbEncrypted` 格式），
> 密钥在客户端内部，无法直接从文件读出明文。请从网页端获取凭证。

**方式 A：Token（推荐）**

1. 打开 [www.codebuddy.cn](https://www.codebuddy.cn) 并登录
2. 按 `F12` 打开开发者工具 → 切到 **Network**（网络）标签
3. 在页面上点一下任意功能，触发 API 请求
4. 点开任意一条请求，在 **Request Headers** 里找到：

   ```
   Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
   ```

5. 复制 `Bearer ` 后面整串（以 `ey` 开头的 JWT），作为 `CODEBUDDY_TOKEN`

**方式 B：Cookie（备用）**

同样的 Network 面板里，找到 **Request Headers** 的 `cookie` 行，
把 `session=...; session_2=...` 整段复制下来，作为 `CODEBUDDY_COOKIE`。

脚本两种方式都支持：配置了 `CODEBUDDY_TOKEN` 就用 Token，只用 `CODEBUDDY_COOKIE` 就走 Cookie。

### 3. 配置 GitHub Secrets

在 GitHub 仓库页面：**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 值 | 必填 |
|-------------|---|------|
| `CODEBUDDY_TOKEN` | 网页端复制的 JWT Token | 二选一 |
| `CODEBUDDY_COOKIE` | 网页端复制的 Cookie 串 | 二选一 |
| `SC_KEY` | Server 酱 sendkey | 可选，用于微信推送通知 |
| `WEBHOOK_URL` | 通用 Webhook 地址 | 可选，POST JSON 通知 |

### 4. 启用 Actions

- 进入仓库 **Actions** 页面，确认 workflows 已启用
- 手动点击 **Run workflow** 测试一次
- 定时任务每天北京时间 08:00 和 10:00 自动执行

## 定时规则

```yaml
schedule:
  - cron: '0 0 * * *'   # UTC 00:00 = 北京时间 08:00（主签到）
  - cron: '0 2 * * *'   # UTC 02:00 = 北京时间 10:00（兜底补签）
```

GitHub Actions 的 cron 可能有 5-15 分钟延迟，属正常现象。每天跑两次确保签到成功。

## 推送通知策略

**仅在以下情况推送通知**（通过 Server 酱或 Webhook）：

- 首次签到成功
- 签到失败
- Token 过期/失效

今日已签到的重复执行**不推送**，避免打扰。

## 注意事项

1. **Token 有效期约 60 天**，过期后需重新登录客户端并提取新 Token
2. **签到积分有保质期**（通常 30 天），记得及时使用
3. 脚本是幂等的——今日已签则会跳过，不会重复签到
4. Token 存储在 GitHub Secrets 中，不会泄露
5. 如签到接口变更，可能需要更新脚本中的 API 端点

## 本地运行

```bash
# Token 模式
set CODEBUDDY_TOKEN=你的Token
python checkin.py

# Cookie 模式
set CODEBUDDY_COOKIE=session=xxx; session_2=xxx
python checkin.py
```

## 常见问题

**Q: Token 过期了怎么办？**
A: 新版客户端本地存储的 Token 已加密（`$wbEncrypted`），无法从文件直接提取。
   请按「2. 获取凭证」从网页端复制新的 Token 或 Cookie，更新 GitHub Secrets 后重跑。

**Q: 能不能降级客户端版本来绕过加密？**
A: 不建议。降级后客户端通常会强制更新，且服务端认证逻辑不随之改变，
   旧版仍可能使用加密存储。从网页端获取凭证更可靠。

**Q: 为什么不用本地脚本自动提取 Token？**
A: 客户端用 AES-128-GCM 加密 Token，密钥（keyId `9127dea1b44020a7`）保存在客户端内部，
   不在任何明文文件中，纯本地脚本无法解密。

**Q: 怎么收到签到结果通知？**
A: 配置 `SC_KEY`（Server 酱）或 `WEBHOOK_URL`（飞书/钉钉/企微等 Webhook），签到结果会自动推送到微信。

**Q: GitHub Actions 被禁用怎么办？**
A: GitHub 会在仓库 60 天无活动时自动禁用 Actions。定期 push 代码或手动触发 workflow 即可保持活跃。
