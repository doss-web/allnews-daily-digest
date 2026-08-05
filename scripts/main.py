"""
新闻每日简报 - Main entry point.
Fetches 知乎 + 观察者网 news, summarizes with DeepSeek, pushes to Feishu.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from sources import fetch_all
from summarize import summarize


def send_to_feishu(subject: str, markdown: str) -> None:
    """Push the digest to a Feishu group bot via webhook."""
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        print("[Feishu] FEISHU_WEBHOOK_URL not set, skipping.")
        return

    # Split long content into multiple markdown elements (18K chars each max)
    chunk_size = 18000
    if len(markdown) <= chunk_size:
        elements = [{"tag": "markdown", "content": markdown}]
    else:
        elements = []
        chunk = ""
        for line in markdown.split("\n"):
            if len(chunk) + len(line) + 1 > chunk_size:
                elements.append({"tag": "markdown", "content": chunk})
                chunk = line
            else:
                chunk += ("\n" + line) if chunk else line
        if chunk:
            elements.append({"tag": "markdown", "content": chunk})

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": subject},
                "template": "blue",
            },
            "elements": elements,
        },
    }

    resp = requests.post(webhook_url, json=payload, timeout=30)
    if resp.status_code == 200 and resp.json().get("code") == 0:
        print("[Feishu] Sent successfully!")
    else:
        print(f"[Feishu] Failed HTTP {resp.status_code}: {resp.text[:200]}")


def main():
    # Use Beijing time for the date
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz)
    date_str = today.strftime("%Y-%m-%d")

    print(f"=== 新闻每日简报 for {date_str} ===\n")

    # Step 1: fetch from all sources
    print("[Step 1] Fetching data from sources...")
    items = fetch_all()
    print(f"\nTotal items fetched: {len(items)}")

    if not items:
        print("All sources failed. Notifying and exiting with failure.")
        send_to_feishu(
            f"⚠️ 新闻简报抓取失败 · {date_str}",
            "**今天所有数据源（知乎热榜/日报、观察者网）均抓取失败**，请检查 GitHub Actions 日志。",
        )
        sys.exit(1)

    # Step 2: save raw data for traceability
    print("\n[Step 2] Saving raw data...")
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    raw_file = data_dir / f"{date_str}.raw.json"
    raw_file.write_text(
        json.dumps(
            {"date": date_str, "count": len(items), "items": items},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  Saved to {raw_file}")

    # Step 3: AI summarization
    print("\n[Step 3] Generating AI summary...")
    markdown = summarize(items, date_str)

    # Step 4: save daily markdown
    print("\n[Step 4] Saving digest...")
    output_dir = Path(__file__).parent.parent / "daily"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{date_str}.md"
    output_file.write_text(markdown, encoding="utf-8")
    print(f"  Saved to {output_file}")

    # Step 5: push to Feishu
    print("\n[Step 5] Pushing to Feishu...")
    send_to_feishu(f"新闻每日简报 · {date_str}", markdown)

    print("\nDone!")


if __name__ == "__main__":
    main()
