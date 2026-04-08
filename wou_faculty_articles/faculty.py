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
    # ── Dean's Office ───────────────────────────────────────────────
    {"first": "Theresa",  "last": "Hickey",         "division": "Dean's Office",
     "title": "Dean, College of Education"},
    {"first": "Marie",    "last": "LeJeune",        "division": "Dean's Office",
     "title": "Interim Associate Dean / Professor"},
    {"first": "Mark",     "last": "Girod",          "division": "Dean's Office",
     "title": "Former Dean / Professor of Teacher Education"},

    # ── Division of Education & Leadership ──────────────────────────
    {"first": "Cindy",    "last": "Ryan",           "division": "Education & Leadership",
     "title": "Associate Professor / Division Chair"},
    {"first": "Ken",      "last": "Carano",         "division": "Education & Leadership",
     "title": "Professor, Social Studies Education"},
    {"first": "Katrina",  "last": "Hovey",          "division": "Education & Leadership",
     "title": "Assistant Professor, Special Education"},
    {"first": "Alicia",   "last": "Wenzel",         "division": "Education & Leadership",
     "title": "Professor, Curriculum & Assessment"},
    {"first": "Lin",      "last": "Wu",             "division": "Education & Leadership",
     "title": "Assistant Professor"},
    {"first": "Andrea",   "last": "Emerson",        "division": "Education & Leadership",
     "title": "Assistant Professor, Early Childhood Education"},
    {"first": "Melanie",  "last": "Landon-Hays",    "division": "Education & Leadership",
     "title": "Professor, Content Area Literacy"},
    {"first": "Kristen",  "last": "Pratt",          "division": "Education & Leadership",
     "title": "Associate Professor, ESOL/Bilingual Education"},
    {"first": "Maria",    "last": "Dantas-Whitney", "division": "Education & Leadership",
     "title": "Professor, ESOL/Bilingual Education"},
    {"first": "Gregory",  "last": "Zobel",          "division": "Education & Leadership",
     "title": "Associate Professor, Educational Technology"},
    {"first": "Annie",    "last": "Delbridge",      "division": "Education & Leadership",
     "title": "Assistant Professor, Literacy Education"},
    {"first": "Jaclyn",   "last": "Caires-Hurley",  "division": "Education & Leadership",
     "title": "Assistant Professor / COE JEDI Coordinator"},
    {"first": "Dani",     "last": "Lane",           "division": "Education & Leadership",
     "title": "Professor, Special Education Graduate Program"},
    {"first": "Mary",     "last": "Scarlato",       "division": "Education & Leadership",
     "title": "Professor, Special Education"},

    # ── Division of Deaf Studies & Professional Studies ──────────────
    {"first": "Elisa",    "last": "Maroney",        "division": "Deaf Studies & Professional Studies",
     "title": "Professor / Program Co-Coordinator, Interpreting Studies"},
    {"first": "Amanda",   "last": "Smith",          "division": "Deaf Studies & Professional Studies",
     "title": "Professor / Program Co-Coordinator"},
    {"first": "Patrick",  "last": "Graham",         "division": "Deaf Studies & Professional Studies",
     "title": "Associate Professor, DHHE Program Coordinator"},
    {"first": "Chung-Fan","last": "Ni",             "division": "Deaf Studies & Professional Studies",
     "title": "Professor / RMHC Coordinator"},
    {"first": "Chien-Chun","last": "Lin",           "division": "Deaf Studies & Professional Studies",
     "title": "Associate Professor / RMHC Clinical Coordinator"},
    {"first": "Kathy",    "last": "Heide",          "division": "Deaf Studies & Professional Studies",
     "title": "Associate Professor, Rehabilitation Counseling"},
    {"first": "Carlos",   "last": "Texidor Maldonado", "division": "Deaf Studies & Professional Studies",
     "title": "Professor, Rehabilitation & Counseling"},
    {"first": "CM",       "last": "Hall",           "division": "Deaf Studies & Professional Studies",
     "title": "Instructor, Interpreting Studies"},
    {"first": "Brent",    "last": "Redpath",        "division": "Deaf Studies & Professional Studies",
     "title": "Instructor / ASL Studies Program Coordinator"},

    # ── Division of Health & Exercise Science ───────────────────────
    {"first": "Gay",      "last": "Timken",         "division": "Health & Exercise Science",
     "title": "Professor / Division Chair"},
    {"first": "Pamela",   "last": "Cancel",         "division": "Health & Exercise Science",
     "title": "Associate Professor, Health Disparities"},
    {"first": "Daniel",   "last": "Dowhower",       "division": "Health & Exercise Science",
     "title": "Assistant Professor, Public Health"},
    {"first": "Nancy",    "last": "Vargas",         "division": "Health & Exercise Science",
     "title": "Assistant Professor, Public Health"},
    {"first": "Laura",    "last": "Ellingson-Sayen","division": "Health & Exercise Science",
     "title": "Faculty, Exercise Science"},
    {"first": "Jennifer", "last": "Taylor-Winney",  "division": "Health & Exercise Science",
     "title": "Faculty, Exercise Science"},
    {"first": "Shawn",    "last": "Sellers",        "division": "Health & Exercise Science",
     "title": "Instructor, Health Education"},
    {"first": "Marita",   "last": "Cardinal",       "division": "Health & Exercise Science",
     "title": "Professor, Dance & Physical Education"},
    {"first": "Tom",      "last": "Kelly",          "division": "Health & Exercise Science",
     "title": "Assistant Professor"},
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
