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


def detect_ru_market(text, default_market):
    """Если мировая новость касается России, нефти/газа РФ, рубля или санкций — относим к рынку РФ."""
    ru_keywords = r"\b(russia\w*|ruble\w*|rouble\w*|moscow|kremlin|gazprom|lukoil|rosneft|sberbank|urals|novatek|opec\+?)\b"
    if re.search(ru_keywords, text, flags=re.IGNORECASE):
        return "РФ"
    return default_market


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    added_count = 0
    logs = []
    translator = GoogleTranslator(source="en", target="ru")

    yf_targets = [
        # Крипта
        ("BTC-USD", "Крипта"),
        ("ETH-USD", "Крипта"),
        ("SOL-USD", "Крипта"),
        # США и Макро
        ("NVDA", "США"),
        ("AAPL", "США"),
        ("TSLA", "США"),
        ("MSFT", "США"),
        ("^GSPC", "США"),
        # Сырье, Валюта и РФ-контекст
        ("BZ=F", "РФ"),
        ("NG=F", "РФ"),
        ("GC=F", "США"),
        ("USDRUB=X", "РФ"),
    ]

    market_counts = {"РФ": 0, "США": 0, "Крипта": 0}

    for ticker, default_market in yf_targets:
        try:
            news_list = yf.Ticker(ticker).news
            for item in news_list:
                content = item.get("content", item)
                raw_title = content.get("title", "")
                raw_summary = content.get("summary", raw_title)
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                link_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = link_obj.get("url") if isinstance(link_obj, dict) else content.get("link", "")
                pub = content.get("pubDate", datetime.now().isoformat())

                if not raw_title or not link:
                    continue

                # Проверяем, не добавлена ли уже эта ссылка (чтобы не тратить время на перевод дублей)
                cursor.execute("SELECT 1 FROM news WHERE link = ?", (link.strip(),))
                if cursor.fetchone():
                    continue

                actual_market = detect_ru_market(f"{raw_title} {raw_summary}", default_market)

                # Переводим заголовок на русский язык
                try:
                    ru_title = translator.translate(raw_title)
                except Exception:
                    ru_title = raw_title

                added = save_news(cursor, provider, actual_market, ru_title, f"{ru_title} ({raw_title})", link, pub)
                added_count += added
                market_counts[actual_market] += added
        except Exception as e:
            logs.append(f"{ticker}: {str(e)[:30]}")

    logs.insert(0, f"РФ/Сырье: +{market_counts['РФ']} | США: +{market_counts['США']} | Крипта: +{market_counts['Крипта']}")

    conn.commit()
    conn.close()
    return added_count, logs
