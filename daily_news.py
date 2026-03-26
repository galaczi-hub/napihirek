def fetch_google_news(query, max_results=10, hl="hu", gl="HU"):
    """Google News RSS lekérése + erős debug"""
    encoded = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid=HU:hu"
    
    print(f"→ Lekérés: {query}")
    print(f"   URL: {url}")
    
    try:
        feed = feedparser.parse(url)
        print(f"   Feed status: {feed.get('status', 'N/A')} | Bozo: {feed.get('bozo', False)}")
        
        articles = []
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:250].strip()
            if title and title != "" and "[Removed]" not in title:
                articles.append({
                    "title": title,
                    "desc": summary or "Nincs leírás",
                    "source": "Google News",
                    "link": entry.get("link", "")
                })
        
        print(f"   Talált cikkek: {len(articles)} db")
        if len(articles) == 0 and len(feed.entries) > 0:
            print(f"   Figyelem: feed.entries = {len(feed.entries)} db, de egyik sem volt érvényes cím!")
            print(f"   Első entry példa: {feed.entries[0].get('title', 'Nincs title')}")
        
        return articles
    except Exception as e:
        print(f"   Hiba a lekérés közben: {e}")
        return []


def fetch_all_news():
    print("Google News RSS lekérése indul...\n")
    
    queries = {
        "econ":  "gazdaság OR infláció OR ECB OR EKB OR kamat OR tőzsde OR eurozone",
        "eu":    "\"Európai Unió\" OR \"Ursula von der Leyen\" OR Brüsszel OR \"EU Bizottság\"",
        "war":   "Ukrajna háború OR Putyin OR Zelenszkij OR \"orosz-ukrán\"",
        "spain": "Spanyolország OR Sánchez OR Madrid OR PSOE"
    }
    
    results = {}
    for key, q in queries.items():
        results[key] = fetch_google_news(q, max_results=12)
        time.sleep(3)   # Google terhelés csökkentése
    
    return results


def get_news(date_str):
    raw = fetch_all_news()
    
    total_articles = sum(len(arts) for arts in raw.values())
    print(f"\nÖsszesen talált cikkek minden kategóriában: {total_articles} db\n")
    
    if total_articles == 0:
        print("FIGYELMEZTETÉS: Egyetlen cikk sem érkezett! Az email küldés ki lesz hagyva.")
    
    cats = [
        ("econ",  "Gazdaság & Tőzsdés Hírek"),
        ("eu",    "EU & Európai Politika"),
        ("war",   "Háborús és Geopolitikai Hírek"),
        ("spain", "Spanyol Hírek")
    ]
    
    categories = []
    for idx, (cid, ctitle) in enumerate(cats):
        print(f"Feldolgozás: {ctitle}... ({len(raw[cid])} nyers cikk)")
        if idx > 0:
            time.sleep(10)
        
        news_items = summarize_with_groq(raw[cid], ctitle, date_str)
        print(f"   Groq visszaadott: {len(news_items)} összefoglalót")
        
        for i, item in enumerate(news_items):
            item["num"] = str(i+1).zfill(2)
        
        categories.append({"id": cid, "title": ctitle, "news": news_items})
    
    return {"date": date_str, "categories": categories}


def run():
    today  = datetime.date.today()
    days   = ["hétfő","kedd","szerda","csütörtök","péntek","szombat","vasárnap"]
    months = ["január","február","március","április","május","június","július","augusztus","szeptember","október","november","december"]
    
    date_str = f"{today.year}. {months[today.month-1]} {today.day}., {days[today.weekday()]}"
    
    print(f"Európai Hírlap napi futtatás indul... ({date_str})\n")
    
    news_data = get_news(date_str)
    
    # Extra ellenőrzés
    total_news = sum(len(cat.get("news", [])) for cat in news_data["categories"])
    print(f"\nVégső összesített hírek száma: {total_news} db")
    
    if total_news >= 3:        # legalább 3 összefoglaló kell az email küldéshez
        html_email = build_html(news_data)
        send_email(html_email, date_str)
    else:
        print("Nincs elég hír az email küldéshez (minimum 3 összefoglaló kell).")
        print("Ellenőrizd a Groq API kulcsot és a quota-t is!")
