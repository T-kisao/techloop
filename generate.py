"""
TechLoop — Daily News Aggregator
---------------------------------
Fetches RSS feeds, generates AI summaries via Groq (free tier),
and rebuilds index.html ready for Vercel deployment.

Usage:
    python generate.py

Requirements:
    pip install feedparser requests groq python-dateutil

Environment variables:
    GROQ_API_KEY  — your Groq API key (console.groq.com)
"""

import os
import json
import re
import hashlib
import feedparser
import requests
from groq import Groq
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL     = "llama-3.1-8b-instant"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

MAX_OG_IMAGES        = 15
MAX_PER_CATEGORY     = 6
MAX_AI_SUMMARIES     = 10
FEATURED_COUNT       = 3
SEEN_ARTICLES_TTL_DAYS = 7
SEEN_ARTICLES_FILE   = Path("seen_articles.json")

# Phrases that indicate the AI could not access/summarise the article
_INACCESSIBLE_PHRASES = [
    "i'm unable to access",
    "i am unable to access",
    "i cannot access",
    "i can't access",
    "not provided",
    "could not access",
    "no content provided",
    "unable to summarize",
    "unable to summarise",
    "i would be happy to summarize if you",
    "please provide the article",
    "i don't have access",
]

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities from a string."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s{2,}", " ", text).strip()

def _is_inaccessible(summary: str) -> bool:
    """Return True if the AI summary indicates the article could not be accessed."""
    low = summary.lower()
    return any(phrase in low for phrase in _INACCESSIBLE_PHRASES)

def _title_words(title: str) -> set:
    """Return significant words from a title for fuzzy comparison."""
    stopwords = {"a","an","the","is","in","of","to","and","or","for","on",
                 "with","at","by","it","its","this","that","are","was","be",
                 "as","not","but","from","has","have","will","what","how",
                 "who","why","when","says","say","new","just","about","up",
                 "after","more","than","could","would","should"}
    words = re.findall(r"[a-z0-9']+", title.lower())
    return {w for w in words if w not in stopwords and len(w) > 2}

def _is_duplicate_title(title: str, seen_titles_words: list, threshold: float = 0.35) -> bool:
    """Return True if title shares >= threshold of the shorter title's words with any seen title.
    Using the shorter title as denominator catches same-story coverage across different sources."""
    words = _title_words(title)
    if not words:
        return False
    for seen_words in seen_titles_words:
        if not seen_words:
            continue
        overlap = len(words & seen_words) / min(len(words), len(seen_words))
        if overlap >= threshold:
            return True
    return False

# Track Pexels URLs already used this build to avoid duplicate images
_pexels_used_urls: set = set()

# ── RSS SOURCES ───────────────────────────────────────────────────────────────

FEEDS = {
    "AI": [
        "https://feeds.feedburner.com/mit-technology-review/fvDp",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.wired.com/feed/tag/artificial-intelligence/rss",
    ],
    "Gadgets": [
        "https://www.theverge.com/rss/index.xml",
        "https://9to5mac.com/feed/",
        "https://www.gsmarena.com/rss-news-reviews.php3",
        "https://www.engadget.com/rss.xml",
    ],
    "Innovation": [
        "https://news.mit.edu/rss/topic/innovation",
        "https://www.fastcompany.com/technology/rss",
        "https://feeds.newscientist.com/science-technology",
    ],
    "Startups": [
        "https://techcrunch.com/feed/",
        "https://www.siliconrepublic.com/feed/",
        "https://www.eu-startups.com/feed/",
        "https://sifted.eu/feed/",
    ],
    "Gaming": [
        "https://feeds.ign.com/ign/all",
        "https://www.eurogamer.net/feed",
        "https://www.polygon.com/rss/index.xml",
    ],
}

CAT_CSS = {
    "AI":         "ai",
    "Gadgets":    "gadgets",
    "Innovation": "innovation",
    "Startups":   "startups",
    "Gaming":     "gaming",
}

CAT_ICONS = {
    "AI": "🤖",
    "Gadgets": "📱",
    "Innovation": "💡",
    "Startups": "🚀",
    "Gaming": "🎮",
}

# ── SEEN ARTICLES ─────────────────────────────────────────────────────────────

def load_seen_articles():
    if not SEEN_ARTICLES_FILE.exists():
        return {}
    try:
        data     = json.loads(SEEN_ARTICLES_FILE.read_text(encoding="utf-8"))
        cutoff   = (datetime.now(timezone.utc) - timedelta(days=SEEN_ARTICLES_TTL_DAYS)).isoformat()
        return {k: v for k, v in data.items() if v >= cutoff}
    except Exception:
        return {}

def save_seen_articles(seen):
    try:
        SEEN_ARTICLES_FILE.write_text(json.dumps(seen, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  Warning: could not save seen articles — {e}")

def article_hash(title):
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]

# ── FETCH FEEDS ───────────────────────────────────────────────────────────────

def fetch_og_image(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TechLoop/1.0)"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return ""
        html = resp.text[:50000]
        idx = html.lower().find('property="og:image"')
        if idx == -1:
            idx = html.lower().find("property='og:image'")
        if idx == -1:
            return ""
        chunk = html[idx:idx+200]
        for attr in ['content="', "content='"]:
            ci = chunk.lower().find(attr)
            if ci != -1:
                start = ci + len(attr)
                end   = chunk.find(attr[-1], start)
                if end != -1:
                    return chunk[start:end]
        return ""
    except Exception:
        return ""

def _pexels_query_from_title(title: str, category: str) -> str:
    """Extract 3-4 meaningful keywords from the article title for Pexels search."""
    stopwords = {
        "a","an","the","is","in","of","to","and","or","for","on","with","at",
        "by","it","its","this","that","are","was","be","as","not","but","from",
        "has","have","will","what","how","who","why","when","says","say","new",
        "just","about","up","after","more","than","could","would","should","get",
        "gets","got","make","makes","made","let","lets","now","over","out","all",
        "can","may","their","our","your","his","her","they","you","we","us",
        "plan","plans","report","reports","claims","claim",
    }
    words = re.findall(r"[a-zA-Z]{4,}", title)
    keywords = [w for w in words if w.lower() not in stopwords][:4]
    if keywords:
        return " ".join(keywords)
    cat_fallbacks = {
        "AI": "artificial intelligence technology",
        "Gadgets": "technology gadgets devices",
        "Innovation": "innovation science research",
        "Startups": "startup business technology",
        "Gaming": "video game gaming",
    }
    return cat_fallbacks.get(category, "technology")

def fetch_pexels_image(title: str, category: str) -> str:
    """Fetch a unique Pexels image based on article title keywords."""
    if not PEXELS_API_KEY:
        return ""
    query = _pexels_query_from_title(title, category)
    try:
        import random
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 15, "orientation": "landscape"},
            timeout=8,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            unused = [p for p in photos if p["src"]["medium"] not in _pexels_used_urls]
            if not unused:
                unused = photos  # fallback: allow reuse if all exhausted
            if unused:
                photo = random.choice(unused[:8])
                url = photo["src"]["medium"]
                _pexels_used_urls.add(url)
                print(f"  Pexels [{query[:40]}]: {url[:60]}...")
                return url
    except Exception as e:
        print(f"  Warning: Pexels fetch failed for '{title[:40]}' — {e}")
    return ""

def fetch_articles(category, urls, seen):
    articles = []
    headers  = {"User-Agent": "TechLoop/1.0 (+https://techloop.ie)"}
    for url in urls:
        try:
            resp        = requests.get(url, headers=headers, timeout=10)
            feed        = feedparser.parse(resp.content)
            source_name = feed.feed.get("title", url.split("/")[2])
            for entry in feed.entries[:10]:
                published = None
                if hasattr(entry, "published"):
                    try:
                        published = dateparser.parse(entry.published)
                    except Exception:
                        published = datetime.now(timezone.utc)
                else:
                    published = datetime.now(timezone.utc)
                if published and published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                title = entry.get("title", "").strip()
                if not title:
                    continue
                h = article_hash(title)
                if h in seen:
                    continue
                raw_summary = _strip_html(entry.get("summary", ""))
                articles.append({
                    "title":     title,
                    "link":      entry.get("link", ""),
                    "summary":   raw_summary[:500].strip(),
                    "image":     _extract_image(entry),
                    "source":    source_name,
                    "category":  category,
                    "published": published,
                    "hash":      h,
                })
        except Exception as e:
            print(f"  Warning: could not fetch {url} — {e}")

    deduped = []
    seen_titles_words_local = []
    for a in sorted(articles, key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        if _is_duplicate_title(a["title"], seen_titles_words_local):
            continue
        seen_titles_words_local.append(_title_words(a["title"]))
        deduped.append(a)
    return deduped[:MAX_PER_CATEGORY]

def _extract_image(entry):
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")
    if hasattr(entry, "media_content") and entry.media_content:
        for m in entry.media_content:
            if m.get("type", "").startswith("image"):
                return m.get("url", "")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href", "")
    return ""

# ── AI SUMMARIES ──────────────────────────────────────────────────────────────

def generate_summary(client, article):
    clean_title   = _strip_html(article["title"])
    clean_content = _strip_html(article["summary"])
    prompt = (
        "Write a 2-sentence summary of this tech article for a general audience. "
        "Be concise, factual, and engaging. Do not start with 'This article'.\n\n"
        f"Title: {clean_title}\n"
        f"Content: {clean_content}"
    )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content.strip()
        if _is_inaccessible(result):
            return None  # Signal caller to skip this article
        return result
    except Exception as e:
        print(f"  Warning: summary failed for '{article['title'][:40]}' — {e}")
        return article["summary"][:200] + "..."

def generate_daily_digest(client, all_articles):
    top    = all_articles[:8]
    titles = "\n".join(f"- [{a['category']}] {a['title']}" for a in top)
    prompt = (
        "You are the editor of TechLoop, a tech news digest. "
        "Write a single engaging paragraph (4-5 sentences) summarising today's most important tech stories. "
        "Highlight 3-4 specific stories by name. Be sharp, insightful, and written for a broad tech audience. "
        "Do not use bullet points.\n\n"
        f"Today's top stories:\n{titles}"
    )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  Warning: digest generation failed — {e}")
        return "Today's digest could not be generated. Check back soon."

# ── HTML GENERATION ───────────────────────────────────────────────────────────

def time_ago(dt):
    if not dt:
        return ""
    now     = datetime.now(timezone.utc)
    diff    = now - dt
    minutes = int(diff.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"

def _cat_badge(category):
    css = CAT_CSS.get(category, "ai")
    return f'<span class="card__cat card__cat--{css}">{category}</span>'

def _card_meta(article):
    ago = time_ago(article["published"])
    return f'''<div class="card__meta">
        <span class="card__source">{article["source"]}</span>
        <span>·</span>
        <span>{ago}</span>
      </div>'''

def _img_tag(url, alt, style=""):
    if url:
        return f'<img src="{url}" alt="{alt}" class="card__image" style="{style}" loading="lazy">'
    return f'<div class="card__image card__img-wrap" style="{style}"><svg class="card__img-placeholder" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg></div>'


# ── Featured Top: AI (main) + Gadgets + Innovation ────────────────────────────

def featured_top_html(articles):
    """
    Expects list of 3 articles: [AI, Gadgets, Innovation]
    Outputs:
      <div class="featured-top">
        card--main   (AI)
        card--side   (Gadgets)
        card--side   (Innovation)
      </div>
    """
    if not articles:
        return '<div class="featured-top"><p class="empty-state">No featured stories today.</p></div>'

    html = '<div class="featured-top">\n'

    # Main card (AI)
    main = articles[0]
    summary = (main.get("ai_summary") or main["summary"][:220] + "…").replace("<", "&lt;").replace(">", "&gt;")
    title_esc = main["title"].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    html += f'''  <div class="card card--main fade-in">
    <a class="card__overlay" href="{main["link"]}" target="_blank" rel="noopener" aria-label="{title_esc}"></a>
    {_img_tag(main.get("image",""), title_esc)}
    <div class="card__body">
      {_cat_badge(main["category"])}
      <div class="card__title">{main["title"]}</div>
      <div class="card__summary">{summary}</div>
      {_card_meta(main)}
    </div>
  </div>\n'''

    # Side cards (Gadgets, Innovation)
    for a in articles[1:3]:
        title_esc = a["title"].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        html += f'''  <div class="card card--side fade-in">
    <a class="card__overlay" href="{a["link"]}" target="_blank" rel="noopener" aria-label="{title_esc}"></a>
    {_img_tag(a.get("image",""), title_esc)}
    <div class="card__body">
      {_cat_badge(a["category"])}
      <div class="card__title">{a["title"]}</div>
      {_card_meta(a)}
    </div>
  </div>\n'''

    html += '</div>\n'
    return html


# ── Featured Bottom: Startups + Gaming ───────────────────────────────────────

def featured_bottom_html(articles):
    """
    Expects list of 2 articles: [Startups, Gaming]
    Outputs:
      <div class="featured-bottom">
        card--bottom  (Startups)
        card--bottom  (Gaming)
      </div>
    """
    if not articles:
        return '<div class="featured-bottom"><p class="empty-state">No stories today.</p></div>'

    html = '<div class="featured-bottom">\n'
    for a in articles[:2]:
        summary = (a.get("ai_summary") or a["summary"][:160] + "…").replace("<", "&lt;").replace(">", "&gt;")
        title_esc = a["title"].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        html += f'''  <div class="card card--bottom fade-in">
    <a class="card__overlay" href="{a["link"]}" target="_blank" rel="noopener" aria-label="{title_esc}"></a>
    {_img_tag(a.get("image",""), title_esc, "width:140px;flex-shrink:0;object-fit:cover;")}
    <div class="card__body">
      {_cat_badge(a["category"])}
      <div class="card__title">{a["title"]}</div>
      <div class="card__summary">{summary}</div>
      {_card_meta(a)}
    </div>
  </div>\n'''
    html += '</div>\n'
    return html


# ── Latest grid ───────────────────────────────────────────────────────────────

def latest_cards_html(articles):
    """
    Outputs <div class="latest__grid"> with card--small items.
    """
    if not articles:
        return '<div class="latest__grid"><p class="empty-state">No articles yet.</p></div>'

    html = '<div class="latest__grid">\n'
    for a in articles:
        summary = (a.get("ai_summary") or a["summary"][:160] + "…").replace("<", "&lt;").replace(">", "&gt;")
        title_esc = a["title"].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        img_html = ""
        if a.get("image"):
            img_html = f'<div class="card__image-wrap"><img src="{a["image"]}" alt="{title_esc}" class="card__image" loading="lazy"></div>'
        html += f'''  <div class="card card--small fade-in">
    <a class="card__overlay" href="{a["link"]}" target="_blank" rel="noopener" aria-label="{title_esc}"></a>
    {img_html}
    <div class="card__body">
      {_cat_badge(a["category"])}
      <div class="card__title">{a["title"]}</div>
      <div class="card__summary">{summary}</div>
      {_card_meta(a)}
    </div>
  </div>\n'''
    html += '</div>\n'
    return html


# ── Ticker ────────────────────────────────────────────────────────────────────

def ticker_items_html(articles):
    items = ""
    for a in articles[:14]:
        css   = CAT_CSS.get(a["category"], "ai")
        title = a["title"].replace("<", "&lt;").replace(">", "&gt;")
        items += f'<span class="ticker__item"><a href="{a["link"]}" target="_blank" rel="noopener"><span class="ticker__cat ticker__cat--{css}">{a["category"]}</span> {title}</a></span><span class="ticker__sep">◆</span>\n'
    # Duplicate for seamless loop
    return items + items


# ── Category pills ────────────────────────────────────────────────────────────

def category_pills_html(all_articles):
    counts = {}
    for a in all_articles:
        counts[a["category"]] = counts.get(a["category"], 0) + 1

    html = '<div class="cats-grid">\n'
    for cat, css in CAT_CSS.items():
        count = counts.get(cat, 0)
        icon  = CAT_ICONS.get(cat, "📰")
        html += f'''  <a href="#" class="cat-pill cat-pill--{css}">
    <div class="cat-pill__icon">{icon}</div>
    <div class="cat-pill__name">{cat}</div>
    <div class="cat-pill__count">{count} articles</div>
  </a>\n'''
    html += '</div>\n'
    return html


# ── Daily Digest items ────────────────────────────────────────────────────────

def digest_items_html(articles, digest_text):
    """
    Renders the digest paragraph + numbered article list
    inside the .digest__body container.
    """
    digest_esc = digest_text.replace("<", "&lt;").replace(">", "&gt;")
    html = f'<p class="digest__intro">{digest_esc}</p>\n<div class="digest__items">\n'

    for i, a in enumerate(articles[:6], 1):
        title_esc = a["title"].replace("<", "&lt;").replace(">", "&gt;")
        summary   = (a.get("ai_summary") or a["summary"][:160] + "…").replace("<", "&lt;").replace(">", "&gt;")
        css       = CAT_CSS.get(a["category"], "ai")
        num       = f"0{i}" if i < 10 else str(i)

        # Thumbnail
        if a.get("image"):
            thumb_html = f'<img src="{a["image"]}" alt="{title_esc}" style="width:100px;height:100px;object-fit:cover;border-radius:8px;flex-shrink:0;margin-top:2px;" loading="lazy">'
        else:
            thumb_html = f'<div style="width:100px;height:100px;border-radius:8px;flex-shrink:0;background:var(--bg-card);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:28px;">{CAT_ICONS.get(a["category"],"📰")}</div>'

        html += f'''  <div class="digest__item" style="align-items:flex-start;gap:14px;">
    <div class="digest__num">{num}</div>
    {thumb_html}
    <div class="digest__content">
      <div class="digest__item-title"><a href="{a["link"]}" target="_blank" rel="noopener">{a["title"]}</a></div>
      <div class="digest__item-sum">{summary}</div>
      <span class="card__cat card__cat--{css} digest__item-cat">{a["category"]}</span>
    </div>
  </div>\n'''

    html += '</div>\n'
    return html


# ── TEMPLATE REBUILD ──────────────────────────────────────────────────────────

def rebuild_html(all_articles, all_articles_including_seen, digest_text):
    template_path = Path("template.html")
    if not template_path.exists():
        print("Error: template.html not found.")
        return

    html      = template_path.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).strftime("%-d %b %Y · %H:%M UTC")

    # ── STEP 1: FEATURED — selected first, guaranteed 1 per category ──────────
    # Build best-article-per-category from full pool (new + seen fallback)
    featured_by_cat = {}
    for a in all_articles_including_seen:
        cat = a["category"]
        if cat not in featured_by_cat:
            featured_by_cat[cat] = a

    used_links = set()  # tracks every article already placed on the page

    # Top 3: AI, Gadgets, Innovation
    top_order = ["AI", "Gadgets", "Innovation"]
    f_top = []
    for cat in top_order:
        if cat in featured_by_cat:
            a = featured_by_cat[cat]
            if a["link"] not in used_links:
                f_top.append(a)
                used_links.add(a["link"])

    # Fill remaining top slots with any unused new article
    for a in all_articles:
        if len(f_top) >= 3:
            break
        if a["link"] not in used_links:
            f_top.append(a)
            used_links.add(a["link"])

    # Bottom 2: Startups, Gaming
    bottom_order = ["Startups", "Gaming"]
    f_bottom = []
    for cat in bottom_order:
        if cat in featured_by_cat:
            a = featured_by_cat[cat]
            if a["link"] not in used_links:
                f_bottom.append(a)
                used_links.add(a["link"])

    # Fill remaining bottom slots with any unused new article
    for a in all_articles:
        if len(f_bottom) >= 2:
            break
        if a["link"] not in used_links:
            f_bottom.append(a)
            used_links.add(a["link"])

    print(f"  Featured top: {[a['category'] for a in f_top]}")
    print(f"  Featured bottom: {[a['category'] for a in f_bottom]}")

    # ── STEP 2: DIGEST — exclude all featured articles ────────────────────────
    digest_articles = []
    for a in all_articles:
        if len(digest_articles) >= 6:
            break
        if a["link"] not in used_links:
            digest_articles.append(a)
            used_links.add(a["link"])

    # ── STEP 3: LATEST — exclude featured + digest ────────────────────────────
    latest_pool = []
    for a in all_articles:
        if len(latest_pool) >= 9:
            break
        if a["link"] not in used_links:
            latest_pool.append(a)
            used_links.add(a["link"])

    # ── STEP 4: TICKER — exclude everything already placed ────────────────────
    ticker_pool = [a for a in all_articles if a["link"] not in used_links]
    # Prepend featured + digest to ticker so it always has content
    ticker_all  = f_top + f_bottom + digest_articles + ticker_pool

    injections = {
        "<!-- INJECT:FEATURED_TOP -->":    featured_top_html(f_top),
        "<!-- INJECT:FEATURED_BOTTOM -->": featured_bottom_html(f_bottom),
        "<!-- INJECT:DIGEST -->":          digest_items_html(digest_articles, digest_text),
        "<!-- INJECT:LATEST -->":          latest_cards_html(latest_pool),
        "<!-- INJECT:TICKER -->":          ticker_items_html(ticker_all),
        "<!-- INJECT:CATS -->":            category_pills_html(all_articles),
        "<!-- INJECT:TIMESTAMP -->":       timestamp,
    }

    for marker, content in injections.items():
        html = html.replace(marker, content)

    Path("index.html").write_text(html, encoding="utf-8")
    print(f"  index.html rebuilt — {len(all_articles)} articles | "
          f"featured={len(f_top+f_bottom)} digest={len(digest_articles)} "
          f"latest={len(latest_pool)} ticker={len(ticker_all)}")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("TechLoop — starting daily build\n")

    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    if not client:
        print("Warning: GROQ_API_KEY not set — AI summaries will be skipped.\n")

    seen = load_seen_articles()
    print(f"Seen articles in memory: {len(seen)}\n")

    all_articles = []
    for category, urls in FEEDS.items():
        print(f"Fetching {category}...")
        articles = fetch_articles(category, urls, seen)
        print(f"  {len(articles)} new articles")
        all_articles.extend(articles)

    # Also fetch 1 recent article per category ignoring seen filter
    # — used only as Featured fallback if a category has no new articles today
    print("\nFetching seen-fallback pool for Featured (1 per category)...")
    seen_fallback_by_cat = {}
    for category, urls in FEEDS.items():
        if category in {a["category"] for a in all_articles}:
            # Already have new articles for this category
            continue
        for url in urls[:2]:  # only check first 2 feeds per category
            try:
                headers = {"User-Agent": "TechLoop/1.0 (+https://techloop.ie)"}
                resp    = requests.get(url, headers=headers, timeout=10)
                feed    = feedparser.parse(resp.content)
                source_name = feed.feed.get("title", url.split("/")[2])
                for entry in feed.entries[:5]:
                    title = entry.get("title", "").strip()
                    if not title or category in seen_fallback_by_cat:
                        break
                    published = datetime.now(timezone.utc)
                    if hasattr(entry, "published"):
                        try:
                            published = dateparser.parse(entry.published)
                            if published and published.tzinfo is None:
                                published = published.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                    raw_summary = _strip_html(entry.get("summary", ""))
                    seen_fallback_by_cat[category] = {
                        "title":     title,
                        "link":      entry.get("link", ""),
                        "summary":   raw_summary[:500].strip(),
                        "image":     _extract_image(entry),
                        "source":    source_name,
                        "category":  category,
                        "published": published,
                        "hash":      article_hash(title),
                    }
                    break
            except Exception:
                continue

    # Merge: new articles first, then seen fallbacks for missing categories
    new_article_cats = {a["category"] for a in all_articles}
    all_articles_including_seen = list(all_articles)
    for cat, article in seen_fallback_by_cat.items():
        if cat not in new_article_cats:
            all_articles_including_seen.append(article)
            print(f"  Added seen fallback for {cat}: {article['title'][:50]}...")

    all_articles.sort(
        key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )

    # Global deduplication across all categories (same build)
    # Uses exact link/title match + fuzzy title word-overlap to catch
    # the same story covered by multiple sources.
    global_seen_links  = set()
    seen_title_words   = []
    deduped_all = []
    for a in all_articles:
        link_key = a["link"].strip().lower()
        if link_key in global_seen_links:
            continue
        if _is_duplicate_title(a["title"], seen_title_words):
            continue
        global_seen_links.add(link_key)
        seen_title_words.append(_title_words(a["title"]))
        deduped_all.append(a)
    all_articles = deduped_all
    print(f"\nTotal new articles (after global dedup): {len(all_articles)}")

    if client and all_articles:
        print(f"\nGenerating summaries (top {MAX_AI_SUMMARIES})...")
        kept = []
        skipped = 0
        i = 0
        candidates = list(all_articles)  # iterate over full pool
        summarised = 0
        for article in candidates:
            if summarised >= MAX_AI_SUMMARIES:
                kept.append(article)  # keep remaining without summary
                continue
            print(f"  [{summarised+1}/{MAX_AI_SUMMARIES}] {article['title'][:50]}...")
            summary = generate_summary(client, article)
            if summary is None:
                print(f"    → Skipped (inaccessible content)")
                skipped += 1
                continue
            article["ai_summary"] = summary
            kept.append(article)
            summarised += 1
        all_articles = kept
        print(f"  Skipped {skipped} inaccessible article(s).")
        print("\nGenerating daily digest...")
        digest_text = generate_daily_digest(client, all_articles)
        print("  Done.")
    else:
        digest_text = "Today's digest is unavailable — check back soon."

    print(f"\nFetching OG images (top {MAX_OG_IMAGES})...")
    for i, article in enumerate(all_articles[:MAX_OG_IMAGES]):
        if not article.get("image"):
            img = fetch_og_image(article["link"])
            if img:
                article["image"] = img
                print(f"  [{i+1}] Got OG image for: {article['title'][:40]}...")

    # Pexels fallback — for any article still without an image
    if PEXELS_API_KEY:
        print("\nApplying Pexels fallback for articles without images...")
        for article in all_articles:
            if not article.get("image"):
                article["image"] = fetch_pexels_image(article["title"], article["category"])

    print("\nRebuilding index.html...")
    rebuild_html(all_articles, all_articles_including_seen, digest_text)

    now = datetime.now(timezone.utc).isoformat()
    for a in all_articles:
        seen[a["hash"]] = now
    save_seen_articles(seen)
    print(f"Marked {len(all_articles)} articles as seen.")
    print("\nBuild complete.")


if __name__ == "__main__":
    main()
