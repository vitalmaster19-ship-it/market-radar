import sqlite3
from datetime import datetime
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

    # Прямой сбор новостей по всем 3 рынкам через надежный канал yfinance
    yf_targets = [
        # Крипта
        ("BTC-USD", "Крипта"),
        ("ETH-USD", "Крипта"),
        ("SOL-USD", "Крипта"),
        # США и Сырье
        ("NVDA", "США"),
        ("AAPL", "США"),
        ("TSLA", "США"),
        ("MSFT", "США"),
        ("^GSPC", "США"),
        ("BZ=F", "США"),
        ("GC=F", "США"),
        # Рынок РФ и Рубль
        ("IMOEX.ME", "РФ"),
        ("SBER.ME", "РФ"),
        ("GAZP.ME", "РФ"),
        ("LKOH.ME", "РФ"),
        ("USDRUB=X", "РФ"),
    ]

    market_counts = {"Крипта": 0, "США": 0, "РФ": 0}

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

                added = save_news(cursor, provider, market, title, summary, link, pub)
                added_count += added
                market_counts[market] += added
        except Exception as e:
            logs.append(f"{ticker}: {str(e)[:35]}")

    logs.insert(0, f"Крипта: +{market_counts['Крипта']} | США: +{market_counts['США']} | РФ: +{market_counts['РФ']}")

    conn.commit()
    conn.close()
    return added_count, logs
