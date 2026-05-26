# price_tracker.py
"""Check the current price of an online product (Amazon and similar pages).

Ported and generalised from the gaurav-jarvis "amazon.py" price-tracker, which
scraped an Amazon product page and emailed an alert when the price dropped.

Given a product URL it scrapes the live price and reports it. If a `target`
price is supplied and the current price is at or below it, it optionally sends
an email alert (reusing the existing send_email tool / Gmail config).

Note: scraping retail sites is inherently fragile — pages change layout and may
block automated requests. This tries several common selectors and degrades
gracefully with a clear message when it can't find a price.
"""
import re

import requests
from bs4 import BeautifulSoup

try:
    from actions.email_sender import send_email
except Exception:  # pragma: no cover - allow standalone import
    from email_sender import send_email

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

# CSS selectors tried in order — covers current and legacy Amazon layouts plus
# common Open Graph / schema.org price tags on other shops.
_PRICE_SELECTORS = [
    "span.a-price span.a-offscreen",
    "#corePrice_feature_div span.a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#priceblock_saleprice",
    "span.a-price-whole",
    'meta[property="product:price:amount"]',
    'meta[property="og:price:amount"]',
    'meta[itemprop="price"]',
    '[itemprop="price"]',
    # Generic fallbacks for other shops
    ".price_color",
    ".product-price",
    ".price",
]


def _parse_amount(text: str) -> float | None:
    """Pull the first sensible numeric amount out of a price string."""
    if not text:
        return None
    # Keep digits, separators; drop currency symbols/words.
    m = re.search(r"\d[\d.,]*", text.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(0)
    # If both separators present, assume the last one is the decimal point.
    if "," in raw and "." in raw:
        raw = raw.replace("," if raw.rfind(".") > raw.rfind(",") else ".", "")
        raw = raw.replace(",", ".") if "." not in raw else raw
    else:
        # Lone comma -> treat as thousands sep if it looks like one (e.g. 1,299)
        if raw.count(",") == 1 and len(raw.split(",")[-1]) == 3:
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract(soup: BeautifulSoup):
    for sel in _PRICE_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        raw = el.get("content") if el.has_attr("content") else el.get_text()
        amount = _parse_amount(raw or "")
        if amount is not None:
            return amount, (raw or "").strip()
    return None, None


def _title(soup: BeautifulSoup) -> str:
    for sel in ("#productTitle", 'meta[property="og:title"]', "title"):
        el = soup.select_one(sel)
        if el:
            text = el.get("content") if el.has_attr("content") else el.get_text()
            if text and text.strip():
                return text.strip()[:90]
    return "the product"


def track_price(parameters: dict = None, response=None, player=None,
                session_memory=None) -> str:
    params = parameters or {}
    url = str(params.get("url", "")).strip()
    if not url.startswith("http"):
        return "Sir, please give me the full product URL to check its price."

    target_raw = params.get("target")
    target = None
    if target_raw not in (None, ""):
        target = _parse_amount(str(target_raw))

    notify_email = str(params.get("notify_email", "")).strip()

    print(f"[Price] 🔎 {url[:70]}")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        resp.raise_for_status()
    except Exception as e:
        return f"Sir, I couldn't reach that page: {e}"

    # Use raw bytes so BeautifulSoup detects the real encoding (avoids £ -> Â£).
    soup = BeautifulSoup(resp.content, "html.parser")
    amount, raw_price = _extract(soup)
    title = _title(soup)

    if amount is None:
        return ("I reached the page but couldn't read a price — the site may "
                "have blocked the request or changed its layout, sir.")

    result = f"The current price of {title} is {raw_price}."

    # Target comparison + optional email alert.
    if target is not None:
        if amount <= target:
            result += f" That's at or below your target of {target:g}, sir — good time to buy!"
            if notify_email:
                mail = send_email(parameters={
                    "to": notify_email,
                    "subject": "Price drop alert",
                    "body": (f"{title}\n\nCurrent price: {raw_price} "
                             f"(target {target:g})\n\n{url}"),
                }, player=player)
                result += f" ({mail})"
        else:
            result += f" It's still above your target of {target:g}, sir."

    if player:
        player.write_log(f"[price] {raw_price} — {title[:40]}")
    if session_memory:
        try:
            session_memory.set_last_search(query=f"price of {title}", response=result)
        except Exception:
            pass
    return result
