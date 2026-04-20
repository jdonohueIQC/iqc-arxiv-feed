#!/usr/bin/env python3
"""
Fetches arXiv papers by University of Waterloo authors from OpenAlex,
filtered to those hosted on arXiv. Outputs an RSS feed and JSON file
for the IQC arXiv feed GitHub Pages site.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — edit these to adjust behaviour
# ---------------------------------------------------------------------------

# OpenAlex institution ID for University of Waterloo.
# Look up others at https://openalex.org/institutions
INSTITUTION_ID = "I141945490"

# Your email — OpenAlex gives faster "polite pool" responses when provided.
MAILTO = "your@email.com"

# How many days back to fetch on the very first run (backfill).
BACKFILL_DAYS = 60

# How many days back to fetch on regular daily runs.
# Set wider than 1 to account for OpenAlex indexing lag on new preprints.
LOOKBACK_DAYS = 7

# Maximum number of papers to keep in the feed (most recent first).
MAX_FEED_ITEMS = 200

# Output directory (relative to this script).
OUTPUT_DIR = Path(__file__).parent / "docs"

# ---------------------------------------------------------------------------

OPENALEX_API = "https://api.openalex.org/works"

# OpenAlex source ID for arXiv — filters results to arXiv-hosted papers only.
ARXIV_SOURCE_ID = "s4306400194"


def fetch_page(from_date: str, page: int = 1) -> dict:
    params = urllib.parse.urlencode({
        # Filter by: UWaterloo institution AND hosted on arXiv AND published since from_date.
        # No topic/field filter — catches all subjects (quant-ph, cs, math, etc.)
        # so IQC papers aren't excluded by OpenAlex's topic classification.
        "filter": (
            f"authorships.institutions.id:{INSTITUTION_ID},"
            f"locations.source.id:{ARXIV_SOURCE_ID},"
            f"from_publication_date:{from_date}"
        ),
        "sort": "publication_date:desc",
        "per_page": 100,
        "page": page,
        "mailto": MAILTO,
    })
    url = f"{OPENALEX_API}?{params}"
    print(f"  Fetching page {page}: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"IQC-arXiv-Feed/1.0 (mailto:{MAILTO})"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def extract_arxiv_id(work: dict) -> str | None:
    """Extract arXiv ID from a work's locations and ids fields."""
    # Check ids block first (most reliable)
    ids = work.get("ids", {})
    if "arxiv" in ids:
        raw = ids["arxiv"]
        return raw.replace("https://arxiv.org/abs/", "").strip()

    # Fall back to scanning all locations
    for loc in work.get("locations", []) + [
        work.get("primary_location") or {},
        work.get("best_oa_location") or {},
    ]:
        url = loc.get("landing_page_url") or ""
        if "arxiv.org/abs/" in url:
            return url.split("arxiv.org/abs/")[-1].strip()

    return None


def to_paper(work: dict) -> dict | None:
    arxiv_id = extract_arxiv_id(work)
    if not arxiv_id:
        return None

    authors = []
    iqc_authors = []
    for auth in work.get("authorships", []):
        name = auth.get("author", {}).get("display_name", "")
        institutions = auth.get("institutions", [])
        inst_names = [i.get("display_name", "") for i in institutions]
        inst_ids = [i.get("id", "") for i in institutions]
        is_waterloo = any(INSTITUTION_ID in i for i in inst_ids)
        authors.append({"name": name, "affiliations": inst_names})
        if is_waterloo:
            iqc_authors.append(name)

    published = work.get("publication_date") or ""
    title = work.get("title") or ""
    summary = work.get("abstract") or "Abstract not available."
    topic = (work.get("primary_topic") or {}).get("display_name", "")

    return {
        "id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "title": title,
        "summary": summary,
        "authors": authors,
        "iqc_authors": iqc_authors,
        "published": published,
        "updated": work.get("updated_date") or published,
        "categories": [topic] if topic else [],
        "matched_keywords": ["University of Waterloo (OpenAlex)"],
    }


def load_existing(json_path: Path) -> dict:
    if json_path.exists():
        with open(json_path) as f:
            return {p["id"]: p for p in json.load(f).get("papers", [])}
    return {}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_rss(papers: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for p in papers:
        author_names = ", ".join(a["name"] for a in p["authors"])
        iqc_note = ""
        if p["iqc_authors"]:
            iqc_note = f"\n\nIQC-affiliated authors: {', '.join(p['iqc_authors'])}"
        try:
            dt = datetime.fromisoformat(p["published"])
            pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub_date = now

        items.append(f"""    <item>
      <title>{esc(p["title"])}</title>
      <link>{p["url"]}</link>
      <guid isPermaLink="true">{p["url"]}</guid>
      <pubDate>{pub_date}</pubDate>
      <author>{esc(author_names)}</author>
      <description>{esc(p["summary"])}{esc(iqc_note)}</description>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>IQC arXiv Feed</title>
    <link>https://arxiv.org/list/quant-ph/recent</link>
    <description>arXiv papers by University of Waterloo / IQC authors.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <ttl>360</ttl>
{chr(10).join(items)}
  </channel>
</rss>"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "papers.json"
    rss_path = OUTPUT_DIR / "feed.xml"

    existing = load_existing(json_path)
    is_first_run = len(existing) == 0
    print(f"Loaded {len(existing)} existing papers. First run: {is_first_run}")

    days_back = BACKFILL_DAYS if is_first_run else LOOKBACK_DAYS
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    print(f"Fetching OpenAlex works since {from_date}...")

    new_count = 0
    page = 1
    while True:
        data = fetch_page(from_date, page)
        results = data.get("results", [])
        if not results:
            break

        for work in results:
            paper = to_paper(work)
            if paper and paper["id"] not in existing:
                existing[paper["id"]] = paper
                new_count += 1

        total = data.get("meta", {}).get("count", 0)
        fetched_so_far = (page - 1) * 100 + len(results)
        print(f"  Page {page}: {len(results)} results ({fetched_so_far}/{total} total)")

        if fetched_so_far >= total or len(results) < 100:
            break
        page += 1

    print(f"Found {new_count} new papers.")

    all_papers = sorted(
        existing.values(),
        key=lambda p: p.get("published", ""),
        reverse=True,
    )[:MAX_FEED_ITEMS]

    with open(json_path, "w") as f:
        json.dump({
            "updated": datetime.now(timezone.utc).isoformat(),
            "total": len(all_papers),
            "papers": all_papers,
        }, f, indent=2)
    print(f"Wrote {json_path}")

    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(build_rss(all_papers))
    print(f"Wrote {rss_path}")
    print("Done.")


if __name__ == "__main__":
    main()
