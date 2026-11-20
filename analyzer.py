import re
import sqlite3
from datetime import datetime

DB_NAME = "market_radar.db"

TOPICS = [
    # Ваш криптопортфель
    (r"\b(биткоин\w*|bitcoin|btc)\b", "#Биткоин", "BTC-USD"),
    (r"\b(эфир\w*|ethereum|eth)\b", "#Эфириум", "ETH-USD"),
    (r"\b(солана|solana|sol)\b", "#Solana", "SOL-USD"),
    (r"\b(ton|toncoin|тонкоин|дуров\w*|telegram)\b", "#Toncoin", "TON-USD"),
    (r"\b(xrp|ripple|рипл)\b", "#Ripple", "XRP-USD"),
    (r"\b(link|chainlink|чейнлинк)\b", "#Chainlink", "LINK-USD"),
    (r"\b(hype|hyperliquid|гиперликвид)\b", "#Hyperliquid", "HYPE-USD"),
    (r"\b(near|near\s+protocol)\b", "#NEAR", "NEAR-USD"),
    (r"\b(aave|ааве)\b", "#Aave", "AAVE-USD"),
    (r"\b(крипт\w*|crypto\w*|блокчейн\w*|defi)\b", "#Крипторынок", "BTC-USD"),

    # Ваш портфель РФ
    (r"\b(индекс\s+мосбирж\w*|imoex|мосбирж\w*|moex)\b", "#ИндексМосбиржи", "IMOEX.ME"),
    (r"\b(сбер\w*|sber\w*)\b", "#Сбербанк", "SBER.ME"),
    (r"\b(лукойл\w*|lukoil)\b", "#Лукойл", "LKOH.ME"),
    (r"\b(татнефт\w*|tatneft)\b", "#Татнефть", "TATN.ME"),
    (r"\b(x5|х5|пятерочк\w*|перекресток|чижик)\b", "#X5Group", "X5.ME"),
    (r"\b(транснефт\w*|transneft)\b", "#Транснефть", "TRNFP.ME"),
    (r"\b(новатэк\w*|новатек\w*|novatek)\b", "#Новатэк", "NVTK.ME"),
    (r"\b(банк\s+санкт-петербург\w*|бспб|bspb)\b", "#БанкСПб", "BSPB.ME"),
    (r"\b(ленэнерго|россети|lsng)\b", "#Ленэнерго", "LSNGP.ME"),
    (r"\b(полюс\w*|polyus|золот\w*|gold)\b", "#ПолюсЗолото", "PLZL.ME"),

    # Общие макро-теги РФ и мира
    (r"\b(газпром\w*|gazprom)\b", "#Газпром", "GAZP.ME"),
    (r"\b(цб|центробанк\w*|набиуллин\w*|ключев\w+\s+ставк\w*)\b", "#СтавкаЦБ", "IMOEX.ME"),
    (r"\b(рубл\w*|доллар\w*|юан\w*|валют\w*|ruble\w*)\b", "#ВалютаРФ", "USDRUB=X"),
    (r"\b(нефт\w*|brent|wti|опек|opec)\b", "#Нефть", "BZ=F"),
    (r"\b(фрс|fed|federal\s+reserve|пауэлл\w*|powell)\b", "#ФРС", "^GSPC"),
    (r"\b(nvidia|нвидиа|nvda|ии|ai)\b", "#ИИ", "NVDA"),
]

POSITIVE_WORDS = [
    "рост", "вырос", "подорож", "рекорд", "прибыл", "одобр", "снижен", "дивиденд",
    "укреп", "покуп", "инвестиц", "успех", "поддерж", "ралли", "оптимизм",
    "surge", "rally", "gain", "bull", "soar", "jump", "profit", "record", "approve", "growth", "rise", "boost"
]

NEGATIVE_WORDS = [
    "паден", "упал", "обвал", "снизил", "санкц", "убыт", "дефолт", "повышен",
    "кризис", "штраф", "запрет", "риск", "угроз", "ослаб", "давлен",
    "crash", "drop", "ban", "bear", "loss", "fall", "plunge", "risk", "crisis", "fine", "slump", "fear"
]


def init_tags_table():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id INTEGER,
            tag TEXT,
            sentiment REAL,
            ticker TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def calculate_sentiment(text):
    text_lower = text.lower()
    score = 0.0
    for word in POSITIVE_WORDS:
        if word in text_lower:
            score += 1.5
    for word in NEGATIVE_WORDS:
        if word in text_lower:
            score -= 1.5
    return max(-5.0, min(5.0, score))


def analyze_news():
    init_tags_table()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, market, title, summary FROM news WHERE analyzed = 0")
    rows = cursor.fetchall()

    now_str = datetime.now().isoformat()
    for news_id, market, title, summary in rows:
        full_text = f"{title} {summary}"
        sentiment = calculate_sentiment(full_text)
        matched = []
        for pattern, tag, ticker in TOPICS:
            if re.search(pattern, full_text, flags=re.IGNORECASE):
                matched.append((tag, ticker))

        if not matched:
            default_map = {"РФ": ("#ИндексМосбиржи", "IMOEX.ME"), "США": ("#РынокСША", "^GSPC"), "Крипта": ("#Крипторынок", "BTC-USD")}
            matched.append(default_map.get(market, ("#Макроэкономика", "NONE")))

        for tag, ticker in matched[:3]:
            cursor.execute("INSERT INTO tags (news_id, tag, sentiment, ticker, created_at) VALUES (?, ?, ?, ?, ?)",
                           (news_id, tag, sentiment, ticker, now_str))
        cursor.execute("UPDATE news SET analyzed = 1 WHERE id = ?", (news_id,))

    conn.commit()
    conn.close()
    return len(rows)
