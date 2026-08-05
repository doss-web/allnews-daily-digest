"""
AI summarization via DeepSeek (OpenAI-compatible API).
Produces a single Chinese daily digest.
"""

import os

import requests

SYSTEM_PROMPT = """你是一位资深新闻主编，为关心国内与国际时事的读者撰写每日新闻简报。读者的诉求是：今天发生了什么重要的事，以及它意味着什么。

【筛选标准】从提供的原始条目中选出 15~20 条最重要的，其余丢弃：
- 重大政策、重要人事、重大突发事件
- 国际局势与中国相关的关键动态
- 重要的经济、科技、社会新闻
- 知乎热榜上讨论度高、真正值得知道的议题
- 知乎日报编辑精选的高质量内容优先保留
- 观察者网的要闻与风闻（热门观点）中，有信息增量的优先保留

【丢弃标准】
- 同一条新闻被多个来源重复报道的，只保留最详细的一条
- 纯娱乐八卦、广告软文、标题党但无实质信息的内容
- 明显过时或与前文重复的内容

【输出格式】只输出中文，严格遵守以下结构：

### ⚡ 今日必读（置顶 3 条最重要的，让读者 30 秒掌握今日核心）

> **1. [标题]** — 一句话摘要
> **2. [标题]** — 一句话摘要
> **3. [标题]** — 一句话摘要

### 📰 分类精读

按内容主题自然分组（如：国内时政 / 国际 / 经济财经 / 科技互联网 / 社会民生，实际用到哪些就写哪些），每组 3~5 条，每条：

**🔥 [标题]**
- **内容**：（2-3 句，讲清事件本身：谁、做了什么、关键细节。不要只复述标题，要补充上下文。）
- **为什么值得关注**：（1-2 句，影响面或后续值得跟踪的点；没有就省略。）
- 来源：[知乎热榜](URL)

### 🧭 深度观察

5-6 句话，有观点有判断。回答：今天这些事件拼在一起，揭示了什么趋势或转折？明天值得盯什么？

【写作要求】
1. 严格基于原文，严禁编造事实、数字或细节
2. 专有名词保留原文，其余用中文
3. 禁用"重磅""炸裂""震惊""震撼"等营销词
4. 每条来源链接必须原样保留原始条目里的 URL"""


def format_raw_content(items):
    """Format fetched items into a text block for the AI, grouped by source."""
    sections = {}
    for item in items:
        sections.setdefault(item["source"], []).append(item)

    blocks = []
    for source, group in sections.items():
        blocks.append(f"=== {source} ===")
        for item in group:
            blocks.append(
                f"- {item['title']}\n"
                f"  URL: {item['url']}\n"
                f"  {item['summary'] or '(无摘要)'}"
            )
    return "\n\n".join(blocks)


def summarize(items, date_str):
    """Generate a Chinese daily digest via DeepSeek. Returns markdown string."""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        raise ValueError("API_KEY environment variable is required")

    base_url = os.environ.get("API_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("API_MODEL", "deepseek-chat")

    raw_content = format_raw_content(items)
    if not raw_content.strip():
        return f"# 新闻每日简报 · {date_str}\n\n> 今天没有抓到任何内容。\n"

    user_prompt = f"""今天是 {date_str}。

以下是今天从知乎热榜、知乎日报、观察者网收集到的原始资讯，请整理成每日新闻简报，优先选择最重要、最有信息增量的内容：

{raw_content}"""

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 16384,
    }

    print(f"Calling {model}...")
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()

    text = resp.json()["choices"][0]["message"]["content"].strip()
    return f"# 新闻每日简报 · {date_str}\n\n{text}\n\n---\n*由 DeepSeek ({model}) 生成*"
