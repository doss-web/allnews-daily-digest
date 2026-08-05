"""
AI summarization via DeepSeek (OpenAI-compatible API).
Produces a single Chinese daily digest, split into 知乎 / 观察者网 sections.
"""

import os

import requests

SYSTEM_PROMPT = """你是一位资深新闻主编，为关心国内与国际时事的读者撰写每日新闻简报。

【输入】原始条目来自两个来源板块：知乎（热榜、日报）和观察者网（头条、要闻）。

【输出要求】只输出中文，严格遵守以下结构：

## 🟦 知乎

从知乎的原始条目中，选出最重要、最有信息增量的 12~15 条，按重要程度从高到低平铺列出（不要按主题分组），每条：

**🔥 [标题]**
- **内容**：（4-5 句，按以下层次逐层展开，不要复述标题，严格基于原文：
  第 1 句 · 事件主体与动作：谁、做了什么
  第 2 句 · 关键细节：具体的时间、数字、引语、地点
  第 3 句 · 背景与前因：这件事为什么发生
  第 4 句 · 影响：对相关方、行业、局势的具体影响
  第 5 句 · 后续关注：接下来值得盯什么）
- 来源：[知乎热榜](URL)

## 🟥 观察者网

观察者网的条目全部列出（头条 1 条放在最上，随后是各条要闻），每条：

**🔥 [标题]**
- **内容**：（2-3 句，讲清事件本身。不要只复述标题，要补充上下文。）
- 来源：[观察者网·头条](URL)

### 🧭 深度观察

3-5 句话，有观点有判断。回答：今天这些事件拼在一起，揭示了什么趋势或转折？明天值得盯什么？

【写作要求】
1. 严格基于原文，严禁编造事实、数字或细节
2. 专有名词保留原文，其余用中文
3. 禁用"重磅""炸裂""震惊""震撼"等营销词
4. 每条来源链接必须原样保留原始条目里的 URL
5. 知乎和观察者网两个板块各自独立、互不合并：同一主题在两个板块同时出现时，各自保留在各自的板块里，不要做跨板块去重"""


def _format_item(item):
    return (
        f"- [{item['source']}] {item['title']}\n"
        f"  URL: {item['url']}\n"
        f"  {item['summary'] or '(无摘要)'}"
    )


def format_raw_content(items):
    """Format fetched items for the AI, grouped into 知乎 / 观察者网 blocks."""
    blocks = []

    zhihu_items = [it for it in items if "知乎" in it["source"]]
    if zhihu_items:
        blocks.append("=== 知乎板块 ===")
        blocks.extend(_format_item(it) for it in zhihu_items)
        blocks.append("")

    guancha_items = [it for it in items if "观察者网" in it["source"]]
    if guancha_items:
        blocks.append("=== 观察者网板块 ===")
        blocks.extend(_format_item(it) for it in guancha_items)

    return "\n".join(blocks).strip()


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

以下是今天收集到的原始资讯，按板块整理，请按输出要求生成简报：

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
