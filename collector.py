import sqlite3
from datetime import datetime
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

    # 1. GDELT API — мировая база новостей в реальном времени (индексирует РБК, ТАСС, Интерфакс, Коммерсантъ)
    # Отлично работает из дата-центров США без ключей и капчи
    gdelt_queries = [
        ("СМИ РФ (Акции/Биржа)", "РФ", "(Мосбиржа OR Сбербанк OR Газпром OR Лукойл) sourcelang:russian"),
        ("СМИ РФ (ЦБ/Рубль/Экономика)", "РФ", "(Центробанк OR Набиуллина OR рубль OR инфляция) sourcelang:russian"),
        ("СМИ РФ (Криптовалюты)", "Крипта", "(биткоин OR криптовалюта OR эфириум) sourcelang:russian"),
    ]

    ru_added = 0
    gdelt_url = "https://gdeltproject.org"

    for name, market, q in gdelt_queries:
        try:
            params = {
                "query": q,
                "mode": "ArtList",
                "maxrecords": 25,
                "format": "json",
                "timespan": "24h"
            }
            r = requests.get(gdelt_url, params=params, timeout=12)
            articles = r.json().get("articles", [])
            f_added = 0
            for art in articles:
                title = art.get("title", "")
                domain = art.get("domain", name)
                link = art.get("url", "")
                pub = art.get("seendate", datetime.now().isoformat())
                f_added += save_news(cursor, domain, market, title, title, link, pub)
            ru_added += f_added
            logs.append(f"{name}: +{f_added}")
        except Exception as e:
            logs.append(f"{name} err: {str(e)[:40]}")

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
