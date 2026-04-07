#!/usr/bin/env python3
"""
OcasionPlus.com HTTP scraper.
Parses JSON-LD structured data (schema.org Vehicle objects) embedded in server-rendered
Next.js pages, supplemented with HTML parsing for location and discounted prices.
Outputs normalized JSON to stdout.

Architecture note:
  OcasionPlus is a Next.js app with React Server Components. Each listing page embeds
  two key data sources:
    1. JSON-LD <script type="application/ld+json"> containing an ItemList of 20 Vehicle
       objects per page with structured fields (brand, model, transmission, fuelType,
       mileageFromOdometer, productionDate, offers.price, image, url).
    2. HTML car cards with additional data not in JSON-LD: location (city/province)
       and discounted price (the JSON-LD only has the original/list price).

  URL query parameters (cambio, precio_max, ano_min, km_max, combustible) are accepted
  by the URL router but do NOT filter the server response. The JSON-LD and HTML cards
  always return the full brand inventory in default order. All filtering is done as
  post-processing in Python.

  Pagination: 20 cars per page via ?page=N. Pages beyond the last return an empty
  ItemList in the JSON-LD, which serves as the termination signal.
"""

import json
import re
import sys
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip3 install requests beautifulsoup4 lxml", file=sys.stderr)
    sys.exit(1)

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage, parse_price,
                   parse_hp, detect_fuel_type, detect_transmission)


# OcasionPlus brand URL slugs (path segment after /coches-segunda-mano/)
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
    "mercedes": "mercedes",
    "mercedes-benz": "mercedes",
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

BASE_URL = "https://www.ocasionplus.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Map OcasionPlus Spanish fuel types to normalized values
FUEL_TYPE_MAP = {
    "gasolina": "Gasoline",
    "diésel": "Diesel",
    "diesel": "Diesel",
    "híbrido": "Hybrid",
    "hibrido": "Hybrid",
    "híbrido enchufable": "PHEV",
    "hibrido enchufable": "PHEV",
    "eléctrico": "Electric",
    "electrico": "Electric",
    "glp": "Gasoline",   # LPG -> Gasoline bucket
    "gnc": "Gasoline",   # CNG -> Gasoline bucket
}


def build_url(brand_slug: str, page: int = 1) -> str:
    """Build OcasionPlus listing URL for a brand + page.

    Query parameters are included for URL correctness but do NOT trigger
    server-side filtering — all filtering is done as post-processing.
    """
    url = f"{BASE_URL}/coches-segunda-mano/{brand_slug}"
    if page > 1:
        url += f"?page={page}"
    return url


def extract_json_ld_vehicles(html: str) -> list:
    """Extract Vehicle objects from JSON-LD structured data in the page.

    Looks for <script type="application/ld+json"> containing an ItemList
    with Vehicle itemListElement entries. Returns the list of vehicle dicts.
    """
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single object and array of objects
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") == "ItemList" and "itemListElement" in item:
                elements = item["itemListElement"]
                # Extract Vehicle objects from the list
                vehicles = []
                for el in elements:
                    if isinstance(el, dict):
                        if el.get("@type") == "Vehicle":
                            vehicles.append(el)
                        elif "item" in el and isinstance(el["item"], dict):
                            if el["item"].get("@type") == "Vehicle":
                                vehicles.append(el["item"])
                return vehicles

    return []


def extract_json_ld_offer_count(html: str) -> int:
    """Extract the total offer count from JSON-LD AggregateOffer.

    Returns the offerCount (total cars for this brand) or 0 if not found.
    """
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") == "Product":
                offers = item.get("offers", {})
                if offers.get("@type") == "AggregateOffer":
                    return int(offers.get("offerCount", 0))

    return 0


def extract_html_card_data(html: str) -> dict:
    """Extract supplementary data from HTML car cards that isn't in JSON-LD.

    Returns a dict mapping car detail URL path -> {location, discounted_price}
    The JSON-LD has the original/list price; the HTML shows both original (struck)
    and discounted prices plus the location.
    """
    soup = BeautifulSoup(html, "lxml")
    card_data = {}

    # Find all links to car detail pages
    links = soup.find_all("a", href=re.compile(r"^/coches-segunda-mano/[a-z].*-\w{6,}$"))

    for link in links:
        href = link.get("href", "")
        if not href or href in card_data:
            continue

        text = link.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        data = {"location": "", "discounted_price": 0}

        # Extract location from the card text
        # Location follows a location icon and is typically a Spanish province/city
        location_match = re.search(
            r'(?:Álava|Albacete|Alicante|Almería|Asturias|Ávila|Badajoz|Barcelona|'
            r'Bizkaia|Burgos|Cáceres|Cádiz|Cantabria|Castellón|Ciudad Real|Córdoba|'
            r'Cuenca|Gipuzkoa|Girona|Granada|Guadalajara|Huelva|Huesca|Illes Balears|'
            r'Jaén|La Coruña|La Rioja|Las Palmas|León|Lleida|Lugo|Madrid|Málaga|Murcia|'
            r'Navarra|Ourense|Palencia|Pontevedra|Salamanca|Santa Cruz|Segovia|Sevilla|'
            r'Soria|Tarragona|Teruel|Toledo|Valencia|Valladolid|Zamora|Zaragoza)'
            r'(?:\s*-\s*[^€\d][^\n]*)?',
            text
        )
        if location_match:
            data["location"] = location_match.group(0).strip()

        # Extract prices from the text
        # Pattern: "22.190€20.547€" (original then discounted) or just "9.490€"
        # IMPORTANT: Exclude monthly payments like "desde263€/mes" or "1.207€/mes".
        # In the HTML-to-text output, monthly payments may appear as:
        #   "1207\n€\n/mes" (separate lines) or "263€/mes" (inline).
        # We use a negative lookahead that allows optional whitespace before /mes.
        prices = re.findall(r'([\d.]+)\s*€(?!\s*/mes)', text)
        valid_prices = []
        for p in prices:
            try:
                val = int(p.replace(".", ""))
                # Car prices are at least 3000€ — this also excludes monthly
                # payments that slip through (e.g., "263€" or "1.207€")
                if 3000 < val < 500000:
                    valid_prices.append(val)
            except ValueError:
                pass
        if len(valid_prices) >= 2:
            p1, p2 = valid_prices[0], valid_prices[1]
            # The discounted price is the lower one
            if p2 < p1:
                data["discounted_price"] = p2
            elif p1 < p2:
                data["discounted_price"] = p1

        card_data[href] = data

    return card_data


def parse_year_from_date(date_str: str) -> int:
    """Parse year from ISO 8601 date string (e.g., '2023-09-06T00:00:00.000Z')."""
    if not date_str:
        return 0
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.year
    except (ValueError, TypeError):
        # Fallback: extract 4-digit year
        match = re.search(r'(20[1-3]\d)', date_str)
        return int(match.group(1)) if match else 0


def normalize_fuel_type(raw: str) -> str:
    """Normalize Spanish fuel type labels to standard values."""
    key = raw.lower().strip()
    return FUEL_TYPE_MAP.get(key, detect_fuel_type(raw))


def parse_hp_from_model(model_str: str) -> int:
    """Extract HP from model string like 'BMW Serie 3 320d (184 CV)'.

    Returns 0 if not found.
    """
    match = re.search(r'\((\d+)\s*CV\)', model_str)
    if match:
        hp = int(match.group(1))
        if 30 < hp < 1000:
            return hp
    return 0


def parse_model_parts(full_model: str, brand_name: str) -> tuple:
    """Parse the full model string into (model, variant).

    Input examples:
        "Audi A4 Avant Advanced 35 TFSI (150 CV) S tronic"
        "BMW Serie 2 216d Gran Coupe (116 CV)"
        "Toyota C-HR 180H GR Sport (184 CV)"
        "Mercedes Clase A 180 CDI Style (109 CV)"
        "Volvo XC40 B3 G Core Auto (163 CV)"

    Returns (model, variant) where model is the short model name and variant
    is the rest (trim level, engine spec, etc.).
    """
    # Remove the brand prefix if present
    text = full_model.strip()
    brand_lower = brand_name.lower()

    # Remove brand name from start (case-insensitive)
    if text.lower().startswith(brand_lower):
        text = text[len(brand_lower):].strip()

    # Remove HP suffix like "(184 CV)" for cleaner parsing
    hp_match = re.search(r'\s*\(\d+\s*CV\)\s*', text)
    hp_suffix = ""
    if hp_match:
        hp_suffix = hp_match.group(0).strip()
        text = text[:hp_match.start()] + " " + text[hp_match.end():]
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return ("", "")

    parts = text.split()

    # Handle multi-word model names: "Serie X", "Clase X", "Land Cruiser", etc.
    model = ""
    variant_start = 1

    # Known two-word model name prefixes (first word -> requires second word)
    TWO_WORD_PREFIXES = {"serie", "clase", "class", "land", "aygo", "proace",
                         "yaris", "eclipse", "id."}
    # Known two-word model names (exact match for first two words)
    TWO_WORD_MODELS = {
        "land cruiser", "yaris cross", "aygo x", "proace verso", "proace city",
        "eclipse cross", "id.3", "id.4", "id.5",
    }

    if len(parts) >= 2:
        two_words = f"{parts[0]} {parts[1]}".lower()
        if two_words in TWO_WORD_MODELS or parts[0].lower() in TWO_WORD_PREFIXES:
            model = f"{parts[0]} {parts[1]}"
            variant_start = 2
        else:
            model = parts[0]
    else:
        model = parts[0]

    variant_parts = parts[variant_start:]
    variant = " ".join(variant_parts).strip()

    # Add HP back to variant if present
    if hp_suffix and variant:
        variant = f"{variant} {hp_suffix}"
    elif hp_suffix:
        variant = hp_suffix

    return (model, variant)


def parse_vehicle(vehicle: dict, html_data: dict) -> CarListing:
    """Parse a JSON-LD Vehicle object into a normalized CarListing.

    Enriches with HTML-extracted data (location, discounted price) when available.

    JSON-LD Vehicle fields:
        @type, name, brand.name, model, vehicleTransmission (AUTO|MANUAL),
        fuelType, productionDate (ISO 8601), description,
        mileageFromOdometer.value, mileageFromOdometer.unitText,
        offers.price, offers.priceCurrency, offers.url, offers.availability,
        image
    """
    # Brand
    brand_data = vehicle.get("brand", {})
    brand_name = brand_data.get("name", "") if isinstance(brand_data, dict) else str(brand_data)
    make = normalize_brand(brand_name)

    # Full model string (e.g., "Audi A4 Avant Advanced 35 TFSI (150 CV) S tronic")
    full_model = vehicle.get("model", "") or vehicle.get("description", "")

    # Short name (e.g., "Audi A4")
    short_name = vehicle.get("name", "")

    # Parse model and variant from the full model string
    model, variant = parse_model_parts(full_model, brand_name)

    # HP from model string
    hp = parse_hp_from_model(full_model) or None

    # Transmission
    raw_transmission = vehicle.get("vehicleTransmission", "")
    if raw_transmission == "AUTO":
        transmission = "Automatic"
    elif raw_transmission == "MANUAL":
        transmission = "Manual"
    else:
        transmission = detect_transmission(full_model)

    # Fuel type
    raw_fuel = vehicle.get("fuelType", "")
    fuel_type = normalize_fuel_type(raw_fuel)

    # Detect PHEV/mild hybrid from model string if fuel shows as Hybrid
    if fuel_type == "Hybrid" and full_model:
        model_lower = full_model.lower()
        if "enchufable" in model_lower or "plug-in" in model_lower or "phev" in model_lower:
            fuel_type = "PHEV"
        elif "mhev" in model_lower or "mild" in model_lower or "48v" in model_lower:
            fuel_type = "Mild Hybrid"

    # Year from productionDate
    year = parse_year_from_date(vehicle.get("productionDate", ""))

    # Mileage
    mileage_data = vehicle.get("mileageFromOdometer", {})
    mileage_km = 0
    if isinstance(mileage_data, dict):
        mileage_km = int(mileage_data.get("value", 0))
    elif isinstance(mileage_data, (int, float)):
        mileage_km = int(mileage_data)

    # Price (JSON-LD has original/list price)
    offers = vehicle.get("offers", {})
    original_price = 0
    if isinstance(offers, dict):
        original_price = int(offers.get("price", 0))
    elif isinstance(offers, list) and offers:
        original_price = int(offers[0].get("price", 0))

    # URL
    url = ""
    if isinstance(offers, dict):
        url = offers.get("url", "")
    elif isinstance(offers, list) and offers:
        url = offers[0].get("url", "")

    # Ensure full URL
    if url and not url.startswith("http"):
        url = f"{BASE_URL}{url}"

    # Image
    image_url = vehicle.get("image", "")
    if isinstance(image_url, list):
        image_url = image_url[0] if image_url else ""

    # --- Enrich from HTML card data ---
    # Match by URL path (strip base URL for matching)
    url_path = url.replace(BASE_URL, "") if url else ""
    html_extra = html_data.get(url_path, {})

    location = html_extra.get("location", "")
    discounted_price = html_extra.get("discounted_price", 0)

    # Determine price and original_price
    # JSON-LD price = original (list) price
    # HTML discounted_price = sale price (lower)
    price = original_price
    final_original_price = None

    if discounted_price and discounted_price < original_price:
        price = discounted_price
        final_original_price = original_price
    elif discounted_price and discounted_price > original_price:
        # Edge case: discounted > original means our parsing got them swapped
        price = original_price
        final_original_price = discounted_price

    # Body type
    body_type = detect_body_type(model, variant) if model else ""

    return CarListing(
        platform="ocasionplus",
        url=url,
        image_url=image_url,
        make=make,
        model=model,
        variant=variant,
        year=year,
        price=price,
        original_price=final_original_price,
        mileage_km=mileage_km,
        fuel_type=fuel_type,
        hp=hp,
        transmission=transmission,
        location=location,
        body_type=body_type,
    )


def scrape_brand(session: requests.Session, brand: str, filters: SearchFilters) -> list:
    """Scrape all matching cars for a single brand from OcasionPlus.

    Strategy:
      - Fetch pages sequentially (20 cars per page)
      - Parse JSON-LD for structured vehicle data
      - Parse HTML for location and discounted price
      - Apply all filters as post-filters
      - Stop when JSON-LD returns 0 vehicles or page cap reached

    Optimization: estimate total pages from offerCount on page 1 and cap.
    """
    slug = BRAND_SLUGS.get(brand.lower(), brand.lower())
    cars = []
    page = 1
    max_pages = 50  # Hard safety limit
    cars_per_page = 20

    while page <= max_pages:
        url = build_url(slug, page)
        print(f"  [{slug}] Page {page}: {url}", file=sys.stderr)

        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            if resp.status_code == 404:
                print(f"  [{slug}] 404 on page {page}, stopping.", file=sys.stderr)
                break
            print(f"  [{slug}] HTTP {resp.status_code} on page {page}, stopping.", file=sys.stderr)
            break
        except Exception as e:
            print(f"  [{slug}] Error on page {page}: {e}", file=sys.stderr)
            break

        html = resp.text

        # On page 1, estimate total pages from offerCount
        if page == 1:
            offer_count = extract_json_ld_offer_count(html)
            if offer_count > 0:
                estimated_pages = (offer_count + cars_per_page - 1) // cars_per_page
                max_pages = min(estimated_pages, max_pages)
                print(f"  [{slug}] {offer_count} total cars, ~{estimated_pages} pages "
                      f"(capped at {max_pages})", file=sys.stderr)

        # Extract JSON-LD vehicle data
        vehicles = extract_json_ld_vehicles(html)
        if not vehicles:
            print(f"  [{slug}] No vehicles in JSON-LD on page {page}, stopping.", file=sys.stderr)
            break

        # Extract supplementary HTML data (location, discounted price)
        html_data = extract_html_card_data(html)

        # Parse each vehicle
        page_cars = []
        for v in vehicles:
            car = parse_vehicle(v, html_data)
            if car.is_valid():
                page_cars.append(car)

        # Apply post-filters
        qualifying = 0
        for car in page_cars:
            # Price filter (use the effective/sale price)
            if car.price > filters.max_price:
                continue
            # Year filter
            if car.year < filters.min_year:
                continue
            # Mileage filter
            if filters.max_mileage and car.mileage_km > filters.max_mileage:
                continue
            # Transmission filter
            if filters.transmission == "automatic" and car.transmission == "Manual":
                continue
            if filters.transmission == "manual" and car.transmission == "Automatic":
                continue
            # Fuel type filter
            if filters.fuel_types:
                if car.fuel_type.lower() not in [f.lower() for f in filters.fuel_types]:
                    continue
            cars.append(car)
            qualifying += 1

        print(f"  [{slug}] Page {page}: {len(vehicles)} in JSON-LD, "
              f"{len(page_cars)} valid, {qualifying} qualifying, "
              f"{len(cars)} total", file=sys.stderr)

        page += 1

    return cars


def scrape_ocasionplus(filters: SearchFilters) -> list:
    """Scrape all matching cars from OcasionPlus across all requested brands."""
    all_cars = []
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"[ocasionplus] Starting scrape: price<={filters.max_price}, "
          f"year>={filters.min_year}, transmission={filters.transmission}, "
          f"mileage<={filters.max_mileage}, brands={len(filters.brands)}",
          file=sys.stderr)

    for brand in filters.brands:
        brand_slug = BRAND_SLUGS.get(brand.lower())
        if not brand_slug:
            print(f"[ocasionplus] Unknown brand '{brand}', skipping.", file=sys.stderr)
            continue
        brand_cars = scrape_brand(session, brand, filters)
        all_cars.extend(brand_cars)

    # Deduplicate by URL
    seen = set()
    deduped = []
    for car in all_cars:
        if car.url and car.url not in seen:
            seen.add(car.url)
            deduped.append(car)

    print(f"[ocasionplus] Done: {len(deduped)} unique cars "
          f"({len(all_cars) - len(deduped)} duplicates removed)", file=sys.stderr)
    return deduped


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = scrape_ocasionplus(filters)
    output_results(cars)
