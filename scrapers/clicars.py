#!/usr/bin/env python3
"""
Clicars.es HTTP scraper.
Scrapes server-rendered listing pages — no browser automation needed.
Outputs normalized JSON to stdout.
"""

import asyncio
import json
import re
import sys
from urllib.parse import urlencode
from dataclasses import asdict

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip3 install requests beautifulsoup4 lxml", file=sys.stderr)
    sys.exit(1)

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage, parse_price,
                   parse_hp, parse_year, detect_fuel_type, detect_transmission)


# Clicars brand ID mapping (from their URL params)
BRAND_IDS = {
    "alfa-romeo": 3, "audi": 9, "bmw": 15, "cupra": 25, "hyundai": 41,
    "kia": 43, "lexus": 53, "mazda": 60, "mercedes": 65, "mitsubishi": 68,
    "skoda": 69, "tesla": 72, "toyota": 82, "volkswagen": 91, "volvo": 100,
    # Additional aliases
    "mercedes-benz": 65, "vw": 91,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9",
}


def build_url(filters: SearchFilters, page: int = 1) -> str:
    """Build Clicars search URL with filters."""
    params = []

    # Brand IDs
    for brand in filters.brands:
        brand_key = brand.lower().strip()
        if brand_key in BRAND_IDS:
            params.append(f"makers[]={BRAND_IDS[brand_key]}")

    # Transmission
    if filters.transmission == "automatic":
        transmission_slug = "automatico"
    else:
        transmission_slug = ""

    # Price and year
    params.append(f"priceMax={filters.max_price}")
    params.append(f"yearMin={filters.min_year}")
    params.append("order=price.desc")

    if page > 1:
        params.append(f"page={page}")

    base = f"https://www.clicars.com/coches-segunda-mano-ocasion"
    if transmission_slug:
        base += f"/{transmission_slug}"

    return f"{base}?{'&'.join(params)}"


def parse_listing_page(html: str) -> list:
    """Parse car listings from a Clicars search results page."""
    soup = BeautifulSoup(html, "lxml")
    cars = []

    # Find car cards — they're typically <a> tags linking to /coches-segunda-mano-ocasion/comprar-*
    links = soup.find_all("a", href=re.compile(r"/coches-segunda-mano-ocasion/comprar-"))
    seen_urls = set()

    for link in links:
        href = link.get("href", "")
        if href in seen_urls:
            continue
        seen_urls.add(href)

        url = f"https://www.clicars.com{href}" if not href.startswith("http") else href
        text = link.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Find image
        img = link.find("img")
        image_url = ""
        if img:
            image_url = img.get("src") or img.get("data-src") or ""

        car = CarListing(platform="clicars", url=url, image_url=image_url)

        # Parse from text lines
        for line in lines:
            # Prices
            price = parse_price(line)
            if price:
                if not car.price:
                    car.price = price
                elif price < car.price:
                    # Lower price = sale price
                    car.original_price = car.price
                    car.price = price
                elif price > car.price:
                    car.original_price = price

            # Mileage
            km = parse_mileage(line)
            if km:
                car.mileage_km = km

            # Year
            year = parse_year(line)
            if year and not car.year:
                car.year = year

            # HP
            hp = parse_hp(line)
            if hp:
                car.hp = hp

            # Fuel
            fuel = detect_fuel_type(line)
            if fuel:
                car.fuel_type = fuel

            # Transmission
            trans = detect_transmission(line)
            if trans:
                car.transmission = trans

        # Extract make/model from URL
        # Pattern: /comprar-{make}-{model}-{variant}-...-{id}
        url_match = re.search(r'/comprar-([^/]+?)_?\d+/?$', href) if href else None
        if url_match:
            slug = url_match.group(1)
            # Try to extract make from the slug
            for brand_slug, brand_name in [
                ("alfa-romeo", "Alfa Romeo"), ("audi", "Audi"), ("bmw", "BMW"),
                ("cupra", "CUPRA"), ("hyundai", "Hyundai"), ("kia", "Kia"),
                ("lexus", "Lexus"), ("mazda", "Mazda"),
                ("mercedes", "Mercedes"), ("mitsubishi", "Mitsubishi"),
                ("skoda", "Skoda"), ("tesla", "Tesla"), ("toyota", "Toyota"),
                ("volkswagen", "Volkswagen"), ("volvo", "Volvo"),
            ]:
                if slug.startswith(brand_slug):
                    car.make = brand_name
                    remainder = slug[len(brand_slug)+1:]  # +1 for the dash
                    # Try to get model
                    model_parts = remainder.split("-")
                    if len(model_parts) >= 2:
                        # Model is usually the first meaningful segment(s)
                        car.model = " ".join(model_parts[:2]).title()
                        car.variant = " ".join(model_parts[2:]).title() if len(model_parts) > 2 else ""
                    break

        # Detect body type
        if car.model:
            car.body_type = detect_body_type(car.model, car.variant)

        if car.is_valid():
            cars.append(car)

    return cars


def scrape_clicars(filters: SearchFilters) -> list:
    """Scrape all matching cars from Clicars."""
    all_cars = []
    page = 1
    max_pages = 30  # Safety limit
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"[clicars] Starting scrape with filters: price≤{filters.max_price}, "
          f"year≥{filters.min_year}, brands={len(filters.brands)}", file=sys.stderr)

    while page <= max_pages:
        url = build_url(filters, page)
        print(f"[clicars] Page {page}: {url[:100]}...", file=sys.stderr)

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[clicars] Error on page {page}: {e}", file=sys.stderr)
            break

        cars = parse_listing_page(resp.text)
        if not cars:
            print(f"[clicars] No cars found on page {page}, stopping.", file=sys.stderr)
            break

        # Apply post-filters
        for car in cars:
            if filters.max_mileage and car.mileage_km > filters.max_mileage:
                continue
            all_cars.append(car)

        print(f"[clicars] Page {page}: {len(cars)} cars parsed, {len(all_cars)} total", file=sys.stderr)
        page += 1

    # Deduplicate by URL
    seen = set()
    deduped = []
    for car in all_cars:
        if car.url not in seen:
            seen.add(car.url)
            deduped.append(car)

    print(f"[clicars] Done: {len(deduped)} unique cars", file=sys.stderr)
    return deduped


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = scrape_clicars(filters)
    output_results(cars)
