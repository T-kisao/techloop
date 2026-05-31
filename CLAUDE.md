# TechLoop — Project Context for Claude Code

## What is TechLoop
TechLoop (techloop.ie) is a curated AI-powered tech news digest targeting busy people in tech in Ireland, UK and Europe. It aggregates RSS feeds, generates AI summaries via Groq, and rebuilds a static site daily. The tagline is "beyond, curated" and the second line is "The fastest way for busy people in tech to stay on top of what actually matters."

---

## Identity
- **Name:** TechLoop
- **Tagline:** AI-powered news digest
- **URL:** techloop.ie ✅ ACTIVE
- **Vercel URL:** techloop-two.vercel.app (redirects to techloop.ie)
- **Target:** Ireland, UK and Europe
- **Email:** hello@techloop.ie ✅ ACTIVE (forwards to thiagokisuk@gmail.com via Cloudflare Email Routing)
- **GitHub:** T-kisao/techloop
- **LinkedIn:** Added under Projects ✅

---

## Tech Stack
| Component     | Technology                                      |
|---------------|-------------------------------------------------|
| Frontend      | HTML + CSS + Vanilla JS (static site)           |
| Generator     | Python (generate.py)                            |
| AI Summaries  | Groq API (llama-3.1-8b-instant)                 |
| Images        | OG tags + Pexels API (fallback by title)        |
| Hosting       | Vercel (free tier)                              |
| Repository    | GitHub (T-kisao/techloop)                       |
| Automation    | cron-job.org (2 triggers) + GitHub Actions      |

---

## Costs
| Service       | Cost                  |
|---------------|-----------------------|
| Vercel        | €0                    |
| GitHub        | €0                    |
| Groq API      | €0 (free tier)        |
| Pexels API    | €0 (free tier)        |
| cron-job.org  | €0                    |
| Cloudflare    | €0 (free tier)        |
| Domain        | ~€28/year (Blacknight)|

---

## File Structure
```
techloop/
├── CLAUDE.md              ← this file
├── template.html          ← template with INJECT markers + 52 polls
├── generate.py            ← Python script that generates index.html + category pages
├── index.html             ← generated daily by Python
├── about.html
├── privacy.html
├── contact.html
├── sitemap.xml
├── robots.txt
├── favicon.png            ← TL blue/purple logo
├── seen_articles.json     ← seen articles memory (7 days TTL)
├── requirements.txt
├── category/
│   ├── ai.html
│   ├── gadgets.html
│   ├── innovation.html
│   ├── startups.html
│   └── gaming.html
└── .github/
    └── workflows/
        └── daily-build.yml
```

---

## Automation
- **cron-job.org #1** — 8:00 UTC (morning trigger)
- **cron-job.org #2** — 16:00 UTC (afternoon trigger)
- **GitHub Actions** — workflow_dispatch only (no schedule of its own)
- **Vercel** — auto-deploy after each push

---

## RSS Feeds (generate.py — FEEDS dict)
Categorisation is done entirely by which feed URL is listed under which category key. There is no keyword filtering.

```python
FEEDS = {
    "AI": [
        "https://feeds.feedburner.com/mit-technology-review/fvDp",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.wired.com/feed/category/artificial-intelligence/rss",
    ],
    "Gadgets": [
        "https://www.theverge.com/rss/tech/index.xml",
        "https://9to5mac.com/feed/",
        "https://www.gsmarena.com/rss-news-reviews.php3",
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
        "https://kotaku.com/rss",
        "https://www.eurogamer.net/feed",
        "https://www.polygon.com/rss/index.xml",
    ],
}
```

### Feed decisions made (28/05/2026)
- `feeds.ign.com/ign/all` → replaced with `kotaku.com/rss` (IGN was showing non-gaming articles like cars and films)
- `theverge.com/rss/index.xml` → replaced with `theverge.com/rss/tech/index.xml` (too general)
- `engadget.com/rss.xml` → removed (no valid category-specific feed found; remaining 3 Gadgets feeds are solid)
- `wired.com/feed/tag/artificial-intelligence/rss` → replaced with `wired.com/feed/category/artificial-intelligence/rss` (more specific)

---

## Categories & Colours
| Category   | Colour | Hex     |
|------------|--------|---------|
| AI         | Cyan   | #22D3EE |
| Gadgets    | Purple | #8B5CF6 |
| Innovation | Green  | #34d399 |
| Startups   | Blue   | #3B82F6 |
| Gaming     | Amber  | #f59e0b |

---

## Design
- **Style:** Dark mode, modern
- **Background primary:** #0B1120
- **Background secondary:** #111827
- **Card background:** #13203a
- **Fonts:** Syne (display) + DM Sans (body) + Space Mono (mono)

---

## Hero Section (template.html)
Current state of the hero subtitle block:
```html
<p class="hero__sub">
  The top tech stories from Europe and beyond, curated and summarised daily.
</p>
<p class="hero__sub" style="margin-top: 10px;">
  The fastest way for busy people in tech to stay on top of what actually matters.
</p>
```
Both lines use `.hero__sub` styling (15px, color: #94A3B8, font-weight: 400). The second line has margin-top: 10px only — no bold, no different colour.

---

## Weekly Poll
- 52 questions — 1 per week, no repeats for 1 year
- Split by theme: AI (15), Gadgets (10), Startups (10), Gaming (10), Innovation (7)
- Storage via localStorage + fake votes 23-78 for engagement
- Phase 2: migrate to Supabase for shared votes

---

## Infrastructure
- **Email:** hello@techloop.ie configured via Cloudflare Email Routing → thiagokisuk@gmail.com
- **DNS:** Migrated from Blacknight to Cloudflare (nameservers: hera.ns.cloudflare.com + yew.ns.cloudflare.com)
- **Sending tool (Phase 2):** Brevo free tier (300 emails/day)

---

## What is Done ✅
- Site live at techloop.ie
- www.techloop.ie configured
- Full dark mode design
- Navbar, Ticker, Hero, Featured, Categories, Daily Digest, Weekly Poll, Latest, Footer
- Global anti-duplicate system
- Pexels image fallback by article title
- 5 category pages auto-generated by Python
- generate.py updated to populate category pages
- About, Privacy Policy and Contact pages
- Footer without Sources section
- sitemap.xml created and submitted to Google Search Console
- robots.txt created
- favicon.png created (TL blue/purple logo)
- Google Search Console verified
- DNS migrated from Blacknight to Cloudflare
- 52 Weekly Poll questions
- Fake votes (23-78) for engagement
- cron-job.org with 2 triggers (8:00 and 16:00 UTC)
- GitHub Actions without its own schedule
- LinkedIn — TechLoop added under Projects
- Hero section — em dash removed, replaced with comma
- Hero section — second line added (same style as first, no bold, margin-top: 10px)
- Email hello@techloop.ie configured via Cloudflare Email Routing
- RSS feeds updated to reduce miscategorisation (28/05/2026)
- Local repo synced with GitHub via git fetch + reset --hard
- Claude Code installed and authenticated (Windows, Node.js v24.16.0)

---

## Pending 🔜

### Monitoring
- 📊 Google Search Console — verify if sitemap was processed

### Growth
- 📱 X/Twitter — create TechLoop account
- 💬 Reddit/Discord — share in Irish/European tech groups

### Phase 2 — Monetisation
- 💰 NordVPN affiliates — when 500-1000 visits/month
- 💰 Canva Pro affiliates — same threshold

### Phase 2 — Technical improvements
- 🗳️ Supabase — shared votes for Weekly Poll
- 📰 Newsletter — plain text, ~8 news items, 14:00 daily, last item affiliate in separate block ("This week's pick"), tool: Brevo free tier
- 📈 Analytics — Plausible or Google Analytics
- 🔍 Individual article pages — unique URL per article

---

## Important Rules for Claude Code
- **Always confirm before making any changes** — show the proposed change and wait for approval
- **Always run `git pull` before starting any session** to ensure local files are up to date
- **Never commit sensitive files** — "Token para o Schedule no Cron" and any files with API keys or tokens must never be committed to GitHub
- **The daily-build.yml belongs only in `.github/workflows/`** — never in the project root
- **After any change**, remind Thiago to commit and push to GitHub so Vercel deploys automatically
