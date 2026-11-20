import re
import sqlite3
from datetime import datetime

DB_NAME = "market_radar.db"

TOPICS = [
    (r"\b(биткоин\w*|bitcoin|btc)\b", "#Биткоин", "BTC-USD"),
    (r"\b(эфир\w*|ethereum|eth)\b", "#Эфириум", "ETH-USD"),
    (r"\b(солана|solana|sol)\b", "#Solana", "SOL-USD"),
    (r"\b(крипт\w*|crypto\w*|блокчейн\w*)\b", "#Крипторынок", "BTC-USD"),
    (r"\b(цб|центробанк\w*|набиуллин\w*|ключев\w+\s+ставк\w*)\b", "#СтавкаЦБ", "IMOEX.ME"),
    (r"\b(сбер\w*|sber\w*)\b", "#Сбербанк", "SBER.ME"),
    (r"\b(газпром\w*|gazprom)\b", "#Газпром", "GAZP.ME"),
    (r"\b(лукойл\w*|lukoil)\b", "#Лукойл", "LKOH.ME"),
    (r"\b(роснефт\w*|rosneft)\b", "#Роснефть", "ROSN.ME"),
    (r"\b(яндекс\w*|yandex|ydex)\b", "#Яндекс", "YDEX.ME"),
    (r"\b(мосбирж\w*|moex)\b", "#Мосбиржа", "MOEX.ME"),
    (r"\b(рубл\w*|доллар\w*|юан\w*|валют\w*)\b", "#ВалютаРФ", "USDRUB=X"),
    (r"\b(санкци\w*|sanctions)\b", "#Санкции", "IMOEX.ME"),
    (r"\b(дивиденд\w*|dividends?)\b", "#Дивиденды", "IMOEX.ME"),
    (r"\b(фрс|fed|federal\s+reserve|пауэлл\w*|powell)\b", "#ФРС", "^GSPC"),
    (r"\b(инфляци\w*|inflation|cpi)\b", "#Инфляция", "^GSPC"),
    (r"\b(nvidia|нвидиа|nvda)\b", "#NVIDIA", "NVDA"),
    (r"\b(ии|искусственн\w+\s+интеллект\w*|\bai\b|openai)\b", "#ИИ", "NVDA"),
    (r"\b(apple|эппл|aapl)\b", "#Apple", "AAPL"),
    (r"\b(tesla|тесла|tsla|маск\w*)\b", "#Tesla", "TSLA"),
    (r"\b(нефт\w*|brent|wti|опек|opec)\b", "#Нефть", "BZ=F"),
    (r"\b(золот\w*|gold)\b", "#Золото", "GC=F"),
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
            default_map = {"РФ": ("#РынокРФ", "IMOEX.ME"), "США": ("#РынокСША", "^GSPC"), "Крипта": ("#Крипторынок", "BTC-USD")}
            matched.append(default_map.get(market, ("#Макроэкономика", "NONE")))

        for tag, ticker in matched[:3]:
            cursor.execute("INSERT INTO tags (news_id, tag, sentiment, ticker, created_at) VALUES (?, ?, ?, ?, ?)",
                           (news_id, tag, sentiment, ticker, now_str))
        cursor.execute("UPDATE news SET analyzed = 1 WHERE id = ?", (news_id,))

    conn.commit()
    conn.close()
    return len(rows)
