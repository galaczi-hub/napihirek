#!/usr/bin/env python3
"""
Europai Hirlap – Napi automatikus küldő
Javított 2026.03 verzió: NewsAPI [Removed] kezelés + Groq rugalmasabb JSON
"""
import os
import json
import re
import smtplib
import datetime
import requests
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# KONFIGURÁCIÓ (titkosítva GitHub Secrets-ben)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS = {"econ": "📈", "eu": "🇪🇺", "war": "⚔️", "spain": "🇪🇸"}
CAT_COLORS = {"econ": "#1a4a6b", "eu": "#2d6a4f", "war": "#7b2d2d", "spain": "#8B0000"}

def fetch_articles(query, language="en", page_size=15):
    """Lekérdezés – több cikk, lazább szűrő"""
    today = datetime.date.today().isoformat()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": today,
        "to": today,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for a in data.get("articles", []):
            title = (a.get("title") or "").strip()
            desc = (a.get("description") or "").strip()
            source = a.get("source", {}).get("name", "Ismeretlen")
            url_link = a.get("url", "#")

            # Ha title "[Removed]" vagy üres → description-ből cím, ha van
            if "[Removed]" in title or not title:
                if desc and len(desc) > 30:
                    title = desc[:100] + "..." if len(desc) > 100 else desc
                elif url_link != "#":
                    title = "Cikk: " + source
                else:
                    continue

            if title:  # csak ha van valami cím
                results.append({"title": title, "desc": desc[:300], "source": source, "url": url_link})

        print(f"[{query}] Letöltve {len(results)} használható cikk (nyelv: {language})")
        return results
    except Exception as e:
        print(f"NewsAPI hiba ({query}): {e}")
        return []

def fetch_all_news():
    print("NewsAPI hírek letöltése...")
    return {
        "econ": fetch_articles("Europe economy OR stock market OR ECB OR inflation OR eurozone finance OR EU GDP", page_size=15),
        "eu": fetch_articles("European Union OR EU politics OR Brussels OR Ursula von der Leyen OR EU Commission OR EU summit", page_size=15),
        "war": fetch_articles("Ukraine war OR Russia Ukraine OR Gaza OR Israel Hamas OR Middle East conflict", page_size=15),
        "spain": fetch_articles("España OR Spain politics OR Pedro Sánchez OR PP OR Vox OR Spanish economy", language="es", page_size=15),
    }

def summarize_with_groq(articles, category_name, date_str):
    if not articles:
        return [{"num": "01", "title": f"Ma nincs kiemelt hír – {category_name}", "body": "A nap folyamán nem érkezett elegendő releváns friss hír ehhez a témához. Holnap többet tudunk mutatni!", "source": "NewsAPI"}]

    articles_text = "\n".join([f"- {a['title']} | {a['desc']} | Forrás: {a['source']}" for a in articles])

    prompt = f"""Mai hírek alapján készíts **legfeljebb 5**, de **legalább 2-5** releváns magyar hírösszefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek (használj csak ezeket, ne találj ki!):
{articles_text}

Szabályok:
- Legfeljebb 5 tétel (ha kevesebb jó minőségű van, kevesebbet adj)
- Minden tétel: rövid, figyelemfelkeltő magyar cím + pontosan 2 mondatos összefoglaló magyarul + forrás neve
- Legyenek tényszerűek és érdekesek
- Válaszolj **KIZÁRÓLAG** valid JSON tömbbel, semmi bevezetővel vagy magyarázattal:
[{{"num":"01","title":"Magyar cím példa","body":"Első mondat. Második mondat.","source":"Reuters"}}]
Csak a JSON tömböt írd ki!"""

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.35,
    }

    for attempt in range(5):
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=80)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

            # Erősebb clean: eltávolítunk minden nem-JSON részt
            text = re.sub(r'^[^[]*\[', '[', text)  # elejéről mindent vágunk az első [ -ig
            text = re.sub(r'\][^]]*$', ']', text)  # végéről mindent vágunk az utolsó ] után
            text = re.sub(r'```json|```', '', text).strip()

            result = json.loads(text)
            print(f"Groq OK: {len(result)} elem '{category_name}' kategóriában")
            return result[:5]

        except json.JSONDecodeError as je:
            print(f"Groq JSON parse hiba ({category_name}): {je} | Raw: {text[:400]}")
        except Exception as e:
            print(f"Groq hívás hiba ({attempt+1}/5) [{category_name}]: {e}")

        if attempt < 4:
            import time
            time.sleep(15 * (attempt + 1))  # backoff

    # Ultimate fallback
    return [{"num": "01", "title": f"Összefoglaló hiba – {category_name}", "body": "Technikai probléma miatt nem sikerült feldolgozni a híreket. Ellenőrizzük az API kulcsokat és a kapcsolatot.", "source": "Rendszer"}]

# get_news, build_html, send_email – kicsit módosítva a fallback miatt (korábbi üzenetben már benne voltak a fallback-ek)
# ... (a get_news, build_html és send_email részeket hagyd úgy, ahogy az előző javított verzióban voltak – azok már kezelik az üres listát)

def run():
    today = datetime.date.today()
    days = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    months = ["január", "február", "március", "április", "május", "június", "július", "augusztus", "szeptember", "október", "november", "december"]
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    print(f"Indítás: {date_str}")
    news_data = get_news(date_str)
    html_email = build_html(news_data)
    send_email(html_email, date_str)

if __name__ == "__main__":
    run()
