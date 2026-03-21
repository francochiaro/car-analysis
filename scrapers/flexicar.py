#!/usr/bin/env python3
"""
Flexicar.es Playwright browser automation scraper.
Scrapes their Next.js SPA by rendering pages with headless Chromium.
Outputs normalized JSON to stdout.
"""

import asyncio
import json
import re
import sys
from dataclasses import asdict

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Missing playwright. Run: pip3 install playwright && python3 -m playwright install chromium",
          file=sys.stderr)
    sys.exit(1)

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage,
                   parse_hp, detect_fuel_type, detect_transmission,
                   extract_location_from_url)


# Flexicar brand URL slugs
BRAND_SLUGS = {
    "alfa-romeo": "alfa-romeo",
    "audi": "audi",
    "bmw": "bmw",
    "cupra": "cupra",
    "hyundai": "hyundai",
    "kia": "kia",
    "lexus": "lexus",
    "mazda": "mazda",
    "mercedes": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "mitsubishi": "mitsubishi",
    "skoda": "skoda",
    "tesla": "tesla",
    "toyota": "toyota",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "volvo": "volvo",
}

BASE_URL = "https://www.flexicar.es"


async def scrape_brand_listing(context, brand_slug: str) -> list:
    """Scrape car cards from a brand listing page."""
    url = f"{BASE_URL}/{brand_slug}/segunda-mano/"
    page = await context.new_page()
    cards = []

    try:
        print(f"  [{brand_slug}] Loading listing page...", file=sys.stderr)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Accept cookies
        try:
            btn = page.locator("button:has-text('Aceptar'), button:has-text('Acepto')")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        # Scroll to load more (Flexicar SSR renders ~12 cards)
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            try:
                load_more = page.locator("button:has-text('Ver más'), button:has-text('Cargar más')")
                if await load_more.count() > 0 and await load_more.first.is_visible():
                    await load_more.first.click()
                    await page.wait_for_timeout(2000)
            except:
                pass

        # Extract car links
        raw_cards = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a[href*="/coches-ocasion/"]').forEach(a => {
                const href = a.getAttribute('href');
                if (!href || href.endsWith('/coches-ocasion/')) return;
                const img = a.querySelector('img');
                results.push({
                    url: href.startsWith('http') ? href : 'https://www.flexicar.es' + href,
                    text: (a.innerText || '').trim().substring(0, 500),
                    image: img ? (img.src || img.getAttribute('data-src') || '') : ''
                });
            });
            return results;
        }""")

        print(f"  [{brand_slug}] Found {len(raw_cards)} card links", file=sys.stderr)
        cards = raw_cards

    except Exception as e:
        print(f"  [{brand_slug}] ERROR: {e}", file=sys.stderr)
    finally:
        await page.close()

    return cards


async def scrape_detail_page(context, url: str, semaphore) -> dict:
    """Scrape full specs from a car detail page."""
    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

            data = await page.evaluate("""() => {
                const body = document.body.innerText || '';
                const title = document.title || '';
                const imgs = document.querySelectorAll('img');
                let image = '';
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.includes('Exterior') || src.includes('imp2f')) {
                        image = src; break;
                    }
                }
                if (!image) {
                    for (const img of imgs) {
                        if (img.naturalWidth > 200 || img.width > 200) {
                            image = img.src; break;
                        }
                    }
                }
                // Extract prices
                const prices = [];
                document.querySelectorAll('[class*="price"], [class*="precio"]').forEach(el => {
                    const p = parseInt(el.textContent.replace(/[^\\d]/g, ''));
                    if (p > 5000 && p < 200000) prices.push(p);
                });
                return { title, body: body.substring(0, 3000), image, prices, url: window.location.href };
            }""")
            return data
        except Exception as e:
            return {"error": str(e), "url": url}
        finally:
            await page.close()


def parse_car_from_detail(raw_card: dict, detail: dict, brand_slug: str) -> CarListing:
    """Build a normalized CarListing from raw card + detail data."""
    url = raw_card.get("url", "")
    text = raw_card.get("text", "") + "\n" + detail.get("body", "")
    title = detail.get("title", "")

    car = CarListing(
        platform="flexicar",
        url=url,
        image_url=detail.get("image") or raw_card.get("image", ""),
    )

    # Make from brand slug
    car.make = normalize_brand(brand_slug)

    # Model + variant from title
    # Title pattern: "Comprar {Make} {Model} {Variant} de segunda mano..."
    if title:
        cleaned = re.sub(r'(Comprar|de segunda mano|Flexicar|coches ocasión).*', '', title, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^' + re.escape(car.make) + r'\s*', '', cleaned, flags=re.IGNORECASE).strip()
        parts = cleaned.split(" ", 1)
        if parts:
            car.model = parts[0].strip()
            car.variant = parts[1].strip() if len(parts) > 1 else ""

    # Year
    year_match = re.findall(r'\b(20[2-9]\d)\b', text)
    if year_match:
        car.year = int(year_match[0])

    # HP
    hp = parse_hp(text)
    if hp:
        car.hp = hp

    # Mileage
    km = parse_mileage(text)
    if km:
        car.mileage_km = km

    # Fuel
    car.fuel_type = detect_fuel_type(text)

    # Transmission
    car.transmission = detect_transmission(text)

    # Price — use the lowest from detail page prices, or parse from text
    if detail.get("prices"):
        car.price = min(detail["prices"])
        if len(detail["prices"]) > 1:
            car.original_price = max(detail["prices"])
    else:
        # Try to parse from text
        price_matches = re.findall(r'([\d.]+)\s*€', text.replace('.', '').replace(',', '.'))
        prices = []
        for p in price_matches:
            try:
                val = int(float(p))
                if 5000 < val < 200000:
                    prices.append(val)
            except:
                pass
        if prices:
            car.price = min(prices)

    # Location from URL
    car.location = extract_location_from_url(url)

    # Body type
    car.body_type = detect_body_type(car.model, car.variant)

    return car


async def scrape_flexicar(filters: SearchFilters) -> list:
    """Full Flexicar scrape: listing pages → detail pages → normalized output."""
    print(f"[flexicar] Starting scrape: price≤{filters.max_price}, year≥{filters.min_year}, "
          f"brands={len(filters.brands)}", file=sys.stderr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Phase 1: Listing pages
        all_raw_cards = []
        brand_map = {}  # url → brand_slug

        for brand in filters.brands:
            slug = BRAND_SLUGS.get(brand.lower(), brand.lower())
            cards = await scrape_brand_listing(context, slug)
            for card in cards:
                brand_map[card["url"]] = slug
            all_raw_cards.extend(cards)

        # Deduplicate by URL
        seen = set()
        unique_cards = []
        for card in all_raw_cards:
            if card["url"] not in seen:
                seen.add(card["url"])
                unique_cards.append(card)

        print(f"[flexicar] {len(unique_cards)} unique detail URLs from {len(filters.brands)} brands",
              file=sys.stderr)

        # Phase 2: Detail pages (batched, 3 concurrent)
        semaphore = asyncio.Semaphore(3)
        detail_data = {}

        for i in range(0, len(unique_cards), 10):
            batch = unique_cards[i:i+10]
            batch_num = i // 10 + 1
            total_batches = (len(unique_cards) + 9) // 10
            print(f"[flexicar] Detail batch {batch_num}/{total_batches}...", file=sys.stderr)
            tasks = [scrape_detail_page(context, c["url"], semaphore) for c in batch]
            results = await asyncio.gather(*tasks)
            for card, data in zip(batch, results):
                detail_data[card["url"]] = data
            await asyncio.sleep(1)

        await browser.close()

    # Phase 3: Parse and filter
    cars = []
    for card in unique_cards:
        detail = detail_data.get(card["url"], {})
        brand_slug = brand_map.get(card["url"], "")
        car = parse_car_from_detail(card, detail, brand_slug)

        # Apply filters
        if car.price > filters.max_price:
            continue
        if car.year < filters.min_year:
            continue
        if car.mileage_km > filters.max_mileage:
            continue
        if filters.transmission == "automatic" and car.transmission.lower() not in ("automatic", "automática", ""):
            continue

        if car.is_valid():
            cars.append(car)

    print(f"[flexicar] Done: {len(cars)} qualifying cars", file=sys.stderr)
    return cars


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = asyncio.run(scrape_flexicar(filters))
    output_results(cars)
