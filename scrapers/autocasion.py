#!/usr/bin/env python3
"""
Autocasion.com HTTP scraper.
Scrapes server-rendered listing pages from Spain's Vocento-group car marketplace.
Uses path-based filter URLs + query param pagination.
Outputs normalized JSON to stdout.
"""

import re
import sys

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip3 install requests beautifulsoup4 lxml", file=sys.stderr)
    sys.exit(1)

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage, parse_price,
                   parse_hp, parse_year, detect_fuel_type, detect_transmission)


# Autocasion brand slugs (used in URL path: /coches-segunda-mano/{slug}-ocasion)
BRAND_SLUGS = {
    "alfa-romeo": "alfa-romeo",
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

# Fuel type slugs for URL path filters
FUEL_SLUGS = {
    "diesel": "diesel",
    "gasoline": "gasolina",
    "electric": "electrico",
    "hybrid": "hibrido",
    "phev": "hibrido-enchufable",
}

# Transmission slugs for URL path filters
TRANSMISSION_SLUGS = {
    "automatic": "cambio-automatic",
    "manual": "cambio-manual",
}

BASE_URL = "https://www.autocasion.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9",
}


def build_url(brand_slug: str, filters: SearchFilters, page: int = 1) -> str:
    """Build Autocasion listing URL with path-based filters and query param pagination.

    URL structure: /coches-segunda-mano/{brand}-ocasion/{filter-segments}?sort=price&direction=desc&page={N}
    Supported path segments: cambio-automatic, precio-hasta-{N}, km-hasta-{N}, {fuel}
    Note: year filter (ano-desde) is NOT supported in the URL — applied as post-filter.
    """
    segments = [f"{brand_slug}-ocasion"]

    # Transmission
    if filters.transmission in TRANSMISSION_SLUGS:
        segments.append(TRANSMISSION_SLUGS[filters.transmission])

    # Price ceiling
    if filters.max_price:
        segments.append(f"precio-hasta-{filters.max_price}")

    # Mileage ceiling
    if filters.max_mileage:
        segments.append(f"km-hasta-{filters.max_mileage}")

    # Fuel type (only if a single fuel type is specified — multiple not supported in URL)
    if len(filters.fuel_types) == 1:
        fuel_key = filters.fuel_types[0].lower()
        if fuel_key in FUEL_SLUGS:
            segments.append(FUEL_SLUGS[fuel_key])

    path = "/coches-segunda-mano/" + "/".join(segments)
    params = f"sort=price&direction=desc&page={page}"
    return f"{BASE_URL}{path}?{params}"


def parse_listing_page(html: str) -> list:
    """Parse car listings from an Autocasion search results page.

    Each listing is an <article class="anuncio ..."> containing:
    - Image in <picture> / <img> tags
    - Detail link as <a href="..."> wrapping .contenido-anuncio
    - Title in <h2 itemprop="name"> or <h3 itemprop="name">
    - Price in <p class="precio">
    - Financed price in <p class="precio financiado">
    - Specs in <ul> with <li> items: year, fuel, mileage, location
    """
    soup = BeautifulSoup(html, "lxml")
    cars = []
    seen_urls = set()

    articles = soup.find_all("article", class_=re.compile(r"anuncio"))

    for article in articles:
        car = CarListing(platform="autocasion", url="")

        # --- Detail URL ---
        # Primary: <a> tag wrapping contenido-anuncio
        detail_link = article.find("a", href=re.compile(r"/coches-segunda-mano/|/coches-km0/"))
        if detail_link:
            href = detail_link.get("href", "")
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"
            car.url = href
        else:
            # Fallback: data-path attribute on carousel or image div
            path_el = article.find(attrs={"data-path": True})
            if path_el:
                path = path_el["data-path"]
                car.url = f"{BASE_URL}{path}" if path.startswith("/") else path

        if not car.url or car.url in seen_urls:
            continue
        seen_urls.add(car.url)

        # --- Image ---
        img = article.find("img")
        if img:
            car.image_url = img.get("src") or img.get("data-src") or ""
            # Fix protocol-relative URLs
            if car.image_url.startswith("//"):
                car.image_url = f"https:{car.image_url}"

        # --- Title (make + model + variant) ---
        title_el = article.find(["h2", "h3"], attrs={"itemprop": "name"})
        if title_el:
            title_text = title_el.get_text(strip=True)
            _parse_title(car, title_text)

        # --- Content block ---
        content = article.find("div", class_="contenido-anuncio")
        if not content:
            continue

        # --- Price ---
        price_el = content.find("p", class_="precio")
        if price_el:
            # Exclude nested <span> labels to get just the price number
            price_text = price_el.get_text(separator=" ", strip=True)
            price = parse_price(price_text)
            if price:
                car.price = price

        # Financed price (sometimes lower)
        financed_el = content.find("p", class_=re.compile(r"precio\s+financiado"))
        if financed_el:
            fin_text = financed_el.get_text(separator=" ", strip=True)
            fin_price = parse_price(fin_text)
            if fin_price and car.price:
                if fin_price < car.price:
                    car.original_price = car.price
                    car.price = fin_price
                elif fin_price > car.price:
                    car.original_price = fin_price

        # --- Specs from <ul> <li> items ---
        specs_ul = content.find("ul")
        if specs_ul:
            for li in specs_ul.find_all("li"):
                # Skip promotional/claim items
                li_classes = li.get("class", [])
                if "claim" in li_classes:
                    continue

                li_text = li.get_text(strip=True)
                if not li_text:
                    continue

                # Year (4-digit number matching 20xx)
                if not car.year:
                    year = parse_year(li_text)
                    if year:
                        car.year = year
                        continue

                # Mileage
                if not car.mileage_km and "km" in li_text.lower():
                    km = parse_mileage(li_text)
                    if km:
                        car.mileage_km = km
                        continue

                # Fuel type
                if not car.fuel_type:
                    fuel = _detect_fuel_from_li(li_text)
                    if fuel:
                        car.fuel_type = fuel
                        continue

                # Location (last remaining li is typically the province)
                if not car.location and not re.match(r'^\d', li_text):
                    # Skip known non-location labels
                    if li_text.lower() not in ("km0", "certificado", "garantía"):
                        # Check it's not a tag
                        if "etiqueta" not in " ".join(li_classes):
                            car.location = li_text.strip()

        # --- Extract make/model from URL if not parsed from title ---
        if not car.make and car.url:
            _parse_make_model_from_url(car)

        # --- Body type ---
        if car.model:
            car.body_type = detect_body_type(car.model, car.variant)

        # --- Transmission from URL or title ---
        if not car.transmission:
            combined = f"{car.variant} {car.model} {car.url}".lower()
            car.transmission = detect_transmission(combined)

        if car.is_valid():
            cars.append(car)

    return cars


def _parse_title(car: CarListing, title: str):
    """Parse make, model, and variant from a listing title.

    Titles follow the pattern: BRAND Model Variant
    Examples:
        "BMW Serie 3 330iA"
        "AUDI Q3 35 TFSI Advanced"
        "MERCEDES-BENZ Clase GLA 200 d"
    """
    title = title.strip()
    if not title:
        return

    # Try to match known brands at the start
    title_lower = title.lower()
    matched_brand = None
    brand_end = 0

    for slug, brand_name in sorted(BRAND_SLUGS.items(), key=lambda x: len(x[1]), reverse=True):
        brand_check = brand_name.lower()
        if title_lower.startswith(brand_check):
            matched_brand = normalize_brand(slug)
            brand_end = len(brand_check)
            break

    # Also try common display names
    brand_display_map = {
        "alfa romeo": "Alfa Romeo",
        "mercedes-benz": "Mercedes",
        "mercedes benz": "Mercedes",
    }
    if not matched_brand:
        for display, normalized in brand_display_map.items():
            if title_lower.startswith(display):
                matched_brand = normalized
                brand_end = len(display)
                break

    if matched_brand:
        car.make = matched_brand
        remainder = title[brand_end:].strip()
        if remainder:
            # Split into model and variant
            # Model is typically 1-2 words, variant is the rest
            parts = remainder.split(" ", 2)
            if len(parts) >= 2:
                # Handle multi-word model names like "Serie 3", "Clase GLA", "Serie 1"
                if parts[0].lower() in ("serie", "clase", "class"):
                    car.model = f"{parts[0]} {parts[1]}"
                    car.variant = parts[2] if len(parts) > 2 else ""
                else:
                    car.model = parts[0]
                    car.variant = " ".join(parts[1:])
            else:
                car.model = parts[0]
    else:
        # Fallback: first word is brand, rest is model
        parts = title.split(" ", 1)
        car.make = normalize_brand(parts[0])
        if len(parts) > 1:
            model_parts = parts[1].split(" ", 1)
            car.model = model_parts[0]
            car.variant = model_parts[1] if len(model_parts) > 1 else ""


def _detect_fuel_from_li(text: str) -> str:
    """Detect fuel type from a listing spec <li> text.

    Autocasion uses Spanish fuel labels in the listing cards:
    Diésel, Gasolina, Eléctrico, Híbrido, Híbrido Enchufable, Gas, GLP, GNC
    """
    t = text.lower().strip()
    fuel_map = {
        "eléctrico": "Electric",
        "electrico": "Electric",
        "híbrido enchufable": "PHEV",
        "hibrido enchufable": "PHEV",
        "híbrido": "Hybrid",
        "hibrido": "Hybrid",
        "diésel": "Diesel",
        "diesel": "Diesel",
        "gasolina": "Gasoline",
        "gas": "Gasoline",  # Gas/GLP/GNC → Gasoline bucket
        "glp": "Gasoline",
        "gnc": "Gasoline",
    }
    for key, val in fuel_map.items():
        if t == key or t.startswith(key):
            return val
    return ""


def _parse_make_model_from_url(car: CarListing):
    """Extract make and model from the Autocasion detail URL.

    URL patterns:
        /coches-segunda-mano/bmw-serie-3-ocasion/330ia-ref19247946
        /coches-segunda-mano/audi-q3-ocasion/q3-35-tfsi-ref12345678
        /coches-km0/km-0/bmw-x1-km0/ix1-xdrive30a-ref19690663
    """
    # Match the brand-model-ocasion segment
    match = re.search(r'/coches-segunda-mano/([^/]+)-ocasion/', car.url)
    if not match:
        match = re.search(r'/coches-km0/km-0/([^/]+)-km0/', car.url)
    if not match:
        return

    slug = match.group(1)  # e.g., "bmw-serie-3", "audi-q3"

    for brand_key, brand_slug in BRAND_SLUGS.items():
        clean_slug = brand_slug.lower()
        if slug.startswith(clean_slug):
            car.make = normalize_brand(brand_key)
            model_part = slug[len(clean_slug):].lstrip("-")
            if model_part:
                car.model = model_part.replace("-", " ").title()
            break


def get_total_pages(html: str) -> int:
    """Extract total number of pages from the pagination section.

    Autocasion uses standard pagination with numbered links.
    The last page number gives us the total pages.
    """
    soup = BeautifulSoup(html, "lxml")

    # Look for pagination links with page= parameter
    page_links = soup.find_all("a", href=re.compile(r"page=\d+"))
    max_page = 1
    for link in page_links:
        href = link.get("href", "")
        match = re.search(r'page=(\d+)', href)
        if match:
            page_num = int(match.group(1))
            max_page = max(max_page, page_num)

    # Also check the title for total count (e.g., "1.752 BMW de segunda mano")
    title = soup.find("title")
    if title:
        count_match = re.search(r'([\d.]+)\s+\w+\s+de segunda mano', title.get_text())
        if count_match:
            count_str = count_match.group(1).replace(".", "")
            try:
                total = int(count_str)
                # ~25 items per page based on observed data
                estimated_pages = (total + 24) // 25
                max_page = max(max_page, estimated_pages)
            except ValueError:
                pass

    return max_page


def scrape_brand(session: requests.Session, brand: str, filters: SearchFilters) -> list:
    """Scrape all matching cars for a single brand.

    Pagination strategy:
    - URL filters handle price, mileage, transmission, and single fuel type
    - Year is NOT filterable via URL — must post-filter
    - We track yield rate (qualifying cars / parsed cars) and stop early when
      consecutive low-yield pages indicate diminishing returns
    - Hard cap of 30 pages per brand to keep total runtime reasonable
    """
    slug = BRAND_SLUGS.get(brand.lower(), brand.lower())
    cars = []
    page = 1
    max_pages = 30  # Hard safety limit
    consecutive_low_yield = 0
    LOW_YIELD_THRESHOLD = 3  # Stop after 3 consecutive pages with <10% yield

    while page <= max_pages:
        url = build_url(slug, filters, page)
        print(f"  [{slug}] Page {page}/{max_pages}: {url[:120]}...", file=sys.stderr)

        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 404:
                print(f"  [{slug}] 404 on page {page}, brand likely has no listings.", file=sys.stderr)
                break
            print(f"  [{slug}] HTTP error on page {page}: {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"  [{slug}] Error on page {page}: {e}", file=sys.stderr)
            break

        # On first page, detect total pages and refine limit
        if page == 1:
            total_pages = get_total_pages(resp.text)
            max_pages = min(total_pages, max_pages)
            print(f"  [{slug}] Estimated {max_pages} pages", file=sys.stderr)

        page_cars = parse_listing_page(resp.text)
        if not page_cars:
            print(f"  [{slug}] No cars found on page {page}, stopping.", file=sys.stderr)
            break

        # Apply post-filters that aren't in the URL (year)
        prev_count = len(cars)
        for car in page_cars:
            if car.year < filters.min_year:
                continue
            # Fuel type post-filter when multiple types specified
            if len(filters.fuel_types) > 1:
                if car.fuel_type.lower() not in [f.lower() for f in filters.fuel_types]:
                    continue
            cars.append(car)

        page_qualifying = len(cars) - prev_count
        yield_rate = page_qualifying / len(page_cars) if page_cars else 0

        print(f"  [{slug}] Page {page}: {len(page_cars)} parsed, "
              f"{page_qualifying} qualifying ({yield_rate:.0%}), "
              f"{len(cars)} total", file=sys.stderr)

        # Early termination: stop if yield rate is consistently low
        # (year filter causes many non-qualifying cars on later pages)
        if yield_rate < 0.10:
            consecutive_low_yield += 1
            if consecutive_low_yield >= LOW_YIELD_THRESHOLD:
                print(f"  [{slug}] {LOW_YIELD_THRESHOLD} consecutive low-yield pages, "
                      f"stopping early.", file=sys.stderr)
                break
        else:
            consecutive_low_yield = 0

        page += 1

    return cars


def scrape_autocasion(filters: SearchFilters) -> list:
    """Scrape all matching cars from Autocasion across all requested brands."""
    all_cars = []
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"[autocasion] Starting scrape: price<={filters.max_price}, "
          f"year>={filters.min_year}, transmission={filters.transmission}, "
          f"brands={len(filters.brands)}", file=sys.stderr)

    for brand in filters.brands:
        brand_cars = scrape_brand(session, brand, filters)
        all_cars.extend(brand_cars)

    # Deduplicate by URL
    seen = set()
    deduped = []
    for car in all_cars:
        if car.url not in seen:
            seen.add(car.url)
            deduped.append(car)

    print(f"[autocasion] Done: {len(deduped)} unique cars "
          f"({len(all_cars) - len(deduped)} duplicates removed)", file=sys.stderr)
    return deduped


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = scrape_autocasion(filters)
    output_results(cars)
