# SakuraFRP Auto Checkin

话不多说，直接上图：

<table>
  <tr>
    <td><img width="100%" alt="稳定签到成功" src="https://github.com/user-attachments/assets/34c9ce9a-95ad-49c5-81be-1aadfe69b91c" /></td>
    <td><img width="100%" alt="多轮失败重试" src="https://github.com/user-attachments/assets/e543e7f3-524a-466c-bdcf-6c7ffe9f713c" /></td>
    <td><img width="100%" alt="邮件内容展示" src="https://github.com/user-attachments/assets/7d6f766a-cfe0-497c-8a6d-ccd1ea0f4623" /></td>
  </tr>
  <tr>
    <td align="center">（a）稳定签到成功</td>
    <td align="center">（b）多轮失败重试</td>
    <td align="center">（c）邮件内容展示</td>
  </tr>
</table>

---

稳定版 SakuraFRP 自动签到脚本，支持：

- Playwright 自动化登录与签到
- 验证码检测；需要交互验证时安全停止并记录
- 单次执行内多轮重试
- 成功/失败邮件通知
- 本地运行 + GitHub Actions 每日定时运行

原始项目参考链接：

- https://github.com/RyanStarFox/SakuraFRP_Auto_AI_check

## 1. 功能概览

当前版本重点在稳定性：

- 严格签到成功判定，避免误报
- 登录状态二次确认与自动补登录
- 18+ 弹窗自动处理
- 网络或程序错误可重试；验证码出现时停止重试并提示人工处理
- 失败退出码正确返回，便于调度层重试

## 2. 项目结构

```text
.
├── main.py                  # 主程序
├── ai_service.py            # AI 能力封装
├── logger.py                # 日志记录器
├── requirements.txt         # Python 依赖
├── env.example              # 环境变量模板
├── run_checkin.sh           # 本地/服务器执行脚本（含外层重试）
├── generate_random_time.sh  # 本地随机时刻生成脚本
├── logs/                    # 运行日志
└── .github/workflows/       # GitHub Actions 工作流
```

## 3. 本地运行

### 3.1 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3.2 配置文件

1. 复制环境变量模板

```bash
cp env.example .env
```

2. 创建账号文件 `account.txt`

```text
第一行: 用户名
第二行: 密码
```

### 3.3 手动执行

```bash
source .venv/bin/activate
python main.py --both
```

## 4. 关键配置

在 `.env` 中常用配置如下：

- `ZHIPU_API_KEY`: 智谱 API Key
- `ZHIPU_MODEL_VISION`: 视觉模型（默认 `glm-4.6v-flash`）
- `ZHIPU_MODEL_TEXT`: 文本模型（默认 `glm-4.7-flash`）
- `AI_CALL_MAX_RETRIES`: AI 调用失败重试次数
- `USE_STATE_CACHE`: 是否复用 state 登录态（推荐 `false`）
- `CHECKIN_MAX_RETRIES`: 外层重试次数（建议 5）
- `CHECKIN_RETRY_INTERVAL_SECONDS`: 外层重试间隔秒数（建议 30）

### 4.1 验证码检测与处理

脚本会检测已知的九宫格和滑块验证码。检测到后会记录日志、停止本次自动签到并以专用退出码结束；不会调用视觉模型解题、点击答案或提交验证。GitHub-hosted runner 无法进行人工交互，因此这次任务需要你按 SakuraFrp 页面提示手动完成验证。普通网络或程序错误仍按工作流重试。

### 4.2 邮件通知策略

用 `EMAIL_NOTIFY_POLICY` 控制通知频率，默认值为 `all`，每天会收到一次签到状态邮件（新签到或“今日已签到”）：

| 取值 | 行为 |
| --- | --- |
| `none` | 从不发邮件 |
| `failure_only` | 仅最终失败时发 |
| `change` | 最终失败 + 当天首次签到成功；“今日已签到”不发 |
| `all` | **默认**，每次运行都发，包括“今日已签到” |

另外两点：

- 单次运行最多发一封邮件，失败邮件与连续失败告警邮件不再重复轰炸
- `FAIL_ALERT_ENABLED` 默认改为 `false`。GitHub Actions runner 每次都是干净环境，
  `alert_state.json` 无法跨天保留，连续失败计数在 CI 下本就不成立

## 5. GitHub Actions 部署

仓库内已提供工作流：

- 文件: `.github/workflows/checkin.yml`
- 触发方式:
  - 每天定时执行
  - 手动触发（workflow_dispatch）

### 5.1 定时说明

GitHub Actions 使用 UTC 时区。

- 目标: 每天北京时间 12:07
- 对应 cron: `7 4 * * *`（UTC）

### 5.2 需要配置的 Secrets

签到使用的 Secrets（保留现有配置）：

- `SAKURA_USERNAME`
- `SAKURA_PASSWORD`
- `ZHIPU_API_KEY`
- `HTTP_PROXY` (可选)

如需邮件通知，在 `Settings -> Secrets and variables -> Actions -> Secrets` 中添加以下邮件 Secrets：

- `EMAIL_SMTP_USER`：SMTP 发件账号
- `EMAIL_SMTP_PASSWORD`：SMTP 授权码或应用密码
- `EMAIL_TO`：收件地址；多个地址用逗号分隔

邮件服务器默认使用 `smtp.qq.com`。其他服务商可在 Actions 的 Repository variables 中设置 `EMAIL_SMTP_HOST`。如已设置 `EMAIL_NOTIFY_POLICY` 变量，其值会覆盖工作流的默认 `all`。

工作流通过步骤级环境变量向运行进程提供 Secrets，不会把值插入 shell 脚本或写入 artifact。没有邮件 SMTP 配置时，签到仍会执行，日志会提示邮件未发送。

### 5.3 首次验证

1. 打开 Actions 页面
2. 手动运行 `SakuraFRP Daily Check-in`
3. 检查 Job 日志和 secret-free 验证任务
4. 下载 artifacts 查看 `logs/`
5. 配好 SMTP Secrets 后确认是否收到邮件；手动运行成功只能验证当次登录/签到结果，不能证明视觉 API 或验证码处理有效

## 6. 安全建议

- 不要把 `.env`、`account.txt`、`state.json` 提交到 Git
- 不要在 Issue/日志中粘贴明文密钥
- 建议定期轮换 API Key 与 SMTP 授权码

## 7. 故障排查

### 7.1 需要人工完成验证码

- 查看邮件/Actions 日志确认已检测到验证码
- 按 SakuraFrp 页面提示人工完成验证；脚本不会自动识别或提交

### 7.2 邮件未收到

- 检查 SMTP 授权码是否有效
- 检查 `EMAIL_SMTP_USER`、`EMAIL_SMTP_PASSWORD`、`EMAIL_TO` 是否已配置
- 检查邮箱垃圾箱
- 查看日志中 `邮件发送失败` 报错

### 7.3 Actions 执行失败

- 检查 Secrets 是否配置完整
- 检查 Playwright 依赖安装日志
- 下载 artifacts 查看 `logs/checkin_YYYY-MM-DD.log`

## 8. 免责声明

本项目仅用于个人学习与自动化实践。请遵守目标网站服务条款与当地法律法规。
