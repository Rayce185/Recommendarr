"""Minimal RSS/Atom parser — no external XML dependency needed.

Handles RSS 2.0 and Atom feeds, extracts title/description/link/published.
Used by Cultural Pulse for feed ingestion.
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


async def fetch_rss(url: str, max_items: int = 20) -> list[dict]:
    """Fetch RSS feed, return list of {title, description, link, published}."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url, headers={"User-Agent": "Recommendarr/1.0"})
            resp.raise_for_status()
            return parse_rss_xml(resp.text, max_items)
    except Exception as e:
        logger.warning(f"RSS fetch failed for {url}: {e}")
        return []


def parse_rss_xml(xml_text: str, max_items: int) -> list[dict]:
    """Parse RSS/Atom XML into structured dicts."""
    items = []
    # Match <item> or <entry> blocks
    for block_match in re.finditer(r'<(?:item|entry)[\s>](.*?)</(?:item|entry)>', xml_text, re.DOTALL):
        block = block_match.group(1)
        title = _xml_extract(block, "title")
        desc = _xml_extract(block, "description") or _xml_extract(block, "summary") or ""
        link = _xml_extract(block, "link") or _xml_attr(block, "link", "href")
        pub = _xml_extract(block, "pubDate") or _xml_extract(block, "published") or ""

        if title:
            # Strip HTML from description
            clean_desc = re.sub(r'<[^>]+>', '', desc).strip()[:500]
            items.append({
                "title": title.strip(),
                "description": clean_desc,
                "link": link,
                "published": pub,
            })
            if len(items) >= max_items:
                break
    return items


def _xml_extract(block: str, tag: str) -> Optional[str]:
    """Extract text content from an XML tag."""
    m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', block, re.DOTALL)
    if m:
        text = m.group(1).strip()
        cdata = re.match(r'<!\[CDATA\[(.*?)\]\]>', text, re.DOTALL)
        return cdata.group(1) if cdata else text
    return None


def _xml_attr(block: str, tag: str, attr: str) -> Optional[str]:
    """Extract attribute value from a self-closing or open tag."""
    m = re.search(rf'<{tag}\s[^>]*{attr}=["\']([^"\']+)["\']', block)
    return m.group(1) if m else None
