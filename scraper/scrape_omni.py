#!/usr/bin/env python3
"""
Omni Changelog & Demos Scraper
================================
Scrapes https://omni.co/changelog and https://omni.co/demos
Merges new entries into existing JSON files (no duplicates, no data loss).
Designed to run in GitHub Actions on a weekly cron + manual dispatch.

Usage:
    python scrape_omni.py
    python scrape_omni.py --force   # re-scrape all weeks, not just new ones
    python scrape_omni.py --dry-run # print what would change, don't write files
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
BASE_CHANGELOG = "https://omni.co/changelog"
BASE_DEMOS     = "https://omni.co/demos"
DATA_DIR       = Path(__file__).parent.parent / "data"
CHANGELOG_FILE = DATA_DIR / "omni_changelog.json"
DEMOS_FILE     = DATA_DIR / "omni_demos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OmniChangelogBot/1.0; "
        "+https://github.com/your-org/omni-tracker)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_DELAY = 1.5   # seconds between requests — be polite!
REQUEST_TIMEOUT = 20

# ── Helpers ───────────────────────────────────────────────────────────────────
def fetch(url: str, retries: int = 3) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  ⚠  Attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * 2)
    print(f"  ✗  Could not fetch {url} after {retries} attempts")
    return None


def load_json(path: Path) -> dict:
    """Load existing JSON file or return empty scaffold."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path: Path, data: dict, dry_run: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"  [dry-run] Would write {path}")
        return
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓  Saved {path} ({path.stat().st_size / 1024:.1f} KB)")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_to_date(url: str) -> str | None:
    """Extract YYYYMMDD from a URL like /changelog/20260208 → '2026-02-08'"""
    m = re.search(r"/(\d{8})$", url.rstrip("/"))
    if m:
        raw = m.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def clean_text(el) -> str:
    """Extract and clean text from a BS4 element."""
    return " ".join(el.get_text(" ", strip=True).split())


# ── Changelog scraping ────────────────────────────────────────────────────────
def scrape_changelog_index(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Parse the changelog index page to get a list of all week URLs.
    Returns: [{"week_label": str, "url": str}, ...]
    """
    weeks = []
    seen_urls = set()

    # The current week's content is on the index page itself
    weeks.append({"week_label": "Current week", "url": base_url})
    seen_urls.add(base_url)

    # Look for links to archived weeks — typically /changelog/YYYYMMDD
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Normalize to absolute
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/changelog/\d{8}", href) and href not in seen_urls:
            label_el = a.find_parent(["li", "div", "article"])
            label = clean_text(a) if a.get_text(strip=True) else href
            weeks.append({"week_label": label, "url": href})
            seen_urls.add(href)

    # Also check for a nav/sidebar list of dates
    # Common pattern: <a href="/changelog/20260208">Week of February 8, 2026</a>
    return weeks


def parse_changelog_week(soup: BeautifulSoup, week_url: str) -> list[dict]:
    """
    Parse a single changelog week page into a list of day entries.
    Returns: [{"date": "YYYY-MM-DD", "items": ["text", ...]}, ...]
    """
    days = []
    current_date = None
    current_items = []

    # Omni's changelog uses a consistent structure:
    # Date heading → list of bullet items beneath it
    # We look for elements that look like dates then collect following list items

    date_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{4}",
        re.IGNORECASE,
    )

    # Walk all block-level elements
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "time"]):
        text = clean_text(el)

        # Check if this element is a date heading
        date_match = date_pattern.search(text)
        if date_match and el.name in ("h1", "h2", "h3", "h4", "h5", "time", "p"):
            # Save previous day if we have one
            if current_date and current_items:
                days.append({"date": current_date, "items": current_items})

            # Parse the date
            try:
                parsed = datetime.strptime(
                    date_match.group(0).replace(",", ""), "%B %d %Y"
                )
                current_date = parsed.strftime("%Y-%m-%d")
            except ValueError:
                current_date = None
            current_items = []

        elif current_date and el.name == "li" and len(text) > 15:
            # This is a changelog item under the current date
            # Skip items that are just navigation links
            if not any(nav in text.lower() for nav in ["previous", "next", "week of", "back to"]):
                current_items.append(text)

    # Don't forget the last day
    if current_date and current_items:
        days.append({"date": current_date, "items": current_items})

    return days


def get_existing_changelog_urls(data: dict) -> set[str]:
    """Return set of already-scraped week URLs from existing data."""
    scraped = set()
    for week in data.get("weeks", []):
        if week.get("fully_scraped") and week.get("source_url"):
            scraped.add(week["source_url"])
    return scraped


def get_indexed_changelog_urls(data: dict) -> dict[str, dict]:
    """Return map of url → index entry for already-indexed weeks."""
    return {entry["url"]: entry for entry in data.get("index", [])}


def scrape_changelog(existing: dict, force: bool = False, dry_run: bool = False) -> dict:
    """
    Main changelog scrape. Fetches index, identifies new weeks,
    scrapes them, and merges into existing data.
    """
    print("\n📋 Scraping changelog...")

    # 1. Fetch the index page
    soup = fetch(BASE_CHANGELOG)
    if not soup:
        print("  ✗  Could not fetch changelog index. Aborting changelog scrape.")
        return existing

    # 2. Parse all weeks from the index
    all_weeks = scrape_changelog_index(soup, BASE_CHANGELOG)
    print(f"  Found {len(all_weeks)} weeks in index")

    # 3. Determine which weeks need scraping
    already_scraped = get_existing_changelog_urls(existing) if not force else set()
    already_indexed = get_indexed_changelog_urls(existing)

    # 4. Build updated index (merge new entries)
    updated_index = list(existing.get("index", []))
    new_index_urls = {e["url"] for e in updated_index}

    for week in all_weeks:
        if week["url"] not in new_index_urls:
            updated_index.append(week)
            new_index_urls.add(week["url"])

    # 5. Scrape each week that hasn't been fully scraped yet
    updated_weeks = {w["source_url"]: w for w in existing.get("weeks", []) if "source_url" in w}
    new_weeks_scraped = 0
    weeks_not_yet_scraped = []

    for week in all_weeks:
        url = week["url"]

        if url in already_scraped and not force:
            print(f"  ⏭  Skipping already-scraped: {week['week_label']}")
            continue

        print(f"  🔍 Scraping: {week['week_label']} ({url})")

        # Fetch week page (reuse soup for index page)
        if url == BASE_CHANGELOG:
            week_soup = soup
        else:
            week_soup = fetch(url)

        if not week_soup:
            weeks_not_yet_scraped.append(url)
            continue

        # Parse the week
        days = parse_changelog_week(week_soup, url)

        if not days:
            print(f"    ⚠  No entries parsed from {url} — marking as not scraped")
            weeks_not_yet_scraped.append(url)
            continue

        # Determine week_start date
        week_start = None
        if days:
            # Use the earliest date in the week
            all_dates = [d["date"] for d in days if d.get("date")]
            if all_dates:
                week_start = min(all_dates)

        # Build week entry
        week_entry = {
            "week_start": week_start or url_to_date(url) or "unknown",
            "week_label": week.get("week_label", ""),
            "source_url": url,
            "fully_scraped": True,
            "scraped_at": now_iso(),
            "days": days,
        }

        updated_weeks[url] = week_entry
        new_weeks_scraped += 1
        total_items = sum(len(d["items"]) for d in days)
        print(f"    ✓  {len(days)} days, {total_items} items")

    print(f"\n  Summary: {new_weeks_scraped} new weeks scraped, {len(weeks_not_yet_scraped)} could not be fetched")

    # 6. Assemble final data structure
    result = {
        "meta": {
            "source": BASE_CHANGELOG,
            "last_scraped": now_iso(),
            "scrape_notes": (
                "Auto-scraped by GitHub Action. "
                "Some pages may not be indexable — those are noted in weeks_not_yet_scraped."
            ),
            "total_weeks_indexed": len(updated_index),
            "total_weeks_fully_scraped": len([w for w in updated_weeks.values() if w.get("fully_scraped")]),
            "date_range": existing.get("meta", {}).get("date_range", {}),
        },
        "index": updated_index,
        "weeks": list(updated_weeks.values()),
        "weeks_not_yet_scraped": weeks_not_yet_scraped,
    }

    # Update date range
    all_dates = []
    for w in result["weeks"]:
        for d in w.get("days", []):
            if d.get("date"):
                all_dates.append(d["date"])
    if all_dates:
        result["meta"]["date_range"] = {
            "earliest_indexed": min(all_dates),
            "latest_scraped": max(all_dates),
        }

    return result


# ── Demos scraping ────────────────────────────────────────────────────────────
def scrape_demos_index(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Parse the demos index page."""
    weeks = []
    seen_urls = set()

    # Current week is on the index page
    weeks.append({"date": now_iso()[:10], "week_label": "Current week", "url": base_url})
    seen_urls.add(base_url)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://omni.co" + href
        if re.search(r"/demos/\d{8}", href) and href not in seen_urls:
            label = clean_text(a) if a.get_text(strip=True) else href
            date = url_to_date(href)
            weeks.append({
                "date": date or "",
                "week_label": label,
                "url": href,
            })
            seen_urls.add(href)

    return weeks


def parse_demos_week(soup: BeautifulSoup, week_url: str, week_date: str) -> dict:
    """
    Parse a single demos week page.
    Returns a dict with title, demos list, summary.
    """
    # Extract page title
    title_el = soup.find("h1") or soup.find("h2")
    title = clean_text(title_el) if title_el else ""

    # Extract individual demo entries
    # Omni demos pages typically have: title, description, author, video link
    demos = []
    demo_items = soup.find_all(["article", "section", "li", "div"], class_=re.compile(r"demo|item|card", re.I))

    # If structured items not found, extract bullet points as demo summaries
    if not demo_items:
        bullets = []
        for li in soup.find_all("li"):
            text = clean_text(li)
            if len(text) > 20 and len(text) < 500:
                bullets.append(text)
        if bullets:
            demos = [{"title": b, "description": ""} for b in bullets[:30]]
    else:
        for item in demo_items[:30]:
            title_el = item.find(["h2", "h3", "h4", "strong"])
            desc_el = item.find("p")
            if title_el:
                demos.append({
                    "title": clean_text(title_el),
                    "description": clean_text(desc_el) if desc_el else "",
                })

    # Build a plain-text summary from the page content
    # Take the first few meaningful paragraphs
    summary_parts = []
    for p in soup.find_all("p")[:8]:
        text = clean_text(p)
        if len(text) > 40 and not any(nav in text.lower() for nav in ["cookie", "privacy", "terms"]):
            summary_parts.append(text)

    summary = " ".join(summary_parts[:3]) if summary_parts else ""

    return {
        "date": week_date,
        "url": week_url,
        "fully_scraped": True,
        "scraped_at": now_iso(),
        "title": title,
        "demos": demos,
        "summary": summary[:800] if summary else "",
    }


def scrape_demos(existing: dict, force: bool = False, dry_run: bool = False) -> dict:
    """Main demos scrape."""
    print("\n🎬 Scraping demos...")

    soup = fetch(BASE_DEMOS)
    if not soup:
        print("  ✗  Could not fetch demos index. Aborting demos scrape.")
        return existing

    all_weeks = scrape_demos_index(soup, BASE_DEMOS)
    print(f"  Found {len(all_weeks)} weeks in index")

    # Existing scraped URLs
    existing_detail_urls = {w["url"] for w in existing.get("weeks_detail", [])} if not force else set()
    existing_index_map = {e["url"]: e for e in existing.get("index", [])}

    # Merge index
    updated_index = list(existing.get("index", []))
    indexed_urls = {e["url"] for e in updated_index}

    for week in all_weeks:
        if week["url"] not in indexed_urls:
            updated_index.append({
                "date": week["date"],
                "week_label": week["week_label"],
                "url": week["url"],
                "title": week.get("title", ""),
            })
            indexed_urls.add(week["url"])

    # Scrape detail pages for new weeks only
    updated_details = {w["url"]: w for w in existing.get("weeks_detail", [])}
    new_scraped = 0

    for week in all_weeks[:20]:  # Focus on the 20 most recent
        url = week["url"]
        if url in existing_detail_urls and not force:
            print(f"  ⏭  Skipping: {week['week_label']}")
            continue

        print(f"  🔍 Scraping demos: {week['week_label']} ({url})")
        week_soup = soup if url == BASE_DEMOS else fetch(url)
        if not week_soup:
            continue

        detail = parse_demos_week(week_soup, url, week["date"])

        # Update the index entry with title if we got one
        if detail["title"] and url in {e["url"] for e in updated_index}:
            for entry in updated_index:
                if entry["url"] == url and not entry.get("title"):
                    entry["title"] = detail["title"]

        updated_details[url] = detail
        new_scraped += 1
        print(f"    ✓  {len(detail['demos'])} demos found")

    print(f"\n  Summary: {new_scraped} new demo weeks scraped")

    result = {
        "meta": {
            "source": BASE_DEMOS,
            "last_scraped": now_iso(),
            "scrape_notes": (
                "Auto-scraped by GitHub Action. "
                "Demos are POC/experiments — NOT guaranteed releases. "
                "Cross-reference with omni_changelog.json to determine what shipped."
            ),
            "total_weeks_indexed": len(updated_index),
            "total_weeks_with_detail": len(updated_details),
            "date_range": {
                "earliest": min((e["date"] for e in updated_index if e.get("date")), default=""),
                "latest": max((e["date"] for e in updated_index if e.get("date")), default=""),
            },
            "important_note": (
                "Demos highlight what Omni is working on or experimenting with, "
                "but are NOT a guarantee of release. "
                "Cross-reference with omni_changelog.json to determine what actually shipped."
            ),
        },
        "index": updated_index,
        "weeks_detail": list(updated_details.values()),
    }

    return result


# ── Diff reporting ────────────────────────────────────────────────────────────
def report_diff(old_changelog: dict, new_changelog: dict,
                old_demos: dict,    new_demos: dict) -> str:
    """Generate a human-readable summary of what changed."""
    lines = ["## 🔄 Omni Scraper Update Report", f"*{now_iso()}*", ""]

    # Changelog diff
    old_items = set()
    for w in old_changelog.get("weeks", []):
        for d in w.get("days", []):
            for item in d.get("items", []):
                old_items.add(item[:80])  # use first 80 chars as key

    new_items = []
    for w in new_changelog.get("weeks", []):
        for d in w.get("days", []):
            for item in d.get("items", []):
                if item[:80] not in old_items:
                    new_items.append(f"- `{d['date']}` {item}")

    if new_items:
        lines.append(f"### 📋 New Changelog Entries ({len(new_items)})")
        lines.extend(new_items[:20])
        if len(new_items) > 20:
            lines.append(f"_...and {len(new_items)-20} more_")
        lines.append("")
    else:
        lines.append("### 📋 Changelog — No new entries")
        lines.append("")

    # Demos diff
    old_demo_urls = {e["url"] for e in old_demos.get("index", [])}
    new_demo_urls = {e["url"] for e in new_demos.get("index", [])}
    added_demos = [
        e for e in new_demos.get("index", [])
        if e["url"] not in old_demo_urls
    ]

    if added_demos:
        lines.append(f"### 🎬 New Demo Weeks ({len(added_demos)})")
        for d in added_demos:
            lines.append(f"- `{d.get('date','')}` [{d.get('title','') or d.get('week_label','')}]({d['url']})")
        lines.append("")
    else:
        lines.append("### 🎬 Demos — No new weeks")
        lines.append("")

    # Stats
    lines.append("### 📊 Totals")
    lines.append(f"- Changelog entries: {sum(len(d.get('items',[])) for w in new_changelog.get('weeks',[]) for d in w.get('days',[]))}")
    lines.append(f"- Demo weeks indexed: {len(new_demos.get('index',[]))}")
    lines.append(f"- Demo weeks with detail: {len(new_demos.get('weeks_detail',[]))}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Scrape Omni changelog and demos")
    parser.add_argument("--force",   action="store_true", help="Re-scrape all weeks, not just new ones")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    parser.add_argument("--changelog-only", action="store_true", help="Only scrape changelog")
    parser.add_argument("--demos-only",     action="store_true", help="Only scrape demos")
    args = parser.parse_args()

    if args.force:
        print("⚡ FORCE MODE — re-scraping all weeks")
    if args.dry_run:
        print("🔍 DRY RUN — no files will be written")

    # Load existing data
    old_changelog = load_json(CHANGELOG_FILE)
    old_demos     = load_json(DEMOS_FILE)

    # Scrape
    new_changelog = old_changelog
    new_demos     = old_demos

    if not args.demos_only:
        new_changelog = scrape_changelog(old_changelog, force=args.force, dry_run=args.dry_run)

    if not args.changelog_only:
        new_demos = scrape_demos(old_demos, force=args.force, dry_run=args.dry_run)

    # Report diff
    report = report_diff(old_changelog, new_changelog, old_demos, new_demos)
    print("\n" + report)

    # Save
    if not args.dry_run:
        save_json(CHANGELOG_FILE, new_changelog)
        save_json(DEMOS_FILE, new_demos)

        # Write report to file for GitHub Actions step summary
        report_path = DATA_DIR / "last_scrape_report.md"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\n✓ Report written to {report_path}")

    print("\n✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
