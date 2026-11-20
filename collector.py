import sqlite3
from datetime import datetime
import feedparser
import requests

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

    # 1. Надежные RSS и Google News (отлично работают из облака США)
    feeds = [
        ("Google News РФ", "РФ", "https://google.com"),
        ("ТАСС Экономика", "РФ", "https://tass.ru"),
        ("Google News США", "США", "https://google.com"),
        ("CNBC Finance", "США", "https://cnbc.com"),
        ("CoinTelegraph", "Крипта", "https://cointelegraph.com"),
        ("Google News Крипта", "Крипта", "https://google.com"),
    ]

    for name, market, url in feeds:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            parsed = feedparser.parse(r.content)
            f_added = 0
            for entry in parsed.entries[:25]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                pub = entry.get("published", datetime.now().isoformat())
                f_added += save_news(cursor, name, market, title, summary, link, pub)
            added_count += f_added
            logs.append(f"{name}: +{f_added}")
        except Exception as e:
            logs.append(f"{name} ошибка: {str(e)[:60]}")

    # 2. Reddit Finance (исправленная ссылка)
    for sub in ["stocks", "CryptoCurrency"]:
        try:
            reddit_url = "https://reddit.com" + "/r/" + sub + "/hot.json?limit=20"
            r = requests.get(reddit_url, headers={"User-Agent": "python:marketradar:v1.0"}, timeout=10)
            posts = r.json().get("data", {}).get("children", [])
            r_added = 0
            market_label = "Крипта" if sub == "CryptoCurrency" else "США"
            for post in posts:
                p = post.get("data", {})
                if p.get("stickied"):
                    continue
                r_added += save_news(
                    cursor,
                    f"Reddit r/{sub}",
                    market_label,
                    p.get("title", ""),
                    p.get("selftext", "")[:300],
                    "https://reddit.com" + p.get("permalink", ""),
                    datetime.fromtimestamp(p.get("created_utc", 0)).isoformat()
                )
            added_count += r_added
            logs.append(f"Reddit r/{sub}: +{r_added}")
        except Exception as e:
            logs.append(f"Reddit r/{sub} ошибка: {str(e)[:60]}")

    conn.commit()
    conn.close()
    return added_count, logs
