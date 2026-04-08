"""
Search for open-access articles by faculty members using free scholarly APIs.

Uses three APIs in a layered approach:
  1. OpenAlex  – best open-access metadata & direct PDF links
  2. Semantic Scholar – good OA PDF detection (arXiv, PubMed Central, etc.)
  3. CrossRef  – broadest coverage as fallback

All APIs are free and require no authentication for basic use.
"""

import time
import logging
import urllib.parse
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

POLITE_EMAIL = "wou.faculty.scraper@example.com"  # polite-pool identifier

REQUEST_HEADERS = {
    "User-Agent": f"WOU-Faculty-Article-Scraper/1.0 (mailto:{POLITE_EMAIL})",
    "Accept": "application/json",
}


@dataclass
class Article:
    """Represents one open-access article."""
    title: str
    authors: list[str]           # list of "First Last" strings
    year: int | None
    doi: str | None
    pdf_url: str | None          # direct PDF link (may be None)
    landing_url: str | None      # journal / repo landing page
    source_api: str              # which API found it
    oa_status: str = ""          # gold, green, hybrid, bronze, etc.
    faculty_last_name: str = ""  # the WOU faculty member who matched

    @property
    def has_pdf(self) -> bool:
        return bool(self.pdf_url)

    def filename_prefix(self) -> str:
        """Return 'LastName_Year' prefix for the downloaded file."""
        name = self.faculty_last_name or "Unknown"
        year = self.year or "NoYear"
        return f"{name}_{year}"


# ── Throttle helper ─────────────────────────────────────────────────────────

def _throttle(seconds: float = 0.2):
    time.sleep(seconds)


# ── OpenAlex ────────────────────────────────────────────────────────────────

def search_openalex(first: str, last: str, max_results: int = 50) -> list[Article]:
    """Search OpenAlex for open-access works by an author."""
    articles: list[Article] = []
    author_query = f"{first} {last}"
    params = {
        "filter": f"author.search:{author_query},is_oa:true",
        "per_page": min(max_results, 50),
        "mailto": POLITE_EMAIL,
    }
    url = "https://api.openalex.org/works"

    try:
        resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("OpenAlex error for %s %s: %s", first, last, exc)
        return articles

    for work in data.get("results", []):
        title = work.get("title") or ""
        year = work.get("publication_year")
        doi = work.get("doi")
        oa = work.get("open_access", {})
        oa_url = oa.get("oa_url")
        oa_status = oa.get("oa_status", "")

        # Get best PDF URL
        pdf_url = None
        best_loc = work.get("best_oa_location") or {}
        pdf_url = best_loc.get("pdf_url") or best_loc.get("landing_page_url")
        if not pdf_url:
            pdf_url = oa_url

        # Extract author names
        authors = []
        for authorship in work.get("authorships", []):
            author_obj = authorship.get("author", {})
            display = author_obj.get("display_name", "")
            if display:
                authors.append(display)

        # Verify the WOU faculty member is actually among the authors
        if not _author_matches(first, last, authors):
            continue

        articles.append(Article(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            pdf_url=pdf_url,
            landing_url=oa_url,
            source_api="openalex",
            oa_status=oa_status,
            faculty_last_name=last,
        ))

    logger.info("OpenAlex: %d OA articles for %s %s", len(articles), first, last)
    _throttle(0.15)
    return articles


# ── Semantic Scholar ────────────────────────────────────────────────────────

def search_semantic_scholar(first: str, last: str, max_results: int = 50) -> list[Article]:
    """Search Semantic Scholar for open-access papers by an author."""
    articles: list[Article] = []

    # Step 1: find the author
    search_url = "https://api.semanticscholar.org/graph/v1/author/search"
    params = {"query": f"{first} {last}", "fields": "name,paperCount", "limit": 5}

    try:
        resp = requests.get(search_url, params=params, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        author_data = resp.json().get("data", [])
    except Exception as exc:
        logger.warning("Semantic Scholar author search error for %s %s: %s", first, last, exc)
        return articles

    if not author_data:
        return articles

    # Pick best-matching author by name similarity
    author_id = None
    for candidate in author_data:
        cname = (candidate.get("name") or "").lower()
        if last.lower() in cname:
            author_id = candidate.get("authorId")
            break
    if not author_id:
        author_id = author_data[0].get("authorId")
    if not author_id:
        return articles

    _throttle(1.0)  # Semantic Scholar is stricter on rate limits

    # Step 2: get author's papers
    papers_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
    params = {
        "fields": "title,year,authors,openAccessPdf,isOpenAccess,externalIds",
        "limit": min(max_results, 100),
    }

    try:
        resp = requests.get(papers_url, params=params, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        papers = resp.json().get("data", [])
    except Exception as exc:
        logger.warning("Semantic Scholar papers error for author %s: %s", author_id, exc)
        return articles

    for paper in papers:
        if not paper.get("isOpenAccess"):
            continue

        oa_pdf = paper.get("openAccessPdf") or {}
        pdf_url = oa_pdf.get("url")
        if not pdf_url:
            continue

        title = paper.get("title") or ""
        year = paper.get("year")
        authors = [a.get("name", "") for a in paper.get("authors", [])]
        ext_ids = paper.get("externalIds") or {}
        doi = ext_ids.get("DOI")

        articles.append(Article(
            title=title,
            authors=authors,
            year=year,
            doi=f"https://doi.org/{doi}" if doi else None,
            pdf_url=pdf_url,
            landing_url=None,
            source_api="semantic_scholar",
            faculty_last_name=last,
        ))

    logger.info("Semantic Scholar: %d OA articles for %s %s", len(articles), first, last)
    _throttle(1.0)
    return articles


# ── CrossRef (fallback) ────────────────────────────────────────────────────

def search_crossref(first: str, last: str, max_results: int = 30) -> list[Article]:
    """Search CrossRef for works with full-text links by an author."""
    articles: list[Article] = []
    url = "https://api.crossref.org/works"
    params = {
        "query.author": f"{first} {last}",
        "filter": "has-full-text:true",
        "rows": min(max_results, 50),
        "mailto": POLITE_EMAIL,
    }

    try:
        resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except Exception as exc:
        logger.warning("CrossRef error for %s %s: %s", first, last, exc)
        return articles

    for item in items:
        title_parts = item.get("title", [])
        title = title_parts[0] if title_parts else ""
        doi = item.get("DOI")

        # Year
        year = None
        pub_date = item.get("published-print") or item.get("published-online") or {}
        date_parts = pub_date.get("date-parts", [[]])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        # Authors
        authors = []
        for auth in item.get("author", []):
            given = auth.get("given", "")
            family = auth.get("family", "")
            authors.append(f"{given} {family}".strip())

        if not _author_matches(first, last, authors):
            continue

        # PDF link
        pdf_url = None
        for link in item.get("link", []):
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL")
                break
        if not pdf_url:
            # Use DOI as landing page
            pdf_url = f"https://doi.org/{doi}" if doi else None

        articles.append(Article(
            title=title,
            authors=authors,
            year=year,
            doi=f"https://doi.org/{doi}" if doi else None,
            pdf_url=pdf_url,
            landing_url=f"https://doi.org/{doi}" if doi else None,
            source_api="crossref",
            faculty_last_name=last,
        ))

    logger.info("CrossRef: %d articles for %s %s", len(articles), first, last)
    _throttle(0.15)
    return articles


# ── Helpers ─────────────────────────────────────────────────────────────────

def _author_matches(first: str, last: str, author_names: list[str]) -> bool:
    """Check if any name in the author list matches the target faculty member."""
    target_last = last.lower().split()[0]  # handle compound last names
    target_first_init = first[0].lower() if first else ""

    for name in author_names:
        name_lower = name.lower()
        if target_last in name_lower:
            # Also check first-name initial to reduce false positives
            parts = name_lower.split()
            if any(p.startswith(target_first_init) for p in parts):
                return True
    return False


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """Remove duplicate articles (same DOI or same title)."""
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[Article] = []

    for art in articles:
        key_doi = art.doi.lower().strip() if art.doi else None
        key_title = art.title.lower().strip()[:80] if art.title else None

        if key_doi and key_doi in seen_dois:
            continue
        if key_title and key_title in seen_titles:
            continue

        if key_doi:
            seen_dois.add(key_doi)
        if key_title:
            seen_titles.add(key_title)
        unique.append(art)

    return unique


def find_articles_for_faculty(
    first: str,
    last: str,
    max_per_api: int = 50,
) -> list[Article]:
    """Search all APIs and return a deduplicated list of OA articles."""
    all_articles: list[Article] = []

    # Try OpenAlex first (best OA metadata)
    all_articles.extend(search_openalex(first, last, max_per_api))

    # Supplement with Semantic Scholar
    all_articles.extend(search_semantic_scholar(first, last, max_per_api))

    # CrossRef as fallback (only if we have few results so far)
    if len(all_articles) < 5:
        all_articles.extend(search_crossref(first, last, max_per_api))

    deduped = deduplicate_articles(all_articles)
    # Only keep articles with a downloadable PDF
    with_pdf = [a for a in deduped if a.has_pdf]

    logger.info(
        "Total for %s %s: %d unique articles, %d with PDF links",
        first, last, len(deduped), len(with_pdf),
    )
    return with_pdf
