# Car Analysis

An AI-powered used car search and evaluation tool for the Spanish market. It scrapes multiple platforms (Clicars, Flexicar), applies expert-level car knowledge to evaluate each listing, calculates total cost of ownership, and generates a visual HTML showcase with filters.

This is a **full program** — not just a script. It has scrapers, a validated cost model, an HTML template engine, and a Claude Code skill that orchestrates the whole pipeline.

## How It Works

```
Free-text query → Filter parsing → Platform scrapers → Raw car data
→ Cost model application → Expert evaluation (by Claude) → Ranked HTML showcase + CSV
```

### Via Claude Code (recommended)

Navigate to this directory and use the skill:

```
cd ~/Documents/Car\ analysis
/car-search
```

Claude will ask for your search. You can say anything:

```
"Find me a premium SUV under 20k, automatic, low mileage"
"BMW or Mercedes, max 25000, 2021+"
"Something fun to drive, hybrid, budget 18k"
"Just search everything with defaults"
```

It will parse your query into structured filters, confirm them with you, then offer to run the full pipeline. Say **"go"** to auto-approve all operations (scrapers, file writes, etc.) and skip the ~50 individual permission prompts.

### Via Python CLI (for manual runs or debugging)

Each scraper can run independently and outputs normalized JSON to stdout:

```bash
# Clicars (HTTP-based, ~2 min)
cd ~/Documents/Car\ analysis
python3 scrapers/clicars.py \
  --max-price 20000 \
  --min-year 2021 \
  --brands "bmw,volvo,lexus" \
  --transmission automatic \
  --max-mileage 100000

# Flexicar (Playwright browser automation, ~5 min)
python3 scrapers/flexicar.py \
  --max-price 20000 \
  --min-year 2021 \
  --brands "bmw,volvo,lexus"
```

All CLI arguments are optional — defaults: €25k max, 2020+, automatic, all 15 brands, 150k km max.

The scrapers output raw JSON. The evaluation, cost model, verdicts, and HTML/CSV generation are handled by Claude via the skill.

## Setup

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

## Project Structure

```
Car analysis/
├── CLAUDE.md                  # Claude Code project instructions
├── skill-car-search.md        # The skill — Claude's orchestration playbook
│
├── scrapers/                  # Platform scrapers (Python)
│   ├── base.py                # Normalized car schema + CLI arg parser
│   ├── utils.py               # Shared parsing (prices, mileage, fuel detection)
│   ├── clicars.py             # Clicars — HTTP scraping (server-rendered)
│   └── flexicar.py            # Flexicar — Playwright browser automation (SPA)
│
├── config/
│   └── cost-model.json        # Insurance, fuel, and service cost rates (validated)
│
├── templates/
│   └── showcase.html          # HTML template with placeholder for car data
│
├── output/                    # Generated files per run
│   ├── showcase-YYYY-MM-DD.html
│   └── cars-evaluated-YYYY-MM-DD.csv
│
├── Results/                   # Archive of completed analyses
│
└── requirements.txt
```

## What Each Piece Does

| Component | Role | Runs how |
|-----------|------|----------|
| `skill-car-search.md` | Orchestration: filter parsing, evaluation logic, verdict rules, output generation | Read by Claude Code |
| `scrapers/clicars.py` | Scrapes Clicars listing pages via HTTP requests + BeautifulSoup | `python3` via Bash |
| `scrapers/flexicar.py` | Scrapes Flexicar SPA via headless Chromium (Playwright) | `python3` via Bash |
| `scrapers/base.py` | Defines the `CarListing` schema that all scrapers output | Imported by scrapers |
| `config/cost-model.json` | Insurance tiers, fuel costs, service rates — validated against real Spanish market data (March 2026) | Read by Claude during evaluation |
| `templates/showcase.html` | Dark-themed card UI with filters, sorting, cost tooltips, expand/collapse evaluations | Template filled by Claude |

## Supported Platforms

| Platform | Scraping Method | Notes |
|----------|----------------|-------|
| **Clicars** | HTTP + BeautifulSoup | Server-rendered. Paginates through listing pages (12 cars/page). Fast. |
| **Flexicar** | Playwright (headless Chrome) | Next.js SPA. Renders ~12 cars per brand page via SSR. Scrapes detail pages for full specs. Slower. |

## Adding a New Platform

1. Create `scrapers/newplatform.py` implementing the same CLI interface (`--max-price`, `--brands`, etc.)
2. Output the same normalized JSON schema (see `base.py` → `CarListing`)
3. Test: `python3 scrapers/newplatform.py --max-price 20000 --brands "bmw" | python3 -m json.tool`
4. Add the platform to the skill's Step 2 scraper commands
5. The HTML showcase auto-detects platforms from the data — no template changes needed

## Cost Model

The cost model at `config/cost-model.json` was validated against real data from:
- **Insurance**: Rastreator, RapidSecur, CHECK24, KIA FAQ forum, SegurosNews, MBFAQ
- **Service**: km77, carwow, BMW FAQ, Club Toyota C-HR, Alfistas, Kia FAQ
- **Fuel**: Spanish average prices Q1 2026

Assumptions: 15,000 km/year, ~30yo driver in Madrid, todo riesgo con franquicia.
