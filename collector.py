import sqlite3
from datetime import datetime
import feedparser
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

    # 1. Рынок РФ и Крипта на русском языке через Bing News RSS и Google News RSS
    # (работают из облака США без гео-блокировок)
    news_feeds = [
        ("Bing News (Акции РФ)", "РФ", "https://bing.com"),
        ("Bing News (Экономика/ЦБ)", "РФ", "https://bing.com"),
        ("Google News (Рынок РФ)", "РФ", "https://google.com"),
        ("Bing News (Крипта RU)", "Крипта", "https://bing.com"),
    ]

    ru_added = 0
    for name, market, url in news_feeds:
        try:
            feed = feedparser.parse(url)
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

    added_count += ru_added

    # 2. Рынок США и Крипта через yfinance
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
