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

    # 1. Прямой сбор новостей через yfinance (США и Крипта — работает 100% в облаке)
    yf_targets = [
        ("BTC-USD", "Крипта"),
        ("ETH-USD", "Крипта"),
        ("NVDA", "США"),
        ("AAPL", "США"),
        ("^GSPC", "США"),
        ("BZ=F", "США"),
    ]
    yf_added = 0
    for ticker, market in yf_targets:
        try:
            news_list = yf.Ticker(ticker).news
            for item in news_list:
                # Поддержка новой и старой структуры ответа yfinance
                content = item.get("content", item)
                title = content.get("title", "")
                summary = content.get("summary", title)
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                
                link_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = link_obj.get("url") if isinstance(link_obj, dict) else content.get("link", "")
                pub = content.get("pubDate", datetime.now().isoformat())

                yf_added += save_news(cursor, provider, market, title, summary, link, pub)
        except Exception as e:
            logs.append(f"YF ({ticker}) err: {str(e)[:40]}")

    added_count += yf_added
    logs.append(f"Yahoo Finance (США/Крипта): +{yf_added}")

    # 2. Прямой feedparser для RSS (РФ и Мир)
    rss_feeds = [
        ("Коммерсантъ", "РФ", "https://kommersant.ru"),
        ("Лента.ру Экономика", "РФ", "https://lenta.ru"),
        ("Ведомости", "РФ", "https://vedomosti.ru"),
        ("CoinTelegraph", "Крипта", "https://cointelegraph.com"),
        ("CNBC", "США", "https://cnbc.com"),
    ]

    for name, market, url in rss_feeds:
        try:
            feed = feedparser.parse(url)
            f_added = 0
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                pub = entry.get("published", datetime.now().isoformat())
                f_added += save_news(cursor, name, market, title, summary, link, pub)
            added_count += f_added
            logs.append(f"{name}: +{f_added} (в ленте: {len(feed.entries)})")
        except Exception as e:
            logs.append(f"{name} ошибка: {str(e)[:40]}")

    conn.commit()
    conn.close()
    return added_count, logs
