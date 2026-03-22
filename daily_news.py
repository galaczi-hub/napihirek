#!/usr/bin/env python3
"""
Európai Hírlap – Napi automatikus küldő
Javított 2026.03 verzió
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

# ────────────────────────────────────────────────
# KONFIGURÁCIÓ (GitHub Secrets-ben legyenek!)
# ────────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "").strip()
NEWS_API_KEY    = os.environ.get("NEWS_API_KEY", "").strip()
GMAIL_USER      = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS       = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS = {
    "econ":  "📈",
    "eu":    "🇪🇺",
    "war":   "⚔️",
    "spain": "🇪🇸"
}
CAT_COLORS = {
    "econ":  "#1a4a6b",
    "eu":    "#2d6a4f",
    "war":   "#7b2d2d",
    "spain": "#8B0000"
}

CATEGORIES = {
    "econ":  "economy EU OR eurozone OR inflation OR ECB",
    "eu":    "European Union OR EU Commission OR Ursula von der Leyen OR Brussels",
    "war":   "Ukraine war OR Russia Ukraine OR Putin OR Zelenskyy",
    "spain": "Spain OR Sánchez OR Madrid OR PSOE"
}

# ────────────────────────────────────────────────
def fetch_articles(query, language="en", page_size=12):
    if not NEWS_API_KEY:
        print("Hiányzik NEWS_API_KEY → üres lista")
        return []

    today = datetime.date.today().isoformat()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": today,
        "to": today,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "ok":
            print("NewsAPI hiba:", data.get("message", "ismeretlen"))
            return []

        articles = data.get("articles", [])
        print(f"[{query}] talált cikkek: {len(articles)} db")

        # Egyszerű szűrés / tisztítás
        cleaned = []
        seen_urls = set()
        for art in articles:
            url = art.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = (art.get("title") or "").strip()
            desc = (art.get("description") or art.get("content") or "").strip()

            if len(title) < 8 or "Removed" in title:
                continue

            cleaned.append({
                "title": title,
                "url": url,
                "desc": desc[:180] + "..." if len(desc) > 180 else desc,
                "source": art.get("source", {}).get("name", "–")
            })

        return cleaned[:page_size]  # ne vigyük túlzásba

    except Exception as e:
        print("Hiba a NewsAPI lekérésnél:", str(e))
        traceback.print_exc()
        return []


# ────────────────────────────────────────────────
def send_email(categorized_news):
    if not GMAIL_USER or not GMAIL_APP_PASS:
        print("Hiányzik GMAIL_USER vagy GMAIL_APP_PASS → nem küldök")
        return False

    if not any(categorized_news.values()):
        print("Nincs hír egyik kategóriában sem → nem küldök levelet")
        return False

    today_str = datetime.date.today().strftime("%Y. %m. %d. – %A")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Európai Hírlap – {today_str}"
    msg["From"]    = f"Európai Hírlap <{GMAIL_USER}>"
    msg["To"]      = ", ".join(TO_EMAILS)

    # ───── Plain text verzió ─────
    lines = [f"Európai Hírlap – {today_str}\n" + "="*50 + "\n"]

    for cat, query in CATEGORIES.items():
        articles = categorized_news.get(cat, [])
        if not articles:
            continue
        lines.append(f"\n{ICONS.get(cat, '•')} {cat.upper()} ({len(articles)} hír)")
        for a in articles:
            lines.append(f"• {a['title']}")
            lines.append(f"  {a['url'][:90]}")
            lines.append("")

    plain_body = "\n".join(lines)

    # ───── HTML verzió (szépebb) ─────
    html_lines = [
        "<html><head><meta charset='utf-8'></head><body style='font-family:Arial,sans-serif; color:#222;'>",
        f"<h2 style='color:#1a3c5e;'>Európai Hírlap – {today_str}</h2>",
        "<hr style='border:none; border-top:1px solid #ccc; margin:20px 0;'>"
    ]

    for cat, query in CATEGORIES.items():
        articles = categorized_news.get(cat, [])
        if not articles:
            continue

        color = CAT_COLORS.get(cat, "#444")
        html_lines.append(f"<h3 style='color:{color}; margin-top:1.8em;'>{ICONS.get(cat,'•')} {cat.upper()} ({len(articles)})</h3>")
        html_lines.append("<ul style='margin:0; padding-left:1.4em; line-height:1.5;'>")

        for a in articles:
            html_lines.append(
                f"<li style='margin-bottom:1.1em;'>"
                f"<strong><a href='{a['url']}' style='color:{color}; text-decoration:none;'>{a['title']}</a></strong>"
                f"<br><small style='color:#555;'>{a['source']} • {a['desc']}</small>"
                f"</li>"
            )

        html_lines.append("</ul>")

    html_lines.append("<br><hr><p style='color:#777; font-size:0.9em;'>"
                      "Ez egy automatikus napi hírlevél. Leiratkozás: válaszolj erre a levélre.</p>"
                      "</body></html>")

    html_body = "\n".join(html_lines)

    # Csatolás
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    # Küldés
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.send_message(msg)
        print("Email sikeresen elküldve")
        return True
    except Exception as e:
        print("EMAIL KÜLDÉSI HIBA:", str(e))
        traceback.print_exc()
        return False


# ────────────────────────────────────────────────
# FŐ PROGRAM
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Európai Hírlap napi futtatás indul...")

    categorized = {}

    for cat, query in CATEGORIES.items():
        print(f"\n→ Lekérés: {cat} ({query})")
        arts = fetch_articles(query, language="en", page_size=10)
        if arts:
            categorized[cat] = arts

    # Teszteléshez kiírjuk, mi gyűlt össze
    for cat, lst in categorized.items():
        print(f"{cat:6} → {len(lst)} db")

    # Küldés csak akkor, ha van valami
    if categorized:
        send_email(categorized)
    else:
        print("Nem volt hír ma → nem küldök levelet")
