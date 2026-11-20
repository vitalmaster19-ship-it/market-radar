import sqlite3
from datetime import datetime
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
        "User-Agent": "MarketRadarBot/1.0 (Educational Finance Project)"
    }

    # 1. Крипторынок (CryptoCompare Open API)
    try:
        r = requests.get("https://cryptocompare.com", headers=headers, timeout=10)
        data = r.json().get("Data", [])
        c_added = 0
        for item in data[:40]:
            c_added += save_news(
                cursor,
                item.get("source_info", {}).get("name", "CryptoCompare"),
                "Крипта",
                item.get("title", ""),
                item.get("body", "")[:300],
                item.get("url", ""),
                datetime.fromtimestamp(item.get("published_on", 0)).isoformat()
            )
        added_count += c_added
        logs.append(f"Крипта (CryptoCompare): +{c_added}")
    except Exception as e:
        logs.append(f"Крипта ошибка: {e}")

    # 2. Рынок РФ (Официальный открытый API Московской Биржи)
    try:
        r = requests.get("https://moex.com", headers=headers, timeout=10)
        news_block = r.json().get("sitenews", {})
        columns = news_block.get("columns", [])
        rows = news_block.get("data", [])
        m_added = 0
        if "title" in columns and "id" in columns:
            idx_id = columns.index("id")
            idx_title = columns.index("title")
            idx_date = columns.index("published_at") if "published_at" in columns else None
            for row in rows[:40]:
                news_id = row[idx_id]
                title = row[idx_title]
                pub = row[idx_date] if idx_date is not None else datetime.now().isoformat()
                link = f"https://moex.com{news_id}"
                m_added += save_news(cursor, "Мосбиржа (MOEX)", "РФ", title, title, link, pub)
        added_count += m_added
        logs.append(f"РФ (MOEX API): +{m_added}")
    except Exception as e:
        logs.append(f"РФ ошибка: {e}")

    # 3. Рынок США (Reddit r/stocks и r/investing)
    for sub in ["stocks", "investing"]:
        try:
            r = requests.get(f"https://reddit.com{sub}/hot.json?limit=25", headers=headers, timeout=10)
            posts = r.json().get("data", {}).get("children", [])
            r_added = 0
            for post in posts:
                p = post.get("data", {})
                if p.get("stickied"):
                    continue
                r_added += save_news(
                    cursor,
                    f"Reddit r/{sub}",
                    "США",
                    p.get("title", ""),
                    p.get("selftext", "")[:300],
                    f"https://reddit.com{p.get('permalink', '')}",
                    datetime.fromtimestamp(p.get("created_utc", 0)).isoformat()
                )
            added_count += r_added
            logs.append(f"США (r/{sub}): +{r_added}")
        except Exception as e:
            logs.append(f"США (r/{sub}) ошибка: {e}")

    conn.commit()
    conn.close()
    return added_count, logs
