#!/usr/bin/env python3
"""
Fetches recent quant-ph papers from arXiv and filters for those
with authors affiliated with the Institute for Quantum Computing (IQC)
at the University of Waterloo. Outputs an RSS feed and JSON file.
"""

import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Configuration — edit these to adjust filtering behaviour
# ---------------------------------------------------------------------------

# At least one of these strings must appear (case-insensitive) in the
# affiliation or abstract text for a paper to be included.
AFFILIATION_KEYWORDS = [
    "Institute for Quantum Computing",
    "IQC",
]

# These are secondary/supporting keywords — a paper matching ONLY these
# (without any primary keyword) is NOT included, to reduce false positives.
# Remove this list entirely if you want broader matching.
SECONDARY_KEYWORDS = [
    "University of Waterloo",
    "Waterloo",
    "Perimeter Institute",
]

# How many papers to fetch per paginated request
MAX_RESULTS = 300

# For the initial backfill, how many pages to fetch (300 × 5 = 1500 papers ≈ 1 month)
# After the first run, only 1 page is needed to catch new daily submissions.
BACKFILL_PAGES = 5

# Maximum number of papers to keep in the feed (most recent first).
MAX_FEED_ITEMS = 200

# Output directory (relative to this script).
OUTPUT_DIR = Path(__file__).parent / "docs"

# ---------------------------------------------------------------------------

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"

ET.register_namespace("", ATOM_NS)
ET.register_namespace("arxiv", ARXIV_NS)


def fetch_arxiv(start: int = 0) -> ET.Element:
    params = urllib.parse.urlencode({
        "search_query": "cat:quant-ph",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": MAX_RESULTS,
        "start": start,
    })
    url = f"{ARXIV_API}?{params}"
    print(f"  Fetching: {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        return ET.fromstring(resp.read())


def get_text(element, tag, ns=ATOM_NS):
    el = element.find(f"{{{ns}}}{tag}")
    return el.text.strip() if el is not None and el.text else ""


def get_affiliations(entry: ET.Element) -> list[str]:
    affs = []
    for author in entry.findall(f"{{{ATOM_NS}}}author"):
        for aff in author.findall(f"{{{ARXIV_NS}}}affiliation"):
            if aff.text:
                affs.append(aff.text.strip())
    return affs


def get_authors(entry: ET.Element) -> list[dict]:
    authors = []
    for author in entry.findall(f"{{{ATOM_NS}}}author"):
        name = get_text(author, "name")
        affs = [
            aff.text.strip()
            for aff in author.findall(f"{{{ARXIV_NS}}}affiliation")
            if aff.text
        ]
        authors.append({"name": name, "affiliations": affs})
    return authors


def matches_iqc(entry: ET.Element) -> tuple[bool, list[str]]:
    """
    Returns (is_match, matched_keywords).
    Searches author affiliations and the abstract text.
    """
    summary = get_text(entry, "summary")
    affiliations = get_affiliations(entry)
    search_text = " ".join(affiliations) + " " + summary
    search_lower = search_text.lower()

    matched = [
        kw for kw in AFFILIATION_KEYWORDS
        if kw.lower() in search_lower
    ]
    if matched:
        return True, matched

    # Secondary keywords only count if at least one primary keyword is *also*
    # present anywhere including the title (slightly wider search for abstract).
    title = get_text(entry, "title")
    wide_text = (search_text + " " + title).lower()
    secondary_hits = [kw for kw in SECONDARY_KEYWORDS if kw.lower() in wide_text]
    # Secondary-only matches are excluded to avoid false positives.
    return False, []


def parse_entry(entry: ET.Element) -> dict | None:
    arxiv_id_url = get_text(entry, "id")
    arxiv_id = arxiv_id_url.split("/abs/")[-1]

    is_match, matched_kws = matches_iqc(entry)
    if not is_match:
        return None

    authors = get_authors(entry)
    published = get_text(entry, "published")
    updated = get_text(entry, "updated")
    title = re.sub(r"\s+", " ", get_text(entry, "title"))
    summary = re.sub(r"\s+", " ", get_text(entry, "summary"))

    # Find which authors have IQC affiliations
    iqc_authors = []
    for a in authors:
        aff_text = " ".join(a["affiliations"]).lower()
        if any(kw.lower() in aff_text for kw in AFFILIATION_KEYWORDS + SECONDARY_KEYWORDS):
            iqc_authors.append(a["name"])

    categories = [
        el.get("term", "")
        for el in entry.findall(f"{{{ATOM_NS}}}category")
    ]

    return {
        "id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "title": title,
        "summary": summary,
        "authors": authors,
        "iqc_authors": iqc_authors,
        "published": published,
        "updated": updated,
        "categories": categories,
        "matched_keywords": matched_kws,
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
        iqc_note = ""
        if p["iqc_authors"]:
            iqc_note = f"\n\n🔬 IQC-affiliated authors: {', '.join(p['iqc_authors'])}"
        pub_date = ""
        if p["published"]:
            try:
                dt = datetime.fromisoformat(p["published"].replace("Z", "+00:00"))
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                pub_date = now

        desc = p["summary"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        iqc_note_escaped = iqc_note.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        items.append(f"""    <item>
      <title>{p["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</title>
      <link>{p["url"]}</link>
      <guid isPermaLink="true">{p["url"]}</guid>
      <pubDate>{pub_date}</pubDate>
      <author>{author_names}</author>
      <description>{desc}{iqc_note_escaped}</description>
    </item>""")

    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>IQC arXiv Feed — quant-ph</title>
    <link>https://arxiv.org/list/quant-ph/recent</link>
    <description>Recent quant-ph papers with authors affiliated with the Institute for Quantum Computing (IQC), University of Waterloo.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <ttl>360</ttl>
{items_xml}
  </channel>
</rss>"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "papers.json"
    rss_path = OUTPUT_DIR / "feed.xml"

    # Load previously seen papers (for deduplication)
    existing = load_existing(json_path)
    print(f"Loaded {len(existing)} existing papers.")

    print("Fetching from arXiv...")
    entries = []
    is_first_run = len(existing) == 0
    pages = BACKFILL_PAGES if is_first_run else 1
    for page in range(pages):
        root = fetch_arxiv(start=page * MAX_RESULTS)
        batch = root.findall(f"{{{ATOM_NS}}}entry")
        entries.extend(batch)
        print(f"  Page {page+1}: got {len(batch)} entries")
        if len(batch) < MAX_RESULTS:
            break  # no more results
    
    print(f"Got {len(entries)} entries from arXiv.")

    new_count = 0
    for entry in entries:
        paper = parse_entry(entry)
        if paper and paper["id"] not in existing:
            existing[paper["id"]] = paper
            new_count += 1

    print(f"Found {new_count} new IQC-affiliated papers.")

    # Sort by published date descending, keep up to MAX_FEED_ITEMS
    all_papers = sorted(
        existing.values(),
        key=lambda p: p.get("published", ""),
        reverse=True,
    )[:MAX_FEED_ITEMS]

    # Write JSON
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "total": len(all_papers),
        "papers": all_papers,
    }
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {json_path}")

    # Write RSS
    rss = build_rss(all_papers)
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Wrote {rss_path}")
    print("Done.")


if __name__ == "__main__":
    main()
