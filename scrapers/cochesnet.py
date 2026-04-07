#!/usr/bin/env python3
"""
Coches.net Playwright browser automation scraper.
Scrapes the largest car marketplace in Spain — filters for professional/dealer sellers only.
Outputs normalized JSON to stdout.
"""

import asyncio
import re
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Missing playwright. Run: pip3 install playwright && python3 -m playwright install chromium",
          file=sys.stderr)
    sys.exit(1)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage, parse_price,
                   parse_hp, detect_fuel_type, detect_transmission)


# Coches.net brand URL slugs — path-based filtering is more reliable than MakeIds
# Slugs verified from coches.net's own SEO footer links
BRAND_SLUGS = {
    "alfa-romeo": "alfa_romeo",
    "audi": "audi",
    "bmw": "bmw",
    "byd": "byd",
    "cupra": "cupra",
    "honda": "honda",
    "hyundai": "hyundai",
    "jaguar": "jaguar",
    "kia": "kia",
    "lexus": "lexus",
    "mazda": "mazda",
    "mercedes": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "mitsubishi": "mitsubishi",
    "nissan": "nissan",
    "porsche": "porsche",
    "skoda": "skoda",
    "subaru": "subaru",
    "tesla": "tesla",
    "toyota": "toyota",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "volvo": "volvo",
}

# SellerTypeId: 1 = Profesional (dealer), 2 = Particular (private)
SELLER_TYPE_PROFESSIONAL = 1

BASE_URL = "https://www.coches.net"


def build_search_url(filters: SearchFilters, brand_slug: str, page: int = 1) -> str:
    """Build a coches.net search URL using path-based brand filtering + query params.

    URL pattern: https://www.coches.net/{brand}/segunda-mano/?MaxPrice=...&SellerTypeId=1&pg=1
    Path-based brand filtering is reliable; query params handle all other filters.
    """
    brand_key = brand_slug.lower().strip()
    url_slug = BRAND_SLUGS.get(brand_key)
    if not url_slug:
        return ""

    params = [
        f"MaxPrice={filters.max_price}",
        f"MinYear={filters.min_year}",
        f"MaxKms={filters.max_mileage}",
        f"SellerTypeId={SELLER_TYPE_PROFESSIONAL}",
    ]

    # Transmission: 1 = Automatic, 2 = Manual
    if filters.transmission.lower() == "automatic":
        params.append("TransmissionTypeId=1")
    elif filters.transmission.lower() == "manual":
        params.append("TransmissionTypeId=2")

    # Fuel types (IDs discovered from site: 1=Diesel, 2=Gasolina, 3=PHEV, 4=Electric, 5=Hybrid)
    fuel_id_map = {
        "diesel": 1, "gasoline": 2, "electric": 4, "hybrid": 5, "phev": 3,
    }
    for i, ft in enumerate(filters.fuel_types):
        fuel_id = fuel_id_map.get(ft.lower())
        if fuel_id:
            params.append(f"FuelTypeIds[{i}]={fuel_id}")

    # Pagination
    params.append(f"pg={page}")

    return f"{BASE_URL}/{url_slug}/segunda-mano/?{'&'.join(params)}"


def parse_url_metadata(url: str) -> dict:
    """Extract make, model, variant, fuel, year, location from a coches.net listing URL.

    URL patterns:
      /bmw-serie-1-118d-business-auto-5p-diesel-2022-en-alicante-70259508-covo.aspx
      /tesla-model-3-electrico-hibrido-2020-en-malaga-62665195-covo.aspx  (no doors)
    """
    # Try standard pattern with door count first
    match = re.search(
        r'/([a-z0-9-]+)-(\d+)p-([a-z-]+)-(\d{4})-en-([a-z0-9-]+)-(\d+)-covo\.aspx',
        url, re.IGNORECASE
    )
    if match:
        name_slug = match.group(1)
        fuel_slug = match.group(3)
        year = int(match.group(4))
        location_slug = match.group(5)
        listing_id = match.group(6)
    else:
        # Fallback: no door count — use non-greedy name_slug to avoid eating fuel slug
        match = re.search(
            r'/([a-z0-9-]+?)-(electrico-hibrido|diesel|gasolina|electrico|hibrido|gas-licuado|gas-natural)-(\d{4})-en-([a-z0-9-]+)-(\d+)-covo\.aspx',
            url, re.IGNORECASE
        )
        if not match:
            return {}
        name_slug = match.group(1)
        fuel_slug = match.group(2)
        year = int(match.group(3))
        location_slug = match.group(4)
        listing_id = match.group(5)

    # Parse make from the name slug
    make = ""
    model = ""
    variant = ""
    # Build a set of URL-level brand prefixes from BRAND_SLUGS values + keys
    brand_prefixes = set()
    for k, v in BRAND_SLUGS.items():
        brand_prefixes.add(k)
        # Also add the URL slug form (underscores → hyphens for URL matching)
        brand_prefixes.add(v.replace("_", "-"))
    for brand_slug in sorted(brand_prefixes, key=len, reverse=True):
        if brand_slug == "vw":
            continue  # skip alias
        if name_slug.startswith(brand_slug + "-") or name_slug == brand_slug:
            make = normalize_brand(brand_slug)
            remainder = name_slug[len(brand_slug) + 1:] if len(name_slug) > len(brand_slug) else ""
            if remainder:
                parts = remainder.split("-")
                # Model is typically 1-3 segments (e.g., "serie-1", "x1", "serie-2-gran-coupe")
                # Heuristic: if it starts with "serie", take first 2 parts as model
                if parts[0] in ("serie", "clase", "model"):
                    model = " ".join(parts[:2]).title() if len(parts) >= 2 else parts[0].title()
                    variant = " ".join(parts[2:]).title() if len(parts) > 2 else ""
                else:
                    model = parts[0].upper() if len(parts[0]) <= 3 else parts[0].title()
                    variant = " ".join(parts[1:]).title() if len(parts) > 1 else ""
            break

    # Fuel type from URL slug
    fuel_map = {
        "diesel": "Diesel",
        "gasolina": "Gasoline",
        "electrico": "Electric",
        "electrico-hibrido": "PHEV",
        "hibrido": "Hybrid",
        "gas-licuado": "LPG",
        "gas-natural": "CNG",
    }
    fuel_type = fuel_map.get(fuel_slug, "")

    location = location_slug.replace("-", " ").title()

    return {
        "make": make,
        "model": model,
        "variant": variant,
        "fuel_type": fuel_type,
        "year": year,
        "location": location,
        "listing_id": listing_id,
    }


async def extract_cards_from_page(page) -> list:
    """Extract all car card data from the current page using DOM queries."""
    return await page.evaluate("""() => {
        const cards = document.querySelectorAll('.mt-CardAd');
        const results = [];

        cards.forEach(card => {
            try {
                // Title and URL
                const titleLink = card.querySelector('.mt-CardAd-infoHeaderTitleLink');
                if (!titleLink) return;

                const title = (titleLink.textContent || '').trim();
                const href = titleLink.href || titleLink.getAttribute('href') || '';
                if (!href || !href.includes('-covo.aspx')) return;
                const url = href.startsWith('http') ? href : 'https://www.coches.net' + href;

                // Price
                const priceEl = card.querySelector('.mt-CardAdPrice-cashAmount');
                const priceText = priceEl ? priceEl.textContent.trim() : '';

                // Original price (crossed out / financed label area)
                const cashLabel = card.querySelector('.mt-CardAdPrice-cashLabel');
                const cashLabelText = cashLabel ? cashLabel.textContent.trim() : '';

                // Attributes: [fuel_type, year, km, cv, location]
                const attrItems = card.querySelectorAll('.mt-CardAd-attrItem');
                const attrs = [];
                attrItems.forEach(a => {
                    const text = a.textContent.trim();
                    // Skip environmental label items
                    if (!a.classList.contains('mt-CardAd-attrItemEnvironmentalLabel') && text) {
                        attrs.push(text);
                    }
                });

                // Tags (Profesional, Reservable, etc.)
                const tagEls = card.querySelectorAll('.mt-CardAd-tag');
                const tags = [];
                tagEls.forEach(t => tags.push(t.textContent.trim()));

                // Image — try multiple sources (lazy-loaded images use data-src or srcset)
                let imageUrl = '';
                const imgSelectors = [
                    'img[src*="ccdn.es/cnet"]',
                    'img[data-src*="ccdn.es/cnet"]',
                    'img[src*="ccdn.es"]',
                    '.mt-CardAd-media img',
                    '.mt-CardAd-mediaContainer img',
                ];
                for (const sel of imgSelectors) {
                    const img = card.querySelector(sel);
                    if (img) {
                        imageUrl = img.src || img.getAttribute('data-src') ||
                                   img.getAttribute('srcset')?.split(' ')[0] || '';
                        if (imageUrl && !imageUrl.includes('eco-label') && !imageUrl.includes('data:image')) {
                            break;
                        }
                        imageUrl = '';
                    }
                }
                // Last resort: any img with a real URL
                if (!imageUrl) {
                    const anyImg = card.querySelector('img');
                    if (anyImg) {
                        const src = anyImg.src || anyImg.getAttribute('data-src') || '';
                        if (src && !src.includes('eco-label') && !src.includes('data:image')
                            && !src.includes('.svg')) {
                            imageUrl = src;
                        }
                    }
                }

                results.push({
                    title: title,
                    url: url,
                    priceText: priceText,
                    cashLabelText: cashLabelText,
                    attrs: attrs,
                    tags: tags,
                    imageUrl: imageUrl
                });
            } catch(e) {
                // Skip malformed cards
            }
        });

        return results;
    }""")


def parse_card_to_listing(card: dict, search_transmission: str = "") -> CarListing:
    """Convert a raw card dict from DOM extraction into a normalized CarListing."""
    url = card.get("url", "")
    title = card.get("title", "")

    listing = CarListing(
        platform="coches.net",
        url=url,
        image_url=card.get("imageUrl", ""),
    )

    # Parse URL for structured metadata
    url_meta = parse_url_metadata(url)
    if url_meta:
        listing.make = url_meta.get("make", "")
        listing.model = url_meta.get("model", "")
        listing.variant = url_meta.get("variant", "")
        listing.year = url_meta.get("year", 0)
        listing.location = url_meta.get("location", "")
        listing.fuel_type = url_meta.get("fuel_type", "")

    # Override/supplement with title if URL parsing missed something
    if not listing.make and title:
        # Title format: "BMW Serie 1 118d Business Auto."
        for brand_slug, brand_name in [
            ("alfa romeo", "Alfa Romeo"), ("audi", "Audi"), ("bmw", "BMW"),
            ("cupra", "CUPRA"), ("hyundai", "Hyundai"), ("kia", "Kia"),
            ("lexus", "Lexus"), ("mazda", "Mazda"),
            ("mercedes-benz", "Mercedes"), ("mercedes", "Mercedes"),
            ("mitsubishi", "Mitsubishi"), ("skoda", "Skoda"), ("tesla", "Tesla"),
            ("toyota", "Toyota"), ("volkswagen", "Volkswagen"), ("volvo", "Volvo"),
        ]:
            if title.lower().startswith(brand_slug):
                listing.make = brand_name
                remainder = title[len(brand_slug):].strip()
                parts = remainder.split(" ", 1)
                if parts:
                    listing.model = parts[0]
                    listing.variant = parts[1] if len(parts) > 1 else ""
                break

    # Price from card text
    price_text = card.get("priceText", "")
    if price_text:
        price = parse_price(price_text)
        if price:
            listing.price = price

    # Attributes: typically [fuel_type, year, km, cv, location]
    attrs = card.get("attrs", [])
    for attr in attrs:
        attr_clean = attr.strip()
        if not attr_clean:
            continue

        # Year (4-digit number)
        year_match = re.match(r'^(20[1-3]\d)$', attr_clean)
        if year_match:
            listing.year = int(year_match.group(1))
            continue

        # Mileage (e.g., "44,897 km" or "108.000 km")
        km = parse_mileage(attr_clean)
        if km:
            listing.mileage_km = km
            continue

        # Horsepower (e.g., "150 cv")
        hp = parse_hp(attr_clean)
        if hp:
            listing.hp = hp
            continue

        # Fuel type
        fuel = detect_fuel_type(attr_clean)
        if fuel:
            listing.fuel_type = fuel
            continue

        # Location — remaining attr that's not a number pattern
        if not re.match(r'^[\d.,]+', attr_clean):
            # Strip "Ubicación" prefix if present
            loc = re.sub(r'^Ubicaci[oó]n\s*', '', attr_clean, flags=re.IGNORECASE)
            if loc and not listing.location:
                listing.location = loc

    # Transmission — detect from title, variant, and URL
    full_text = f"{title} {listing.variant}"
    listing.transmission = detect_transmission(full_text)
    # If not detected from text, check URL for common automatic keywords
    if not listing.transmission and url:
        url_lower = url.lower()
        auto_keywords = [
            "auto", "dct", "dsg", "s-tronic", "tiptronic", "steptronic",
            "xdrive", "e-cvt", "edct", "at-", "aut-",
        ]
        if any(kw in url_lower for kw in auto_keywords):
            listing.transmission = "Automatic"

    # If transmission still unknown but search filter was set to automatic,
    # all returned results are automatic (server-side filtered)
    if not listing.transmission and search_transmission == "automatic":
        listing.transmission = "Automatic"

    # Body type
    if listing.model:
        listing.body_type = detect_body_type(listing.model, listing.variant)

    return listing


async def get_total_results(page) -> int:
    """Extract total result count from the page heading (e.g., '1.292 BMW de segunda mano')."""
    try:
        count = await page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            if (h1) {
                const match = h1.textContent.match(/([\\d.]+)/);
                if (match) {
                    return parseInt(match[1].replace(/\\./g, ''), 10);
                }
            }
            return 0;
        }""")
        return count or 0
    except Exception:
        return 0


async def scrape_brand(context, filters: SearchFilters, brand_slug: str,
                       cookies_accepted: bool = False) -> tuple:
    """Scrape all pages of results for a single brand.

    Uses a single browser tab for all pages of the same brand to avoid
    Adevinta's bot detection which triggers on new tab creation patterns.

    Returns (list_of_cars, cookies_accepted_flag).
    """
    cars = []
    page_num = 1
    max_pages = 50  # Safety limit per brand
    total_results = 0
    cards_per_page = 36  # Expected cards per page on coches.net

    brand_display = normalize_brand(brand_slug)

    # Use a single tab for all pages of this brand (bot detection workaround)
    page = await context.new_page()

    try:
        while page_num <= max_pages:
            url = build_search_url(filters, brand_slug, page_num)
            if not url:
                print(f"  [{brand_display}] Unknown brand slug: {brand_slug}", file=sys.stderr)
                break

            if page_num == 1:
                print(f"  [{brand_display}] Loading page {page_num}: {url[:100]}...", file=sys.stderr)
            else:
                print(f"  [{brand_display}] Page {page_num}...", file=sys.stderr)

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Accept cookies (only needed once per context)
            if not cookies_accepted:
                try:
                    cookie_btn = page.locator(
                        "button:has-text('Aceptar'), button:has-text('Acepto'), "
                        "button:has-text('Accept'), #didomi-notice-agree-button"
                    )
                    if await cookie_btn.count() > 0:
                        await cookie_btn.first.click()
                        await page.wait_for_timeout(1000)
                        cookies_accepted = True
                except Exception:
                    pass

            # Wait for initial cards to render
            try:
                await page.wait_for_selector(".mt-CardAd", timeout=10000)
            except Exception:
                # Check if the page has a "no results" or bot detection message
                page_state = await page.evaluate("""() => {
                    const body = document.body.innerText || '';
                    return {
                        noResults: body.includes('No hemos encontrado') ||
                                   body.includes('Sin resultados') || body.includes('0 '),
                        botBlock: body.includes('bot') || body.includes('Ups!')
                    };
                }""")
                if page_state.get("botBlock"):
                    print(f"  [{brand_display}] Bot detection triggered on page {page_num}, stopping.",
                          file=sys.stderr)
                    break
                if page_state.get("noResults") and page_num == 1:
                    print(f"  [{brand_display}] No results for this brand/filters.", file=sys.stderr)
                else:
                    print(f"  [{brand_display}] No cards on page {page_num}, stopping.", file=sys.stderr)
                break

            # Get total result count on first page
            if page_num == 1:
                total_results = await get_total_results(page)
                if total_results:
                    est_pages = (total_results + cards_per_page - 1) // cards_per_page
                    max_pages = min(max_pages, est_pages)
                    print(f"  [{brand_display}] {total_results} total results (~{est_pages} pages)",
                          file=sys.stderr)

            # Scroll down to trigger lazy loading of all cards
            prev_count = 0
            for scroll_round in range(15):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(350)
                current_count = await page.evaluate(
                    "document.querySelectorAll('.mt-CardAd').length"
                )
                if current_count == prev_count and scroll_round > 4:
                    break  # No new cards loaded
                prev_count = current_count

            # Small extra wait for last cards to finish rendering
            await page.wait_for_timeout(500)

            # Extract card data
            raw_cards = await extract_cards_from_page(page)

            if not raw_cards:
                print(f"  [{brand_display}] No cards extracted on page {page_num}, stopping.",
                      file=sys.stderr)
                break

            # Parse cards
            page_cars = []
            for raw_card in raw_cards:
                car = parse_card_to_listing(raw_card, filters.transmission)
                if car.is_valid():
                    page_cars.append(car)

            cars.extend(page_cars)
            print(f"  [{brand_display}] Page {page_num}: {len(page_cars)} valid cars "
                  f"(from {len(raw_cards)} cards), {len(cars)} total", file=sys.stderr)

            # Determine if there are more pages
            if len(raw_cards) < 15:
                # Very few cards — likely last page or error
                break

            # Check pagination: look for links with pg= parameter for the next page
            next_page_num = page_num + 1
            has_next = await page.evaluate(
                """(nextPg) => {
                    const links = document.querySelectorAll('a[href*="pg="]');
                    for (const a of links) {
                        if (a.href.includes('pg=' + nextPg)) return true;
                    }
                    return false;
                }""",
                next_page_num
            )

            if not has_next:
                print(f"  [{brand_display}] No link to page {next_page_num} found, stopping.",
                      file=sys.stderr)
                break

            page_num += 1

            # Rate limiting between pages — human-like delay
            await asyncio.sleep(2 + (page_num % 3) * 0.5)

    except Exception as e:
        print(f"  [{brand_display}] Error on page {page_num}: {e}", file=sys.stderr)
    finally:
        await page.close()

    return cars, cookies_accepted


async def scrape_cochesnet(filters: SearchFilters) -> list:
    """Full coches.net scrape: iterate brands, paginate, extract & normalize."""
    print(f"[coches.net] Starting scrape: price<={filters.max_price}, year>={filters.min_year}, "
          f"transmission={filters.transmission}, brands={len(filters.brands)}, "
          f"max_mileage={filters.max_mileage}", file=sys.stderr)
    print(f"[coches.net] Filtering for PROFESSIONAL sellers only", file=sys.stderr)

    async with async_playwright() as p:
        # Coches.net (Adevinta) has aggressive bot detection that blocks headless browsers.
        # headless=False (headful) bypasses this reliably. A browser window will appear
        # but won't interfere with operation. On Linux, use Xvfb for headless-like behavior.
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
        )
        # Apply stealth patches to avoid detection fingerprints
        if HAS_STEALTH:
            stealth = Stealth(
                navigator_languages_override=("es-ES", "es"),
                navigator_platform_override="MacIntel",
            )
            await stealth.apply_stealth_async(context)

        all_cars = []
        cookies_accepted = False

        for brand in filters.brands:
            brand_cars, cookies_accepted = await scrape_brand(
                context, filters, brand, cookies_accepted
            )
            all_cars.extend(brand_cars)

            # Brief pause between brands to avoid rate limiting
            if brand != filters.brands[-1]:
                await asyncio.sleep(2)

        await browser.close()

    # Apply post-filters
    filtered = []
    for car in all_cars:
        if car.price > filters.max_price:
            continue
        if car.year < filters.min_year:
            continue
        if car.mileage_km > filters.max_mileage:
            continue
        if filters.transmission == "automatic" and car.transmission:
            if car.transmission.lower() not in ("automatic", "automática", "auto", ""):
                continue
        if filters.fuel_types:
            if car.fuel_type.lower() not in [f.lower() for f in filters.fuel_types]:
                continue
        filtered.append(car)

    # Deduplicate by URL
    seen = set()
    deduped = []
    for car in filtered:
        if car.url not in seen:
            seen.add(car.url)
            deduped.append(car)

    print(f"[coches.net] Done: {len(deduped)} unique cars "
          f"(from {len(all_cars)} total, {len(all_cars) - len(deduped)} filtered/duplicates)",
          file=sys.stderr)
    return deduped


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = asyncio.run(scrape_cochesnet(filters))
    output_results(cars)
