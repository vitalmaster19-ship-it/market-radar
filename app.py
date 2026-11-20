import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from analyzer import analyze_news, init_tags_table
from collector import collect_news, init_db

st.set_page_config(page_title="Market Radar AI", layout="wide")
DB_NAME = "market_radar.db"

init_db()
init_tags_table()

# Сопоставление тикеров с рабочими биржевыми инструментами для графика
CHART_TICKER_MAP = {
    "IMOEX.ME": ("USDRUB=X", "Курс USD/RUB (индикатор рынка РФ)"),
    "SBER.ME": ("USDRUB=X", "Курс USD/RUB (индикатор фин. сектора РФ)"),
    "GAZP.ME": ("NG=F", "Фьючерс на природный газ (индикатор Газпрома)"),
    "LKOH.ME": ("BZ=F", "Нефть Brent (главный драйвер Лукойла)"),
    "ROSN.ME": ("BZ=F", "Нефть Brent (главный драйвер Роснефти)"),
    "YDEX.ME": ("NASDAQ:NDX", "Индекс NASDAQ (бенчмарк техсектора)"),
}


def load_candles(ticker_symbol):
    """Загружает дневные свечи за последний месяц через Yahoo Finance."""
    if ticker_symbol in CHART_TICKER_MAP:
        yf_symbol, title = CHART_TICKER_MAP[ticker_symbol]
    else:
        yf_symbol, title = ticker_symbol, f"График цены {ticker_symbol}"

    try:
        hist = yf.Ticker(yf_symbol).history(period="1mo", interval="1d")
        return hist, title
    except Exception:
        return pd.DataFrame(), title


st.title("📡 Market Radar: Анализ инфошума и влияния на портфель")

with st.sidebar:
    st.header("⚙️ Управление данными")
    if st.button("🔄 Собрать и проанализировать новости", use_container_width=True):
        with st.spinner("Собираю новости РФ, США и Крипты..."):
            added, logs = collect_news()
            processed = analyze_news()
        st.success(f"Новых: {added} | Обработано: {processed}")
        for log in logs:
            st.caption(log)

    if st.button("🗑️ Очистить базу и собрать заново", use_container_width=True):
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
        init_db()
        init_tags_table()
        st.rerun()

    st.divider()
    st.header("💼 Мой портфель")
    st.caption("Укажите тикеры через запятую (например: BTC-USD, NVDA, AAPL, SBER.ME, GAZP.ME, LKOH.ME)")
    default_portfolio = "BTC-USD, ETH-USD, NVDA, AAPL, SBER.ME, GAZP.ME, LKOH.ME"
    user_tickers_raw = st.text_area("Ваши активы:", value=default_portfolio, height=100)
    portfolio_tickers = [t.strip().upper() for t in user_tickers_raw.split(",") if t.strip()]

conn = sqlite3.connect(DB_NAME)
df_tags = pd.read_sql_query("""
    SELECT t.tag, t.sentiment, t.ticker, n.market, n.title, n.source, n.link, n.published_at
    FROM tags t
    JOIN news n ON t.news_id = n.id
""", conn)
conn.close()

if df_tags.empty:
    st.info("База пока пуста. Нажмите кнопку **«🔄 Собрать и проанализировать новости»** в меню слева!")
    st.stop()

markets = st.multiselect("Фильтр по рынкам:", options=df_tags["market"].unique(), default=list(df_tags["market"].unique()))
df_filtered = df_tags[df_tags["market"].isin(markets)]

tag_stats = df_filtered.groupby(["tag", "ticker", "market"]).agg(
    mentions=("tag", "count"),
    avg_sentiment=("sentiment", "mean")
).reset_index().sort_values(by="mentions", ascending=False)

# БЛОК 1: Влияние на портфель
st.subheader("🎯 Влияние информационного шума на ваш портфель")
portfolio_impact = tag_stats[tag_stats["ticker"].isin(portfolio_tickers)]

if portfolio_impact.empty:
    st.write("По вашим тикерам пока нет громких новостей в текущей выборке.")
else:
    cols = st.columns(min(len(portfolio_impact), 4))
    for idx, (_, row) in enumerate(portfolio_impact.head(4).iterrows()):
        sentiment_val = round(row["avg_sentiment"], 2)
        delta_label = "Позитивный фон" if sentiment_val > 0.3 else ("Негативный фон" if sentiment_val < -0.3 else "Нейтрально")
        cols[idx].metric(
            label=f"{row['tag']} ({row['ticker']})",
            value=f"{row['mentions']} упом.",
            delta=f"{sentiment_val:+.2f} ({delta_label})"
        )

st.divider()

# БЛОК 2: Пузырьковое облако тегов и Топ тем
col1, col2 = st.columns([1.4, 1])

with col1:
    st.subheader("🫧 Облако популярных тегов (размер = шум, цвет = сентимент)")
    fig_bubble = px.scatter(
        tag_stats.head(25),
        x="tag",
        y="mentions",
        size="mentions",
        color="avg_sentiment",
        color_continuous_scale=["#ff4b4b", "#ffd166", "#06d6a0"],
        range_color=[-3, 3],
        hover_data=["ticker", "market", "avg_sentiment"],
        size_max=55
    )
    fig_bubble.update_layout(xaxis_title="", yaxis_title="Количество упоминаний", height=420)
    st.plotly_chart(fig_bubble, use_container_width=True)

with col2:
    st.subheader("🔥 Топ-10 набирающих шум тем")
    st.dataframe(
        tag_stats[["tag", "ticker", "mentions", "avg_sentiment"]].head(10).rename(
            columns={"tag": "Тег", "ticker": "Тикер", "mentions": "Упом.", "avg_sentiment": "Сентимент"}
        ),
        use_container_width=True,
        hide_index=True
    )

st.divider()

# БЛОК 3: Влияние выбранного тега на график цены
st.subheader("📈 Связь выбранного тега с движением рынка")
selected_tag = st.selectbox("Выберите тег для проверки реакции цены:", options=tag_stats["tag"].unique())
ticker_symbol = tag_stats.loc[tag_stats["tag"] == selected_tag, "ticker"].values[0]

c1, c2 = st.columns([1.3, 1])
with c1:
    if ticker_symbol and ticker_symbol != "NONE":
        hist, chart_title = load_candles(ticker_symbol)
        if not hist.empty:
            fig_price = go.Figure(data=[go.Candlestick(
                x=hist.index, open=hist["Open"], high=hist["High"], low=hist["Low"], close=hist["Close"]
            )])
            fig_price.update_layout(title=f"{chart_title} (1 мес.)", height=360, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig_price, use_container_width=True)
        else:
            st.warning(f"Не удалось загрузить свечи для {ticker_symbol}.")
    else:
        st.info("Для этого общего тега не привязан конкретный биржевой тикер.")

with c2:
    st.markdown(f"**Последние новости и посты по тегу {selected_tag}:**")
    tag_news = df_filtered[df_filtered["tag"] == selected_tag].drop_duplicates(subset=["title"]).head(7)
    for _, n_row in tag_news.iterrows():
        icon = "🟢" if n_row["sentiment"] > 0.3 else ("🔴" if n_row["sentiment"] < -0.3 else "⚪")
        st.markdown(f"{icon} [{n_row['title']}]({n_row['link']}) *({n_row['source']})*")
