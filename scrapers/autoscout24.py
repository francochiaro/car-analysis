#!/usr/bin/env python3
"""
AutoScout24.es Playwright browser automation scraper.
Scrapes Spain's largest used car marketplace by rendering pages with headless Chromium.
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

from base import CarListing, SearchFilters, parse_cli_args, output_results
from utils import normalize_brand, detect_body_type, detect_transmission


# AutoScout24 brand URL slugs (used in /lst/{slug})
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

# AutoScout24 fuel type URL param values
FUEL_TYPE_PARAMS = {
    "diesel": "D",
    "gasoline": "B",
    "electric": "E",
    "hybrid": "2",       # Hybrid (petrol/electric)
    "phev": "2",         # Also maps to hybrid param
    "mild hybrid": "2",
    "lpg": "L",
    "cng": "C",
}

BASE_URL = "https://www.autoscout24.es"
RESULTS_PER_PAGE = 20
MAX_PAGES = 20  # AutoScout24 caps at 20 pages (400 results)


def build_search_url(brand_slug: str, filters: SearchFilters, page: int = 1) -> str:
    """Build AutoScout24 search URL with filters."""
    params = [
        f"atype=C",                    # Car type
        f"cy=E",                       # Country: Spain
        f"fregfrom={filters.min_year}",  # Year from
        f"kmto={filters.max_mileage}",   # Max mileage
        f"priceto={filters.max_price}",  # Max price
        f"sort=standard",              # Default sorting
        f"ustate=N%2CU",              # New + Used
    ]

    # Transmission filter
    if filters.transmission == "automatic":
        params.append("gear=A")
    elif filters.transmission == "manual":
        params.append("gear=M")

    # Fuel type filter
    if filters.fuel_types:
        fuel_codes = set()
        for ft in filters.fuel_types:
            code = FUEL_TYPE_PARAMS.get(ft.lower())
            if code:
                fuel_codes.add(code)
        for code in sorted(fuel_codes):
            params.append(f"fuel={code}")

    # Pagination
    if page > 1:
        params.append(f"page={page}")

    return f"{BASE_URL}/lst/{brand_slug}?{'&'.join(params)}"


def parse_title(title_text: str, brand_slug: str) -> tuple:
    """Parse make, model, and variant from AutoScout24 title.

    AutoScout24 titles follow patterns like:
    - "BMW X2sDrive 18iA" -> make=BMW, model=X2, variant=sDrive 18iA
    - "Audi Q3Sportback 35 TFSI" -> make=Audi, model=Q3, variant=Sportback 35 TFSI
    - "Volkswagen T-Roc1.5 TSI" -> make=Volkswagen, model=T-Roc, variant=1.5 TSI
    """
    make = normalize_brand(brand_slug.replace("-", " "))
    text = title_text.strip()

    # Remove the make prefix if present (case-insensitive)
    for prefix in [make, brand_slug.replace("-", " ").title(), brand_slug.upper()]:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
            break

    # Known model patterns for each brand (to split model from variant)
    # This handles cases where there's no space between model and variant
    model_patterns = [
        # BMW
        r'^(X[1-7]|i[3-8X]|iX[1-3]?|Serie [1-8]|[1-8][0-9]{2}|M[2-8]|Z[34]|Active Hybrid \d)',
        # Audi
        r'^(Q[2-8]|A[1-8]|e-tron(?:\s*GT)?|TT|RS\s*\d|S[1-8])',
        # Mercedes
        r'^(Clase [A-Z]{1,3}|GLA|GLB|GLC|GLE|GLS|CLA|CLS|EQA|EQB|EQC|EQE|EQS|Vito|Sprinter|AMG GT)',
        # Volkswagen
        r'^(Golf|Polo|T-Roc|T-Cross|Tiguan|Touareg|Touran|Passat|Arteon|ID\.\d|Taigo|Caddy|Multivan|Up)',
        # Toyota
        r'^(Yaris(?:\s*Cross)?|Corolla|RAV4|C-HR|Camry|Hilux|Land Cruiser|Prius|Proace|Highlander|Aygo(?:\s*X)?|bZ4X)',
        # Hyundai
        r'^(Tucson|Kona|i[123]0|i[123]0 N|Bayon|Santa Fe|IONIQ\s*\d?|Nexo)',
        # Kia
        r'^(Sportage|Niro|Ceed|XCeed|Stonic|Sorento|EV\d|Picanto|Rio|Soul|Proceed)',
        # Volvo
        r'^(XC[46]0|V[46]0|S[69]0|C[34]0|EX[39]0)',
        # CUPRA
        r'^(Formentor|Born|Leon|Ateca|Tavascan)',
        # Mazda
        r'^(CX-[35]|CX-[36]0|MX-[35]|Mazda[236])',
        # Skoda
        r'^(Octavia|Superb|Fabia|Karoq|Kodiaq|Kamiq|Enyaq|Scala|Rapid)',
        # Lexus
        r'^(NX|RX|UX|ES|IS|LC|LS|LBX)',
        # Mitsubishi
        r'^(Outlander|Eclipse Cross|ASX|Space Star|L200)',
        # Tesla
        r'^(Model [3SYXR])',
        # Alfa Romeo
        r'^(Giulia|Stelvio|Tonale|Junior)',
        # Generic: series numbers like "118", "218", "320"
        r'^(\d{3})',
    ]

    model = ""
    variant = ""

    for pattern in model_patterns:
        m = re.match(pattern, text, re.IGNORECASE)
        if m:
            model = m.group(1).strip()
            variant = text[m.end():].strip()
            break

    if not model:
        # Fallback: split at first digit-letter or letter-digit transition
        parts = text.split(" ", 1)
        if parts:
            model = parts[0]
            variant = parts[1] if len(parts) > 1 else ""

    return make, model, variant


def parse_power(text: str) -> int:
    """Parse HP from AutoScout24 power format like '103 kW (140 CV)' or '140 CV'."""
    # Try CV first (HP in Spanish)
    m = re.search(r'(\d+)\s*CV', text)
    if m:
        return int(m.group(1))
    # Try kW conversion
    m = re.search(r'(\d+)\s*kW', text)
    if m:
        kw = int(m.group(1))
        return round(kw * 1.36)  # kW to HP/CV conversion
    return 0


async def dismiss_cookies(page):
    """Dismiss the cookie consent banner if present."""
    try:
        # AutoScout24 uses a consent banner with "Aceptar" or "Aceptar y cerrar"
        for selector in [
            "button:has-text('Aceptar y cerrar')",
            "button:has-text('Aceptar')",
            "button:has-text('Accept')",
            "[data-testid='consent-accept']",
            ".consent-accept",
        ]:
            btn = page.locator(selector)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                await page.wait_for_timeout(1000)
                return
    except Exception:
        pass


async def extract_listings_from_page(page) -> list:
    """Extract car listing data from the current page using JS evaluation.

    AutoScout24 renders listing cards as <article> elements with rich data-*
    attributes containing structured listing data. The text content provides
    title (make + model on line 1, variant on line 2) and additional specs.
    """
    listings = await page.evaluate("""() => {
        const results = [];
        const articles = document.querySelectorAll('article[data-testid="list-item"]');

        for (const card of articles) {
            // Extract structured data from data-* attributes
            const guid = card.getAttribute('data-guid') || card.id || '';
            const price = parseInt(card.getAttribute('data-price') || '0', 10);
            const make = card.getAttribute('data-make') || '';
            const model = card.getAttribute('data-model') || '';
            const mileage = parseInt(card.getAttribute('data-mileage') || '0', 10);
            const fuelType = card.getAttribute('data-fuel-type') || '';
            const firstReg = card.getAttribute('data-first-registration') || '';
            const zipCode = card.getAttribute('data-listing-zip-code') || '';
            const position = card.getAttribute('data-position') || '';
            const source = card.getAttribute('data-source') || '';
            const otp = card.getAttribute('data-otp') || '';
            const boostLevel = card.getAttribute('data-boost_level') || '';
            const appliedBoost = card.getAttribute('data-applied_boost_level') || '';
            const relevance = card.getAttribute('data-relevance_adjustment') || '';
            const boostProduct = card.getAttribute('data-boosting_product') || '';

            // Get text content (for variant, HP, location city, etc.)
            const text = (card.innerText || '').trim();

            // Find image
            let imageUrl = '';
            const imgs = card.querySelectorAll('img');
            for (const img of imgs) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src.includes('listing-images') || src.includes('pictures.autoscout24')) {
                    imageUrl = src.replace(/\\/\\d+x\\d+\\.webp$/, '/720x540.webp');
                    break;
                }
            }

            // Extract the detail page URL from anchor elements
            // AutoScout24 uses two anchors:
            //   .DeclutteredListItem_overlay_anchor (full absolute URL)
            //   .ListItemTitle_anchor (relative path)
            let detailUrl = '';
            const anchors = card.querySelectorAll('a[href]');
            for (const a of anchors) {
                const href = a.href || '';  // .href gives resolved absolute URL
                if (href.includes('/anuncios/')) {
                    // Strip tracking query params for cleaner URL
                    detailUrl = href.split('?')[0];
                    break;
                }
            }
            // Fallback: construct from GUID if no link found
            if (!detailUrl && guid) {
                detailUrl = 'https://www.autoscout24.es/anuncios/' + make + '-' + model + '-' + guid;
            }

            if (price > 0 || make) {
                results.push({
                    guid: guid,
                    url: detailUrl,
                    data_make: make,
                    data_model: model,
                    data_price: price,
                    data_mileage: mileage,
                    data_fuel_type: fuelType,
                    data_first_reg: firstReg,
                    data_zip_code: zipCode,
                    text: text.substring(0, 2000),
                    image: imageUrl,
                });
            }
        }

        return results;
    }""")

    return listings


def parse_title_from_url(url: str, brand_slug: str) -> tuple:
    """Extract make, model, variant from AutoScout24 detail URL.

    URL pattern: /anuncios/bmw-x2-sdrive-18i-gasolina-blanco-{uuid}
    Structure: {brand}-{model}-{variant...}-{fuel}-{color}-{uuid}

    Examples:
    - bmw-x2-sdrive-18i-gasolina-blanco -> model=X2, variant=sDrive 18i
    - bmw-218-218da-gran-coupe-diesel-gris -> model=218, variant=218dA Gran Coupe
    - bmw-active-hybrid-5-318d-auto-touring-electro-gasolina-gris -> model=Active Hybrid 5, variant=318d Auto Touring
    """
    make = normalize_brand(brand_slug.replace("-", " "))

    match = re.search(r'/anuncios/(.+?)(?:\?|$)', url)
    if not match:
        return make, "", ""

    slug = match.group(1)

    # Remove the UUID at the end (8-4-4-4-12 hex pattern)
    slug = re.sub(r'-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', '', slug)

    # Remove known color words from the end
    colors = {'negro', 'blanco', 'gris', 'azul', 'rojo', 'plata', 'plateado',
              'verde', 'naranja', 'marron', 'beige', 'amarillo', 'dorado',
              'bronce', 'burdeos', 'violeta', 'oro', 'antracita', 'grafito'}
    parts = slug.split('-')
    while parts and parts[-1].lower() in colors:
        parts.pop()

    # Remove fuel type words from the end (can be multi-word like "electro-gasolina")
    fuels = {'gasolina', 'diesel', 'electrico', 'hibrido', 'glp', 'gnc',
             'electro', 'benzin'}
    while parts and parts[-1].lower() in fuels:
        parts.pop()

    # Remove brand prefix
    brand_parts = brand_slug.lower().split('-')
    if parts[:len(brand_parts)] == brand_parts:
        parts = parts[len(brand_parts):]

    if not parts:
        return make, "", ""

    # Reconstruct and parse title to extract model vs variant
    title_text = ' '.join(parts)
    _, model, variant = parse_title(title_text, brand_slug)

    # Clean up variant: capitalize properly
    if variant:
        # Fix common abbreviations that should stay uppercase/specific
        variant = variant.replace('sdrive', 'sDrive').replace('xdrive', 'xDrive')
        variant = variant.replace('tdci', 'TDCi').replace('tfsi', 'TFSI')
        variant = variant.replace('tsi', 'TSI').replace('tdi', 'TDI')
        variant = variant.replace('dct', 'DCT').replace('dsg', 'DSG')

    return make, model, variant


def parse_listing(raw: dict, brand_slug: str) -> CarListing:
    """Parse a CarListing from data attributes + card text.

    Data attributes (from <article> data-* attrs) provide reliable structured data:
    - data_make, data_model, data_price, data_mileage, data_fuel_type, data_first_reg

    Card text provides supplementary data:
    - Variant (line 2 of card text), HP, location city, transmission
    """
    url = raw.get("url", "")
    image = raw.get("image", "")
    text = raw.get("text", "")

    car = CarListing(
        platform="autoscout24",
        url=url,
        image_url=image,
    )

    # -- Primary: data attributes (highly reliable) --

    # Make — data attribute returns slugs like "mercedes-benz", "alfa-romeo"
    data_make = raw.get("data_make", "")
    if data_make:
        car.make = normalize_brand(data_make)
    else:
        car.make = normalize_brand(brand_slug)

    # Model from data attribute
    data_model = raw.get("data_model", "")

    # Price from data attribute
    data_price = raw.get("data_price", 0)
    if data_price:
        car.price = data_price

    # Mileage from data attribute
    data_mileage = raw.get("data_mileage", 0)
    if data_mileage:
        car.mileage_km = data_mileage

    # Year from data-first-registration (format: "MM-YYYY")
    data_first_reg = raw.get("data_first_reg", "")
    if data_first_reg:
        reg_match = re.search(r'(\d{4})', data_first_reg)
        if reg_match:
            car.year = int(reg_match.group(1))

    # Fuel type from data attribute code
    FUEL_CODE_MAP = {
        "b": "Gasoline",
        "d": "Diesel",
        "e": "Electric",
        "2": "Hybrid",   # Electro/Gasoline or Electro/Diesel
        "3": "PHEV",     # Plug-in hybrid
        "l": "LPG",
        "c": "CNG",
        "m": "Mild Hybrid",
    }
    data_fuel = raw.get("data_fuel_type", "")
    if data_fuel:
        car.fuel_type = FUEL_CODE_MAP.get(data_fuel.lower(), "")

    # -- Secondary: parse text for variant, HP, location, transmission --

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Title structure in card text:
    #   Line 0: "{Make} {Model}" (e.g., "BMW X3")
    #   Line 1: "{Variant}" (e.g., "xDrive20d")
    # Extract model and variant from the first two lines
    title_line = ""
    variant_line = ""
    found_title = False

    for i, line in enumerate(lines):
        # Skip short lines and pure numbers
        if len(line) < 2:
            continue
        if re.match(r'^\d{1,3}$', line):
            continue

        if not found_title:
            # First substantial line should be the title (make + model)
            # Verify it looks like a car title (starts with brand name)
            make_lower = car.make.lower() if car.make else brand_slug.replace("-", " ").lower()
            if line.lower().startswith(make_lower) or (data_model and data_model.lower() in line.lower()):
                title_line = line
                found_title = True
                continue
            # Also accept if it starts with the brand uppercase
            brand_upper = brand_slug.upper().replace("-", " ")
            if line.upper().startswith(brand_upper):
                title_line = line
                found_title = True
                continue
        elif found_title and not variant_line:
            # The next line after title is the variant
            # Skip known non-variant lines
            lower = line.lower()
            if lower in ("guardar", "nuevo", "calcula tu seguro"):
                continue
            if re.search(r'€|ES-\d{5}', line):
                break
            variant_line = line
            break

    # Parse model from title line (data attribute) and variant from second line
    if data_model:
        car.model = data_model.upper() if len(data_model) <= 4 else data_model.title()
        # Fix common model name casing
        model_casing = {
            "x1": "X1", "x2": "X2", "x3": "X3", "x4": "X4", "x5": "X5", "x6": "X6", "x7": "X7",
            "i3": "i3", "i4": "i4", "i5": "i5", "i7": "i7", "i8": "i8",
            "ix": "iX", "ix1": "iX1", "ix2": "iX2", "ix3": "iX3",
            "q2": "Q2", "q3": "Q3", "q5": "Q5", "q7": "Q7", "q8": "Q8",
            "a1": "A1", "a3": "A3", "a4": "A4", "a5": "A5", "a6": "A6",
            "c-hr": "C-HR", "rav4": "RAV4", "cx-5": "CX-5", "cx-30": "CX-30",
            "t-roc": "T-Roc", "t-cross": "T-Cross", "id.3": "ID.3", "id.4": "ID.4", "id.5": "ID.5",
            "ev6": "EV6", "ev9": "EV9",
            "clase-a": "Clase A", "clase-b": "Clase B", "clase-c": "Clase C", "clase-e": "Clase E",
            "gla": "GLA", "glb": "GLB", "glc": "GLC", "gle": "GLE", "gls": "GLS",
            "cla": "CLA", "cls": "CLS",
            "eqa": "EQA", "eqb": "EQB", "eqc": "EQC", "eqe": "EQE", "eqs": "EQS",
            "xc40": "XC40", "xc60": "XC60", "v60": "V60", "v90": "V90",
            "s60": "S60", "s90": "S90", "c40": "C40", "ex30": "EX30", "ex90": "EX90",
            "active-hybrid-5": "Active Hybrid 5", "active-hybrid-3": "Active Hybrid 3",
            # Toyota
            "rav 4": "RAV4", "rav4": "RAV4", "c-hr": "C-HR", "corolla": "Corolla",
            "yaris": "Yaris", "yaris cross": "Yaris Cross", "camry": "Camry",
            "highlander": "Highlander", "prius": "Prius", "aygo x": "Aygo X",
            "aygo": "Aygo", "proace": "Proace", "bz4x": "bZ4X",
            "land cruiser": "Land Cruiser", "hilux": "Hilux",
            # Hyundai
            "tucson": "Tucson", "kona": "Kona", "bayon": "Bayon",
            "ioniq 5": "IONIQ 5", "ioniq 6": "IONIQ 6", "ioniq": "IONIQ",
            "i10": "i10", "i20": "i20", "i30": "i30",
            "santa fe": "Santa Fe", "nexo": "Nexo",
            # Kia
            "sportage": "Sportage", "niro": "Niro", "ceed": "Ceed",
            "xceed": "XCeed", "stonic": "Stonic", "sorento": "Sorento",
            "picanto": "Picanto", "rio": "Rio", "soul": "Soul",
            "proceed": "ProCeed",
            # Skoda
            "octavia": "Octavia", "superb": "Superb", "fabia": "Fabia",
            "karoq": "Karoq", "kodiaq": "Kodiaq", "kamiq": "Kamiq",
            "enyaq": "Enyaq", "scala": "Scala",
            # Lexus
            "nx": "NX", "rx": "RX", "ux": "UX", "es": "ES", "is": "IS",
            "lbx": "LBX",
            # Mitsubishi
            "outlander": "Outlander", "eclipse cross": "Eclipse Cross",
            "asx": "ASX", "space star": "Space Star",
            # CUPRA
            "formentor": "Formentor", "born": "Born", "leon": "Leon",
            "ateca": "Ateca", "tavascan": "Tavascan",
            # Alfa Romeo
            "giulia": "Giulia", "stelvio": "Stelvio", "tonale": "Tonale",
            "junior": "Junior",
            # Tesla
            "model 3": "Model 3", "model s": "Model S", "model x": "Model X",
            "model y": "Model Y",
        }
        car.model = model_casing.get(data_model.lower(), car.model)

        # Prefix-based casing for models like "Gla 200" -> "GLA 200", "Cla 180" -> "CLA 180"
        # These are common for Mercedes where data-model = "{series} {number}"
        prefix_casing = {
            "gla": "GLA", "glb": "GLB", "glc": "GLC", "gle": "GLE", "gls": "GLS",
            "cla": "CLA", "cls": "CLS", "cle": "CLE",
            "eqa": "EQA", "eqb": "EQB", "eqc": "EQC", "eqe": "EQE", "eqs": "EQS",
            "amg": "AMG",
        }
        model_lower = car.model.lower()
        for prefix, replacement in prefix_casing.items():
            if model_lower.startswith(prefix + " ") or model_lower == prefix:
                car.model = replacement + car.model[len(prefix):]
                break

    if variant_line:
        car.variant = variant_line
        # Clean up variant: remove leading model name if duplicated with a space
        # e.g., "RAV4 RAV4 2.5l 220H Style" -> "2.5l 220H Style"
        # But keep "218dA Gran Coupé" when model is "218" (variant extends the model number)
        if car.model:
            model_lower = car.model.lower()
            prefix = model_lower + " "
            # Strip repeated model prefix (AutoScout24 sometimes doubles it)
            while car.variant.lower().startswith(prefix):
                car.variant = car.variant[len(car.model):].strip()

    # If still no model/variant, try URL-based extraction
    if not car.model and url and '/anuncios/' in url:
        car.make, car.model, car.variant = parse_title_from_url(url, brand_slug)

    # Parse remaining fields from text lines
    for line in lines:
        # Power: "103 kW (140 CV)" or "140 CV"
        if not car.hp:
            hp = parse_power(line)
            if hp:
                car.hp = hp

        # Refine fuel type from text if data attribute was too generic
        if car.fuel_type == "Hybrid" and not car.fuel_type.startswith("P"):
            lower = line.lower()
            if "enchufable" in lower or "plug-in" in lower:
                car.fuel_type = "PHEV"
            elif "electro/gasolina" in lower:
                car.fuel_type = "Hybrid"
            elif "electro/diésel" in lower:
                car.fuel_type = "Hybrid"

        # Transmission
        if not car.transmission:
            lower = line.lower()
            if "automático" in lower or "automática" in lower:
                car.transmission = "Automatic"
            elif "manual" in lower and "multifunción" not in lower:
                car.transmission = "Manual"

        # Location: "ES-{zip} {city}" pattern
        if not car.location:
            loc_match = re.search(r'ES-\d{5}\s+(.+?)$', line)
            if loc_match:
                car.location = loc_match.group(1).strip().title()

    # Detect transmission from variant text if not found
    if not car.transmission and car.variant:
        car.transmission = detect_transmission(car.variant)

    # Body type detection
    if car.model:
        car.body_type = detect_body_type(car.model, car.variant)
        # Mercedes prefix-based body types (data attrs return "A 180", "GLA 200", etc.)
        if car.body_type == "Other" and car.make == "Mercedes":
            model_prefix = car.model.split()[0].upper() if car.model else ""
            mercedes_body = {
                "A": "Hatchback", "B": "MPV", "C": "Sedan", "E": "Sedan", "S": "Sedan",
                "GLA": "SUV", "GLB": "SUV", "GLC": "SUV", "GLE": "SUV", "GLS": "SUV",
                "CLA": "Sedan", "CLS": "Sedan", "CLE": "Sedan",
                "EQA": "SUV", "EQB": "SUV", "EQC": "SUV", "EQE": "Sedan", "EQS": "Sedan",
                "EQV": "Van", "V": "Van",
            }
            car.body_type = mercedes_body.get(model_prefix, "Other")
        # Supplementary body type mapping for models not in shared utils
        if car.body_type == "Other":
            model_lower = car.model.lower().replace(" ", "")
            extra_body_types = {
                "rav4": "SUV", "highlander": "SUV", "landcruiser": "SUV",
                "hilux": "Pickup", "proace": "Van",
                "bz4x": "SUV", "aygox": "Hatchback", "camry": "Sedan",
                "prius": "Hatchback", "corolla": "Hatchback",
                "ioniq5": "Crossover", "ioniq6": "Sedan", "ioniq": "Hatchback",
                "i10": "Hatchback", "santafe": "SUV", "nexo": "SUV",
                "sorento": "SUV", "soul": "Crossover", "picanto": "Hatchback",
                "rio": "Hatchback", "stonic": "Crossover", "ceed": "Hatchback",
                "proceed": "Estate",
                "superb": "Sedan", "enyaq": "SUV", "scala": "Hatchback",
                "es": "Sedan", "is": "Sedan", "lbx": "Crossover",
                "spacestar": "Hatchback", "asx": "Crossover", "l200": "Pickup",
                "tavascan": "SUV",
                "model3": "Sedan", "models": "Sedan", "modelx": "SUV", "modely": "SUV",
                "serie2": "Other", "serie1": "Hatchback", "serie3": "Sedan",
                "serie5": "Sedan",
                # Mercedes (data attrs return "a 180", "gla 200", etc.)
                "citan": "Van", "claset": "MPV", "vito": "Van", "sprinter": "Van",
                "eqv": "Van",
            }
            car.body_type = extra_body_types.get(model_lower, "Other")

    return car


async def scrape_brand(context, brand_slug: str, filters: SearchFilters) -> list:
    """Scrape all pages for a single brand."""
    all_cars = []
    page_num = 1
    consecutive_empty = 0

    while page_num <= MAX_PAGES:
        url = build_search_url(brand_slug, filters, page_num)
        page = await context.new_page()

        try:
            print(f"  [{brand_slug}] Page {page_num}: loading...", file=sys.stderr)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Dismiss cookies on first page
            if page_num == 1:
                await dismiss_cookies(page)
                await page.wait_for_timeout(1000)

            # Scroll down to trigger lazy loading
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(800)

            # Extract listings
            raw_listings = await extract_listings_from_page(page)
            print(f"  [{brand_slug}] Page {page_num}: {len(raw_listings)} raw cards",
                  file=sys.stderr)

            if not raw_listings:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    print(f"  [{brand_slug}] No more results, stopping.", file=sys.stderr)
                    break
            else:
                consecutive_empty = 0

            for raw in raw_listings:
                car = parse_listing(raw, brand_slug)

                # If we searched with automatic filter, set transmission if unknown
                if filters.transmission == "automatic" and not car.transmission:
                    car.transmission = "Automatic"

                if car.is_valid():
                    all_cars.append(car)

            # Check if this was a short page (last page)
            if len(raw_listings) < RESULTS_PER_PAGE:
                print(f"  [{brand_slug}] Short page ({len(raw_listings)} < {RESULTS_PER_PAGE}), "
                      f"likely last page.", file=sys.stderr)
                break

            page_num += 1

        except Exception as e:
            print(f"  [{brand_slug}] ERROR on page {page_num}: {e}", file=sys.stderr)
            break
        finally:
            await page.close()

        # Small delay between pages to be respectful
        await asyncio.sleep(1)

    return all_cars


async def scrape_autoscout24(filters: SearchFilters) -> list:
    """Full AutoScout24 scrape: iterate brands, paginate, parse, filter, deduplicate."""
    print(f"[autoscout24] Starting scrape: price<={filters.max_price}, year>={filters.min_year}, "
          f"mileage<={filters.max_mileage}, transmission={filters.transmission}, "
          f"brands={len(filters.brands)}", file=sys.stderr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES",
        )

        all_cars = []

        # Process brands sequentially (like flexicar.py pattern)
        for brand in filters.brands:
            slug = BRAND_SLUGS.get(brand.lower(), brand.lower())
            print(f"[autoscout24] Scraping brand: {slug}", file=sys.stderr)
            brand_cars = await scrape_brand(context, slug, filters)
            all_cars.extend(brand_cars)
            print(f"[autoscout24] {slug}: {len(brand_cars)} valid cars", file=sys.stderr)

        await browser.close()

    # Deduplicate by URL
    seen = set()
    unique_cars = []
    for car in all_cars:
        key = car.url if car.url else f"{car.make}_{car.model}_{car.price}_{car.mileage_km}"
        if key not in seen:
            seen.add(key)
            unique_cars.append(car)

    # Apply post-filters
    filtered = []
    for car in unique_cars:
        if car.price > filters.max_price:
            continue
        if car.year < filters.min_year:
            continue
        if car.mileage_km > filters.max_mileage:
            continue
        if filters.transmission == "automatic" and car.transmission.lower() not in (
            "automatic", "automática", "auto", ""
        ):
            continue
        if filters.fuel_types:
            if car.fuel_type.lower() not in [f.lower() for f in filters.fuel_types]:
                continue
        filtered.append(car)

    print(f"[autoscout24] Done: {len(filtered)} qualifying cars "
          f"({len(all_cars)} total, {len(unique_cars)} unique, "
          f"{len(unique_cars) - len(filtered)} filtered out)", file=sys.stderr)
    return filtered


if __name__ == "__main__":
    filters = parse_cli_args()
    cars = asyncio.run(scrape_autoscout24(filters))
    output_results(cars)
