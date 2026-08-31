# TraeWork + CodeBuddy 自动签到

在 GitHub Actions 上自动完成 TraeWork (TRAE SOLO CN) 和 CodeBuddy (WorkBuddy) 的每日签到，无需服务器、无需付费。

## 签到收益

| 平台 | 每日积分 | 说明 |
|------|---------|------|
| TraeWork | 200 积分/天 | TRAE Work 专属积分，可用于调用 AI 模型 |
| CodeBuddy | 100 积分/天 | Buddy 加油站通用积分，连续签到有额外奖励 |

## 原理

通过逆向分析客户端的签到接口，直接用 HTTP API 调用完成签到，无需启动桌面客户端。

- **TraeWork**: `POST https://api.trae.cn/trae/api/v2/ug/checkin_credits/claim`
- **CodeBuddy**: `POST https://www.codebuddy.cn/v2/billing/meter/daily-checkin`

签到脚本纯 Python 标准库实现，GitHub Actions 直接运行，零依赖。

## 部署步骤

### 1. Fork 或创建仓库

将本项目文件推送到你的 GitHub 仓库，目录结构：

```
.
├── .github/workflows/checkin.yml   # GitHub Actions 定时任务
├── checkin.py                       # 签到主脚本
├── extract_tokens.py                # 本地 token 提取工具
├── requirements.txt
└── README.md
```

### 2. 本地提取 Token

在你的电脑上（已安装并登录 TraeWork / CodeBuddy 客户端）运行：

```bash
pip install pycryptodome
python extract_tokens.py
```

脚本会自动从本地客户端文件中解密并提取 Token：

| 平台 | 本地文件路径 |
|------|-------------|
| TraeWork | `%APPDATA%\TRAE SOLO CN\User\globalStorage\storage.json` |
| CodeBuddy | `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` |

TraeWork 的 Token 使用 AES-128-CBC 加密存储，提取脚本内置了从客户端源码中逆向得到的盐值，可自动解密。

### 3. 配置 GitHub Secrets

在 GitHub 仓库页面：**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 值 | 必填 |
|-------------|---|------|
| `TRAE_TOKEN` | TraeWork 提取的 JWT Token | 签到 TraeWork 时必填 |
| `CODEBUDDY_TOKEN` | CodeBuddy 提取的 accessToken | 签到 CodeBuddy 时必填 |
| `SC_KEY` | Server 酱 sendkey（可选） | 可选，用于微信推送通知 |
| `WEBHOOK_URL` | 通用 Webhook 地址（可选） | 可选，POST JSON 通知 |

### 4. 启用 Actions

- 进入仓库 **Actions** 页面，确认 workflows 已启用
- 手动点击 **Run workflow** 测试一次
- 定时任务每天北京时间 08:00 和 20:00 自动执行

## 定时规则

```yaml
schedule:
  - cron: '0 0 * * *'   # UTC 00:00 = 北京时间 08:00
  - cron: '0 12 * * *'  # UTC 12:00 = 北京时间 20:00
```

GitHub Actions 的 cron 可能有 5-15 分钟延迟，属正常现象。每天跑两次确保签到成功。

## 注意事项

1. **Token 有效期约 60 天**，过期后需重新登录客户端并提取新 Token
2. **签到积分有保质期**（通常 30 天），记得及时使用
3. 脚本是幂等的——今日已签则会跳过，不会重复签到
4. Token 存储在 GitHub Secrets 中，不会泄露
5. 如签到接口变更，可能需要更新脚本中的 API 端点

## 本地运行

```bash
# 设置环境变量
export TRAE_TOKEN="你的TraeWork Token"
export CODEBUDDY_TOKEN="你的CodeBuddy Token"

# 运行
python checkin.py
```

## 常见问题

**Q: Token 过期了怎么办？**
A: 重新打开 TraeWork / CodeBuddy 客户端并登录，然后重新运行 `extract_tokens.py` 提取新 Token，更新 GitHub Secrets。

**Q: 只想签到其中一个平台怎么办？**
A: 只配置对应的 Secret 即可。只配 `TRAE_TOKEN` 就只签到 TraeWork，只配 `CODEBUDDY_TOKEN` 就只签到 CodeBuddy。

**Q: 怎么收到签到结果通知？**
A: 配置 `SC_KEY`（Server 酱）或 `WEBHOOK_URL`（飞书/钉钉/企微等 Webhook），签到结果会自动推送。

**Q: GitHub Actions 被禁用怎么办？**
A: GitHub 会在仓库 60 天无活动时自动禁用 Actions。定期 push 代码或手动触发 workflow 即可保持活跃。
