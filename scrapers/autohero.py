#!/usr/bin/env python3
"""
Autohero.com HTTP scraper.
Scrapes the Apollo GraphQL state embedded in the server-rendered search page.
Outputs normalized JSON to stdout.

Architecture note:
  Autohero is a React SPA backed by Apollo Client. The server-side render embeds
  a JSON blob in `window.__APOLLO_STATE__` containing the initial 24 car listings
  with full structured data (manufacturer, model, price, mileage, fuel, gear, HP,
  images, location, etc.). URL query params do NOT trigger server-side filtering
  except for `sort`. All other filters (brand, price, year, mileage, etc.) are
  applied as post-filters in Python.

  The scraper fetches the search page HTML, parses the Apollo state, and extracts
  normalized CarListing objects from the embedded JSON data.
"""

import json
import re
import sys

try:
    import requests
except ImportError:
    print("Missing dependencies. Run: pip3 install requests", file=sys.stderr)
    sys.exit(1)

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import (normalize_brand, detect_body_type, parse_mileage,
                   detect_fuel_type, detect_transmission)


# Autohero internal fuel type codes (from JS bundle)
FUEL_TYPE_MAP = {
    1039: "Gasoline",      # Benzin
    1040: "Diesel",
    1041: "LPG",           # Gas
    1042: "CNG",           # Erdgas
    1043: "",              # Other
    1044: "Electric",      # Elektro
    1045: "Ethanol",
    1046: "Hybrid",
    1047: "Hydrogen",      # Wasserstoff
    "plug_in_hybrid": "PHEV",
}

# Autohero internal gear type codes (from JS bundle)
GEAR_TYPE_MAP = {
    1138: "Manual",
    1139: "Automatic",
    1140: "Automatic",     # Semi-automatic -> treated as Automatic
    1141: "Manual",        # Duplex -> treated as Manual
}

# Brand slug normalization: CLI brand -> Autohero manufacturer name
BRAND_NAMES = {
    "alfa-romeo": "Alfa Romeo",
    "audi": "Audi",
    "bmw": "BMW",
    "byd": "BYD",
    "cupra": "CUPRA",
    "honda": "Honda",
    "hyundai": "Hyundai",
    "jaguar": "Jaguar",
    "kia": "Kia",
    "lexus": "Lexus",
    "mazda": "Mazda",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "mitsubishi": "Mitsubishi",
    "nissan": "Nissan",
    "porsche": "Porsche",
    "skoda": "Skoda",
    "subaru": "Subaru",
    "tesla": "Tesla",
    "toyota": "Toyota",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "volvo": "Volvo",
}

# Reverse: Autohero manufacturer name -> normalized make
MANUFACTURER_TO_MAKE = {
    "Alfa Romeo": "Alfa Romeo",
    "Audi": "Audi",
    "BMW": "BMW",
    "BYD": "BYD",
    "CUPRA": "CUPRA",
    "Honda": "Honda",
    "Hyundai": "Hyundai",
    "Jaguar": "Jaguar",
    "Kia": "Kia",
    "Lexus": "Lexus",
    "Mazda": "Mazda",
    "Mercedes-Benz": "Mercedes",
    "MINI": "MINI",
    "Mitsubishi": "Mitsubishi",
    "Nissan": "Nissan",
    "Porsche": "Porsche",
    "Skoda": "Skoda",
    "Subaru": "Subaru",
    "Tesla": "Tesla",
    "Toyota": "Toyota",
    "Volkswagen": "Volkswagen",
    "Volvo": "Volvo",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Sort options that work server-side
SORT_OPTIONS = [
    "price_desc",   # Highest price first (gets premium cars within budget)
    "price_asc",    # Lowest price first
    "newest",       # Newest listings
    "most_popular", # Default (no sort param needed)
]

BASE_URL = "https://www.autohero.com/es/search/"


def build_url(sort: str = "most_popular") -> str:
    """Build Autohero search URL.

    Only the sort parameter affects server-side results.
    All other filters are applied as post-filters.
    """
    if sort and sort != "most_popular":
        return f"{BASE_URL}?sort={sort}"
    return BASE_URL


def extract_apollo_state(html: str) -> dict:
    """Extract and parse the Apollo GraphQL state from the server-rendered HTML.

    The state is embedded as: window.__APOLLO_STATE__ = "...escaped JSON...";
    """
    idx = html.find('window.__APOLLO_STATE__')
    if idx == -1:
        return {}

    try:
        eq_idx = html.index('= "', idx) + 3
        end_idx = html.index('";', eq_idx)
        raw = html[eq_idx:end_idx]

        # Step 1: Decode JS string escapes (\\\" -> ", \\u002F -> /, etc.)
        decoded = raw.encode('utf-8').decode('unicode_escape')

        # Step 2: Fix UTF-8 corruption caused by unicode_escape treating
        # multi-byte UTF-8 chars as Latin-1 individual bytes.
        # Re-encode as Latin-1 and decode as UTF-8 to restore proper characters.
        try:
            decoded = decoded.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass  # Fallback: keep the unicode_escape result

        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[autohero] Failed to parse Apollo state: {e}", file=sys.stderr)
        return {}


def extract_cars_from_state(state: dict) -> tuple:
    """Extract car data list and total count from the Apollo state.

    Returns (cars_list, total_count).
    """
    root = state.get("ROOT_QUERY", {})

    for key, value in root.items():
        if key.startswith("searchAdV9AdsV2"):
            data = value.get("data", [])
            total = value.get("total", 0)
            return data, total

    return [], 0


def _clean_model_name(model: str, manufacturer: str) -> str:
    """Clean Autohero model names to match standard naming.

    Autohero uses some non-standard model names:
      - "UX-Serie" -> "UX"  (Lexus)
      - "Serie 1" stays as-is (BMW standard naming in Spain)
      - "MINI" when manufacturer is MINI -> keep for body_type detection
      - "C 3" -> "C3" (Citroen, remove internal space)
      - "i10" stays as-is (Hyundai)
      - "Q3 Sportback" stays as-is (Audi)
    """
    if not model:
        return model

    # Remove "-Serie" suffix (Lexus: "UX-Serie" -> "UX", "NX-Serie" -> "NX")
    if model.endswith("-Serie"):
        model = model.replace("-Serie", "")

    # Citroen spacing: "C 3" -> "C3", "C 4" -> "C4" (but keep "C4 Cactus" etc.)
    if manufacturer == "Citroen":
        model = re.sub(r'^C (\d)', r'C\1', model)

    return model


def parse_car(raw: dict) -> CarListing:
    """Parse a single car from the Apollo state JSON into a normalized CarListing.

    Apollo state car fields:
      id, manufacturer, model, subType, subTypeExtra,
      offerPrice.amountMinorUnits, financedPrice.amountMinorUnits,
      mileage.distance, builtYear, firstRegistrationYear,
      fuelType (int code), gearType (int code), kw,
      mainImageUrl, carUrlTitle, esBranch.city,
      driveTrain, co2Value, ccm, acceleration,
      carPreownerCount, numberOfAccidents
    """
    car_id = raw.get("id", "")
    manufacturer = raw.get("manufacturer", "")
    model = raw.get("model", "")
    sub_type = raw.get("subType", "")
    sub_type_extra = raw.get("subTypeExtra", "")
    car_url_title = raw.get("carUrlTitle", "")

    # Build URL
    url = ""
    if car_url_title and car_id:
        url = f"https://www.autohero.com/es/{car_url_title}/id/{car_id}/"

    # Image URL — replace {size} placeholder with a standard resolution
    image_url = raw.get("mainImageUrl", "") or raw.get("ahMainImageUrl", "")
    if image_url:
        image_url = image_url.replace("{size}", "768x432-")

    # Make
    make = MANUFACTURER_TO_MAKE.get(manufacturer, normalize_brand(manufacturer))

    # Clean model name — Autohero uses some non-standard names
    # e.g. "UX-Serie" -> "UX", "MINI" (when manufacturer is also MINI) -> keep as is
    model = _clean_model_name(model, manufacturer)

    # Variant: combine subType and subTypeExtra
    variant_parts = []
    if sub_type:
        variant_parts.append(sub_type)
    if sub_type_extra:
        variant_parts.append(sub_type_extra)
    variant = " ".join(variant_parts)

    # Price — offerPrice is the cash price (higher), financedPrice is lower
    offer_price_raw = raw.get("offerPrice", {})
    financed_price_raw = raw.get("financedPrice", {})

    price = 0
    original_price = None
    if offer_price_raw:
        minor = offer_price_raw.get("amountMinorUnits", 0)
        conv = offer_price_raw.get("conversionMajor", 100)
        price = minor // conv if conv else 0

    # If there's a financed (discounted) price that's lower, use it as the price
    if financed_price_raw:
        fin_minor = financed_price_raw.get("amountMinorUnits", 0)
        fin_conv = financed_price_raw.get("conversionMajor", 100)
        fin_price = fin_minor // fin_conv if fin_conv else 0
        if fin_price and fin_price < price:
            original_price = price
            price = fin_price

    # Year
    year = raw.get("builtYear", 0) or raw.get("firstRegistrationYear", 0)

    # Mileage
    mileage_data = raw.get("mileage", {})
    mileage_km = mileage_data.get("distance", 0) if mileage_data else 0

    # Fuel type
    fuel_code = raw.get("fuelType")
    fuel_type = FUEL_TYPE_MAP.get(fuel_code, "")
    # Check isPluginSystem flag
    if raw.get("isPluginSystem") and fuel_type == "Hybrid":
        fuel_type = "PHEV"

    # Transmission
    gear_code = raw.get("gearType")
    transmission = GEAR_TYPE_MAP.get(gear_code, "")

    # HP from kW
    kw = raw.get("kw", 0)
    hp = round(kw * 1.36) if kw else None

    # Location from esBranch
    location = ""
    branch = raw.get("esBranch", {})
    if branch:
        city = branch.get("city", "")
        area = branch.get("area", "")
        location = area or city

    # Body type
    body_type = detect_body_type(model, variant) if model else ""

    car = CarListing(
        platform="autohero",
        url=url,
        image_url=image_url,
        make=make,
        model=model,
        variant=variant,
        year=year,
        price=price,
        original_price=original_price,
        mileage_km=mileage_km,
        fuel_type=fuel_type,
        hp=hp,
        transmission=transmission,
        location=location,
        body_type=body_type,
    )

    return car


def matches_brand_filter(car: CarListing, brand_names: set) -> bool:
    """Check if a car matches any of the requested brands."""
    if not brand_names:
        return True  # No brand filter = accept all
    return car.make.lower() in brand_names or car.make in brand_names


def scrape_autohero(filters: SearchFilters) -> list:
    """Scrape all matching cars from Autohero.

    Strategy:
      1. Fetch the search page with different sort orders to maximize coverage
      2. Parse the Apollo state from each page (24 cars per sort order)
      3. Apply all filters as post-filters (brand, price, year, mileage, etc.)
      4. Deduplicate by URL
    """
    all_cars = []
    session = requests.Session()
    session.headers.update(HEADERS)

    # Build set of target brand names for filtering
    target_brands = set()
    for brand in filters.brands:
        name = BRAND_NAMES.get(brand.lower().strip())
        if name:
            # Add both the Autohero name and our normalized name
            target_brands.add(name)
            normalized = MANUFACTURER_TO_MAKE.get(name, name)
            target_brands.add(normalized)
        else:
            target_brands.add(brand.title())

    print(f"[autohero] Starting scrape with filters: price<={filters.max_price}, "
          f"year>={filters.min_year}, mileage<={filters.max_mileage}, "
          f"transmission={filters.transmission}, brands={len(filters.brands)}",
          file=sys.stderr)

    # Fetch multiple sort orders to maximize car diversity
    # price_desc gets premium cars first (most likely to match our brand filters)
    # price_asc gets budget cars
    # most_popular and newest provide additional variety
    sort_orders = ["price_desc", "price_asc", "most_popular", "newest"]

    for sort in sort_orders:
        url = build_url(sort)
        print(f"[autohero] Fetching sort={sort}: {url}", file=sys.stderr)

        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"[autohero] Error fetching sort={sort}: {e}", file=sys.stderr)
            continue

        # Parse Apollo state
        state = extract_apollo_state(resp.text)
        if not state:
            print(f"[autohero] No Apollo state found for sort={sort}", file=sys.stderr)
            continue

        raw_cars, total = extract_cars_from_state(state)
        if not raw_cars:
            print(f"[autohero] No cars in Apollo state for sort={sort}", file=sys.stderr)
            continue

        print(f"[autohero] sort={sort}: {len(raw_cars)} cars in Apollo state "
              f"(total inventory: {total})", file=sys.stderr)

        for raw in raw_cars:
            car = parse_car(raw)
            if car.is_valid():
                all_cars.append(car)

    # Deduplicate by URL
    seen = set()
    unique_cars = []
    for car in all_cars:
        if car.url and car.url not in seen:
            seen.add(car.url)
            unique_cars.append(car)

    print(f"[autohero] {len(unique_cars)} unique cars after dedup "
          f"(from {len(all_cars)} total)", file=sys.stderr)

    # Apply post-filters
    filtered = []
    for car in unique_cars:
        # Brand filter
        if not matches_brand_filter(car, target_brands):
            continue
        # Price filter
        if car.price > filters.max_price:
            continue
        # Year filter
        if car.year < filters.min_year:
            continue
        # Mileage filter
        if filters.max_mileage and car.mileage_km > filters.max_mileage:
            continue
        # Transmission filter
        if filters.transmission == "automatic" and car.transmission.lower() not in (
            "automatic", ""
        ):
            continue
        # Fuel type filter
        if filters.fuel_types:
            if car.fuel_type.lower() not in [f.lower() for f in filters.fuel_types]:
                continue
        filtered.append(car)

    print(f"[autohero] Done: {len(filtered)} qualifying cars "
          f"({len(unique_cars)} unique, {len(unique_cars) - len(filtered)} filtered out)",
          file=sys.stderr)
    return filtered


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = scrape_autohero(filters)
    output_results(cars)
