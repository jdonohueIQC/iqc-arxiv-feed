#!/usr/bin/env python3
"""
Fetches recent quant-ph papers from OpenAlex filtered by IQC/UWaterloo affiliation.
OpenAlex has curated institution data, making affiliation filtering much more reliable
than the arXiv Atom API which often omits affiliation fields.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "docs"
MAX_FEED_ITEMS = 200

# OpenAlex institution ID for University of Waterloo
# Find others at https://openalex.org/institutions
INSTITUTION_ID = "I141945490"  # University of Waterloo

# How many days back to look on a backfill run (when papers.json doesn't exist yet)
BACKFILL_DAYS = 90

OPENALEX_API = "https://api.openalex.org/works"
# Polite pool: include your email so OpenAlex gives you faster responses
MAILTO = "your@email.com"  # <-- change this


def fetch_page(from_date: str, page: int = 1) -> dict:
    params = urllib.parse.urlencode({
        "filter": f"authorships.institutions.id:{INSTITUTION_ID},primary_topic.field.id:fields/26,from_publication_date:{from_date}",
        "sort": "publication_date:desc",
        "per_page": 100,
        "page": page,
        "mailto": MAILTO,
    })
    url = f"{OPENALEX_API}?{params}"
    print(f"  Fetching page {page}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"IQC-arXiv-Feed/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def to_paper(work: dict) -> dict | None:
    # Only include works that have an arXiv ID
    arxiv_id = None
    for loc in work.get("locations", []):
        src = loc.get("source") or {}
        if src.get("id") == "https://openalex.org/S4306400194":  # arXiv source
            url = loc.get("landing_page_url", "")
            if "arxiv.org/abs/" in url:
                arxiv_id = url.split("arxiv.org/abs/")[-1]
                break
    # Also check primary_location and best_oa_location
    for key in ("primary_location", "best_oa_location"):
        loc = work.get(key) or {}
        url = loc.get("landing_page_url", "") or ""
        if "arxiv.org/abs/" in url and not arxiv_id:
            arxiv_id = url.split("arxiv.org/abs/")[-1]

    if not arxiv_id:
        # Try the doi or ids block
        ids = work.get("ids", {})
        if "arxiv" in ids:
            arxiv_id = ids["arxiv"].replace("https://arxiv.org/abs/", "")

    if not arxiv_id:
        return None  # skip non-arXiv works

    authors = []
    iqc_authors = []
    for auth in work.get("authorships", []):
        name = auth.get("author", {}).get("display_name", "")
        inst_names = [i.get("display_name", "") for i in auth.get("institutions", [])]
        inst_ids = [i.get("id", "") for i in auth.get("institutions", [])]
        is_waterloo = any(INSTITUTION_ID in i for i in inst_ids)
        authors.append({"name": name, "affiliations": inst_names})
        if is_waterloo:
            iqc_authors.append(name)

    return {
        "id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "title": work.get("title") or "",
        "summary": (work.get("abstract") or "Abstract not available."),
        "authors": authors,
        "iqc_authors": iqc_authors,
        "published": work.get("publication_date") or "",
        "updated": work.get("updated_date") or "",
        "categories": [work.get("primary_topic", {}).get("display_name", "")],
        "matched_keywords": ["University of Waterloo (OpenAlex)"],
    }


def load_existing(json_path: Path) -> dict:
    if json_path.exists():
        with open(json_path) as f:
            return {p["id"]: p for p in json.load(f).get("papers", [])}
    return {}


def build_rss(papers: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for p in papers:
        author_names = ", ".join(a["name"] for a in p["authors"])
        iqc_note = f"\n\nIQC-affiliated authors: {', '.join(p['iqc_authors'])}" if p["iqc_authors"] else ""
        try:
            dt = datetime.fromisoformat(p["published"])
            pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub_date = now
        def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
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
    <title>IQC arXiv Feed — quant-ph</title>
    <link>https://arxiv.org/list/quant-ph/recent</link>
    <description>Recent quant-ph papers with authors affiliated with the Institute for Quantum Computing (IQC), University of Waterloo.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <ttl>360</ttl>
{"".join(items)}
  </channel>
</rss>"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "papers.json"
    rss_path = OUTPUT_DIR / "feed.xml"

    existing = load_existing(json_path)
    is_first_run = len(existing) == 0
    print(f"Loaded {len(existing)} existing papers. First run: {is_first_run}")

    if is_first_run:
        from_date = (datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)).strftime("%Y-%m-%d")
    else:
        from_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")

    print(f"Fetching works from OpenAlex since {from_date}...")
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
    all_papers = sorted(existing.values(), key=lambda p: p.get("published", ""), reverse=True)[:MAX_FEED_ITEMS]

    with open(json_path, "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "total": len(all_papers), "papers": all_papers}, f, indent=2)
    print(f"Wrote {json_path}")

    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(build_rss(all_papers))
    print(f"Wrote {rss_path}")
    print("Done.")


if __name__ == "__main__":
    main()
