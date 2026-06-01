import os
import feedparser
import requests
from datetime import datetime, timedelta

# ─── НАСТРОЙКИ ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# ─── RSS-ЛЕНТЫ ПО ТЕМАМ ───────────────────────────────────────────────────────
RSS_FEEDS = {
    "💊 Фарма и аптеки": [
        "https://pharmvestnik.ru/rss/",
        "https://www.apteka.ua/rss/news.xml",
        "https://remedium.ru/rss/news/",
        "https://www.gxpnews.ru/feed/",
    ],
    "🧸 Ритейл игрушек и книг": [
        "https://retailer.ru/feed/",
        "https://www.kommersant.ru/RSS/section-retail.xml",
        "https://iz.ru/xml/rss/retail.xml",
    ],
    "📈 Фондовый рынок": [
        "https://smart-lab.ru/rss.php",
        "https://www.rbc.ru/v10/finance/rss.rss",
        "https://investing.com/rss/news_25.rss",
        "https://vc.ru/finance/rss",
    ],
    "🏪 Ритейл в целом": [
        "https://www.retail.ru/rss/news.xml",
        "https://oborot.ru/feed/",
    ],
}

# ─── СБОР НОВОСТЕЙ ────────────────────────────────────────────────────────────
def fetch_news(feeds_dict, hours_back=24):
    """Собирает новости за последние N часов из RSS-лент."""
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
            all_news[topic] = articles[:20]

    return all_news


# ─── АНАЛИЗ ЧЕРЕЗ GEMINI ──────────────────────────────────────────────────────
def analyze_with_gemini(news_dict):
    """Gemini отбирает важные новости и пишет резюме на русском."""

    news_text = ""
    for topic, articles in news_dict.items():
        news_text += f"\n\n=== {topic} ===\n"
        for i, art in enumerate(articles, 1):
            news_text += f"\n{i}. [{art['date']}] {art['title']}\n{art['summary']}\nURL: {art['link']}\n"

    prompt = f"""Ты — аналитик для финансового директора двух розничных сетей в Казахстане:
1. Europharma — сеть из 180 аптек (лекарства и парафармацевтика)
2. Marwin — сеть из 35 магазинов (игрушки, книги, канцелярия, видеоигры, приставки)

Вот новости за последние 24 часа по нескольким темам:
{news_text}

Твоя задача:
1. Из всего списка отбери 3–5 самых ВАЖНЫХ и РЕЛЕВАНТНЫХ новостей для этого CFO
2. Для каждой выбранной новости напиши:
   - Краткое резюме (2–3 предложения на русском, своими словами)
   - Почему это важно для его бизнеса (1 предложение)
   - Ссылку на источник

Формат ответа — строго Telegram Markdown:
*[Тема]* — Заголовок
📌 Суть: ...
💼 Для бизнеса: ...
🔗 [Читать](<ссылка>)

Пиши только по-русски. Не повторяй новости с одинаковым смыслом. Начни сразу с новостей, без вступления."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


# ─── ОТПРАВКА В TELEGRAM ──────────────────────────────────────────────────────
def send_to_telegram(text):
    """Отправляет сообщение в Telegram, разбивая на части если нужно."""
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
    print(f"Найдено {total} статей. Отправляю в Gemini...")

    digest = analyze_with_gemini(news)

    print("Отправляю в Telegram...")
    send_to_telegram(digest)

    print("Готово!")


if __name__ == "__main__":
    main()


