import re
import sqlite3
from datetime import datetime
import requests
import yfinance as yf

DB_NAME = "market_radar.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            market TEXT,
            title TEXT,
            summary TEXT,
            link TEXT UNIQUE,
            published_at TEXT,
            analyzed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def save_news(cursor, source, market, title, summary, link, published):
    if not title or not link:
        return 0
    try:
        cursor.execute("""
            INSERT INTO news (source, market, title, summary, link, published_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source, market, title.strip(), summary.strip(), link.strip(), published))
        return 1
    except sqlite3.IntegrityError:
        return 0


def parse_telegram_channel(channel_username):
    """Читает последние посты из публичной веб-версии Telegram без API-ключей."""
    url = f"https://t.me{channel_username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=10)
    html = r.text

    # Извлекаем блоки сообщений и ссылки на посты
    messages = re.findall(
        r'data-post="([^"]+)"[\s\S]*?<div class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>',
        html
    )
    results = []
    for post_id, raw_text in messages[-20:]:
        clean_text = re.sub(r"<br\s*/?>", " ", raw_text)
        clean_text = re.sub(r"<[^>]+>", "", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        if len(clean_text) < 25:
            continue
        # Первое предложение или первые 140 символов — в заголовок
        title = clean_text[:150] + ("..." if len(clean_text) > 150 else "")
        link = f"https://t.me{post_id}"
        results.append((title, clean_text[:400], link))
    return results


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    added_count = 0
    logs = []

    # 1. Русскоязычные Telegram-каналы (РФ рынок и Крипта)
    tg_channels = [
        ("rbc_invest", "РБК Инвестиции", "РФ"),
        ("bcs_express", "БКС Экспресс", "РФ"),
        ("markettwits", "MarketTwits", "РФ"),
        ("forklog", "ForkLog Крипта", "Крипта"),
    ]

    tg_added = 0
    for username, source_name, market in tg_channels:
        try:
            posts = parse_telegram_channel(username)
            c_added = 0
            for title, summary, link in posts:
                c_added += save_news(cursor, source_name, market, title, summary, link, datetime.now().isoformat())
            tg_added += c_added
            logs.append(f"TG @{username}: +{c_added}")
        except Exception as e:
            logs.append(f"TG @{username} err: {str(e)[:30]}")

    added_count += tg_added

    # 2. Рынок США и Крипта через yfinance (только валидные международные тикеры)
    yf_targets = [
        ("BTC-USD", "Крипта"),
        ("ETH-USD", "Крипта"),
        ("SOL-USD", "Крипта"),
        ("NVDA", "США"),
        ("AAPL", "США"),
        ("TSLA", "США"),
        ("MSFT", "США"),
        ("^GSPC", "США"),
        ("BZ=F", "США"),
        ("GC=F", "США"),
    ]

    yf_added = 0
    for ticker, market in yf_targets:
        try:
            news_list = yf.Ticker(ticker).news
            for item in news_list:
                content = item.get("content", item)
                title = content.get("title", "")
                summary = content.get("summary", title)
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                link_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = link_obj.get("url") if isinstance(link_obj, dict) else content.get("link", "")
                pub = content.get("pubDate", datetime.now().isoformat())
                yf_added += save_news(cursor, provider, market, title, summary, link, pub)
        except Exception:
            pass

    added_count += yf_added
    logs.insert(0, f"Telegram (РФ/Крипта): +{tg_added} | Yahoo (США/Крипта): +{yf_added}")

    conn.commit()
    conn.close()
    return added_count, logs
