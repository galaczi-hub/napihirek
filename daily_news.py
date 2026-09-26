#!/usr/bin/env python3
"""
Europai Hirlap – Napi automatikus kuldo
NewsAPI (valos hirek) + Groq (magyar forditas + cyber prioritas) - INGYENES

Javitott verzio:
- Jobb, specifikusabb query-k + trusted domains
- Tech = kizárólag cybersecurity (ransomware, malware, breach, zero-day, WordPress/sebezhetőség)
- Forrás-diverzitás kényszer (több forrásból)
- Tech híreknél prioritás: kritikus / fontos / érdekes
- Erősebb fallback + retry
"""

import os
import json
import re
import smtplib
import datetime
import time
import requests
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# KONFIGURÁCIÓ
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
NEWS_API_KEY   = os.environ.get("NEWS_API_KEY", "").strip()
GMAIL_USER     = os.environ.get("GMAIL_USER", "galaczi.usa@gmail.com").strip()
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
TO_EMAILS      = ["galaczi.usa@gmail.com", "kata.gorcsi@gmail.com"]

ICONS = {
    "econ":  "📈",
    "eu":    "🇪🇺",
    "war":   "⚔️",
    "spain": "🇪🇸",
    "tech":  "🛡️",
}
CAT_COLORS = {
    "econ":  "#1a4a6b",
    "eu":    "#2d6a4f",
    "war":   "#7b2d2d",
    "spain": "#8B0000",
    "tech":  "#1a1a2e",
}

# Trusted domains a diverzitásért (NewsAPI domains param)
TRUSTED_DOMAINS = {
    "general": "reuters.com,bbc.co.uk,theguardian.com,apnews.com,bloomberg.com,ft.com,wsj.com,nytimes.com,cnn.com,aljazeera.com",
    "econ":    "reuters.com,bloomberg.com,ft.com,wsj.com,cnbc.com,marketwatch.com,economist.com",
    "eu":      "reuters.com,bbc.co.uk,theguardian.com,politico.eu,euronews.com,ft.com",
    "war":     "reuters.com,bbc.co.uk,apnews.com,aljazeera.com,theguardian.com,cnn.com",
    "spain":   "reuters.com,bbc.co.uk,theguardian.com,elpais.com,elmundo.es,apnews.com",
    "tech":    "bleepingcomputer.com,krebsonsecurity.com,theregister.com,darkreading.com,securityweek.com,thehackernews.com,zdnet.com,wired.com,techcrunch.com,reuters.com",
}


def fetch_articles(query, language="en", page_size=20, domains=None, days_back=1):
    """NewsAPI-tól cikkeket kér le, opcionális domains szűréssel."""
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=days_back)).isoformat()
    to_date = today.isoformat()

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "to": to_date,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": min(page_size, 100),
        "apiKey": NEWS_API_KEY,
    }
    if domains:
        params["domains"] = domains

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  NewsAPI hiba: {e}")
        return []

    results = []
    seen_titles = set()
    for a in data.get("articles", []):
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        source = (a.get("source") or {}).get("name") or "Ismeretlen"
        url_link = a.get("url") or ""

        if not title or "[Removed]" in title:
            continue
        # Egyszerű deduplikáció
        title_key = title.lower()[:80]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        results.append({
            "title": title,
            "desc": desc[:250],
            "source": source,
            "url": url_link,
        })
    return results


def diversify_sources(articles, max_items=12, max_per_source=3):
    """Forrás szerint kiegyensúlyozza a listát, hogy ne egy portál domináljon."""
    if not articles:
        return []

    by_source = defaultdict(list)
    for a in articles:
        by_source[a["source"]].append(a)

    # Round-robin jellegű kiválasztás
    selected = []
    sources = list(by_source.keys())
    idx = 0
    while len(selected) < max_items and sources:
        src = sources[idx % len(sources)]
        if by_source[src]:
            selected.append(by_source[src].pop(0))
            if len([s for s in selected if s["source"] == src]) >= max_per_source:
                sources = [s for s in sources if s != src]
                if not sources:
                    break
                idx = 0
                continue
        else:
            sources = [s for s in sources if s != src]
            if not sources:
                break
            idx = 0
            continue
        idx += 1

    return selected


def fetch_all_news():
    print("NewsAPI hírek letöltése...")

    # === GAZDASÁG ===
    econ = fetch_articles(
        query='("stock market" OR "European markets" OR ECB OR "interest rates" OR inflation OR "eurozone economy" OR "stock exchange")',
        page_size=25,
        domains=TRUSTED_DOMAINS["econ"],
        days_back=1,
    )
    if len(econ) < 6:
        econ += fetch_articles(
            query="European economy OR eurozone OR 'stock market' OR finance",
            page_size=15,
            days_back=2,
        )
    econ = diversify_sources(econ, max_items=12)
    print(f"  econ: {len(econ)} cikk (források: {len(set(a['source'] for a in econ))})")

    # === EU / POLITIKA ===
    eu = fetch_articles(
        query='("European Union" OR "EU Commission" OR Brussels OR "EU Parliament" OR "Ursula von der Leyen" OR "EU politics")',
        page_size=25,
        domains=TRUSTED_DOMAINS["eu"],
        days_back=1,
    )
    if len(eu) < 6:
        eu += fetch_articles(
            query="European Union OR EU politics OR Brussels",
            page_size=15,
            days_back=2,
        )
    eu = diversify_sources(eu, max_items=12)
    print(f"  eu: {len(eu)} cikk (források: {len(set(a['source'] for a in eu))})")

    # === HÁBORÚ / KONFLIKTUS ===
    war = fetch_articles(
        query='(Ukraine OR "Middle East" OR Gaza OR Israel OR Russia OR "armed conflict" OR war) AND (war OR conflict OR attack OR ceasefire OR invasion)',
        page_size=25,
        domains=TRUSTED_DOMAINS["war"],
        days_back=1,
    )
    if len(war) < 6:
        war += fetch_articles(
            query="Ukraine war OR Middle East conflict OR Gaza",
            page_size=15,
            days_back=2,
        )
    war = diversify_sources(war, max_items=12)
    print(f"  war: {len(war)} cikk (források: {len(set(a['source'] for a in war))})")

    # === SPANYOLORSZÁG ===
    spain = fetch_articles(
        query='(Spain OR Spanish OR Madrid OR Sánchez OR Catalonia) AND (politics OR economy OR government OR election OR crisis)',
        page_size=20,
        domains=TRUSTED_DOMAINS["spain"],
        days_back=1,
    )
    if len(spain) < 5:
        spain += fetch_articles(
            query="Spain politics OR Spain economy OR Sánchez",
            page_size=15,
            days_back=2,
        )
    spain = diversify_sources(spain, max_items=12)
    print(f"  spain: {len(spain)} cikk (források: {len(set(a['source'] for a in spain))})")

    # === CYBER / TECH (a legfontosabb javítás) ===
    # Kifejezetten támadások, sebezhetőségek, ransomware, malware, WordPress stb.
    cyber_query = (
        '(ransomware OR malware OR "data breach" OR "cyber attack" OR "cyberattack" OR '
        '"zero-day" OR "zero day" OR "0-day" OR "security vulnerability" OR exploit OR '
        'hacking OR "wordpress" OR "cms vulnerability" OR "supply chain attack" OR '
        '"critical vulnerability" OR "actively exploited" OR "CISA" OR "threat actor")'
    )
    tech = fetch_articles(
        query=cyber_query,
        page_size=30,
        domains=TRUSTED_DOMAINS["tech"],
        days_back=2,  # cyber hírekre 2 nap, mert ritkább a nagy találat
    )
    if len(tech) < 8:
        # Fallback: domain nélkül, szélesebb
        tech += fetch_articles(
            query=cyber_query,
            page_size=20,
            days_back=3,
        )
    if len(tech) < 5:
        # Utolsó esély: általánosabb security
        tech += fetch_articles(
            query='cybersecurity OR "information security" OR "data breach" OR ransomware',
            page_size=15,
            days_back=3,
        )
    tech = diversify_sources(tech, max_items=15, max_per_source=2)
    print(f"  tech/cyber: {len(tech)} cikk (források: {len(set(a['source'] for a in tech))})")

    return {
        "econ":  econ,
        "eu":    eu,
        "war":   war,
        "spain": spain,
        "tech":  tech,
    }


def summarize_with_groq(articles, category_id, category_name, date_str):
    """Groq lefordítja és összefoglalja magyarul. Tech esetén prioritást is ad."""
    if not articles:
        print(f"  Nincs cikk a(z) {category_name} kategóriához.")
        return []

    articles_text = "\n".join([
        f"- {a['title']} | {a['desc']} | Forrás: {a['source']}"
        for a in articles[:12]
    ])

    is_tech = category_id == "tech"

    if is_tech:
        prompt = f"""Az alábbi angol cybersecurity / informatikai biztonsági hírek alapján készíts pontosan 5 magyar hír-összefoglalót.
Dátum: {date_str}

Hírek:
{articles_text}

SZIGORÚ SZABÁLYOK:
1. Csak valódi biztonsági események, támadások, sebezhetőségek, ransomware, malware, adatvédelmi incidensek, zero-day-ek, aktívan kihasznált hibák, WordPress/CMS támadások, supply-chain támadások.
2. KERÜLD a sima AI-híreket, termékbemutatókat, általános tech-híreket, ha nincs biztonsági vonatkozásuk.
3. Pontosan 5 tétel.
4. Minden tételhez add meg a prioritást:
   - "kritikus" = aktív támadás, zero-day, masszív breach, kritikus sebezhetőség (CISA KEV, aktívan exploitált)
   - "fontos"  = jelentős ransomware, nagyobb adatvesztés, új malware kampány
   - "érdekes" = figyelemre méltó, de nem azonnali veszély
5. A legkritikusabbak kerüljenek előre (sorrend: kritikus → fontos → érdekes).
6. Válaszolj KIZÁRÓLAG valid JSON tömbként, semmi más szöveg:

[
  {{"num":"01","priority":"kritikus","title":"Magyar cím","body":"Két mondatos magyar összefoglaló.","source":"Forrás neve"}},
  ...
]

CSAK a JSON tömb, semmi magyarázat, semmi markdown."""
    else:
        prompt = f"""Az alábbi mai angol hírek alapján készíts pontosan 5 magyar hír-összefoglalót a "{category_name}" kategóriához.
Dátum: {date_str}

Hírek:
{articles_text}

Szabályok:
- Pontosan 5 tétel
- Minden tétel: rövid magyar cím + 2 mondatos magyar összefoglaló + forrás neve
- A legfontosabb, legfrissebb hírek kerüljenek előre
- Kerüld a ismétlődéseket
- Válaszolj KIZÁRÓLAG valid JSON tömbként:

[
  {{"num":"01","title":"Magyar cím","body":"Két mondatos összefoglaló magyarul.","source":"Reuters"}},
  ...
]

CSAK JSON tömb, semmi más."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-oss-120b",   # vagy "llama-3.3-70b-versatile" ha az stabilabb
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1800,
        "temperature": 0.25,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=90
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            print(f"  Groq válasz ({len(text)} kar): {text[:180]}...")

            clean = re.sub(r"```json|```", "", text).strip()
            start = clean.find("[")
            end = clean.rfind("]") + 1
            if start >= 0 and end > start:
                clean = clean[start:end]
            result = json.loads(clean)

            # Biztosítjuk a num mezőt
            for i, item in enumerate(result):
                item["num"] = str(i + 1).zfill(2)
                if is_tech and "priority" not in item:
                    item["priority"] = "érdekes"

            print(f"  JSON sikeresen parsed: {len(result)} elem")
            return result[:5]
        except Exception as e:
            print(f"  Groq hiba ({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(12)
    return []


def get_news(date_str):
    raw = fetch_all_news()
    cats = [
        ("econ",  "Gazdaság & Tőzsdei Hírek"),
        ("eu",    "EU & Európai Közösség"),
        ("war",   "Háborús & Konfliktus Hírek"),
        ("spain", "Spanyol Hírek"),
        ("tech",  "Cyberbiztonság & Tech"),
    ]
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"Feldolgozás: {ctitle}...")
        if idx > 0:
            time.sleep(7)  # Groq rate limit
        news_items = summarize_with_groq(raw[cid], cid, ctitle, date_str)
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    return {"date": date_str, "categories": categories}


def priority_badge(priority):
    """HTML badge a prioritáshoz."""
    colors = {
        "kritikus": ("#c0392b", "#fff"),
        "fontos":   ("#e67e22", "#fff"),
        "érdekes":  ("#2980b9", "#fff"),
    }
    bg, fg = colors.get(priority, ("#7f8c8d", "#fff"))
    return f'<span style="display:inline-block;background:{bg};color:{fg};font-size:10px;font-weight:700;padding:2px 7px;border-radius:3px;margin-right:6px;text-transform:uppercase;letter-spacing:0.5px">{priority}</span>'


def build_html(data):
    cats_html = ""
    for cat in data["categories"]:
        cid = cat["id"]
        color = CAT_COLORS.get(cid, "#333333")
        icon = ICONS.get(cid, "●")
        news_rows = ""
        is_tech = cid == "tech"

        for item in cat.get("news", []):
            priority_html = ""
            if is_tech and item.get("priority"):
                priority_html = priority_badge(item["priority"])

            news_rows += f"""
            <tr>
              <td style="width:28px;font-family:Georgia,serif;font-size:13px;color:{color};opacity:0.5;vertical-align:top;padding:12px 6px 12px 0">{item['num']}</td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e2d5;font-family:Georgia,serif;font-size:14px;line-height:1.65;color:#2a2015">
                {priority_html}<strong>{item['title']}</strong><br>
                {item['body']}
                <span style="display:block;font-size:11px;color:#999;font-style:italic;margin-top:4px">Forrás: {item['source']}</span>
              </td>
            </tr>"""

        header_extra = "5 HÍR"
        if is_tech:
            header_extra = "CYBER PRIORITÁS"

        cats_html += f"""
        <tr><td colspan="2" style="padding:0">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="background:{color};padding:16px 32px;font-family:Georgia,serif">
              <span style="font-size:22px">{icon}</span>
              <span style="font-size:20px;font-weight:700;color:#fff;margin-left:12px">{cat['title']}</span>
              <span style="float:right;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:2px;padding-top:4px">{header_extra}</span>
            </td></tr>
            <tr><td style="padding:4px 32px 16px">
              <table width="100%" cellpadding="0" cellspacing="0">{news_rows}</table>
            </td></tr>
          </table>
        </td></tr>
        <tr><td colspan="2" style="height:4px;background:repeating-linear-gradient(90deg,#e8e2d5 0,#e8e2d5 6px,transparent 6px,transparent 10px)"></td></tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#2a2015">
<table width="680" cellpadding="0" cellspacing="0" align="center" style="background:#f5f0e8;margin:20px auto">
  <tr><td colspan="2" style="background:#1a1209;padding:28px 40px 20px;text-align:center;border-bottom:4px solid #b8922a">
    <div style="font-size:38px;font-weight:900;color:#f5f0e8">Europai<span style="color:#b8922a"> Hirlap</span></div>
    <div style="color:#8a7d68;font-size:10px;letter-spacing:4px;text-transform:uppercase;margin-top:8px">Minden reggel · Minden ami számít</div>
    <div style="color:#c5b99a;font-size:13px;font-style:italic;border-top:1px solid #3d3428;padding-top:10px;margin-top:10px">{data['date']} &nbsp;·&nbsp; Reggeli kiadás &nbsp;·&nbsp; 09:00 CET</div>
  </td></tr>
  <tr><td colspan="2" style="background:#b8922a;padding:8px 40px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#1a1209;text-align:center;font-weight:700">
    5 KATEGÓRIA · CYBER PRIORITÁS · DIVERZ FORRÁSOK
  </td></tr>
  {cats_html}
  <tr><td colspan="2" style="background:#1a1209;padding:18px 40px;text-align:center">
    <p style="color:#5a5040;font-size:10px;line-height:1.9;margin:0">
      <span style="color:#b8922a;font-weight:700">Europai Hirlap</span> · NewsAPI + Groq AI<br>
      Minden nap 09:00 CET · galaczi.usa@gmail.com<br>
      <span style="color:#8a7d68">Tech prioritás: kritikus (aktív támadás/zero-day) → fontos → érdekes</span>
    </p>
  </td></tr>
</table>
</body></html>"""


def send_email(html_content, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Europai Hirlap – {date_str}"
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(TO_EMAILS)
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, TO_EMAILS, msg.as_string())
    print(f"Email elküldve: {', '.join(TO_EMAILS)}")


def run():
    today = datetime.date.today()
    days = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    months = ["január", "február", "március", "április", "május", "június",
              "július", "augusztus", "szeptember", "október", "november", "december"]
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    print(f"Hírek összegyűjtése: {date_str}")
    news_data = get_news(date_str)
    html_email = build_html(news_data)
    send_email(html_email, date_str)


if __name__ == "__main__":
    run()
