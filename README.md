# Car Analysis

An AI-powered used car search, evaluation, and financial modeling tool for the Spanish market. It scrapes 7 platforms, applies expert-level car knowledge to evaluate each listing, calculates total cost of ownership, and generates a visual HTML showcase with a per-car financial model.

This is a **full program** — not just a script. It has scrapers, a validated cost model, a financial analysis tool, an HTML template engine, and a Claude Code skill that orchestrates the whole pipeline.

## How to Run

**Important:** The showcase and financial model must be served over HTTP — they will NOT work opened as `file://` URLs (CORS blocks the React financial model).

```bash
cd ~/Documents/Car\ analysis

# Start the local server (keep it running in the background)
python3 -m http.server 8080 &
```

### From scratch (no data)

```bash
# Run the car search skill in Claude Code
/car-search
# Say something like: "BMW or Volvo under 25k, automatic"
# Say "go" to auto-approve all operations

# The pipeline generates the showcase at:
# http://localhost:8080/output/showcase-YYYY-MM-DD.html
```

### With existing data

```bash
# Open the existing showcase
# http://localhost:8080/Results/car-showcase-view.html

# Click "Financial Model" on any car → opens the financial analysis
```

### If you update the financial model code

```bash
cd output/financial-model && npm run build
# Then hard-refresh (Cmd+Shift+R) the browser
```

## How It Works

```
Free-text query → Filter parsing → Platform scrapers → Raw car data
→ Cost model application → Expert evaluation (by Claude) → Ranked HTML showcase + CSV
→ Click any car → Financial Model (purchase vs renting cashflow, NPV comparison)
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
cd ~/Documents/Car\ analysis

# Any scraper — same CLI interface
python3 scrapers/clicars.py \
  --max-price 20000 \
  --min-year 2021 \
  --brands "bmw,volvo,lexus" \
  --transmission automatic \
  --max-mileage 100000
```

All scrapers accept the same CLI arguments. Defaults: €25k max, 2020+, automatic, all brands, 150k km max.

The scrapers output raw JSON. The evaluation, cost model, verdicts, and HTML/CSV generation are handled by Claude via the skill.

When orchestrated via the skill, HTTP scrapers (Clicars, Autohero, Autocasión, OcasionPlus) run in parallel. Playwright scrapers (Flexicar, AutoScout24, Coches.net) run sequentially to avoid browser contention.

## Financial Model

Each car card in the showcase has a **"Financial Model"** button that opens a detailed cashflow analysis tool (React+Vite app).

### What it computes

- **Purchase scenario**: Monthly cashflow table with down payment, ITP, gestoría, French credit installments, insurance, fuel, service, ITV, and residual value at end of horizon
- **Renting scenario**: Monthly fee with auto-renewal, inflation adjustment per period, and early termination penalty for incomplete final periods
- **NPV comparison**: Discounted cashflow comparison of purchase vs renting, highlighting which option is cheaper

### Configurable parameters

All inputs are editable with instant recomputation:

| Parameter | Default | What it affects |
|-----------|---------|-----------------|
| Loan amount | 80% of price | Down payment + installment size |
| Interest rate (APR) | 7% | Monthly installment (French credit) |
| Loan term | 60 months | Installment duration |
| Renting fee | Estimated from car | Monthly renting outflow |
| Renting period | 48 months | Contract length, auto-renews with inflation |
| Time horizon | 48 months | Total analysis period |
| Discount rate | 5% | NPV discounting |
| Inflation rate | 2.5% | Inflates insurance, fuel, service, ITV, and renting renewals |
| Annual km | 15,000 | Scales fuel cost, affects residual value and renting estimate |
| Platform includes taxes | On | Zeroes ITP + gestoría for Clicars/Flexicar |

### Car comparison

Pick a second car from the list to compare cashflows and NPVs side-by-side using the same parameters.

### Modifying the financial model

The app was built with the Ralph iterative agent. To make changes:

```bash
cd output/financial-model
# Edit prd.json — add/modify user stories
./ralph.sh --tool claude 5
npm run build
```

## Setup

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium

# Financial model (one-time)
cd output/financial-model && npm install && npm run build
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
│   ├── clicars.py             # Clicars — HTTP (server-rendered)
│   ├── flexicar.py            # Flexicar — Playwright (Next.js SPA)
│   ├── autohero.py            # Autohero — HTTP (Apollo GraphQL JSON)
│   ├── ocasionplus.py         # OcasionPlus — HTTP (JSON-LD + HTML)
│   ├── cochesnet.py           # Coches.net — Playwright headful (anti-bot)
│   ├── autoscout24.py         # AutoScout24 — Playwright headless
│   └── autocasion.py          # Autocasión — HTTP (server-rendered)
│
├── config/
│   └── cost-model.json        # Insurance, fuel, and service cost rates (validated)
│
├── templates/
│   └── showcase.html          # HTML template with Financial Model CTA
│
├── output/
│   ├── financial-model/       # React+Vite financial model app
│   │   ├── src/               # Source code
│   │   ├── dist/              # Built production files (served by HTTP)
│   │   ├── prd.json           # Ralph user stories
│   │   └── ralph.sh           # Ralph iterative builder
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
| `scrapers/clicars.py` | Clicars — HTTP + BeautifulSoup | `python3` via Bash |
| `scrapers/flexicar.py` | Flexicar — Playwright headless (Next.js SPA) | `python3` via Bash |
| `scrapers/autohero.py` | Autohero — HTTP, parses Apollo GraphQL state from SSR | `python3` via Bash |
| `scrapers/ocasionplus.py` | OcasionPlus — HTTP, JSON-LD structured data + HTML cards | `python3` via Bash |
| `scrapers/cochesnet.py` | Coches.net — Playwright headful (Adevinta anti-bot) | `python3` via Bash |
| `scrapers/autoscout24.py` | AutoScout24 — Playwright headless, data-* attributes | `python3` via Bash |
| `scrapers/autocasion.py` | Autocasión — HTTP + BeautifulSoup (server-rendered) | `python3` via Bash |
| `scrapers/base.py` | Defines the `CarListing` schema that all scrapers output | Imported by scrapers |
| `config/cost-model.json` | Insurance tiers, fuel costs, service rates — validated against real Spanish market data (March 2026) | Read by Claude during evaluation |
| `templates/showcase.html` | Dark-themed card UI with filters, sorting, cost tooltips, Financial Model CTA | Template filled by Claude |
| `output/financial-model/` | React app: cashflow tables, NPV, parameter panel, car comparison | Built with Ralph, served via HTTP |

## Supported Platforms

| Platform | Scraping Method | Volume | Notes |
|----------|----------------|--------|-------|
| **Clicars** | HTTP + BeautifulSoup | ~200 | Server-rendered, 12 cars/page. Fast. |
| **Flexicar** | Playwright headless | ~200 | Next.js SPA. Two prices: cash and financed. |
| **Autohero** | HTTP (Apollo JSON) | ~71 | Parses GraphQL state from SSR HTML. No server-side filtering. |
| **OcasionPlus** | HTTP (JSON-LD + HTML) | ~200+/brand | Specs in JSON-LD, prices + location in HTML. |
| **Coches.net** | Playwright headful | ~1000+/brand | Adevinta bot detection — must run non-headless. Dealer-only filter. |
| **AutoScout24** | Playwright headless | ~400/brand | Rich data-* attributes. Max 20 pages/brand. |
| **Autocasión** | HTTP + BeautifulSoup | ~1000+ | No year filter in URL — results are post-filtered. |

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
