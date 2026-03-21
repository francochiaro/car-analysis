"""Shared utilities for car data parsing and normalization."""

import re
from typing import Optional


# Brand name normalization
BRAND_MAP = {
    "alfa-romeo": "Alfa Romeo",
    "alfa romeo": "Alfa Romeo",
    "audi": "Audi",
    "bmw": "BMW",
    "cupra": "CUPRA",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "lexus": "Lexus",
    "mazda": "Mazda",
    "mercedes": "Mercedes",
    "mercedes-benz": "Mercedes",
    "mitsubishi": "Mitsubishi",
    "skoda": "Skoda",
    "tesla": "Tesla",
    "toyota": "Toyota",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "volvo": "Volvo",
}

# Model → body type mapping
BODY_TYPE_MAP = {
    # Hatchback
    "serie 1": "Hatchback", "a1": "Hatchback", "a3": "Hatchback",
    "clase a": "Hatchback", "golf": "Hatchback", "leon": "Hatchback",
    "mazda3": "Hatchback", "yaris": "Hatchback", "fabia": "Hatchback",
    "polo": "Hatchback", "born": "Hatchback", "junior": "Hatchback",
    "i20": "Hatchback", "model 3": "Sedan",
    # Sedan
    "serie 3": "Sedan", "serie 5": "Sedan", "a4": "Sedan",
    "clase c": "Sedan", "clase e": "Sedan", "s90": "Sedan",
    "octavia": "Sedan", "giulia": "Sedan", "passat": "Sedan",
    "serie 2 gran coupe": "Sedan",
    # SUV / Crossover
    "x1": "SUV", "x2": "SUV", "x3": "SUV", "q2": "SUV", "q3": "SUV",
    "xc40": "SUV", "xc60": "SUV", "clase gla": "SUV", "clase glb": "SUV",
    "tucson": "SUV", "sportage": "SUV", "c-hr": "SUV", "ux": "SUV",
    "stelvio": "SUV", "tonale": "SUV", "formentor": "SUV",
    "t-roc": "SUV", "t-cross": "SUV", "tiguan": "SUV",
    "karoq": "SUV", "kodiaq": "SUV", "kamiq": "SUV",
    "niro": "Crossover", "xceed": "Crossover", "yaris cross": "Crossover",
    "cx-5": "SUV", "cx-30": "Crossover", "id.4": "SUV",
    "ev6": "Crossover", "kona": "Crossover", "outlander": "SUV",
    "eclipse cross": "SUV", "bayon": "Crossover",
    # Estate
    "serie 3 touring": "Estate", "serie 5 touring": "Estate",
    "a4 avant": "Estate", "v60": "Estate", "v90": "Estate",
    "arteon shooting brake": "Estate", "arteon sb": "Estate",
    "passat variant": "Estate", "clase cla shooting brake": "Estate",
    "corolla touring": "Estate", "corolla ts": "Estate",
    "octavia combi": "Estate",
    # MPV
    "clase b": "MPV", "serie 2 active tourer": "MPV",
    "serie 2 gran tourer": "MPV",
}


def normalize_brand(raw: str) -> str:
    """Normalize a brand name."""
    key = raw.lower().strip()
    return BRAND_MAP.get(key, raw.title())


def detect_body_type(model: str, variant: str = "") -> str:
    """Detect body type from model and variant names."""
    combined = f"{model} {variant}".lower()
    # Check longer keys first (more specific)
    for key in sorted(BODY_TYPE_MAP.keys(), key=len, reverse=True):
        if key in combined:
            return BODY_TYPE_MAP[key]
    return "Other"


def parse_mileage(text: str) -> Optional[int]:
    """Parse mileage from Spanish-format text (dots as thousands separators)."""
    text = text.replace("\xa0", " ")
    # Match patterns like "86.460 km", "86460 km", "86,460 km"
    match = re.search(r'([\d.,]+)\s*km', text, re.IGNORECASE)
    if match:
        num_str = match.group(1)
        # Spanish format: dots as thousands separators
        cleaned = num_str.replace(".", "").replace(",", "")
        try:
            km = int(cleaned)
            if 0 < km < 1000000:
                return km
        except ValueError:
            pass
    return None


def parse_price(text: str) -> Optional[int]:
    """Parse price from text with € symbol and Spanish formatting."""
    # Match patterns like "23.490 €", "€23,490", "23490"
    match = re.search(r'([\d.,]+)\s*€|€\s*([\d.,]+)', text)
    if match:
        num_str = match.group(1) or match.group(2)
        cleaned = num_str.replace(".", "").replace(",", "")
        try:
            price = int(cleaned)
            if 1000 < price < 500000:
                return price
        except ValueError:
            pass
    return None


def parse_hp(text: str) -> Optional[int]:
    """Parse horsepower from text."""
    match = re.search(r'(\d+)\s*(?:CV|cv|HP|hp|caballo)', text)
    if match:
        hp = int(match.group(1))
        if 30 < hp < 1000:
            return hp
    return None


def parse_year(text: str) -> Optional[int]:
    """Parse year from text."""
    match = re.search(r'\b(20[1-3]\d)\b', text)
    if match:
        return int(match.group(1))
    return None


def detect_fuel_type(text: str) -> str:
    """Detect fuel type from text."""
    t = text.lower()
    if "eléctric" in t or "electric" in t:
        return "Electric"
    if "híbrido enchufable" in t or "plug-in" in t or "phev" in t:
        return "PHEV"
    if "híbrido" in t or "hybrid" in t or "hev" in t:
        # Distinguish true hybrid from mild hybrid
        if "mhev" in t or "mild" in t or "48v" in t:
            return "Mild Hybrid"
        return "Hybrid"
    if "diésel" in t or "diesel" in t or "tdi" in t or "cdi" in t or "dci" in t:
        return "Diesel"
    if "gasolina" in t or "gasoline" in t or "petrol" in t or "tsi" in t or "tfsi" in t:
        return "Gasoline"
    return ""


def detect_transmission(text: str) -> str:
    """Detect transmission from text."""
    t = text.lower()
    if any(kw in t for kw in ["automática", "automatic", "auto", "dsg", "dct", "s tronic",
                                "e-cvt", "ecvt", "tiptronic", "steptronic", "edct"]):
        return "Automatic"
    if "manual" in t:
        return "Manual"
    return ""


def extract_location_from_url(url: str) -> str:
    """Extract location from Flexicar URL slug."""
    # Pattern: ...-automatica-{location}_{id}/
    match = re.search(r'(?:automatica|manual)-([a-z0-9-]+)_\d+/?$', url)
    if match:
        location = match.group(1)
        # Clean up: replace hyphens, title case
        location = location.replace("-", " ").title()
        # Fix common patterns
        location = location.replace(" 2", "").replace(" 3", "")
        return location
    return ""
