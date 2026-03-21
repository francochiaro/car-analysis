# Car Analysis — Used Car Search & Evaluation Tool

## What This Project Does
Scrapes used car platforms in Spain (Clicars, Flexicar), evaluates each car for premium value, and generates a visual HTML showcase + CSV export. Designed to be run via Claude Code using the `/car-search` skill.

## Skill
The main skill file is at `skill-car-search.md` in this directory. When Franco asks to search for cars, analyze the used car market, or mentions `/car-search`, read and follow that skill file.

## Architecture
- **Scrapers** (`scrapers/`): Python scripts that extract raw car data. Each platform has its own scraper implementing the normalized output schema.
  - `clicars.py` — HTTP-based (server-rendered pages, no browser needed)
  - `flexicar.py` — Playwright browser automation (SPA, requires headless Chrome)
  - `base.py` — Normalized car schema and abstract interface
  - `utils.py` — Shared parsing utilities
- **Config** (`config/cost-model.json`): Validated insurance, fuel, and service cost rates for Spain
- **Templates** (`templates/showcase.html`): HTML template with `/*CARS_JSON*/` placeholder
- **Output** (`output/`): Generated HTML + CSV files per run

## How It Works
1. Franco provides a free-text search query (or structured filters)
2. Claude parses the query into structured filters (see skill file for rules)
3. Claude runs the Python scrapers via Bash with the parsed filters
4. Scrapers output normalized JSON to stdout
5. Claude evaluates each car: assigns verdict, writes evaluation, calculates costs using `config/cost-model.json`
6. Claude generates the final HTML (from template) and CSV
7. Claude opens the HTML and presents a summary

## Environment
- Python 3.9+ with `playwright` installed (browsers already set up)
- Dependencies: `playwright`, `beautifulsoup4`, `lxml`, `requests`
- Install: `pip3 install -r requirements.txt`
- Playwright browsers: `python3 -m playwright install chromium`

## Scraper CLI Interface
Both scrapers accept the same CLI arguments:
```
python3 scrapers/clicars.py \
  --max-price 25000 \
  --min-year 2020 \
  --transmission automatic \
  --brands "bmw,audi,volvo,mercedes,lexus" \
  --max-mileage 150000
```
Output: JSON array of normalized car objects to stdout.

## Normalized Car Schema
Every scraper outputs this structure per car:
```json
{
  "platform": "clicars",
  "url": "https://...",
  "image_url": "https://...",
  "make": "BMW",
  "model": "Serie 5",
  "variant": "520dA Touring",
  "year": 2020,
  "price": 23290,
  "original_price": 27890,
  "mileage_km": 109186,
  "fuel_type": "Diesel",
  "hp": 190,
  "transmission": "Automatic",
  "location": "Madrid",
  "body_type": "Estate"
}
```

## Cost Model
The cost model at `config/cost-model.json` contains validated rates from real Spanish market data (Rastreator, KIA FAQ forum, km77, Alfistas, RapidSecur, etc. — researched March 2026). Do not modify without re-validation.

## Adding a New Platform
1. Create `scrapers/newplatform.py` implementing the same CLI interface and normalized output schema
2. Add the platform name to the skill's platform list
3. Test with `python3 scrapers/newplatform.py --max-price 20000 --brands "bmw" | python3 -m json.tool`
