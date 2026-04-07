# Car Analysis — Used Car Search & Evaluation Tool

## What This Project Does
Scrapes used car platforms in Spain (Clicars, Flexicar, Autohero, OcasionPlus, Coches.net, AutoScout24, Autocasión), evaluates each car for premium value, and generates a visual HTML showcase + CSV export. Designed to be run via Claude Code using the `/car-search` skill.

## Skill
The main skill file is at `skill-car-search.md` in this directory. When Franco asks to search for cars, analyze the used car market, or mentions `/car-search`, read and follow that skill file.

## Architecture
- **Scrapers** (`scrapers/`): Python scripts that extract raw car data. Each platform has its own scraper implementing the normalized output schema.
  - `clicars.py` — HTTP-based (server-rendered pages, no browser needed)
  - `flexicar.py` — Playwright browser automation (SPA, requires headless Chrome)
  - `autohero.py` — HTTP-based (parses Apollo GraphQL state from SSR HTML)
  - `ocasionplus.py` — HTTP-based (JSON-LD structured data + HTML card parsing)
  - `cochesnet.py` — Playwright headful (Adevinta bot detection requires non-headless). Dealer-only filter.
  - `autoscout24.py` — Playwright headless (rich data-* attributes on listing cards)
  - `autocasion.py` — HTTP-based (server-rendered HTML, path-based URL filters)
  - `base.py` — Normalized car schema and abstract interface
  - `utils.py` — Shared parsing utilities
- **Config** (`config/cost-model.json`): Validated insurance, fuel, and service cost rates for Spain
- **Templates** (`templates/showcase.html`): HTML template with `/*CARS_JSON*/` placeholder
- **Output** (`output/`): Generated HTML + CSV files per run

## How It Works
1. Franco provides a free-text search query (or structured filters)
2. Claude parses the query into structured filters (see skill file for rules)
3. Claude runs the Python scrapers via Bash with the parsed filters
   - HTTP scrapers (clicars, autohero, autocasion, ocasionplus) run in parallel
   - Playwright scrapers (flexicar, autoscout24, cochesnet) run sequentially
4. Scrapers output normalized JSON to stdout
5. Claude evaluates each car: assigns verdict, writes evaluation, calculates costs using `config/cost-model.json`
6. Claude generates the final HTML (from template) and CSV
7. Claude serves the output via `python3 -m http.server 8080` and opens it in the browser
   - **IMPORTANT**: Must serve over HTTP, not `file://` — the financial model is a React app that requires HTTP due to CORS
8. Each car card has a "Financial Model" CTA that opens a detailed cashflow analysis (React app at `output/financial-model/dist/`)

## Environment
- Python 3.9+ with `playwright` installed (browsers already set up)
- Dependencies: `playwright`, `playwright-stealth`, `beautifulsoup4`, `lxml`, `requests`
- Install: `pip3 install -r requirements.txt`
- Playwright browsers: `python3 -m playwright install chromium`
- **Coches.net note**: Requires `playwright-stealth` and runs in headful mode (needs display). On Linux, use Xvfb.

## Scraper CLI Interface
All scrapers accept the same CLI arguments:
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

## Platform-Specific Notes

| Platform | Method | Volume Cap | Key Caveat |
|----------|--------|-----------|------------|
| Clicars | HTTP + BS4 | ~200 | Server-rendered, 12 cars/page |
| Autohero | HTTP (Apollo JSON) | ~71 | No server-side filtering; 24 cars × 4 sort orders |
| Autocasión | HTTP + BS4 | ~1000+ | No year filter in URL → post-filtered |
| OcasionPlus | HTTP (JSON-LD + HTML) | ~200+/brand | No server-side filtering. JSON-LD has specs, HTML has discounted price + location. |
| Flexicar | Playwright | ~200 | Next.js SPA. Two prices: cash and financed |
| AutoScout24 | Playwright | ~400/brand | Rich data-* attrs. Max 20 pages/brand |
| Coches.net | Playwright headful | ~1000+/brand | Adevinta bot detection → headful only. Dealer-only via SellerTypeId=1 |

## Known Gotchas (Lessons Learned)

1. **Showcase field name mapping**: The HTML template (`templates/showcase.html`) uses DIFFERENT field names than the scrapers. When building the `/*CARS_JSON*/` array, you MUST rename: `url→link`, `image_url→image`, `mileage_km→mileage`, `fuel_type→fuel`, `monthly_budget→monthly`, `yearly_service→yearlyService`, `original_price→origPrice`, `evaluation→eval`. Calculate `discount = origPrice - price`. See skill Step 7 for full mapping.

2. **Financial model build**: `tsc` is NOT globally installed. Use `./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build` (or `npm install` first if `node_modules` is missing). The showcase stores the car list in `localStorage` (key: `carAnalysis_cars`) — do NOT base64-encode the full list in URL params (causes URL overflow with >50 cars).

3. **Clicars images**: The first `<img>` inside card `<a>` tags is often a badge SVG, not the car photo. The scraper skips `.svg` files and grabs the first real photo (usually from `storage.googleapis.com`).

4. **Salvage/damaged cars**: Platforms like Autocasión list crashed/salvage vehicles at suspiciously low prices with no clear damage flag. Apply price sanity floors before evaluation (see skill Step 3).

5. **Tesla model names on Autocasión**: The model field often comes through as just "Model" instead of "Model 3" or "Model Y". Parse the variant field to fix.

6. **HP extraction**: Most scrapers (especially Autocasión, OcasionPlus) don't extract HP directly. Parse it from variant text: match `(\d{2,3})\s*CV` or `([\d,]+)\s*kW` (×1.36 for HP).

7. **Fuel type detection**: Variants containing "48V" or "MHEV" are Mild Hybrid, not Gasoline. Fix fuel_type during data cleaning.

8. **Clicars brand IDs**: Clicars uses opaque numeric IDs for brands. New brands need their ID discovered from the website — the scraper silently skips unknown brands.

## Cost Model
The cost model at `config/cost-model.json` contains validated rates from real Spanish market data (Rastreator, KIA FAQ forum, km77, Alfistas, RapidSecur, etc. — researched March 2026). Do not modify without re-validation.

## Adding a New Platform
1. Create `scrapers/newplatform.py` implementing the same CLI interface and normalized output schema
2. Add the platform name to the skill's platform list
3. Add platform badge CSS color in `templates/showcase.html`
4. Test with `python3 scrapers/newplatform.py --max-price 20000 --brands "bmw" | python3 -m json.tool`
