import sqlite3
from datetime import datetime
import feedparser
import requests

DB_NAME = "market_radar.db"

RSS_FEEDS = [
    {"source": "РБК", "market": "РФ", "url": "https://rbc.ru"},
    {"source": "Интерфакс", "market": "РФ", "url": "https://interfax.ru"},
    {"source": "Коммерсантъ", "market": "РФ", "url": "https://kommersant.ru"},
    {"source": "CNBC Finance", "market": "США", "url": "https://cnbc.com"},
    {"source": "Google News США", "market": "США", "url": "https://google.com"},
    {"source": "CoinTelegraph", "market": "Крипта", "url": "https://cointelegraph.com"},
    {"source": "ForkLog", "market": "Крипта", "url": "https://forklog.com"},
]


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


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    added_count = 0
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for feed_info in RSS_FEEDS:
        try:
            r = requests.get(feed_info["url"], headers=headers, timeout=10)
            feed = feedparser.parse(r.content)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                link = entry.get("link", "").strip()
                published = entry.get("published", datetime.now().isoformat())
                if not title or not link:
                    continue
                try:
                    cursor.execute("""
                        INSERT INTO news (source, market, title, summary, link, published_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (feed_info["source"], feed_info["market"], title, summary, link, published))
                    added_count += 1
                except sqlite3.IntegrityError:
                    pass
        except Exception:
            pass

    conn.commit()
    conn.close()
    return added_count
