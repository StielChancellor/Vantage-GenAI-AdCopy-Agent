"""Web scraper for hotel reference URLs with 1-level deep crawling."""
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from backend.app.core.database import get_firestore
from backend.app.core.config import get_settings

settings = get_settings()

# Relevant subpages to crawl one level deep
RELEVANT_PATHS = [
    "rooms", "suites", "amenities", "dining", "spa", "facilities",
    "about", "experiences", "offers", "packages", "accommodation",
    "restaurant", "pool", "fitness", "wellness",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VantageAdCopyBot/1.0; +https://vantage-genai.com)"
}


async def scrape_hotel_page(url: str) -> dict:
    """Scrape a hotel's primary page and relevant subpages (1 level deep)."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
        # Scrape main page
        resp = await client.get(url)
        resp.raise_for_status()
        main_soup = BeautifulSoup(resp.text, "lxml")

        main_text = _extract_text(main_soup)
        title = main_soup.title.string if main_soup.title else ""

        # Find relevant subpage links
        subpage_texts = []
        base_domain = urlparse(url).netloc
        links = main_soup.find_all("a", href=True)

        subpage_urls = set()
        for link in links:
            href = urljoin(url, link["href"])
            parsed = urlparse(href)
            # Same domain only
            if parsed.netloc != base_domain:
                continue
            path_lower = parsed.path.lower().strip("/")
            # Check if path contains relevant keywords
            if any(kw in path_lower for kw in RELEVANT_PATHS):
                subpage_urls.add(href)

        # Crawl subpages (limit to 5 to avoid overloading)
        for sub_url in list(subpage_urls)[:5]:
            try:
                sub_resp = await client.get(sub_url)
                sub_resp.raise_for_status()
                sub_soup = BeautifulSoup(sub_resp.text, "lxml")
                subpage_texts.append(_extract_text(sub_soup))
            except Exception:
                continue

    combined_text = main_text + "\n\n".join(subpage_texts)
    # Trim to reasonable size for LLM context
    combined_text = combined_text[:8000]

    return {
        "title": title,
        "url": url,
        "content": combined_text,
        "subpages_crawled": len(subpage_texts),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_text(soup: BeautifulSoup) -> str:
    """Extract meaningful text from HTML, removing scripts/styles/nav."""
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Clean up excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
