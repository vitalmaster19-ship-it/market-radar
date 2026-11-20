from concurrent.futures import ThreadPoolExecutor
import re
import sqlite3
from datetime import datetime
import yfinance as yf

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

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
    ru_keywords = r"\b(russia\w*|ruble\w*|rouble\w*|moscow|kremlin|gazprom|lukoil|rosneft|sberbank|urals|novatek|opec\+?)\b"
    if re.search(ru_keywords, text, flags=re.IGNORECASE):
        return "РФ"
    return default_market


def translate_single(text):
    try:
        res = GoogleTranslator(source="en", target="ru").translate(text)
        return res if res else text
    except Exception:
        return text


def batch_translate_to_ru(titles):
    if not titles or not HAS_TRANSLATOR:
        return titles, False
    with ThreadPoolExecutor(max_workers=10) as executor:
        translated = list(executor.map(translate_single, titles))
    success = any(t != orig for t, orig in zip(translated[:5], titles[:5]))
    return translated, success


def collect_news():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    logs = []

    raw_items = []
    seen_links = set()

    def process_news_list(news_list, default_market, force_market=False):
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

            actual_market = default_market if force_market else detect_ru_market(f"{raw_title} {raw_summary}", default_market)
            raw_items.append((provider, actual_market, raw_title, raw_summary, link, pub))

    ru_search_queries = [
        "Sberbank",
        "Gazprom",
        "Lukoil",
        "Moscow Exchange",
        "Bank of Russia",
        "Russian ruble economy",
    ]
    for q in ru_search_queries:
        try:
            search_res = yf.Search(q, news_count=8).news
            process_news_list(search_res, "РФ", force_market=True)
        except Exception:
            pass

    yf_targets = [
        ("BTC-USD", "Крипта"),
        ("ETH-USD", "Крипта"),
        ("SOL-USD", "Крипта"),
        ("NVDA", "США"),
        ("AAPL", "США"),
        ("TSLA", "США"),
        ("MSFT", "США"),
        ("^GSPC", "США"),
        ("GC=F", "США"),
        ("BZ=F", "РФ"),
        ("NG=F", "РФ"),
        ("USDRUB=X", "РФ"),
    ]

    for ticker, default_market in yf_targets:
        try:
            news_list = yf.Ticker(ticker).news
            process_news_list(news_list, default_market)
        except Exception:
            pass

    ru_titles, tr_ok = batch_translate_to_ru([item for item in raw_items])

    added_count = 0
    market_counts = {"РФ": 0, "США": 0, "Крипта": 0}

    for (provider, market, raw_title, raw_summary, link, pub), ru_title in zip(raw_items, ru_titles):
        final_title = (ru_title or raw_title).strip()
        try:
            cursor.execute("""
                INSERT INTO news (source, market, title, summary, link, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (provider, market, final_title, f"{final_title} ({raw_title})", link, pub))
            added_count += 1
            market_counts[market] += 1
        except sqlite3.IntegrityError:
            pass

    logs.append(f"РФ: +{market_counts['РФ']} | США: +{market_counts['США']} | Крипта: +{market_counts['Крипта']}")
    logs.append(f"Переводчик RU: {'Активен' if tr_ok else 'Не сработал (сделайте Reboot app)'}")
    conn.commit()
    conn.close()
    return added_count, logs
