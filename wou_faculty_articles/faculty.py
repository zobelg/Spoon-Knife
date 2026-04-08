"""
Western Oregon University - College of Education Faculty Directory

Faculty names organized by division, gathered from public WOU web pages.
The script also supports scraping the live WOU faculty pages for the most
up-to-date list (requires network access to wou.edu).
"""

import re
import logging
import requests
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard-coded seed list compiled from public WOU web pages & announcements.
# Each entry: {first, last, division, title (optional)}
# The scraper (below) will attempt to refresh this from the live site.
# ---------------------------------------------------------------------------
SEED_FACULTY = [
    # ── Division of Education & Leadership ──────────────────────────
    {"first": "Marie",    "last": "LeJeune",       "division": "Education & Leadership",
     "title": "Interim Associate Dean / Professor"},
    {"first": "Melanie",  "last": "Landon-Hays",   "division": "Education & Leadership",
     "title": "Professor"},
    {"first": "Yuliana",  "last": "Kenfield",      "division": "Education & Leadership",
     "title": "Assistant Professor"},
    {"first": "Annie",    "last": "Delbridge",      "division": "Education & Leadership",
     "title": "Assistant Professor, Literacy Education"},
    {"first": "Jessica",  "last": "Dougherty",      "division": "Education & Leadership",
     "title": "Assistant Professor, ESOL/BIL"},
    {"first": "Lin",      "last": "Wu",             "division": "Education & Leadership",
     "title": "Professor"},
    {"first": "Amy",      "last": "Layton",         "division": "Education & Leadership",
     "title": "Instructor"},
    {"first": "Rachel",   "last": "Harrington",     "division": "Education & Leadership",
     "title": "Faculty"},

    # ── Division of Deaf Studies & Professional Studies ──────────────
    {"first": "Armond",   "last": "Smith",          "division": "Deaf Studies & Professional Studies",
     "title": "Professor / Program Co-Coordinator"},
    {"first": "Erika",    "last": "Marone",         "division": "Deaf Studies & Professional Studies",
     "title": "Professor / Program Co-Coordinator"},
    {"first": "Patrick",  "last": "Graham",         "division": "Deaf Studies & Professional Studies",
     "title": "Associate Professor, DHHE Program Coordinator"},
    {"first": "Denise",   "last": "Thew Hackett",   "division": "Deaf Studies & Professional Studies",
     "title": "Associate Professor, Deaf Studies"},
    {"first": "Carlos",   "last": "Texidor Maldonado", "division": "Deaf Studies & Professional Studies",
     "title": "Assistant Professor, Rehabilitation & Counseling"},
    {"first": "Elisa",    "last": "Maroney",        "division": "Deaf Studies & Professional Studies",
     "title": "Professor, Interpreting Studies"},

    # ── Special Education ───────────────────────────────────────────
    {"first": "Dani",     "last": "Lane",           "division": "Special Education",
     "title": "Professor, Special Education"},

    # ── Division of Health & Exercise Science ───────────────────────
    {"first": "Emily",    "last": "Vala-Haynes",    "division": "Health & Exercise Science",
     "title": "Professor, Community Health"},
    {"first": "Megan",    "last": "Patton-Lopez",   "division": "Health & Exercise Science",
     "title": "Professor, Community Health"},
    {"first": "Kendra",   "last": "Taylor",         "division": "Health & Exercise Science",
     "title": "Associate Professor"},
    {"first": "Nancy",    "last": "Vargas",         "division": "Health & Exercise Science",
     "title": "Assistant Professor"},
    {"first": "Gay",      "last": "Timken",         "division": "Health & Exercise Science",
     "title": "Professor / Division Chair"},
    {"first": "Shawn",    "last": "Sellers",        "division": "Health & Exercise Science",
     "title": "Instructor"},
    {"first": "Janet",    "last": "Roberts",        "division": "Health & Exercise Science",
     "title": "Instructor / Internship Coordinator"},
    {"first": "Darryl",   "last": "Armstrong",      "division": "Health & Exercise Science",
     "title": "Professor"},
    {"first": "Marita",   "last": "Cardinal",       "division": "Health & Exercise Science",
     "title": "Professor"},

    # ── Dean's Office ───────────────────────────────────────────────
    {"first": "Theresa",  "last": "Hickey",         "division": "Dean's Office",
     "title": "Dean, College of Education"},
]


# ---------------------------------------------------------------------------
# Simple HTML parser to extract faculty names from WOU pages
# ---------------------------------------------------------------------------
class _FacultyPageParser(HTMLParser):
    """Extract text nodes that look like faculty names from WOU directory pages."""

    def __init__(self):
        super().__init__()
        self._in_heading = False
        self._tag_depth = 0
        self.names: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4", "strong"):
            self._in_heading = True
            self._tag_depth += 1

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4", "strong"):
            self._tag_depth -= 1
            if self._tag_depth <= 0:
                self._in_heading = False
                self._tag_depth = 0

    def handle_data(self, data):
        if self._in_heading:
            text = data.strip()
            # Heuristic: looks like a person name (2-4 words, starts uppercase)
            if text and re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z\-']+){1,3}$", text):
                self.names.append(text)


def scrape_wou_faculty_pages(timeout: int = 15) -> list[dict]:
    """Attempt to scrape the live WOU faculty directory pages.

    Returns a list of dicts with 'first', 'last', 'division' keys, or an
    empty list if the pages cannot be reached.
    """
    pages = {
        "Education & Leadership":
            "https://wou.edu/teachered/people/",
        "Deaf Studies & Professional Studies":
            "https://wou.edu/dsps/people/",
        "Health & Exercise Science":
            "https://wou.edu/hexs/faculty-and-staff/",
        "College of Education (all)":
            "https://wou.edu/education/faculty-and-staff/",
    }

    faculty: list[dict] = []
    headers = {"User-Agent": "WOU-Faculty-Article-Scraper/1.0 (educational research)"}

    for division, url in pages.items():
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            parser = _FacultyPageParser()
            parser.feed(resp.text)
            for name in parser.names:
                parts = name.rsplit(" ", 1)
                if len(parts) == 2:
                    faculty.append({
                        "first": parts[0],
                        "last": parts[1],
                        "division": division,
                    })
            logger.info("Scraped %d names from %s", len(parser.names), url)
        except Exception as exc:
            logger.warning("Could not scrape %s: %s", url, exc)

    return faculty


def get_faculty_list(try_scrape: bool = True) -> list[dict]:
    """Return the best-available faculty list.

    If *try_scrape* is True, attempts to fetch live data from wou.edu first.
    Falls back to the hard-coded SEED_FACULTY list.
    """
    if try_scrape:
        live = scrape_wou_faculty_pages()
        if live:
            logger.info("Using %d faculty from live scrape", len(live))
            return live
        logger.info("Live scrape returned nothing; falling back to seed list")

    return list(SEED_FACULTY)
