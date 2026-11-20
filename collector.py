import sqlite3
import time
from datetime import datetime
import feedparser
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


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    added_count = 0
    logs = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # 1. Прямые русскоязычные финансовые ленты (открыты из облака США)
    ru_rss = [
        ("Rambler Финансы", "РФ", "https://rambler.ru"),
        ("Российская Газета (Экономика)", "РФ", "https://rg.ru"),
        ("Habr Финансы и Инвестиции", "РФ", "https://habr.com"),
        ("ForkLog (Крипта RU)", "Крипта", "https://forklog.com"),
    ]

    ru_added = 0
    for name, market, url in ru_rss:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(r.content)
            f_added = 0
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                pub = entry.get("published", datetime.now().isoformat())
                f_added += save_news(cursor, name, market, title, summary, link, pub)
            ru_added += f_added
            logs.append(f"{name}: +{f_added}")
        except Exception as e:
            logs.append(f"{name} err: {str(e)[:30]}")

    # 2. GDELT API с соблюдением лимита (1 запрос с паузой 5 сек)
    try:
        time.sleep(5)
        gdelt_url = "https://gdeltproject.org"
        params = {
            "query": "(Мосбиржа OR Сбербанк OR Газпром OR Центробанк OR рубль) sourcelang:russian",
            "mode": "ArtList",
            "maxrecords": 30,
            "format": "json",
            "timespan": "48h"
        }
        r = requests.get(gdelt_url, params=params, headers=headers, timeout=12)
        if r.text.strip().startswith("{"):
            articles = r.json().get("articles", [])
            g_added = 0
            for art in articles:
                g_added += save_news(
                    cursor,
                    art.get("domain", "СМИ РФ"),
                    "РФ",
                    art.get("title", ""),
                    art.get("title", ""),
                    art.get("url", ""),
                    art.get("seendate", datetime.now().isoformat())
                )
            ru_added += g_added
            logs.append(f"СМИ РФ (GDELT): +{g_added}")
        else:
            logs.append(f"GDELT ответ: {r.text[:40]}")
    except Exception as e:
        logs.append(f"GDELT err: {str(e)[:30]}")

    added_count += ru_added

    # 3. Рынок США и Крипта через yfinance
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
    logs.insert(0, f"РФ/Крипта (RU): +{ru_added} | США/Крипта (EN): +{yf_added}")

    conn.commit()
    conn.close()
    return added_count, logs
