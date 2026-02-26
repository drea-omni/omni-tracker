#!/usr/bin/env python3
"""
Omni Changelog & Demos Scraper — with Playwright for full demo detail
======================================================================
Scrapes https://omni.co/changelog and https://omni.co/demos
Uses requests+BeautifulSoup for changelog (fast, no JS needed)
Uses Playwright for demos (needed to extract YouTube embed URLs + demo detail)

Each demo entry now captures:
  - youtube_id, youtube_url, embed_url, thumbnail
  - title       (from iframe title or heading)
  - description (the blurb below the video)
  - author      (presenter name)
  - tag         (category label, e.g. "Visualization", "AI")

Usage:
    python scrape_omni.py
    python scrape_omni.py --force        # re-scrape all weeks
    python scrape_omni.py --dry-run      # print changes, don't write
    python scrape_omni.py --no-playwright # skip YouTube extraction (faster)
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data"
CHANGELOG_FILE = DATA_DIR / "omni_changelog.json"
DEMOS_FILE     = DATA_DIR / "omni_demos.json"

BASE_CHANGELOG = "https://omni.co/changelog"
BASE_DEMOS     = "https://omni.co/demos"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OmniChangelogBot/1.0)",
    "Accept":     "text/html,application/xhtml+xml",
}

REQUEST_DELAY   = 1.5
REQUEST_TIMEOUT = 20
PLAYWRIGHT_WAIT = 3500   # ms — enough for iframes + lazy content


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def url_to_date(url):
    m = re.search(r"/(\d{8})$", url.rstrip("/"))
    if m:
        raw = m.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None

def clean_text(el):
    return " ".join(el.get_text(" ", strip=True).split())

def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(path, data, dry_run=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"  [dry-run] Would write {path}")
        return
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved {path} ({path.stat().st_size/1024:.1f} KB)")

def fetch_html(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  ⚠ Attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * 2)
    return None


# ── Playwright: full demo detail extraction ───────────────────────────────────

async def extract_demo_details(url, pw):
    """
    Load a demos page with Playwright and extract full per-demo detail:
      title, description, author, tag, youtube_id + derived URLs.

    DOM structure on omni.co/demos/* :
      div.stack.demo
        figure.video  →  iframe[src*=youtube]   (youtube_id, iframe title)
        hgroup.stack  →  h3                      (display title)
        div.editorial-copy  →  p                (description blurb)
        p.meta
          span.stack.author  →  span (name text, skip img)
          span (bullet "•")
          span  (tag label)
    """
    browser = await pw.chromium.launch(headless=True)
    try:
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(PLAYWRIGHT_WAIT)

        # Scroll to trigger lazy iframes
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await page.wait_for_timeout(600)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(600)

        # Extract all week-level summary bullets (top of page before first video)
        summary_bullets = await page.evaluate("""() => {
            const bullets = [];
            // The intro section uses a <ul> or bare <li>s before the demo entries
            const lists = document.querySelectorAll('ul li, ol li');
            for (const li of lists) {
                const text = li.innerText?.trim();
                if (text && text.length > 20 && text.length < 600) {
                    // Only grab bullets that are NOT inside a .demo div
                    if (!li.closest('.demo')) bullets.push(text);
                }
            }
            return bullets;
        }""")

        # Extract per-demo detail
        demos = await page.evaluate("""() => {
            const results = [];
            const demoEls = document.querySelectorAll('div.stack.demo');

            for (const demo of demoEls) {
                // YouTube ID from iframe src
                const iframe = demo.querySelector('iframe[src*="youtube"]');
                let youtube_id = null;
                if (iframe) {
                    const m = (iframe.src || '').match(/youtube\\.com\\/embed\\/([a-zA-Z0-9_-]{11})/);
                    if (m) youtube_id = m[1];
                }

                // Title: prefer h3 text, fall back to iframe title attr
                const h3 = demo.querySelector('h3');
                const title = (h3?.innerText || iframe?.title || '').trim();

                // Description: first <p> inside .editorial-copy
                const descEl = demo.querySelector('.editorial-copy p');
                const description = descEl?.innerText?.trim() || '';

                // Author: text content of span.author (contains an img + text span)
                // We want just the name text, not the img alt
                const authorSpan = demo.querySelector('span.author');
                let author = '';
                if (authorSpan) {
                    // Walk child nodes, grab text nodes only (skip img)
                    for (const node of authorSpan.childNodes) {
                        if (node.nodeType === 3) { // TEXT_NODE
                            const t = node.textContent.trim();
                            if (t) author += t;
                        } else if (node.tagName === 'SPAN') {
                            const t = node.innerText?.trim();
                            if (t) author += t;
                        }
                    }
                    author = author.trim();
                }

                // Tag: last <span> in p.meta (after the bullet •)
                const metaSpans = Array.from(demo.querySelectorAll('p.meta span'));
                // Filter out the bullet and author spans
                const tagSpan = metaSpans.filter(s =>
                    !s.classList.contains('author') &&
                    s.innerText?.trim() !== '•' &&
                    s.innerText?.trim().length > 0
                ).pop();
                const tag = tagSpan?.innerText?.trim() || '';

                if (youtube_id || title) {
                    results.push({ youtube_id, title, description, author, tag });
                }
            }
            return results;
        }""")

        return demos, summary_bullets

    except Exception as e:
        print(f"  ⚠ Playwright error for {url}: {e}")
        return [], []
    finally:
        await browser.close()


# ── Demos scraping ────────────────────────────────────────────────────────────

async def scrape_demos_with_playwright(existing, force=False):
    print("\n🎬 Scraping demos with Playwright...")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  ⚠ Playwright not installed — falling back to requests-only")
        return scrape_demos_requests_only(existing, force)

    soup = fetch_html(BASE_DEMOS)
    if not soup:
        print("  ✗ Could not fetch demos index")
        return existing

    # ── Build week list from index ──
    all_weeks = [{
        "date": now_iso()[:10],
        "week_label": "Current week",
        "url": BASE_DEMOS,
    }]
    seen_urls = {BASE_DEMOS}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/demos/\d{8}", href) and href not in seen_urls:
            all_weeks.append({
                "date": url_to_date(href) or "",
                "week_label": clean_text(a),
                "url": href,
            })
            seen_urls.add(href)

    print(f"  Found {len(all_weeks)} weeks in index")

    # ── Merge index ──
    updated_index = list(existing.get("index", []))
    indexed_urls  = {e["url"] for e in updated_index}

    for week in all_weeks:
        if week["url"] not in indexed_urls:
            updated_index.append({
                "date":       week["date"],
                "week_label": week["week_label"],
                "url":        week["url"],
                "title":      "",
            })
            indexed_urls.add(week["url"])

    # ── Which weeks need scraping? ──
    existing_details = {w["url"]: w for w in existing.get("weeks_detail", [])}
    already_scraped  = set(existing_details.keys()) if not force else set()
    to_scrape        = [w for w in all_weeks if w["url"] not in already_scraped]

    print(f"  {len(to_scrape)} weeks to scrape")
    updated_details = dict(existing_details)

    async with async_playwright() as pw:
        for week in to_scrape:
            url = week["url"]
            print(f"  🎬 {week['week_label']} ({url})")

            demos, summary_bullets = await extract_demo_details(url, pw)
            print(f"     ✓ {len(demos)} demos found")

            # Build video list with full metadata
            videos = []
            for d in demos:
                vid = {
                    "youtube_id":  d["youtube_id"],
                    "youtube_url": f"https://www.youtube.com/watch?v={d['youtube_id']}" if d["youtube_id"] else "",
                    "embed_url":   f"https://www.youtube.com/embed/{d['youtube_id']}"   if d["youtube_id"] else "",
                    "thumbnail":   f"https://img.youtube.com/vi/{d['youtube_id']}/mqdefault.jpg" if d["youtube_id"] else "",
                    "title":       d["title"],
                    "description": d["description"],
                    "author":      d["author"],
                    "tag":         d["tag"],
                }
                videos.append(vid)

            # Page-level title from requests (more reliable than Playwright h1)
            week_soup = fetch_html(url)
            page_title = ""
            if week_soup:
                title_el = week_soup.find("h1") or week_soup.find("h2")
                page_title = clean_text(title_el) if title_el else ""

            updated_details[url] = {
                "date":          week["date"],
                "url":           url,
                "fully_scraped": True,
                "scraped_at":    now_iso(),
                "title":         page_title,
                "summary_bullets": summary_bullets,
                "video_count":   len(videos),
                "videos":        videos,
            }

            # Backfill title + author list into index entry
            all_authors = sorted(set(v["author"] for v in videos if v["author"]))
            all_tags    = sorted(set(v["tag"]    for v in videos if v["tag"]))
            for entry in updated_index:
                if entry["url"] == url:
                    if page_title and not entry.get("title"):
                        entry["title"] = page_title
                    entry["authors"] = all_authors
                    entry["tags"]    = all_tags
                    break

    # ── Rebuild index author/tag lists for previously scraped weeks ──
    for detail in updated_details.values():
        videos = detail.get("videos", [])
        if not videos:
            continue
        all_authors = sorted(set(v["author"] for v in videos if v.get("author")))
        all_tags    = sorted(set(v["tag"]    for v in videos if v.get("tag")))
        for entry in updated_index:
            if entry["url"] == detail["url"]:
                entry.setdefault("authors", all_authors)
                entry.setdefault("tags",    all_tags)
                break

    total_videos = sum(len(d.get("videos", [])) for d in updated_details.values())
    print(f"\n  Done — {total_videos} total videos indexed")

    return {
        "meta": {
            "source":                  BASE_DEMOS,
            "last_scraped":            now_iso(),
            "scrape_method":           "playwright+requests",
            "scrape_notes":            "Playwright extracts YouTube URLs, titles, descriptions, authors, and tags per demo entry.",
            "total_weeks_indexed":     len(updated_index),
            "total_weeks_with_detail": len(updated_details),
            "total_videos_indexed":    total_videos,
            "date_range": {
                "earliest": min((e["date"] for e in updated_index if e.get("date")), default=""),
                "latest":   max((e["date"] for e in updated_index if e.get("date")), default=""),
            },
            "important_note": "Demos are NOT a guarantee of release.",
        },
        "index":        updated_index,
        "weeks_detail": list(updated_details.values()),
    }


def scrape_demos_requests_only(existing, force=False):
    """Fallback: scrape demos index without Playwright (no YouTube URLs)."""
    print("\n🎬 Scraping demos (requests-only fallback)...")
    soup = fetch_html(BASE_DEMOS)
    if not soup:
        return existing

    updated_index = list(existing.get("index", []))
    indexed_urls  = {e["url"] for e in updated_index}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/demos/\d{8}", href) and href not in indexed_urls:
            label = clean_text(a)
            updated_index.append({
                "date":       url_to_date(href) or "",
                "week_label": label,
                "url":        href,
                "title":      label,
                "authors":    [],
                "tags":       [],
            })
            indexed_urls.add(href)

    return {
        **existing,
        "index": updated_index,
        "meta":  {**existing.get("meta", {}), "last_scraped": now_iso()},
    }


# ── Changelog scraping ────────────────────────────────────────────────────────

def scrape_changelog(existing, force=False):
    print("\n📋 Scraping changelog...")
    soup = fetch_html(BASE_CHANGELOG)
    if not soup:
        return existing

    all_weeks = [{"week_label": "Current week", "url": BASE_CHANGELOG}]
    seen      = {BASE_CHANGELOG}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/changelog/\d{8}", href) and href not in seen:
            all_weeks.append({"week_label": clean_text(a), "url": href})
            seen.add(href)

    print(f"  Found {len(all_weeks)} weeks in index")

    already_scraped = (
        {w["source_url"] for w in existing.get("weeks", []) if w.get("fully_scraped")}
        if not force else set()
    )
    updated_weeks = {
        w["source_url"]: w
        for w in existing.get("weeks", [])
        if "source_url" in w
    }

    updated_index = list(existing.get("index", []))
    indexed_urls  = {e["url"] for e in updated_index}
    for week in all_weeks:
        if week["url"] not in indexed_urls:
            updated_index.append(week)
            indexed_urls.add(week["url"])

    date_pat = re.compile(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        re.I,
    )

    for week in all_weeks:
        url = week["url"]
        if url in already_scraped:
            continue

        print(f"  🔍 Scraping: {week['week_label']}")
        week_soup = soup if url == BASE_CHANGELOG else fetch_html(url)
        if not week_soup:
            continue

        days, current_date, current_items = [], None, []
        for el in week_soup.find_all(["h1","h2","h3","h4","h5","p","li","time"]):
            text = clean_text(el)
            dm   = date_pat.search(text)
            if dm and el.name in ("h1","h2","h3","h4","h5","time","p"):
                if current_date and current_items:
                    days.append({"date": current_date, "items": current_items})
                try:
                    parsed       = datetime.strptime(dm.group(0).replace(",",""), "%B %d %Y")
                    current_date = parsed.strftime("%Y-%m-%d")
                except ValueError:
                    current_date = None
                current_items = []
            elif current_date and el.name == "li" and len(text) > 15:
                if not any(n in text.lower() for n in ["previous","next","week of","back to"]):
                    current_items.append(text)

        if current_date and current_items:
            days.append({"date": current_date, "items": current_items})

        if not days:
            continue

        all_dates  = [d["date"] for d in days if d.get("date")]
        week_start = min(all_dates) if all_dates else url_to_date(url) or "unknown"

        updated_weeks[url] = {
            "week_start":    week_start,
            "week_label":    week.get("week_label", ""),
            "source_url":    url,
            "fully_scraped": True,
            "scraped_at":    now_iso(),
            "days":          days,
        }
        print(f"     ✓ {len(days)} days, {sum(len(d['items']) for d in days)} items")

    all_dates = [
        d["date"]
        for w in updated_weeks.values()
        for d in w.get("days", [])
        if d.get("date")
    ]
    return {
        "meta": {
            "source":                  BASE_CHANGELOG,
            "last_scraped":            now_iso(),
            "total_weeks_indexed":     len(updated_index),
            "total_weeks_fully_scraped": len(
                [w for w in updated_weeks.values() if w.get("fully_scraped")]
            ),
            "date_range": {
                "earliest_indexed": min(all_dates) if all_dates else "",
                "latest_scraped":   max(all_dates) if all_dates else "",
            },
        },
        "index":              updated_index,
        "weeks":              list(updated_weeks.values()),
        "weeks_not_yet_scraped": [],
    }


# ── Diff report ───────────────────────────────────────────────────────────────

def report_diff(old_cl, new_cl, old_dm, new_dm):
    lines = ["## 🔄 Omni Scraper Update Report", f"*{now_iso()}*", ""]

    old_items = {
        item[:80]
        for w in old_cl.get("weeks", [])
        for d in w.get("days", [])
        for item in d.get("items", [])
    }
    new_items = [
        f"- `{d['date']}` {item}"
        for w in new_cl.get("weeks", [])
        for d in w.get("days", [])
        for item in d.get("items", [])
        if item[:80] not in old_items
    ]
    if new_items:
        lines += [f"### 📋 New Changelog Entries ({len(new_items)})"] + new_items[:20]
        if len(new_items) > 20:
            lines.append(f"_...and {len(new_items)-20} more_")
    else:
        lines.append("### 📋 Changelog — No new entries")
    lines.append("")

    old_demo_urls = {e["url"] for e in old_dm.get("index", [])}
    added = [e for e in new_dm.get("index", []) if e["url"] not in old_demo_urls]
    if added:
        lines += [f"### 🎬 New Demo Weeks ({len(added)})"]
        for d in added:
            lines.append(f"- `{d.get('date','')}` [{d.get('title') or d.get('week_label','')}]({d['url']})")
    else:
        lines.append("### 🎬 Demos — No new weeks")
    lines.append("")

    # Author diversity stats
    all_authors = sorted(set(
        v["author"]
        for w in new_dm.get("weeks_detail", [])
        for v in w.get("videos", [])
        if v.get("author")
    ))

    total_vids = sum(len(d.get("videos", [])) for d in new_dm.get("weeks_detail", []))
    lines += [
        "### 📊 Totals",
        f"- Changelog entries: {sum(len(d.get('items',[])) for w in new_cl.get('weeks',[]) for d in w.get('days',[]))}",
        f"- Demo weeks indexed: {len(new_dm.get('index', []))}",
        f"- YouTube videos indexed: {total_vids}",
        f"- Unique demo authors: {len(all_authors)}",
        f"- Authors: {', '.join(all_authors[:20])}{'...' if len(all_authors) > 20 else ''}",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",          action="store_true", help="Re-scrape all weeks")
    parser.add_argument("--dry-run",        action="store_true", help="Print changes, don't write")
    parser.add_argument("--changelog-only", action="store_true")
    parser.add_argument("--demos-only",     action="store_true")
    parser.add_argument("--no-playwright",  action="store_true", help="Skip YouTube extraction")
    args = parser.parse_args()

    old_cl = load_json(CHANGELOG_FILE)
    old_dm = load_json(DEMOS_FILE)
    new_cl = old_cl
    new_dm = old_dm

    if not args.demos_only:
        new_cl = scrape_changelog(old_cl, force=args.force)

    if not args.changelog_only:
        if args.no_playwright:
            new_dm = scrape_demos_requests_only(old_dm, force=args.force)
        else:
            new_dm = asyncio.run(scrape_demos_with_playwright(old_dm, force=args.force))

    report = report_diff(old_cl, new_cl, old_dm, new_dm)
    print("\n" + report)

    if not args.dry_run:
        save_json(CHANGELOG_FILE, new_cl)
        save_json(DEMOS_FILE, new_dm)
        report_path = DATA_DIR / "last_scrape_report.md"
        report_path.write_text(report)
        print(f"✓ Report → {report_path}")

    print("\n✅ Done!")


if __name__ == "__main__":
    sys.exit(main())
