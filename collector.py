import re
import sqlite3
from datetime import datetime
from deep_translator import GoogleTranslator
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


def detect_ru_market(text, default_market):
    """Относим новость к РФ только если в ней явно есть российский или рублевый контекст."""
    ru_keywords = r"\b(russia\w*|ruble\w*|rouble\w*|moscow|kremlin|gazprom|lukoil|rosneft|sberbank|urals|novatek)\b"
    if re.search(ru_keywords, text, flags=re.IGNORECASE):
        return "РФ"
    return default_market


def batch_translate_to_ru(titles):
    """Переводит список заголовков на русский язык пачками (быстро и без лимитов)."""
    if not titles:
        return []
    translator = GoogleTranslator(source="en", target="ru")
    translated_all = []
    chunk_size = 15
    for i in range(0, len(titles), chunk_size):
        chunk = titles[i:i + chunk_size]
        joined = "\n".join(t.replace("\n", " ") for t in chunk)
        try:
            res = translator.translate(joined)
            parts = res.split("\n")
            if len(parts) == len(chunk):
                translated_all.extend(parts)
            else:
                translated_all.extend(chunk)
        except Exception:
            translated_all.extend(chunk)
    return translated_all


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    logs = []

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
        ("USDRUB=X", "РФ"),
    ]

    raw_items = []
    seen_links = set()

    for ticker, default_market in yf_targets:
        try:
            news_list = yf.Ticker(ticker).news
            for item in news_list:
                content = item.get("content", item)
                raw_title = content.get("title", "").strip()
                raw_summary = content.get("summary", raw_title).strip()
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                link_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = (link_obj.get("url") if isinstance(link_obj, dict) else content.get("link", "")).strip()
                pub = content.get("pubDate", datetime.now().isoformat())

                if not raw_title or not link or link in seen_links:
                    continue
                seen_links.add(link)

                cursor.execute("SELECT 1 FROM news WHERE link = ?", (link,))
                if cursor.fetchone():
                    continue

                actual_market = detect_ru_market(f"{raw_title} {raw_summary}", default_market)
                raw_items.append((provider, actual_market, raw_title, raw_summary, link, pub))
        except Exception:
            pass

    # Переводим все новые заголовки пачками
    ru_titles = batch_translate_to_ru([item[2] for item in raw_items])

    added_count = 0
    market_counts = {"РФ": 0, "США": 0, "Крипта": 0}

    for (provider, market, raw_title, raw_summary, link, pub), ru_title in zip(raw_items, ru_titles):
        try:
            cursor.execute("""
                INSERT INTO news (source, market, title, summary, link, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (provider, market, ru_title.strip(), f"{ru_title} ({raw_title})", link, pub))
            added_count += 1
            market_counts[market] += 1
        except sqlite3.IntegrityError:
            pass

    logs.append(f"РФ: +{market_counts['РФ']} | США: +{market_counts['США']} | Крипта: +{market_counts['Крипта']}")
    conn.commit()
    conn.close()
    return added_count, logs
