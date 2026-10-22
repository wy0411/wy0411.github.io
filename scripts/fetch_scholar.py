#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch publications from a Google Scholar profile and generate the Markdown
files consumed by the academicpages Jekyll theme (``_publications/*.md``).

This is meant to run in GitHub Actions on a schedule (see
``.github/workflows/scrape_scholar.yml``), but you can also run it locally:

    pip install scholarly
    python scripts/fetch_scholar.py

Configuration (all values have sensible defaults; override via env vars):
    SCHOLAR_ID      Google Scholar user id  -- the ``user=`` part of your
                    profile URL, e.g. "8tJ1XRQAAAAJ".
    OUTPUT_DIR      Directory for the generated .md files (default: _publications).
    CLEAN_OUTPUT    Set to "1" to delete stale .md files in OUTPUT_DIR that no
                    longer exist on Scholar before writing. Default "0" (off),
                    so manually curated files are preserved.
    SCHOLARLY_PROXY Set to "freeproxies" to route requests through free proxies
                    if Google Scholar blocks the runner's IP (less reliable).

NOTE
----
Google Scholar has no official API and actively blocks bots. This script uses
the community `scholarly` package and will usually work, but it can hit a
CAPTCHA / 429 page, especially from shared cloud IPs. If that happens, re-run
the workflow manually (Actions tab -> "Scrape Google Scholar Publications" ->
"Run workflow"), or see the "If it gets blocked" section in the README notes.
"""

import os
import re
import sys
import time
from pathlib import Path

from scholarly import scholarly, ProxyGenerator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCHOLAR_ID = os.environ.get("SCHOLAR_ID", "8tJ1XRQAAAAJ")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "_publications"))
CLEAN_OUTPUT = os.environ.get("CLEAN_OUTPUT", "0") == "1"
PROXY_MODE = os.environ.get("SCHOLARLY_PROXY", "").strip().lower()

MAX_RETRIES = 3          # attempts to fetch the author profile
RETRY_DELAY = 5          # base delay between attempts, seconds


def html_escape(text):
    """Escape characters that would otherwise break the YAML front matter."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def make_slug(title):
    """Turn a title into a URL-safe slug used for the permalink / filename."""
    slug = re.sub(r"[^a-zA-Z0-9 _-]", "", title or "")
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-").lower()
    return slug[:100] or "publication"


def make_date(pub_year):
    """Google Scholar usually only exposes a year; normalise to YYYY-MM-DD."""
    digits = re.sub(r"[^0-9]", "", str(pub_year or ""))
    if len(digits) < 4:
        digits = "1900"
    return f"{digits[:4]}-01-01"


def get_authors(bib):
    """Return the author list. `scholarly` returns a list, but be tolerant."""
    authors = bib.get("author", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    return [a for a in authors if a]


def get_category(bib):
    """Map a Scholar entry type to an academicpages publication category."""
    entrytype = str(bib.get("ENTRYTYPE", "")).lower()
    if entrytype in ("inproceedings", "conference", "proceedings"):
        return "conferences"
    return "manuscripts"


def render_publication(pub):
    """Render a single Scholar publication into (filename, markdown) or None."""
    bib = pub.get("bib", {}) if isinstance(pub, dict) else {}

    title = (bib.get("title") or "").strip()
    if not title:
        return None

    pub_year = bib.get("pub_year", "")
    date = make_date(pub_year)
    slug = make_slug(title)
    filename = f"{date}-{slug}.md"
    permalink = f"/publication/{date}-{slug}"

    authors = get_authors(bib)
    venue = (bib.get("venue") or bib.get("journal") or "").strip()

    # Build a human-readable citation: "A, B. "Title." <i>Venue</i>. YYYY."
    citation = ""
    if authors:
        citation += ", ".join(authors) + ". "
    citation += f'"{title}."'
    if venue:
        citation += f" <i>{venue}</i>."
    if pub_year:
        citation += f" {pub_year}."
    citation = citation.strip()

    paper_url = (pub.get("pub_url") or bib.get("url") or "").strip()

    abstract = (bib.get("abstract") or "").strip()
    excerpt = None
    if abstract:
        excerpt = abstract
        if len(excerpt) > 300:
            excerpt = excerpt[:300].rsplit(" ", 1)[0] + " ..."

    lines = ["---"]
    lines.append(f'title: "{html_escape(title)}"')
    lines.append("collection: publications")
    lines.append(f"category: {get_category(bib)}")
    lines.append(f"permalink: {permalink}")
    if excerpt:
        lines.append(f"excerpt: '{html_escape(excerpt)}'")
    lines.append(f"date: {date}")
    if venue:
        lines.append(f"venue: '{html_escape(venue)}'")
    if paper_url:
        lines.append(f"paperurl: '{paper_url}'")
    lines.append(f"citation: '{html_escape(citation)}'")
    lines.append("---")
    lines.append("")

    return filename, "\n".join(lines)


def fetch_author():
    """Fetch the Scholar profile with retries/backoff. Returns Author or None."""
    if PROXY_MODE == "freeproxies":
        pg = ProxyGenerator()
        if pg.FreeProxies():
            scholarly.use_proxy(pg)
            print("Using free proxies for Google Scholar requests.")
        else:
            print("Warning: free-proxy setup failed; using a direct connection.")

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            author = scholarly.search_author_id(SCHOLAR_ID)
            # sections=['publications'] avoids fetching co-authors, reducing the
            # number of requests (and the chance of being rate-limited).
            author = scholarly.fill(author, sections=["publications"])
            return author
        except Exception as exc:  # noqa: BLE001 - surface the real error below
            last_err = exc
            print(f"Attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    print(f"ERROR: could not fetch Scholar profile '{SCHOLAR_ID}': {last_err}",
          file=sys.stderr)
    return None


def main():
    print(f"Fetching Google Scholar profile: user={SCHOLAR_ID}")

    author = fetch_author()
    if author is None:
        sys.exit(1)

    publications = author.get("publications", []) if isinstance(author, dict) else []
    print(f"Found {len(publications)} publications.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if CLEAN_OUTPUT:
        removed = 0
        for path in OUTPUT_DIR.glob("*.md"):
            path.unlink()
            removed += 1
        if removed:
            print(f"Removed {removed} stale publication files (CLEAN_OUTPUT=1).")

    written = 0
    for i, pub in enumerate(publications):
        # Fill each publication for full details (venue, URL, citation count).
        # If it fails, keep going with whatever the profile already gave us.
        try:
            pub = scholarly.fill(pub)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] could not fill publication #{i}: {exc}")

        rendered = render_publication(pub)
        if rendered is None:
            print(f"  [skip] publication #{i} has no title")
            continue

        filename, content = rendered
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")
        written += 1
        print(f"  wrote {filename}")

    print(f"Done. Wrote {written} publication files to {OUTPUT_DIR}/.")


if __name__ == "__main__":
    main()
