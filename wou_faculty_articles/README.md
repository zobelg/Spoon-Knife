# WOU College of Education - Faculty Article Downloader

A Python tool that identifies faculty members in Western Oregon University's
College of Education, searches for their open-access scholarly articles, and
downloads the PDFs with filenames prefixed by author last name and publication
year.

## How It Works

1. **Faculty Identification** - Scrapes WOU's College of Education web pages
   (`wou.edu/education/faculty-and-staff/` and division-specific pages) to
   get current faculty names. Falls back to a built-in seed list of 25 faculty
   if scraping fails.

2. **Article Search** - Queries three free scholarly APIs:
   - **OpenAlex** - Best open-access metadata and direct PDF links
   - **Semantic Scholar** - Good for arXiv, PubMed Central PDFs
   - **CrossRef** - Broadest DOI coverage as fallback

3. **PDF Download** - Downloads every article that has a freely-available PDF
   link. Files are named: `AuthorLastName_Year_ArticleTitle.pdf`

4. **Manifest** - Writes a CSV file (`article_manifest.csv`) cataloging every
   article found, including those that couldn't be downloaded.

## Installation

```bash
pip install -r requirements.txt
```

The only dependency is `requests`.

## Usage

```bash
# Full run: scrape faculty, search articles, download PDFs
python -m wou_faculty_articles

# Specify output directory
python -m wou_faculty_articles --output-dir ./papers

# Only show the faculty list
python -m wou_faculty_articles --faculty-only

# Search articles but don't download
python -m wou_faculty_articles --no-download

# Process specific faculty members only
python -m wou_faculty_articles --faculty-filter "Landon-Hays,Vala-Haynes"

# Use built-in faculty list (skip wou.edu scraping)
python -m wou_faculty_articles --no-scrape

# Verbose/debug logging
python -m wou_faculty_articles --verbose
```

## Output

Downloaded PDFs are saved to the output directory (default: `wou_education_articles/`):

```
wou_education_articles/
  Landon-Hays_2021_Exploring_Digital_Literacy_Practices.pdf
  Vala-Haynes_2020_Community_Health_Assessment.pdf
  Graham_2019_Deaf_Education_Perspectives.pdf
  ...
  article_manifest.csv
```

## Faculty Divisions Covered

- Division of Education & Leadership
- Division of Deaf Studies & Professional Studies
- Division of Health & Exercise Science
- Special Education
- Dean's Office

## API Rate Limits

The tool respects rate limits for all APIs:
- **OpenAlex**: 10 req/sec (polite pool)
- **Semantic Scholar**: ~1 req/sec (unauthenticated)
- **CrossRef**: ~50 req/sec (polite pool)

A full run across all 25 faculty typically takes 5-10 minutes.
