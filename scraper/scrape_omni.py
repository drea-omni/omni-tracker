#!/usr/bin/env python3
"""
Omni Changelog & Demos Scraper — with Playwright for YouTube URLs
==================================================================
Scrapes https://omni.co/changelog and https://omni.co/demos
Uses requests+BeautifulSoup for changelog (fast, no JS needed)
Uses Playwright for demos (needed to extract YouTube embed URLs)

Usage:
    python scrape_omni.py
    python scrape_omni.py --force          # re-scrape all weeks
    python scrape_omni.py --dry-run        # print changes, don't write
    python scrape_omni.py --no-playwright  # skip YouTube extraction (faster)
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

DATA_DIR       = Path(__file__).parent.parent / "data"
CHANGELOG_FILE = DATA_DIR / "omni_changelog.json"
DEMOS_FILE     = DATA_DIR / "omni_demos.json"

BASE_CHANGELOG = "https://omni.co/changelog"
BASE_DEMOS     = "https://omni.co/demos"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OmniChangelogBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}
REQUEST_DELAY   = 1.5
REQUEST_TIMEOUT = 20
PLAYWRIGHT_WAIT = 3000  # ms to wait after page load for iframes to inject


# ── Helpers ────────────────────────────────────────────────────────────────────
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
    print(f"  ✓  Saved {path} ({path.stat().st_size/1024:.1f} KB)")

def fetch_html(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  ⚠  Attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * 2)
    return None


# ── Playwright: YouTube extraction ────────────────────────────────────────────
async def extract_youtube_ids(url, pw):
    """Load a demos page with Playwright and extract all YouTube video IDs."""
    browser = await pw.chromium.launch(headless=True)
    try:
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(PLAYWRIGHT_WAIT)

        # Scroll to trigger any lazy-loaded iframes
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await page.wait_for_timeout(800)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)

        content = await page.content()

        # Extract IDs from all YouTube URL formats
        raw_ids = []
        for pattern in [
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
            r'youtube-nocookie\.com/embed/([a-zA-Z0-9_-]{11})',
        ]:
            raw_ids.extend(re.findall(pattern, content))

        # Deduplicate preserving order
        seen, unique_ids = set(), []
        for vid_id in raw_ids:
            if vid_id not in seen:
                seen.add(vid_id)
                unique_ids.append(vid_id)

        # Grab iframe titles for video labels
        iframes = await page.query_selector_all("iframe[src*='youtube']")
        titles = []
        for frame in iframes:
            title = await frame.get_attribute("title") or ""
            if title:
                titles.append(title)

        return unique_ids, titles

    except Exception as e:
        print(f"  ⚠  Playwright error for {url}: {e}")
        return [], []
    finally:
        await browser.close()


# ── Demos scraping ─────────────────────────────────────────────────────────────
async def scrape_demos_with_playwright(existing, force=False):
    print("\n🎬 Scraping demos with Playwright...")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  ⚠  Playwright not installed — falling back to requests-only")
        return scrape_demos_requests_only(existing, force)

    soup = fetch_html(BASE_DEMOS)
    if not soup:
        print("  ✗  Could not fetch demos index")
        return existing

    # Build week list from index
    all_weeks = [{"date": now_iso()[:10], "week_label": "Current week", "url": BASE_DEMOS}]
    seen_urls = {BASE_DEMOS}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/demos/\d{8}", href) and href not in seen_urls:
            all_weeks.append({
                "date":       url_to_date(href) or "",
                "week_label": clean_text(a),
                "url":        href,
            })
            seen_urls.add(href)

    print(f"  Found {len(all_weeks)} weeks in index")

    # Merge index
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

    # Which weeks need scraping?
    existing_details = {w["url"]: w for w in existing.get("weeks_detail", [])}
    already_scraped  = set(existing_details.keys()) if not force else set()
    to_scrape        = [w for w in all_weeks[:30] if w["url"] not in already_scraped]
    print(f"  {len(to_scrape)} weeks to scrape")

    updated_details = dict(existing_details)

    async with async_playwright() as pw:
        for week in to_scrape:
            url = week["url"]
            print(f"  🎬 {week['week_label']} ({url})")

            yt_ids, yt_titles = await extract_youtube_ids(url, pw)
            print(f"     ✓  {len(yt_ids)} videos found")

            # Get text summary via requests
            week_soup = fetch_html(url)
            title, summary = "", ""
            if week_soup:
                title_el = week_soup.find("h1") or week_soup.find("h2")
                title    = clean_text(title_el) if title_el else ""
                paras    = [clean_text(p) for p in week_soup.find_all("p")[:6]
                            if len(clean_text(p)) > 40]
                summary  = " ".join(paras[:3])[:800]

            videos = [
                {
                    "youtube_id":  vid_id,
                    "youtube_url": f"https://www.youtube.com/watch?v={vid_id}",
                    "embed_url":   f"https://www.youtube.com/embed/{vid_id}",
                    "title":       yt_titles[i] if i < len(yt_titles) else "",
                    "thumbnail":   f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                }
                for i, vid_id in enumerate(yt_ids)
            ]

            updated_details[url] = {
                "date":          week["date"],
                "url":           url,
                "fully_scraped": True,
                "scraped_at":    now_iso(),
                "title":         title,
                "summary":       summary,
                "video_count":   len(videos),
                "videos":        videos,
            }

            # Backfill title into index
            for entry in updated_index:
                if entry["url"] == url and title and not entry.get("title"):
                    entry["title"] = title

    total_videos = sum(len(d.get("videos", [])) for d in updated_details.values())
    print(f"\n  Done — {total_videos} total videos indexed")

    return {
        "meta": {
            "source":                  BASE_DEMOS,
            "last_scraped":            now_iso(),
            "scrape_method":           "playwright+requests",
            "scrape_notes":            "Playwright extracts individual YouTube URLs per demo entry.",
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
    print("\n🎬 Scraping demos (requests-only)...")
    soup = fetch_html(BASE_DEMOS)
    if not soup:
        return existing

    updated_index  = list(existing.get("index", []))
    indexed_urls   = {e["url"] for e in updated_index}

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
            })
            indexed_urls.add(href)

    return {
        **existing,
        "index": updated_index,
        "meta":  {**existing.get("meta", {}), "last_scraped": now_iso()},
    }


# ── Changelog scraping ─────────────────────────────────────────────────────────
def scrape_changelog(existing, force=False):
    print("\n📋 Scraping changelog...")

    soup = fetch_html(BASE_CHANGELOG)
    if not soup:
        return existing

    all_weeks = [{"week_label": "Current week", "url": BASE_CHANGELOG}]
    seen = {BASE_CHANGELOG}
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
    updated_weeks = {w["source_url"]: w for w in existing.get("weeks", []) if "source_url" in w}
    updated_index = list(existing.get("index", []))
    indexed_urls  = {e["url"] for e in updated_index}

    for week in all_weeks:
        if week["url"] not in indexed_urls:
            updated_index.append(week)
            indexed_urls.add(week["url"])

    date_pat = re.compile(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},?\s+\d{4}", re.I)

    new_scraped = 0
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
        new_scraped += 1
        print(f"    ✓  {len(days)} days, {sum(len(d['items']) for d in days)} items")

    all_dates = [d["date"] for w in updated_weeks.values()
                 for d in w.get("days", []) if d.get("date")]
    return {
        "meta": {
            "source":                    BASE_CHANGELOG,
            "last_scraped":              now_iso(),
            "total_weeks_indexed":       len(updated_index),
            "total_weeks_fully_scraped": len([w for w in updated_weeks.values() if w.get("fully_scraped")]),
            "date_range": {
                "earliest_indexed": min(all_dates) if all_dates else "",
                "latest_scraped":   max(all_dates) if all_dates else "",
            },
        },
        "index":                 updated_index,
        "weeks":                 list(updated_weeks.values()),
        "weeks_not_yet_scraped": [],
    }


# ── Diff report ────────────────────────────────────────────────────────────────
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

    total_vids = sum(len(d.get("videos", [])) for d in new_dm.get("weeks_detail", []))
    lines += [
        "### 📊 Totals",
        f"- Changelog entries: {sum(len(d.get('items',[])) for w in new_cl.get('weeks',[]) for d in w.get('days',[]))}",
        f"- Demo weeks indexed: {len(new_dm.get('index', []))}",
        f"- YouTube videos indexed: {total_vids}",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",          action="store_true")
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--changelog-only", action="store_true")
    parser.add_argument("--demos-only",     action="store_true")
    parser.add_argument("--no-playwright",  action="store_true")
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
