#!/usr/bin/env python3
"""
Fetches arXiv papers by a specific list of tracked authors, using OpenAlex
to resolve author IDs and retrieve their works.

To add or remove authors, edit the AUTHORS list below.
Run locally with: python fetch_papers.py
"""

import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# AUTHORS — edit this list to track different people.
#
# openalex_id can be:
#   - A string:  "A1234567890"
#   - A list:    ["A1234567890", "A9876543210"]  (use when one person has
#                multiple OpenAlex records, e.g. Bradley Hauer)
#   - None:      auto-resolved by name on first run; check the Action log
#                to confirm the right person was picked, then paste the ID in.
#
# To find an author's OpenAlex ID: https://openalex.org/authors?search=<name>
# ---------------------------------------------------------------------------

AUTHORS = [
    {"name": "David Cory",            "openalex_id": "A5033501753"},
    {"name": "Christine Muschik",     "openalex_id": "A5021091852"},
    {"name": "Alan Jamison",          "openalex_id": {"A5020327774", "A5120643698"},
    {"name": "Dmitry Pushin",         "openalex_id": "A5071074359"},
    {"name": "Michal Bajcsy",         "openalex_id": "A5029299711"},
    {"name": "Michele Mosca",         "openalex_id": "A5009567571"},
    {"name": "John Donohue",          "openalex_id": "A5006621633"},
    {"name": "Raymond Laflamme",      "openalex_id": "A5110723059"},
    {"name": "Bradley Hauer",         "openalex_id": ["A5133888074", "A5058034795"]},  # two OA records
    {"name": "Luke Schaeffer",        "openalex_id": "A5114470241"},
    {"name": "Graeme Smith",          "openalex_id": "A5111460938"},
    {"name": "Shalev Ben-David",      "openalex_id": "A5010258967"},
    {"name": "Crystal Senko",         "openalex_id": "A5054684488"},
    {"name": "Rajibul Islam",         "openalex_id": "A5053336892"},
    {"name": "David Gosset",          "openalex_id": "A5103184148"},
    {"name": "Matteo Mariantoni",     "openalex_id": "A5008314339"},
    {"name": "Jonathan Baugh",        "openalex_id": "A5020853148"},
    {"name": "Richard Cleve",         "openalex_id": "A5001743971"},
    {"name": "Raffi Budakian",        "openalex_id": "A5044506827"},
    {"name": "Joseph Emerson",        "openalex_id": "A5112868557"},
    {"name": "Na Young Kim",          "openalex_id": "A5100434951"},
    {"name": "Debbie Leung",          "openalex_id": "A5057755410"},
    {"name": "Adrian Lupascu",        "openalex_id": "A5049962944"},
    {"name": "Guo-Xing Miao",         "openalex_id": "A5120980527"},
    {"name": "Ashwin Nayak",          "openalex_id": "A5017951192"},
    {"name": "Michael Reimer",        "openalex_id": {"A5051932856","A5122652625"}, 
    {"name": "Kevin Resch",           "openalex_id": "A5102053353"},
    {"name": "William Slofstra",      "openalex_id": "A5102809836"},
    {"name": "Adam Tsen",             "openalex_id": "A5038704910"},
    {"name": "Christopher Wilson",    "openalex_id": "A5076530713"},
    {"name": "Alexandre Cooper-Roy",  "openalex_id": "A5120080445"},
    {"name": "George Nichols",        "openalex_id": "A5067202240"},
    {"name": "Thomas Jennewein",      "openalex_id": "A5055373870"},
    {"name": "Norbert Lutkenhaus",    "openalex_id": "A5076065879"},
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAILTO        = "jdonohue@uwaterloo.ca"
BACKFILL_DAYS = 350   # days back on very first run
LOOKBACK_DAYS = 14    # days back on regular daily runs
MAX_FEED_ITEMS = 200
OUTPUT_DIR         = Path(__file__).parent / "docs"
AUTHOR_CACHE_PATH  = Path(__file__).parent / "author_ids.json"

# ---------------------------------------------------------------------------

OPENALEX_AUTHORS_API = "https://api.openalex.org/authors"
OPENALEX_WORKS_API   = "https://api.openalex.org/works"
ARXIV_API            = "https://export.arxiv.org/api/query"
ARXIV_SOURCE_ID      = "s4306400194"


def openalex_get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"IQC-arXiv-Feed/1.0 (mailto:{MAILTO})"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def normalize_ids(raw) -> list[str]:
    """Accept a string, list of strings, or None; always return a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if x]
    return [raw]


def resolve_author_id(name: str) -> str | None:
    """Search OpenAlex for an author by name and return their ID."""
    params = urllib.parse.urlencode({"search": name, "per_page": 5})
    url = f"{OPENALEX_AUTHORS_API}?{params}&mailto={MAILTO}"
    print(f"  Searching OpenAlex for author: {name}")
    data = openalex_get(url)
    results = data.get("results", [])
    if not results:
        print(f"  WARNING: No OpenAlex author found for '{name}'")
        return None

    best = results[0]
    author_id = best["id"].replace("https://openalex.org/", "")
    institution = ""
    for inst in best.get("affiliations", []):
        institution = inst.get("institution", {}).get("display_name", "")
        break
    print(f"  Resolved '{name}' → {author_id} (last known: {institution})")
    if len(results) > 1:
        print(f"  Other candidates:")
        for r in results[1:]:
            alt_id = r["id"].replace("https://openalex.org/", "")
            alt_inst = ""
            for inst in r.get("affiliations", []):
                alt_inst = inst.get("institution", {}).get("display_name", "")
                break
            print(f"    {alt_id} — {r.get('display_name')} ({alt_inst})")
        print(f"  If wrong, set openalex_id manually in AUTHORS.")
    return author_id


def load_author_cache() -> dict:
    if AUTHOR_CACHE_PATH.exists():
        with open(AUTHOR_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_author_cache(cache: dict):
    with open(AUTHOR_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def resolve_all_authors() -> list[dict]:
    """
    Return a flat list of {name, openalex_id} dicts, one per ID.
    Authors with multiple IDs appear multiple times (one per ID),
    so each ID gets its own fetch loop.
    """
    cache = load_author_cache()
    resolved = []
    seen_names = set()
    cache_dirty = False

    for author in AUTHORS:
        name = author["name"]
        if name in seen_names:
            print(f"  Skipping duplicate name entry: {name}")
            continue
        seen_names.add(name)

        ids = normalize_ids(author.get("openalex_id"))

        if not ids:
            # Try cache first, then live lookup
            cached = cache.get(name)
            if cached:
                ids = normalize_ids(cached)
            else:
                oa_id = resolve_author_id(name)
                if oa_id:
                    ids = [oa_id]
                    cache[name] = oa_id
                    cache_dirty = True

        for oa_id in ids:
            print(f"  {name}: {oa_id}")
            resolved.append({"name": name, "openalex_id": oa_id})

    if cache_dirty:
        save_author_cache(cache)

    return resolved


def fetch_works_for_author(openalex_id: str, from_date: str, page: int = 1) -> dict:
    # Note: no source filter here — we filter for arXiv IDs in extract_arxiv_id()
    # instead. Filtering by source would miss papers where OpenAlex's primary
    # location is a journal (e.g. cond-mat papers that are also on arXiv).
    params = urllib.parse.urlencode({
        "filter": (
            f"authorships.author.id:{openalex_id},"
            f"from_publication_date:{from_date}"
        ),
        "sort": "publication_date:desc",
        "per_page": 100,
        "page": page,
        "mailto": MAILTO,
    })
    url = f"{OPENALEX_WORKS_API}?{params}"
    return openalex_get(url)


def arxiv_search_by_name(name: str, from_date: str) -> list[str]:
    """
    Fallback: search arXiv by author name for recent papers.
    Catches papers OpenAlex hasn't linked to an author record yet.
    Searches by full name in quotes for precision; falls back to lastname only.
    """
    # Try quoted full name first for precision, then lastname-only as fallback
    parts = name.strip().split()
    lastname = parts[-1]
    firstname = parts[0] if len(parts) > 1 else ""
    # arXiv author search: "Firstname Lastname" or just Lastname
    search_term = f'"{firstname}+{lastname}"' if firstname else lastname
    query = urllib.parse.urlencode({
        "search_query": f"au:{lastname}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 200,
    })
    url = f"{ARXIV_API}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            xml = resp.read().decode()
    except Exception as e:
        print(f"    arXiv fallback failed for {name}: {e}")
        return []

    entries = re.findall(
        r'<id>(https://arxiv\.org/abs/[^<]+)</id>.*?<published>([^<]+)</published>',
        xml, re.DOTALL,
    )
    cutoff = datetime.fromisoformat(from_date)
    results = []
    for arxiv_url, pub_str in entries:
        try:
            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
            if pub_dt >= cutoff:
                results.append(arxiv_url.replace("https://arxiv.org/abs/", "").strip())
        except Exception:
            continue
    return results


def fetch_openalex_by_arxiv_id(arxiv_id: str) -> dict | None:
    url = f"{OPENALEX_WORKS_API}/https://arxiv.org/abs/{arxiv_id}?mailto={MAILTO}"
    try:
        return openalex_get(url)
    except Exception:
        return None


def extract_arxiv_id(work: dict) -> str | None:
    ids = work.get("ids", {})
    if "arxiv" in ids:
        return ids["arxiv"].replace("https://arxiv.org/abs/", "").strip()
    for loc in (work.get("locations") or []) + [
        work.get("primary_location") or {},
        work.get("best_oa_location") or {},
    ]:
        url = loc.get("landing_page_url") or ""
        if "arxiv.org/abs/" in url:
            return url.split("arxiv.org/abs/")[-1].strip()
    return None


def to_paper(work: dict, tracked_ids: dict[str, str]) -> dict | None:
    arxiv_id = extract_arxiv_id(work)
    if not arxiv_id:
        return None

    authors = []
    iqc_authors = []
    seen_tracked = set()
    for auth in work.get("authorships", []):
        raw_id = (auth.get("author") or {}).get("id") or ""
        short_id = raw_id.replace("https://openalex.org/", "")
        name = (auth.get("author") or {}).get("display_name", "")
        inst_names = [i.get("display_name", "") for i in auth.get("institutions", [])]
        authors.append({"name": name, "affiliations": inst_names})
        if short_id and short_id in tracked_ids:
            display = tracked_ids[short_id]
            if display not in seen_tracked:
                iqc_authors.append(display)
                seen_tracked.add(display)

    topic = (work.get("primary_topic") or {}).get("display_name", "")
    published = work.get("publication_date") or ""

    return {
        "id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "title": work.get("title") or "",
        "summary": work.get("abstract") or "Abstract not available.",
        "authors": authors,
        "iqc_authors": iqc_authors,
        "published": published,
        "updated": work.get("updated_date") or published,
        "categories": [topic] if topic else [],
        "matched_keywords": ["tracked author"],
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
        iqc_note = f"\n\nTracked authors: {', '.join(p['iqc_authors'])}" if p["iqc_authors"] else ""
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
    <description>arXiv papers by tracked IQC authors.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <ttl>360</ttl>
{chr(10).join(items)}
  </channel>
</rss>"""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "papers.json"
    rss_path  = OUTPUT_DIR / "feed.xml"

    existing = load_existing(json_path)
    is_first_run = len(existing) == 0
    print(f"Loaded {len(existing)} existing papers. First run: {is_first_run}")

    print("Resolving author IDs...")
    resolved_authors = resolve_all_authors()
    if not resolved_authors:
        print("No authors resolved — check your AUTHORS list and network access.")
        return

    # Map every openalex_id -> display name (multiple IDs can map to same name)
    tracked_ids = {a["openalex_id"]: a["name"] for a in resolved_authors}
    # Deduplicated list of unique (name, id) pairs for the fetch loop
    seen_ids = set()
    unique_authors = []
    for a in resolved_authors:
        if a["openalex_id"] not in seen_ids:
            seen_ids.add(a["openalex_id"])
            unique_authors.append(a)
    print(f"Tracking {len(unique_authors)} author IDs across {len({a['name'] for a in unique_authors})} people.")

    days_back = BACKFILL_DAYS if is_first_run else LOOKBACK_DAYS
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    print(f"Fetching works since {from_date}...")

    new_count = 0

    # --- Primary pass: OpenAlex by author ID ---
    for author in unique_authors:
        print(f"  OpenAlex: {author['name']} ({author['openalex_id']})...")
        page = 1
        while True:
            data = fetch_works_for_author(author["openalex_id"], from_date, page)
            results = data.get("results", [])
            if not results:
                break
            for work in results:
                paper = to_paper(work, tracked_ids)
                if paper and paper["id"] not in existing:
                    existing[paper["id"]] = paper
                    new_count += 1
            total = data.get("meta", {}).get("count", 0)
            fetched = (page - 1) * 100 + len(results)
            print(f"    Page {page}: {len(results)} works ({fetched}/{total})")
            if fetched >= total or len(results) < 100:
                break
            page += 1

    # --- Fallback pass: arXiv direct search (catches OpenAlex indexing lag) ---
    # Deduplicate by name so we don't double-search for multi-ID authors
    seen_names = set()
    fallback_days = min(days_back, 30)
    fallback_date = (datetime.now(timezone.utc) - timedelta(days=fallback_days)).strftime("%Y-%m-%d")
    print(f"\nFallback arXiv search (last {fallback_days} days)...")
    for author in unique_authors:
        if author["name"] in seen_names:
            continue
        seen_names.add(author["name"])
        candidate_ids = arxiv_search_by_name(author["name"], fallback_date)
        for arxiv_id in candidate_ids:
            if arxiv_id in existing:
                continue
            work = fetch_openalex_by_arxiv_id(arxiv_id)
            if not work:
                continue
            paper = to_paper(work, tracked_ids)
            if paper and paper["id"] not in existing:
                existing[paper["id"]] = paper
                new_count += 1
                print(f"    Fallback found: {arxiv_id} for {author['name']}")

    print(f"\nFound {new_count} new papers total.")

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
