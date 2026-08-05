# 📰 新闻每日简报

每天自动汇总 **知乎热榜 + 知乎日报 + 观察者网** 的重要新闻，用 DeepSeek 筛选总结后推送到飞书群。

## 工作流程

```
每天 8:00（北京时间）GitHub Actions 定时触发
 │
 ├── 知乎热榜    ← 官方公开 API（免登录，20 条）
 ├── 知乎日报    ← RSSHub 公共实例（10 条）
 └── 观察者网    ← RSSHub 公共实例（要闻 10 条 + 风闻 10 条）
 │
 ▼
DeepSeek 从 ~50 条中筛选 15-20 条，生成中文简报（今日必读 / 分类精读 / 深度观察）
 │
 ▼
推送到飞书群 + 存档到 daily/ 和 data/
```

## 部署

1. Fork / clone 本仓库到 GitHub（推荐私有）
2. 配置 GitHub Actions Secrets：
   - `API_KEY` — DeepSeek API Key（[platform.deepseek.com](https://platform.deepseek.com)）
   - `FEISHU_WEBHOOK_URL` — 飞书群机器人 Webhook（可选配置项：`API_BASE_URL`、`API_MODEL`，默认 `https://api.deepseek.com` / `deepseek-chat`）
3. 仓库的 Actions 标签页手动跑一次 `新闻每日简报`，确认成功后再等每日定时

## 本地运行

```bash
cd scripts
pip install -r ../requirements.txt
API_KEY=sk-xxx FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx python main.py
```

## 目录结构

```
├── .github/workflows/daily.yml   # 每日定时任务
├── scripts/
│   ├── sources.py                # 三个数据源抓取（多实例降级）
│   ├── summarize.py              # DeepSeek 筛选 + 中文简报
│   └── main.py                   # 调度 + 飞书推送
├── daily/                        # 每日简报存档（{date}.md）
├── data/                         # 原始抓取数据（{date}.raw.json）
└── requirements.txt
```

## 数据源稳定性说明

- **知乎热榜**：直连官方公开 API（无需登录，带浏览器 UA），是三者中最稳的来源
- **知乎日报 / 观察者网**：走 RSSHub 公共实例，脚本内置多实例自动降级（首个可用实例胜出）+ 重试；个别实例被限流不影响整体
- 抓取失败会自动重试 3 次；若当天所有来源全部失败，会推送一条失败告警到飞书，并在 Actions 中标记失败
