# Ralph Agent Instructions — Car Financial Model

You are an autonomous coding agent building a car financial model tool (React+Vite+Tailwind+TypeScript).

## Your Task

1. Read the PRD at `prd.json` (in this directory)
2. Read `progress.txt` if it exists (check Codebase Patterns section first)
3. Pick the **highest priority** user story where `passes: false`
4. Implement that single user story
5. Ensure the app compiles: run `npm run build` to verify (zero errors required)
6. Update `prd.json` to set `passes: true` for the completed story
7. Append your progress to `progress.txt`

## Design Direction

This is a **financial spreadsheet tool**, NOT a pretty dashboard. Think Bloomberg terminal meets Google Sheets.

**Color palette (dark theme matching the car showcase):**
- Background: #0f1523
- Card/surface: #1a2236
- Card hover: #1f2a42
- Surface: #232d45
- Text primary: #f1f3f7
- Text secondary: #8b95a8
- Text muted: #5a6478
- Border: #2a3550
- Accent: #4f8cff
- Green (positive): #10b981
- Red (negative): #ef4444

**Typography:** System fonts (-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Roboto, sans-serif). Monospace for all financial numbers (font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace).

**Layout:** Desktop-first. The cashflow table is a dense spreadsheet — compact cells, right-aligned numbers, horizontal scroll. NOT mobile-first.

## Key Technical Decisions

- **Pure calculation functions** in src/lib/financial.ts — no React, no side effects, easily testable
- **Cost model data** baked into src/lib/costModel.ts (from the Spanish market data below)
- **URL params** for car data ingestion — the showcase HTML will link here with query params
- **useMemo** for cashflow recomputation — recalculate only when params or car data change
- **No external charting library** — this is a spreadsheet, not a chart dashboard
- **No React Router** — single page app, no navigation needed

## Spanish Cost Model Data

Bake this into src/lib/costModel.ts:

```typescript
export const fuelMonthly: Record<string, number> = {
  Electric: 38, PHEV: 55, Hybrid: 84, "Mild Hybrid": 126, Diesel: 109, Gasoline: 136
};

export const insuranceMonthly: Record<string, number> = {
  Toyota: 42, Hyundai: 42, Kia: 42, Skoda: 42,
  Volkswagen: 46, VW: 46, CUPRA: 46, Mazda: 46, Mitsubishi: 46,
  BMW: 58, Audi: 58, Volvo: 58, Lexus: 58, Tesla: 50,
  Mercedes: 67, "Alfa Romeo": 75
};
export const hpSurchargeThreshold = 200;
export const hpSurchargeAmount = 8;

export const serviceAnnual: Record<string, number> = {
  Tesla: 100, Toyota: 250, Lexus: 250, Hyundai: 250, Kia: 250,
  Mazda: 300, Mitsubishi: 300,
  Volkswagen: 350, VW: 350, Skoda: 350, CUPRA: 350, Volvo: 350,
  BMW: 400, Audi: 400, Mercedes: 400, "Alfa Romeo": 400
};

export const serviceAnnualEV: Record<string, number> = {
  Tesla: 100, Kia: 150, Hyundai: 150, Volkswagen: 150, CUPRA: 150,
  BMW: 200, Volvo: 200, Lexus: 200, Mercedes: 200
};

export const premiumBrands = ["BMW", "Audi", "Volvo", "Lexus", "Mercedes"];
```

## Financial Formulas

**French amortization (fixed installment):**
```
monthlyRate = annualRate / 100 / 12
payment = principal * monthlyRate / (1 - (1 + monthlyRate) ^ -termMonths)
```

**Depreciation (declining balance):**
- Premium: -15% Y1, -10% Y2, -8% Y3, -7% Y4, -5% Y5+
- Standard: -20% Y1, -12% Y2, -10% Y3, -8% Y4, -6% Y5+
- Floor: 10% of original purchase price
- IMPORTANT: account for the car's current age. A 2020 car bought in 2026 has already depreciated 6 years from its original new price. But we only know the CURRENT purchase price, so depreciate forward from the purchase price using the rates for years (currentAge+1), (currentAge+2), etc.

**NPV:**
```
NPV = Σ cashflow[t] / (1 + monthlyDiscountRate) ^ t
monthlyDiscountRate = annualDiscountRate / 100 / 12
```

## Progress Report Format

APPEND to progress.txt:
```
## [Date/Time] - Story [ID]: [Title]
- What was implemented
- Files created/changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Useful context
---
```

## Quality Requirements

- `npm run build` must pass with ZERO errors
- No TypeScript errors
- All financial calculations must be in pure functions (src/lib/financial.ts)
- Numbers must be formatted correctly: € symbol, thousands separator (.), no decimals for integers
- Negative values displayed in red, positive in green

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.
If ALL complete: reply with <promise>COMPLETE</promise>
If stories remain: end your response normally.

## Important Reminders

- Work on ONE story per iteration
- The cashflow table is the hero — it should look like a financial spreadsheet
- Pure functions first, React components second
- No external dependencies beyond React, Tailwind, and what Vite provides
- Desktop-first layout (1200px+ viewport)
