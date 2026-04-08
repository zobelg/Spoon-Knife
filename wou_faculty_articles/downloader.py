"""
Download open-access article PDFs with proper naming convention.

File naming: {AuthorLastName}_{Year}_{sanitized_title}.pdf
"""

import os
import re
import time
import logging
from pathlib import Path

import requests

from .article_search import Article

logger = logging.getLogger(__name__)

# Maximum file-name length (excluding extension)
MAX_TITLE_LEN = 80

# HTTP settings
DOWNLOAD_TIMEOUT = 60  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds (doubles on each retry)

REQUEST_HEADERS = {
    "User-Agent": "WOU-Faculty-Article-Scraper/1.0 (educational research)",
    "Accept": "application/pdf,*/*",
}


def sanitize_filename(text: str) -> str:
    """Convert arbitrary text into a safe filename component."""
    # Replace common separators with underscores
    text = re.sub(r"[\s/\\:;,]+", "_", text)
    # Remove any remaining non-alphanumeric characters (keep hyphens, underscores)
    text = re.sub(r"[^\w\-]", "", text)
    # Collapse multiple underscores
    text = re.sub(r"_+", "_", text)
    # Trim
    text = text.strip("_")
    return text[:MAX_TITLE_LEN]


def build_filename(article: Article) -> str:
    """Build the download filename: LastName_Year_Title.pdf"""
    last = sanitize_filename(article.faculty_last_name or "Unknown")
    year = str(article.year) if article.year else "NoYear"
    title = sanitize_filename(article.title or "untitled")
    return f"{last}_{year}_{title}.pdf"


def download_pdf(url: str, dest_path: Path) -> bool:
    """Download a PDF from *url* to *dest_path* with retries.

    Returns True on success, False otherwise.
    """
    delay = RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=REQUEST_HEADERS,
                timeout=DOWNLOAD_TIMEOUT,
                stream=True,
                allow_redirects=True,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")

            # Write the response content
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = dest_path.stat().st_size

            # Basic validation: file should be non-trivial
            if file_size < 1024:
                logger.warning(
                    "Downloaded file is very small (%d bytes), may not be a valid PDF: %s",
                    file_size, dest_path.name,
                )
                # Check if it's actually an HTML error page
                with open(dest_path, "rb") as f:
                    header = f.read(20)
                if header.startswith(b"<!") or header.startswith(b"<html"):
                    logger.warning("File appears to be HTML, not PDF - removing")
                    dest_path.unlink(missing_ok=True)
                    return False

            # Check for PDF magic bytes
            with open(dest_path, "rb") as f:
                magic = f.read(5)
            if magic != b"%PDF-":
                logger.warning(
                    "File does not start with PDF header (got %r). "
                    "It may be HTML or another format: %s",
                    magic[:10], dest_path.name,
                )
                # Keep the file but warn the user - some PDFs have preamble bytes

            logger.info("Downloaded: %s (%.1f KB)", dest_path.name, file_size / 1024)
            return True

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if status == 403:
                logger.warning("Access denied (403) for %s - skipping", url)
                return False
            if status == 429:
                logger.warning("Rate limited (429), waiting %ds...", delay)
                time.sleep(delay)
                delay *= 2
                continue
            logger.warning("HTTP %s on attempt %d for %s", status, attempt, url)

        except Exception as exc:
            logger.warning("Download error (attempt %d/%d) for %s: %s",
                           attempt, MAX_RETRIES, url, exc)

        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    return False


def download_articles(
    articles: list[Article],
    output_dir: str | Path = "downloads",
    skip_existing: bool = True,
) -> dict:
    """Download all articles to *output_dir*.

    Returns a summary dict with counts of successes, failures, and skips.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {"success": 0, "failed": 0, "skipped": 0, "total": len(articles)}

    for i, article in enumerate(articles, 1):
        if not article.pdf_url:
            stats["skipped"] += 1
            continue

        filename = build_filename(article)
        dest = output_dir / filename

        if skip_existing and dest.exists():
            logger.info("[%d/%d] Already exists, skipping: %s", i, stats["total"], filename)
            stats["skipped"] += 1
            continue

        logger.info(
            "[%d/%d] Downloading: %s\n         URL: %s",
            i, stats["total"], filename, article.pdf_url,
        )

        if download_pdf(article.pdf_url, dest):
            stats["success"] += 1
        else:
            stats["failed"] += 1

        # Be polite between downloads
        time.sleep(0.5)

    return stats
