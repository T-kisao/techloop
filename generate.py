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
import hashlib
import feedparser
import requests
from groq import Groq
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"

MAX_PER_CATEGORY = 6
MAX_AI_SUMMARIES = 10
FEATURED_COUNT   = 3

# How many days to remember seen articles
SEEN_ARTICLES_TTL_DAYS = 7
SEEN_ARTICLES_FILE     = Path("seen_articles.json")

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

CAT_COLORS = {
    "AI":         "cat-ai",
    "Gadgets":    "cat-gadgets",
    "Innovation": "cat-innovation",
    "Startups":   "cat-startups",
    "Gaming":     "cat-gaming",
}

# ── SEEN ARTICLES ─────────────────────────────────────────────────────────────

def load_seen_articles():
    """Load seen article hashes from file, removing expired entries."""
    if not SEEN_ARTICLES_FILE.exists():
        return {}
    try:
        data     = json.loads(SEEN_ARTICLES_FILE.read_text(encoding="utf-8"))
        cutoff   = (datetime.now(timezone.utc) - timedelta(days=SEEN_ARTICLES_TTL_DAYS)).isoformat()
        filtered = {k: v for k, v in data.items() if v >= cutoff}
        return filtered
    except Exception:
        return {}


def save_seen_articles(seen):
    """Save seen article hashes to file."""
    try:
        SEEN_ARTICLES_FILE.write_text(json.dumps(seen, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  Warning: could not save seen articles — {e}")


def article_hash(title):
    """Generate a short hash for an article title."""
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]

# ── FETCH FEEDS ───────────────────────────────────────────────────────────────

def fetch_articles(category, urls, seen):
    """Fetch and parse RSS feeds, skipping already seen articles."""
    articles = []
    headers  = {"User-Agent": "TechLoop/1.0 (+https://techloop.ie)"}

    for url in urls:
        try:
            resp        = requests.get(url, headers=headers, timeout=10)
            feed        = feedparser.parse(resp.content)
            source_name = feed.feed.get("title", url.split("/")[2])

            for entry in feed.entries[:10]:  # fetch more to account for seen filtering
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

                # Skip if already seen in the last 7 days
                h = article_hash(title)
                if h in seen:
                    continue

                articles.append({
                    "title":     title,
                    "link":      entry.get("link", ""),
                    "summary":   entry.get("summary", "")[:500].strip(),
                    "image":     _extract_image(entry),
                    "source":    source_name,
                    "category":  category,
                    "published": published,
                    "hash":      h,
                })
        except Exception as e:
            print(f"  Warning: could not fetch {url} — {e}")

    # Sort by date, remove duplicates
    deduped = []
    seen_titles = set()
    for a in sorted(articles, key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        key = a["title"].lower()[:60]
        if key not in seen_titles:
            seen_titles.add(key)
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
    prompt = (
        "Write a 2-sentence summary of this tech article for a general audience. "
        "Be concise, factual, and engaging. Do not start with 'This article'.\n\n"
        f"Title: {article['title']}\n"
        f"Content: {article['summary']}"
    )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
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


def article_card_html(article, size="normal"):
    cat_class = CAT_COLORS.get(article["category"], "cat-ai")
    ago       = time_ago(article["published"])
    title_esc = article["title"].replace('"', "&quot;")
    summary   = article.get("ai_summary") or article["summary"][:180] + "..."

    if article.get("image"):
        img_html = f'<img src="{article["image"]}" alt="{title_esc}" style="width:100%;height:160px;object-fit:cover;border-radius:8px;margin-bottom:1.2rem">'
    else:
        img_html = '<div class="card-image-placeholder"><div class="img-pattern"></div></div>' if size == "main" else ""

    badge = '<div class="ai-badge">&#9889; AI Summary</div>' if article.get("ai_summary") else ""

    if size == "main":
        return f"""
        <a href="{article['link']}" target="_blank" rel="noopener" class="card card-main" style="text-decoration:none">
          <span class="card-cat {cat_class}">{article['category']}</span>
          {img_html}{badge}
          <h2 class="card-title" style="font-size:1.5rem;margin-bottom:1rem">{article['title']}</h2>
          <p class="card-summary">{summary}</p>
          <div class="card-meta">
            <span class="card-source">{article['source']}</span><span>·</span><span>{ago}</span>
          </div>
        </a>"""
    return f"""
        <a href="{article['link']}" target="_blank" rel="noopener" class="card" style="text-decoration:none">
          <span class="card-cat {cat_class}">{article['category']}</span>
          {badge}
          <h3 class="card-title">{article['title']}</h3>
          <p class="card-summary">{summary}</p>
          <div class="card-meta">
            <span class="card-source">{article['source']}</span><span>·</span><span>{ago}</span>
          </div>
        </a>"""


def latest_card_html(article):
    cat_class = CAT_COLORS.get(article["category"], "cat-ai")
    ago       = time_ago(article["published"])
    summary   = article.get("ai_summary") or article["summary"][:160] + "..."
    return f"""
        <a href="{article['link']}" target="_blank" rel="noopener" class="article-card" style="text-decoration:none">
          <span class="card-cat {cat_class}">{article['category']}</span>
          <h3 class="card-title">{article['title']}</h3>
          <p class="card-summary">{summary}</p>
          <div class="card-meta">
            <span class="card-source">{article['source']}</span><span>·</span><span>{ago}</span>
          </div>
        </a>"""


def ticker_items_html(articles):
    cat_map = {
        "AI": "tc-ai", "Gadgets": "tc-gadgets",
        "Innovation": "tc-innovation", "Startups": "tc-startups", "Gaming": "tc-gaming",
    }
    items = ""
    for a in articles[:12]:
        tc    = cat_map.get(a["category"], "tc-ai")
        title = a["title"].replace("<", "&lt;").replace(">", "&gt;")
        items += f'<span class="ticker-item"><span class="ticker-cat {tc}">{a["category"]}</span> {title}</span>\n    '
    return items + items


def category_counts_html(all_articles):
    counts = {}
    for a in all_articles:
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    icons = {"AI": "🧠", "Gadgets": "📱", "Innovation": "💡", "Startups": "🚀", "Gaming": "🎮"}
    html  = ""
    for cat in CAT_COLORS:
        count = counts.get(cat, 0)
        icon  = icons.get(cat, "📰")
        html += f"""
      <a href="/category/{cat.lower()}" class="cat-card cat-{cat.lower()}-card" style="display:block;text-decoration:none">
        <div class="cat-icon">{icon}</div>
        <div class="cat-name">{cat}</div>
        <div class="cat-count">{count} articles</div>
      </a>"""
    return html

# ── TEMPLATE REBUILD ──────────────────────────────────────────────────────────

def rebuild_html(all_articles, digest):
    template_path = Path("index.html")
    if not template_path.exists():
        print("Error: index.html not found.")
        return

    html      = template_path.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).strftime("%-d %b %Y · %H:%M UTC")

    featured      = all_articles[:FEATURED_COUNT]
    featured_html = "".join(article_card_html(a, "main" if i == 0 else "normal") for i, a in enumerate(featured))
    latest_html   = "".join(latest_card_html(a) for a in all_articles[FEATURED_COUNT:FEATURED_COUNT + 3])

    for marker, content in {
        "<!-- INJECT:FEATURED -->":  featured_html,
        "<!-- INJECT:LATEST -->":    latest_html,
        "<!-- INJECT:TICKER -->":    ticker_items_html(all_articles),
        "<!-- INJECT:CATS -->":      category_counts_html(all_articles),
        "<!-- INJECT:DIGEST -->":    digest,
        "<!-- INJECT:TIMESTAMP -->": timestamp,
    }.items():
        html = html.replace(marker, content)

    template_path.write_text(html, encoding="utf-8")
    print(f"index.html rebuilt — {len(all_articles)} articles injected.")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("TechLoop — starting daily build\n")

    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    if not client:
        print("Warning: GROQ_API_KEY not set — AI summaries will be skipped.\n")

    # Load seen articles
    seen = load_seen_articles()
    print(f"Seen articles in memory: {len(seen)}\n")

    # Fetch all feeds
    all_articles = []
    for category, urls in FEEDS.items():
        print(f"Fetching {category}...")
        articles = fetch_articles(category, urls, seen)
        print(f"  {len(articles)} new articles")
        all_articles.extend(articles)

    # Sort by date
    all_articles.sort(
        key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    print(f"\nTotal new articles: {len(all_articles)}")

    # Generate AI summaries
    if client and all_articles:
        print(f"\nGenerating summaries (top {MAX_AI_SUMMARIES})...")
        for i, article in enumerate(all_articles[:MAX_AI_SUMMARIES]):
            print(f"  [{i+1}/{MAX_AI_SUMMARIES}] {article['title'][:50]}...")
            article["ai_summary"] = generate_summary(client, article)

        print("\nGenerating daily digest...")
        digest = generate_daily_digest(client, all_articles)
        print("  Done.")
    else:
        digest = "Today's digest is unavailable."

    # Rebuild HTML
    print("\nRebuilding index.html...")
    rebuild_html(all_articles, digest)

    # Mark articles as seen
    now = datetime.now(timezone.utc).isoformat()
    for a in all_articles:
        seen[a["hash"]] = now
    save_seen_articles(seen)
    print(f"Marked {len(all_articles)} articles as seen.")

    print("\nBuild complete.")


if __name__ == "__main__":
    main()
