
import gzip
import re
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .store import upsert_document


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

USER_AGENT = "PropertyResearchAssistant/1.0"

REQUEST_DELAY = 0.5
MAX_PAGES_PER_SITE = 10
MAX_SITEMAPS = 5
MAX_CONSECUTIVE_403 = 3

SITES = {
    "DarGlobal": {
        "base": "https://darglobal.co.uk",
        "seeds": [
            "https://darglobal.co.uk/",
            "https://darglobal.co.uk/live-all-in",
            "https://darglobal.co.uk/about",
            "https://darglobal.co.uk/projects/properties-in-uk",
        ],
    },
    "Wasalt": {
        "base": "https://wasalt.sa",
        "seeds": [
            "https://wasalt.sa/en",
            "https://wasalt.sa/en/corporate",
            "https://wasalt.sa/en/properties-for-sale-in-saudi-arabia",
        ],
    },
}


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def normalize_url(url):
    """Remove fragments and trailing slashes from URLs."""

    parsed = urlparse(url)

    return parsed._replace(
        fragment="",
        query=""
    ).geturl().rstrip("/")


def allowed(url, base):
    """Allow only URLs belonging to the configured website."""

    return urlparse(url).netloc.lower() == urlparse(base).netloc.lower()


def sitemap_host_allowed(url, base):
    """Allow the website host and Wasalt's sitemap CDN."""

    hostname = urlparse(url).netloc.lower()
    base_hostname = urlparse(base).netloc.lower()

    return (
        hostname == base_hostname
        or hostname == "cdn.wasalt.sa"
    )


def get_client():
    return httpx.Client(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml",
        },
        timeout=25,
        follow_redirects=True,
    )


# ---------------------------------------------------------
# ROBOTS.TXT
# ---------------------------------------------------------

def get_robots(client, base):
    """
    Read robots.txt and check crawling permissions.

    If robots.txt cannot be accessed, crawling is skipped.
    """

    robots_url = urljoin(base, "/robots.txt")

    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = client.get(robots_url)

        if response.status_code != 200:
            print(
                f"Could not read robots.txt for {base}: "
                f"HTTP {response.status_code}"
            )
            return None

        parser.parse(response.text.splitlines())

        return parser

    except httpx.HTTPError as exc:
        print(f"Robots request failed for {base}: {exc}")
        return None


# ---------------------------------------------------------
# SITEMAP DISCOVERY
# ---------------------------------------------------------

def sitemap_urls(client, base, robots):
    """
    Read sitemap declarations from robots.txt.

    For Wasalt, only the English static sitemap is used.
    Property listing sitemaps are intentionally excluded.
    """

    if robots is None:
        return []

    sitemap_list = []

    for sitemap in robots.site_maps() or []:

        if not sitemap_host_allowed(sitemap, base):
            continue

        if "wasalt.sa" in base:
            if "static_sitemap_en_sa.xml.gz" not in sitemap:
                continue

        sitemap_list.append(sitemap)

    discovered_urls = []

    for sitemap_url in sitemap_list[:MAX_SITEMAPS]:

        try:
            response = client.get(sitemap_url)

            if response.status_code != 200:
                continue

            raw_content = response.content

            if sitemap_url.endswith(".gz"):
                raw_content = gzip.decompress(raw_content)

            root = ET.fromstring(raw_content)

            namespace = ""

            if root.tag.startswith("{"):
                namespace = root.tag.split("}")[0] + "}"

            # Sitemap index
            if root.tag.endswith("sitemapindex"):

                nested_sitemaps = []

                for item in root.findall(
                    f"{namespace}sitemap"
                ):
                    location = item.find(
                        f"{namespace}loc"
                    )

                    if location is not None and location.text:
                        nested_sitemaps.append(location.text.strip())

                for nested_url in nested_sitemaps[:MAX_SITEMAPS]:

                    if not sitemap_host_allowed(nested_url, base):
                        continue

                    try:
                        nested_response = client.get(nested_url)

                        if nested_response.status_code != 200:
                            continue

                        nested_content = nested_response.content

                        if nested_url.endswith(".gz"):
                            nested_content = gzip.decompress(
                                nested_content
                            )

                        nested_root = ET.fromstring(nested_content)

                        nested_ns = ""

                        if nested_root.tag.startswith("{"):
                            nested_ns = (
                                nested_root.tag.split("}")[0] + "}"
                            )

                        for item in nested_root.findall(
                            f"{nested_ns}url"
                        ):
                            location = item.find(
                                f"{nested_ns}loc"
                            )

                            if location is None or not location.text:
                                continue

                            page_url = location.text.strip()

                            if allowed(page_url, base):
                                discovered_urls.append(page_url)

                    except Exception as exc:
                        print(
                            f"Nested sitemap error: {exc}"
                        )

            # Normal sitemap
            else:

                for item in root.findall(
                    f"{namespace}url"
                ):
                    location = item.find(
                        f"{namespace}loc"
                    )

                    if location is None or not location.text:
                        continue

                    page_url = location.text.strip()

                    if allowed(page_url, base):
                        discovered_urls.append(page_url)

        except Exception as exc:
            print(f"Sitemap error for {sitemap_url}: {exc}")

    return list(dict.fromkeys(discovered_urls))


# ---------------------------------------------------------
# PAGE EXTRACTION
# ---------------------------------------------------------

def extract_page(client, url):
    """
    Download a webpage and extract readable text and links.

    Returns:
        title, content, links
    """

    response = client.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove unnecessary HTML elements
    for element in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "iframe",
    ]):
        element.decompose()

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    if not title:
        heading = soup.find("h1")

        if heading:
            title = heading.get_text(
                " ",
                strip=True
            )

    if not title:
        title = urlparse(url).path or "Homepage"

    content = soup.get_text(
        separator=" ",
        strip=True
    )

    content = re.sub(
        r"\s+",
        " ",
        content
    ).strip()

    # Extract same-domain links
    links = []

    for anchor in soup.find_all("a", href=True):

        absolute_url = urljoin(
            url,
            anchor["href"]
        )

        absolute_url = normalize_url(absolute_url)

        if allowed(absolute_url, url):
            links.append(absolute_url)

    return title, content, links


# ---------------------------------------------------------
# MANUAL WASALT KNOWLEDGE
# ---------------------------------------------------------

def ingest_manual_wasalt_homepage():
    """
    Index the Wasalt homepage content supplied manually.

    This is not automated scraping.
    """

    content = """
    WASALT - SAUDI ARABIA REAL ESTATE PLATFORM

    Source note:
    This knowledge was manually provided from the Wasalt homepage.
    It was not collected through automated scraping.

    OVERVIEW

    Wasalt is Saudi Arabia's AI-backed real estate platform
    for verified properties and trusted brokers.

    It helps users buy, rent, sell, invest in, and discover
    properties across Saudi Arabia.

    PROPERTY SERVICES

    - Buy properties
    - Rent properties
    - Sell properties
    - Explore real estate projects
    - Daily rentals
    - Property barter
    - Real estate auctions

    PROPERTY SEARCH

    Users can search properties by:
    - City
    - District
    - Property type

    Riyadh is shown as a searchable city with district-level search.

    SELLING AND RENTING

    Property owners can list properties for sale or rent.

    Wasalt provides a property-posting service intended to help
    owners connect with buyers and renters across Saudi Arabia.

    DAILY RENTALS

    Wasalt supports daily rental listings and promotes:
    - Weekly earnings
    - Free coverage
    - Competitive commission rates

    PROPERTY CATEGORIES

    - Villas for sale
    - Apartments for sale
    - Properties for rent
    - Luxury villas
    - Luxury apartments
    - Land for sale
    - Daily rental properties

    POPULAR CITIES

    - Riyadh
    - Jeddah
    - Makkah
    - Madinah
    - Dammam
    - Al Khobar
    - Khamis Mushayt

    POPULAR RIYADH DISTRICTS

    - Al Rimal
    - Al Olaya
    - Al Yasmeen
    - Al Khaleej
    - Al Nakheel

    REAL ESTATE INVESTMENT

    Wasalt provides access to verified projects and investment
    opportunities.

    Users can explore projects and connect with relevant
    property experts through its matching service.

    MATCHMAKER

    Users can share their property requirements and get
    connected with relevant property professionals.

    AUCTIONS

    Wasalt provides access to Infath and private auctions
    across Saudi Arabia.

    Auction categories include:
    - Real estate
    - Vehicles
    - Movable assets

    INTERNATIONAL PROPERTIES

    Wasalt also promotes international luxury properties,
    global access, exclusive listings, and premium living.

    ABOUT WASALT

    Wasalt is a Saudi-based platform designed to make it easier
    to discover properties, explore opportunities, and connect
    with property experts across the Kingdom.

    LICENSES AND REGISTRATION

    REGA License Number: 1200016591

    Ministry of Tourism License Number: 73106008

    Commercial Registration Number: 7017195509

    Tourism category: Accommodation & Unit Reservation

    APPLICATIONS

    Wasalt provides:
    - Wasalt consumer application
    - Wasalt Business application

    IMPORTANT LIMITATION

    This homepage information does not provide individual
    property prices, availability, exact addresses, or live
    property listing details.

    The chatbot must not invent these details.
    """

    return upsert_document(
        source=(
            "https://wasalt.sa/en"
            "#manually-provided-homepage"
        ),
        domain="Wasalt",
        title=(
            "Wasalt Homepage - Services, Properties and Locations"
        ),
        content=content,
        fetched_at=datetime.now(
            timezone.utc
        ).isoformat(),
    )


# ---------------------------------------------------------
# WEBSITE CRAWLER
# ---------------------------------------------------------

def crawl_site(domain, config, max_pages):
    """
    Crawl one website and save extracted pages.
    """

    base = config["base"]

    result = {
        "visited": 0,
        "saved": 0,
        "errors": [],
    }

    queue = list(config["seeds"])
    visited = set()

    consecutive_403 = 0

    with get_client() as client:

        robots = get_robots(client, base)

        if robots is None:
            result["errors"].append(
                f"{domain}: robots.txt unavailable; crawl skipped"
            )
            return result

        # Add sitemap URLs
        discovered = sitemap_urls(
            client,
            base,
            robots
        )

        queue.extend(discovered)

        while queue and result["visited"] < max_pages:

            url = normalize_url(queue.pop(0))

            if url in visited:
                continue

            if not allowed(url, base):
                continue

            # Respect robots.txt
            if not robots.can_fetch(USER_AGENT, url):
                continue

            visited.add(url)

            try:

                title, content, links = extract_page(
                    client,
                    url
                )

                consecutive_403 = 0

                result["visited"] += 1

                if len(content) >= 80:

                    saved = upsert_document(
                        source=url,
                        domain=domain,
                        title=title,
                        content=content,
                        fetched_at=datetime.now(
                            timezone.utc
                        ).isoformat(),
                    )

                    if saved:
                        result["saved"] += 1

                # Add newly discovered links
                for link in links:

                    link = normalize_url(link)

                    if (
                        link not in visited
                        and link not in queue
                        and allowed(link, base)
                    ):
                        queue.append(link)

                time.sleep(REQUEST_DELAY)

            except httpx.HTTPStatusError as exc:

                status_code = exc.response.status_code

                error_message = (
                    f"{domain}: {url}: HTTP {status_code}"
                )

                result["errors"].append(error_message)

                if status_code == 403:

                    consecutive_403 += 1

                    if consecutive_403 >= MAX_CONSECUTIVE_403:

                        result["errors"].append(
                            f"{domain}: Repeated HTTP 403 responses; "
                            "remaining crawl skipped"
                        )

                        break

                elif status_code == 404:
                    continue

            except Exception as exc:

                result["errors"].append(
                    f"{domain}: {url}: {str(exc)}"
                )

    return result


# ---------------------------------------------------------
# MAIN INGESTION FUNCTION
# ---------------------------------------------------------

def crawl(max_pages=MAX_PAGES_PER_SITE):
    """
    Crawl configured websites and index manually supplied
    Wasalt homepage information.
    """

    results = {
        "saved": 0,
        "visited": 0,
        "errors": [],
        "sites": {
            "DarGlobal": {
                "visited": 0,
                "saved": 0,
                "errors": [],
            },
            "Wasalt": {
                "visited": 0,
                "saved": 0,
                "errors": [],
            },
        },
    }

    # Crawl DarGlobal and Wasalt
    for domain, config in SITES.items():

        site_result = crawl_site(
            domain=domain,
            config=config,
            max_pages=max_pages,
        )

        results["sites"][domain] = site_result

        results["visited"] += site_result["visited"]
        results["saved"] += site_result["saved"]

        results["errors"].extend(
            site_result["errors"]
        )

    # Add manually provided Wasalt homepage knowledge
    try:

        manual_saved = ingest_manual_wasalt_homepage()

        if manual_saved:

            results["saved"] += 1
            results["sites"]["Wasalt"]["saved"] += 1

    except Exception as exc:

        error_message = (
            f"Wasalt manual knowledge ingestion failed: {exc}"
        )

        results["errors"].append(error_message)

        results["sites"]["Wasalt"]["errors"].append(
            error_message
        )

    return results
