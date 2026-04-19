# IQC arXiv Feed

An automated RSS feed for `quant-ph` papers from authors affiliated with the
**Institute for Quantum Computing (IQC)** at the University of Waterloo.

Runs daily via GitHub Actions and publishes a browsable web page + RSS feed
to GitHub Pages — no server required.

---

## Setup (one-time, ~5 minutes)

### 1. Create the repository

Fork or clone this repo into your own GitHub account. It must be **public**
for GitHub Pages to work on the free plan (or you can use a private repo with
GitHub Pro).

### 2. Enable GitHub Pages

In your repo:

1. Go to **Settings → Pages**
2. Under **Source**, choose **Deploy from a branch**
3. Set branch to `main` and folder to `/docs`
4. Click **Save**

GitHub will give you a URL like `https://your-username.github.io/iqc-arxiv-feed/`.
Bookmark it — that's your feed page.

### 3. Run the Action for the first time

1. Go to the **Actions** tab in your repo
2. Select **Update IQC arXiv Feed**
3. Click **Run workflow → Run workflow**

This populates `docs/papers.json` and `docs/feed.xml` immediately.
After that, it runs automatically every day at 08:00 UTC.

---

## Your URLs

| What | URL |
|------|-----|
| Web reader | `https://your-username.github.io/iqc-arxiv-feed/` |
| RSS feed | `https://your-username.github.io/iqc-arxiv-feed/feed.xml` |
| Raw JSON | `https://your-username.github.io/iqc-arxiv-feed/papers.json` |

Add the RSS URL to any feed reader (Reeder, NetNewsWire, Feedly, etc.).

---

## Adjusting the filter

Edit the top of `fetch_papers.py`:

```python
# Primary keywords — at least one must match for a paper to be included
AFFILIATION_KEYWORDS = [
    "Institute for Quantum Computing",
    "IQC",
]

# How many recent papers to pull from arXiv per run
MAX_RESULTS = 300
```

Commit the change and the next run will use the new settings.

---

## How it works

```
GitHub Actions (daily cron)
        │
        ▼
fetch_papers.py
  └─ Queries arXiv API (quant-ph, newest first)
  └─ Checks affiliation fields + abstract for IQC keywords
  └─ Merges with previously found papers (deduplication)
  └─ Writes docs/papers.json + docs/feed.xml
        │
        ▼
git commit & push → GitHub Pages serves docs/
```

Affiliation data on arXiv is author-supplied and inconsistent — some papers
won't have structured affiliation metadata at all. The script also searches
abstracts as a fallback, but this can produce occasional false positives or
misses. For higher coverage, consider augmenting with the
[OpenAlex API](https://docs.openalex.org/) which has curated institution data.
