# Skill: Car Search & Evaluation

## Purpose
Search used car platforms in Spain, evaluate each car for premium value relative to budget, and generate a ranked visual showcase with cost-of-ownership estimates.

## When to Use
- User says `/car-search`
- User asks to find used cars, search for a car, compare car deals
- User mentions Clicars, Flexicar, or used car shopping in Spain

## Inputs Required
The user provides a **free-text search query**. All parameters are optional — use sensible defaults.

### Example Queries
- "Find me a premium SUV under 20k, automatic, low mileage"
- "BMW or Mercedes, max 25000€, 2021 or newer"
- "Coches eléctricos o híbridos baratos en Madrid"
- "Something fun to drive, budget 15-20k, I don't care about fuel type"
- Just "search cars" → use defaults

### Filter Parsing Rules
Convert the free-text query into these structured filters. Infer from context:

| Filter | Default | How to Infer |
|--------|---------|-------------|
| `max_price` | 25000 | Any mention of budget, price, "under X", "max Xk" |
| `min_year` | 2020 | "recent", "new-ish", "2022+", "last 3 years" |
| `transmission` | automatic | Assume automatic unless "manual" explicitly stated |
| `brands` | all 15 | Brand names, "German", "Japanese", "premium", "Korean" |
| `max_mileage` | 150000 | "low mileage" = 60000, "moderate" = 100000 |
| `fuel_types` | all | "electric", "hybrid", "diesel", "no diesel" |
| `body_types` | all | "SUV", "estate", "hatchback", "sedan" |
| `platforms` | clicars,flexicar | Can restrict to one platform |

**Brand group shortcuts:**
- "premium" / "German" → bmw, audi, mercedes, volvo
- "Japanese" → toyota, lexus, mazda
- "Korean" → hyundai, kia
- "all" → alfa-romeo, audi, bmw, cupra, hyundai, kia, lexus, mazda, mercedes, mitsubishi, skoda, tesla, toyota, volkswagen, volvo

### Confirming Filters
After parsing, show the user the interpreted filters in a table and ask: "Look good? Hit enter to run or adjust anything."

## Process

### Step 0 — Permissions & Session Setup

This workflow involves **many** automated operations. Before starting, present this to the user:

```
This search will run:
  - 2 Python scrapers (Bash commands)
  - ~20+ page fetches per platform
  - File writes (CSV, HTML, JSON)
  - File reads (config, templates)

To avoid being asked to approve each one individually,
you can grant blanket permission now:

  → Type "go" or "run it all" to auto-approve everything
  → Or I'll ask per-operation (slower, ~50+ prompts)
```

**If the user says "go" / "run it all" / "yes" / "auto" / "do it":**
- Proceed through ALL steps without asking for intermediate confirmation
- Do NOT pause for permission on file writes, bash commands, or web fetches
- Only pause if something FAILS or if there's an ambiguity in the search query
- Batch operations: write files in bulk, run scrapers in parallel, generate all outputs in one pass

**If the user says nothing or wants control:**
- Ask before each major step (scraping, evaluation, output generation)
- But still batch within each step — don't ask per-page or per-file

**General rules for this skill (regardless of permission mode):**
- Do NOT ask formatting questions ("should I use markdown?", "want a table?") — just do it
- Do NOT ask confirmation before reading files, running scrapers, or writing outputs
- Do NOT narrate each web fetch or page scrape — report progress at milestone level only ("Clicars done: 180 cars. Starting Flexicar...")
- Do NOT ask "shall I continue?" between steps — the pipeline is linear, just run it
- Only stop to ask if: (a) a scraper fails entirely, (b) the filter interpretation is ambiguous, or (c) 0 cars match

### Step 1 — Parse Query
Convert free-text to structured filters using the rules above. Present to user for confirmation.

### Step 2 — Run Scrapers
Run the platform scrapers in parallel when possible:

```bash
# Clicars (HTTP-based, fast)
cd "/Users/francochiaro/Documents/Car Analysis"
python3 scrapers/clicars.py \
  --max-price {max_price} \
  --min-year {min_year} \
  --transmission {transmission} \
  --brands "{brands_csv}" \
  --max-mileage {max_mileage} \
  > output/clicars-raw.json 2>output/clicars-log.txt

# Flexicar (Playwright browser automation, slower)
python3 scrapers/flexicar.py \
  --max-price {max_price} \
  --min-year {min_year} \
  --transmission {transmission} \
  --brands "{brands_csv}" \
  --max-mileage {max_mileage} \
  > output/flexicar-raw.json 2>output/flexicar-log.txt
```

Report progress: "Scraping Clicars... found X cars. Scraping Flexicar... found Y cars."

### Step 3 — Load & Merge Results
Read both JSON outputs. Deduplicate if a car appears on both platforms (match by make+model+year+mileage proximity). Total count.

### Step 4 — Apply Cost Model
Read `config/cost-model.json`. For each car, calculate:
- **Monthly fuel/charging cost** based on fuel_type
- **Monthly insurance** based on brand tier + HP bracket
- **Monthly budget** = fuel + insurance
- **Yearly service cost** based on brand + powertrain

### Step 5 — Evaluate Each Car
For each car, assign a **verdict** and write a **2-3 sentence evaluation**. The HTML showcase has a "Read more" expand/collapse on each card (clamped to 2 lines by default), so evaluations CAN be longer than what's visible at first glance — write enough to be genuinely useful when expanded.

#### Verdict Taxonomy

| Verdict | Criteria |
|---------|----------|
| **BARGAIN** | Genuinely exceptional value. Premium car well below market, OR very low km for price, OR massive depreciation from new MSRP. Must have no major red flags. |
| **TOP PICK** | Strong recommendation. Good balance of brand premium, mileage, price, and running costs. Minor caveats acceptable. |
| **GOOD** | Solid choice. Fair price, acceptable mileage, decent brand. One or two notable caveats. |
| **CAUTION** | Significant red flags. Very high mileage (>100k on non-Toyota), overpriced for spec, fleet-stripped trim, or problematic brand+mileage combo. |
| **NO-GO** | Avoid. Extreme mileage (>130k on premium brands), terrible value vs alternatives on the same list, or mechanical time bomb (high-km PHEV, high-km Alfa). |

#### Red Flag Rules
- >120k km on a 2020-2022 car → CAUTION minimum
- >130k km on any non-Toyota/Lexus → NO-GO candidate
- "Corporate" / fleet trim → flag stripped spec
- PHEV with >100k km → flag battery degradation
- Alfa Romeo + >100k km → flag reliability
- 3-cylinder + >80k km → flag timing chain
- Very high discount from original → investigate why

#### Evaluation Writing Style

**CRITICAL: Every evaluation must read like advice from a car-expert friend — NOT a spec sheet.**

DO NOT write lazy evaluations like: "150HP diesel Q2 with 78k km (2020). RED FLAG: located in Sant Boi. Financed ~€19,990"
That is just restating the data columns. The user can already see the specs in the card.

DO write evaluations like: "Smallest Audi SUV but built on the Golf MQB platform — solid underneath. 35 TDI is the smart engine choice: frugal, torquey, proven. 78k km is fine for the EA288 diesel. RED FLAG: DSG can be jerky at low speeds — test in traffic. Compare to Clicars Q3 at rank 10 for more space at similar money."

Each evaluation MUST contain:
1. **Car-knowledge opinion** — what makes this specific car/engine/trim special, or not. Reference the platform it was built on, how it drives, what it cost new, what segment it sits in.
2. **Engine/drivetrain reputation** — is this engine known to be reliable? Fragile? What are the known failure points at this mileage? Use specific engine codes or names when relevant (B47, EA888, Skyactiv-X, etc.).
3. **RED FLAG with specific reasoning** — not "high mileage" but "118k km on a 2023 = 59k/yr = ex-rental, expect worn interior and tired suspension." Explain WHY the red flag matters for THIS specific car.
4. **Cross-platform comparison** — if a similar car exists on the other platform, say which is the better deal and why ("Clicars has the same UX at rank 11 for €3k less with 40% fewer km").
5. **Location** — mention only if NOT in Madrid area, and only briefly as an aside.
6. **Financed price** — one brief aside at the end if significantly lower than cash.

Rules:
- 1-2 lines max, dense with insight
- Lead with the selling point or the dealbreaker
- Never just restate HP + km + year — the card already shows that
- Be opinionated: "this is the one" or "skip it" — not "this is a car"
- Use the same voice across ALL platforms — Flexicar cars get the same depth as Clicars cars

### Step 6 — Rank & Sort
Sort all cars by: verdict weight (BARGAIN=5, TOP PICK=4, GOOD=3, CAUTION=2, NO-GO=1), then by value score (lower price + lower mileage + newer year = higher score). Assign rank 1-N.

### Step 7 — Generate Outputs
1. **CSV**: Write to `output/cars-evaluated-{YYYY-MM-DD}.csv` with columns:
   `Rank,Verdict,Make,Model,Variant,Year,Price_EUR,Original_Price_EUR,Discount_EUR,Mileage_km,Fuel,HP,Segment,Platform,Monthly_Budget_EUR,Yearly_Service_EUR,Link,Evaluation`

2. **HTML**: Read `templates/showcase.html`, replace `/*CARS_JSON*/` with the JavaScript cars array, replace `/*SEARCH_META*/` with search metadata (query, date, count, platforms). Write to `output/showcase-{YYYY-MM-DD}.html`.

3. **Financial Model build**: Rebuild the financial model app so it's ready for the showcase CTAs:
   ```bash
   cd "/Users/francochiaro/Documents/Car analysis/output/financial-model"
   npm run build
   ```

4. **Serve locally**: Start a local HTTP server (required — `file://` won't work due to CORS with ES modules):
   ```bash
   cd "/Users/francochiaro/Documents/Car analysis"
   python3 -m http.server 8080 &
   ```
   Then open: `http://localhost:8080/output/showcase-{YYYY-MM-DD}.html`

### Step 8 — Report Summary
Present to the user:
- Total cars found per platform
- Verdict distribution (X bargains, Y top picks, etc.)
- Top 5 recommendations with 1-line rationale
- Cheapest monthly cost car
- Lowest mileage car
- Best premium-per-euro car

## Cost Model Reference
The cost model is at `config/cost-model.json`. It was validated against real Spanish market data (March 2026) from:
- Insurance: Rastreator, RapidSecur, CHECK24, KIA FAQ forum, SegurosNews, MBFAQ
- Service: km77, carwow, BMW FAQ, Club Toyota C-HR, Alfistas forum, Kia FAQ
- Fuel: Spanish average fuel prices Q1 2026

Assumptions: 15,000 km/year, ~30yo driver in Madrid, todo riesgo con franquicia.

## Notes
- Clicars scraper pages through their server-rendered listing pages (12 cars/page)
- Flexicar is a Next.js SPA — the scraper uses Playwright to render pages and extract from the DOM
- Flexicar shows two prices: cash (higher, used for comparison) and financed (lower, requires their financing)
- Both scrapers output the same normalized JSON schema (see CLAUDE.md)
- If a scraper fails, continue with the other platform and note the failure

## Financial Model

Each car card in the showcase has a "Financial Model" CTA that opens a standalone React app for cashflow analysis.

### Architecture
- **Location**: `output/financial-model/` (React+Vite+Tailwind, built with Ralph)
- **Built assets**: `output/financial-model/dist/` — the showcase CTA links here
- **Serving**: Must be served over HTTP (not `file://`) due to CORS. Use `python3 -m http.server 8080` from the project root
- **Data flow**: Showcase passes car data as URL query params (make, model, price, year, mileage, fuel, hp, etc.). The full car list is base64-encoded in a `cars` param for the comparison picker.

### What It Does
- **Purchase scenario**: Monthly cashflow table (spreadsheet-style) with: down payment, ITP, gestoría, French credit installments, insurance, fuel, service, ITV, residual value at end of horizon
- **Renting scenario**: Monthly fee cashflow for comparison
- **NPV comparison**: Discounted cashflow comparison of purchase vs renting
- **Parameters panel**: All inputs are configurable (loan amount, APR, term, renting fee, time horizon, discount rate, etc.) with instant recomputation
- **Car comparison**: Pick a second car to compare financials side-by-side

### Cost Model
Uses the same rates from `config/cost-model.json` (baked into the app at build time). If the cost model is updated, rebuild:
```bash
cd output/financial-model && npm run build
```

### Modifying the Financial Model
The app was built with Ralph. To make changes:
1. Edit `output/financial-model/prd.json` — add/modify user stories
2. Run `cd output/financial-model && ./ralph.sh --tool claude 5`
3. Rebuild: `npm run build`
