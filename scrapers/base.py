"""Base scraper interface and normalized car schema."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import argparse
import json
import sys


@dataclass
class CarListing:
    """Normalized car listing — every platform scraper must output this."""
    platform: str
    url: str
    image_url: str = ""
    make: str = ""
    model: str = ""
    variant: str = ""
    year: int = 0
    price: int = 0
    original_price: Optional[int] = None
    mileage_km: int = 0
    fuel_type: str = ""  # Diesel|Gasoline|Electric|PHEV|Hybrid|Mild Hybrid
    hp: Optional[int] = None
    transmission: str = ""  # Automatic|Manual
    location: str = ""
    body_type: str = ""  # Sedan|SUV|Estate|Hatchback|Crossover|MPV

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None and v != "" and v != 0}

    def is_valid(self):
        return bool(self.make and self.model and self.year and self.price and self.url)


@dataclass
class SearchFilters:
    """Structured search filters parsed from user input."""
    max_price: int = 25000
    min_year: int = 2020
    transmission: str = "automatic"
    brands: List[str] = field(default_factory=lambda: [
        "alfa-romeo", "audi", "bmw", "cupra", "hyundai", "kia",
        "lexus", "mazda", "mercedes", "mitsubishi", "skoda",
        "tesla", "toyota", "volkswagen", "volvo"
    ])
    max_mileage: int = 150000
    fuel_types: List[str] = field(default_factory=list)  # empty = all
    body_types: List[str] = field(default_factory=list)   # empty = all


class BaseScraper(ABC):
    """Abstract scraper that all platform scrapers must implement."""

    def __init__(self, filters: SearchFilters):
        self.filters = filters

    @abstractmethod
    async def scrape(self) -> List[CarListing]:
        """Scrape the platform and return normalized car listings."""
        pass

    def filter_car(self, car: CarListing) -> bool:
        """Apply post-scrape filters to a car listing."""
        if car.price > self.filters.max_price:
            return False
        if car.year < self.filters.min_year:
            return False
        if car.mileage_km > self.filters.max_mileage:
            return False
        if self.filters.transmission == "automatic" and car.transmission.lower() != "automatic":
            if car.transmission.lower() not in ("automatic", "automática", "auto", ""):
                return False
        if self.filters.fuel_types:
            if car.fuel_type.lower() not in [f.lower() for f in self.filters.fuel_types]:
                return False
        return True


def parse_cli_args() -> SearchFilters:
    """Parse command-line arguments into SearchFilters."""
    parser = argparse.ArgumentParser(description="Car platform scraper")
    parser.add_argument("--max-price", type=int, default=25000)
    parser.add_argument("--min-year", type=int, default=2020)
    parser.add_argument("--transmission", default="automatic")
    parser.add_argument("--brands", default="all",
                        help="Comma-separated brand slugs, or 'all'")
    parser.add_argument("--max-mileage", type=int, default=150000)
    parser.add_argument("--fuel-types", default="",
                        help="Comma-separated: diesel,gasoline,electric,phev,hybrid")
    args = parser.parse_args()

    all_brands = [
        "alfa-romeo", "audi", "bmw", "cupra", "hyundai", "kia",
        "lexus", "mazda", "mercedes", "mitsubishi", "skoda",
        "tesla", "toyota", "volkswagen", "volvo"
    ]

    brands = all_brands if args.brands == "all" else [b.strip() for b in args.brands.split(",")]
    fuel_types = [f.strip() for f in args.fuel_types.split(",") if f.strip()] if args.fuel_types else []

    return SearchFilters(
        max_price=args.max_price,
        min_year=args.min_year,
        transmission=args.transmission,
        brands=brands,
        max_mileage=args.max_mileage,
        fuel_types=fuel_types,
    )


def output_results(cars: List[CarListing]):
    """Output results as JSON to stdout."""
    valid = [c for c in cars if c.is_valid()]
    print(json.dumps([asdict(c) for c in valid], ensure_ascii=False, indent=2))
    print(f"\n# {len(valid)} cars output ({len(cars) - len(valid)} filtered as invalid)", file=sys.stderr)
