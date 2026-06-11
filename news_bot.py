import os
import feedparser
import requests
from datetime import datetime, timedelta

# ─── НАСТРОЙКИ ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# ─── RSS-ЛЕНТЫ ПО ТЕМАМ ───────────────────────────────────────────────────────
RSS_FEEDS = {
    "💊 Фарма и аптеки": [
        "https://tengrinews.kz/rss/",
        "https://informburo.kz/rss",
        "https://kapital.kz/feed/",
        "https://forbes.kz/feed/",
        "https://remedium.ru/rss/news/",
        "https://pharmvestnik.ru/rss/",
    ],
    "🧸 Ритейл": [
        "https://www.retail.ru/rss/news.xml",
        "https://retailer.ru/feed/",
    ],
    "📈 Фондовый рынок и экономика": [
        "https://smart-lab.ru/rss.php",
        "https://www.rbc.ru/v10/finance/rss.rss",
        "https://vc.ru/finance/rss",
    ],
    "🌍 Казахстан и мир": [
        "https://tengrinews.kz/rss/",
        "https://informburo.kz/rss",
    ],
}

# ─── СБОР НОВОСТЕЙ ────────────────────────────────────────────────────────────
def fetch_news(feeds_dict, hours_back=24):
    cutoff = datetime.now() - timedelta(hours=hours_back)
    all_news = {}

    for topic, urls in feeds_dict.items():
        articles = []
        for url in urls:
            try:
                feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in feed.entries[:10]:
                    pub_date = None
                    for date_field in ["published_parsed", "updated_parsed"]:
                        if hasattr(entry, date_field) and getattr(entry, date_field):
                            pub_date = datetime(*getattr(entry, date_field)[:6])
                            break

                    if pub_date is None or pub_date >= cutoff:
                        articles.append({
                            "title": entry.get("title", "Без заголовка"),
                            "summary": entry.get("summary", entry.get("description", ""))[:500],
                            "link": entry.get("link", ""),
                            "date": pub_date.strftime("%d.%m %H:%M") if pub_date else "—",
                        })
            except Exception as e:
                print(f"Ошибка при загрузке {url}: {e}")

        if articles:
            all_news[topic] = articles[:15]

    return all_news


# ─── АНАЛИЗ ЧЕРЕЗ CLAUDE ──────────────────────────────────────────────────────
def analyze_with_claude(news_dict):
    news_text = ""
    for topic, articles in news_dict.items():
        news_text += f"\n\n=== {topic} ===\n"
        for i, art in enumerate(articles, 1):
            news_text += f"\n{i}. [{art['date']}] {art['title']}\n{art['summary']}\nURL: {art['link']}\n"

    prompt = f"""Ты — аналитик для финансового директора двух розничных сетей в Казахстане.
Приоритет — новости из Казахстана и события которые напрямую влияют на казахстанский рынок. Украинские и российские внутренние новости не релевантны если не касаются Казахстана.

1. Europharma — сеть из 180 аптек (лекарства и парафармацевтика)
2. Marwin — сеть из 35 магазинов (игрушки, книги, канцелярия, видеоигры, приставки)

Вот новости за последние 24 часа:
{news_text}

Твоя задача:
1. Отбери 3–5 самых важных и релевантных новостей для этого CFO
2. Для каждой напиши:
   - Краткое резюме (2–3 предложения на русском)
   - Почему это важно для его бизнеса (1 предложение)
   - Ссылку на источник

Формат — строго Telegram Markdown:
*[Тема]* — Заголовок
📌 Суть: ...
💼 Для бизнеса: ...
🔗 [Читать](<ссылка>)

Пиши только по-русски. Начни сразу с новостей, без вступления."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ─── ОТПРАВКА В TELEGRAM ──────────────────────────────────────────────────────
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    today = datetime.now().strftime("%d.%m.%Y")
    header = f"📰 *Утренний дайджест — {today}*\n_Europharma & Marwin_\n\n"
    full_text = header + text

    max_len = 4000
    chunks = [full_text[i:i+max_len] for i in range(0, len(full_text), max_len)]

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload)
        if not resp.ok:
            print(f"Ошибка отправки в Telegram: {resp.text}")
            payload["parse_mode"] = ""
            requests.post(url, json=payload)


# ─── ГЛАВНАЯ ФУНКЦИЯ ──────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Запуск бота...")

    print("Собираю новости...")
    news = fetch_news(RSS_FEEDS, hours_back=24)

    if not news:
        send_to_telegram("⚠️ Сегодня не удалось загрузить новости. Проверьте RSS-ленты.")
        return

    total = sum(len(v) for v in news.values())
    print(f"Найдено {total} статей. Отправляю в Claude...")

    digest = analyze_with_claude(news)

    print("Отправляю в Telegram...")
    send_to_telegram(digest)

    print("Готово!")


if __name__ == "__main__":
    main()


