"""
WOU College of Education - Faculty Open-Access Article Downloader
=================================================================

Main entry point.  Run with:
    python -m wou_faculty_articles [OPTIONS]

This tool:
  1. Identifies faculty in WOU's College of Education (scrapes wou.edu or
     uses a built-in seed list).
  2. Searches OpenAlex, Semantic Scholar, and CrossRef for their open-access
     publications.
  3. Downloads every freely-available PDF, naming each file:
         AuthorLastName_Year_ArticleTitle.pdf
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from .faculty import get_faculty_list
from .article_search import find_articles_for_faculty, Article
from .downloader import download_articles, build_filename

logger = logging.getLogger("wou_faculty_articles")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def write_manifest(articles: list[Article], path: Path):
    """Write a CSV manifest of all discovered articles."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Faculty Last Name", "Year", "Title", "Authors",
            "DOI", "PDF URL", "OA Status", "Source API", "Filename",
        ])
        for art in articles:
            writer.writerow([
                art.faculty_last_name,
                art.year or "",
                art.title,
                "; ".join(art.authors),
                art.doi or "",
                art.pdf_url or "",
                art.oa_status,
                art.source_api,
                build_filename(art),
            ])


def main():
    parser = argparse.ArgumentParser(
        description="Download open-access articles by WOU College of Education faculty.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m wou_faculty_articles
  python -m wou_faculty_articles --output-dir ./papers --max-articles 20
  python -m wou_faculty_articles --faculty-only
  python -m wou_faculty_articles --no-scrape --verbose
        """,
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="wou_education_articles",
        help="Directory for downloaded PDFs (default: wou_education_articles)",
    )
    parser.add_argument(
        "--max-articles",
        type=int, default=50,
        help="Maximum articles to search per faculty member per API (default: 50)",
    )
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip scraping wou.edu; use built-in faculty list only",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Search for articles but do not download PDFs",
    )
    parser.add_argument(
        "--faculty-only",
        action="store_true",
        help="Only print the faculty list and exit",
    )
    parser.add_argument(
        "--faculty-filter",
        help="Comma-separated last names to process (default: all)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # ── Step 1: Get faculty list ────────────────────────────────────
    print("=" * 70)
    print("  WOU College of Education - Open-Access Article Downloader")
    print("=" * 70)
    print()

    print("[Step 1] Identifying faculty members...")
    faculty = get_faculty_list(try_scrape=not args.no_scrape)

    if args.faculty_filter:
        filter_names = {n.strip().lower() for n in args.faculty_filter.split(",")}
        faculty = [f for f in faculty if f["last"].lower() in filter_names]

    print(f"  Found {len(faculty)} faculty members:\n")
    divisions: dict[str, list] = {}
    for f in faculty:
        div = f.get("division", "Unknown")
        divisions.setdefault(div, []).append(f)

    for div, members in sorted(divisions.items()):
        print(f"  {div}:")
        for m in members:
            title = m.get("title", "")
            title_str = f" - {title}" if title else ""
            print(f"    * {m['first']} {m['last']}{title_str}")
        print()

    if args.faculty_only:
        return

    # ── Step 2: Search for articles ─────────────────────────────────
    print("[Step 2] Searching for open-access articles...")
    print("  (This may take several minutes due to API rate limits)\n")

    all_articles: list[Article] = []
    for i, member in enumerate(faculty, 1):
        first, last = member["first"], member["last"]
        print(f"  [{i}/{len(faculty)}] Searching for {first} {last}...", end=" ", flush=True)

        articles = find_articles_for_faculty(first, last, args.max_articles)
        all_articles.extend(articles)

        print(f"found {len(articles)} downloadable articles")

    print(f"\n  Total articles found: {len(all_articles)}")
    print()

    if not all_articles:
        print("  No open-access articles with PDF links were found.")
        print("  This may be due to API rate limits or network issues.")
        print("  Try again later or with --verbose to see details.")
        return

    # ── Step 3: Write manifest ──────────────────────────────────────
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "article_manifest.csv"
    write_manifest(all_articles, manifest_path)
    print(f"  Article manifest saved to: {manifest_path}")

    # ── Step 4: Download PDFs ───────────────────────────────────────
    if args.no_download:
        print("\n  --no-download specified; skipping PDF downloads.")
        print(f"  Review the manifest at {manifest_path}")
        return

    print(f"\n[Step 3] Downloading {len(all_articles)} PDFs to {output_dir}/...")
    print("  (Files are named: AuthorLastName_Year_Title.pdf)\n")

    stats = download_articles(all_articles, output_dir)

    # ── Summary ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  Download Summary")
    print("=" * 70)
    print(f"  Total articles found:  {stats['total']}")
    print(f"  Successfully downloaded: {stats['success']}")
    print(f"  Failed / access denied:  {stats['failed']}")
    print(f"  Skipped (already exist): {stats['skipped']}")
    print(f"  Output directory: {output_dir.resolve()}")
    print(f"  Manifest CSV:    {manifest_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
