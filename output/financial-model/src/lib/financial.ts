import type {
  AmortizationResult,
  BrandTier,
  CarData,
  CashflowMonth,
  CashflowResult,
  FinancialParams,
  RentingCashflowResult,
} from "../types";
import {
  getBrandTier,
  getFuelMonthly,
  getInsuranceMonthly,
  getServiceAnnual,
} from "./costModel";

const CURRENT_YEAR = 2026;

// --- French amortization (fixed installment) ---

export function frenchAmortization(
  principal: number,
  annualRate: number,
  termMonths: number
): AmortizationResult {
  if (principal <= 0 || termMonths <= 0) {
    return { monthlyPayment: 0, schedule: [] };
  }

  const monthlyRate = annualRate / 100 / 12;

  let monthlyPayment: number;
  if (monthlyRate === 0) {
    monthlyPayment = principal / termMonths;
  } else {
    monthlyPayment =
      (principal * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -termMonths));
  }

  const schedule = [];
  let balance = principal;

  for (let m = 1; m <= termMonths; m++) {
    const interest = balance * monthlyRate;
    const principalPart = monthlyPayment - interest;
    balance = Math.max(0, balance - principalPart);
    schedule.push({
      month: m,
      payment: monthlyPayment,
      principal: principalPart,
      interest,
      balance,
    });
  }

  return { monthlyPayment, schedule };
}

// --- Depreciation (declining balance) ---

const premiumRates = [0.15, 0.10, 0.08, 0.07]; // Y1-Y4, then 0.05
const standardRates = [0.20, 0.12, 0.10, 0.08]; // Y1-Y4, then 0.06

function getDepreciationRate(brandTier: BrandTier, yearIndex: number): number {
  const rates = brandTier === "premium" ? premiumRates : standardRates;
  const fallback = brandTier === "premium" ? 0.05 : 0.06;
  return yearIndex < rates.length ? rates[yearIndex] : fallback;
}

/**
 * Depreciate a car's value over time, with a mileage adjustment.
 *
 * The base depreciation uses a declining-balance curve by brand tier.
 * A mileage multiplier is then applied:
 *   - Below 10k km/year average → +5% value (low-mileage premium)
 *   - 10k–20k km/year → no adjustment (normal range)
 *   - Above 20k km/year → penalty of -1% per 5k km/year over 20k
 *
 * @param totalKmAtEnd - Total odometer reading at the end of the horizon.
 *   If omitted, no mileage adjustment is applied.
 */
export function depreciateValue(
  purchasePrice: number,
  carAgeYears: number,
  brandTier: BrandTier,
  yearsForward: number,
  totalKmAtEnd?: number
): number {
  const floor = purchasePrice * 0.1;
  let value = purchasePrice;

  for (let y = 0; y < yearsForward; y++) {
    const yearIndex = carAgeYears + y;
    const rate = getDepreciationRate(brandTier, yearIndex);
    value = value * (1 - rate);
    if (value <= floor) return floor;
  }

  // Mileage adjustment on residual value
  if (totalKmAtEnd !== undefined) {
    const totalAge = carAgeYears + yearsForward;
    const avgKmPerYear = totalAge > 0 ? totalKmAtEnd / totalAge : 0;

    let mileageMultiplier = 1.0;
    if (avgKmPerYear < 10000) {
      mileageMultiplier = 1.05; // low-mileage premium
    } else if (avgKmPerYear > 20000) {
      // -1% per 5k km/year over 20k
      const excessKmPerYear = avgKmPerYear - 20000;
      const penalty = Math.floor(excessKmPerYear / 5000) * 0.01;
      mileageMultiplier = Math.max(0.85, 1.0 - penalty); // cap at -15%
    }

    value *= mileageMultiplier;
  }

  return Math.max(value, floor);
}

// --- NPV ---

export function computeNPV(
  cashflows: number[],
  monthlyDiscountRate: number
): number {
  let npv = 0;
  for (let t = 0; t < cashflows.length; t++) {
    npv += cashflows[t] / Math.pow(1 + monthlyDiscountRate, t);
  }
  return npv;
}

// --- Reference km for cost model rates ---
const REFERENCE_ANNUAL_KM = 15000;

// --- Purchase Cashflow ---

export function computeCashflow(
  car: CarData,
  params: FinancialParams
): CashflowResult {
  const brandTier = getBrandTier(car.make);
  const carAge = CURRENT_YEAR - car.year;
  const itp = car.price * (params.itpRate / 100);
  const insurancePerMonth = getInsuranceMonthly(car.make, car.hp);

  // Scale fuel cost proportionally to km driven (cost model assumes 15k km/yr)
  const kmFactor = params.annualKm / REFERENCE_ANNUAL_KM;
  const fuelPerMonth = getFuelMonthly(car.fuel) * kmFactor;

  const servicePerYear = getServiceAnnual(car.make, car.fuel);

  const loan = frenchAmortization(
    params.loanAmount,
    params.interestRate,
    params.loanTerm
  );

  const months: CashflowMonth[] = [];
  let cumulative = 0;

  // Total km at end of horizon (current mileage + km driven during ownership)
  const yearsForward = Math.ceil(params.timeHorizon / 12);
  const totalKmAtEnd = car.mileage + params.annualKm * yearsForward;

  const monthlyInflation = params.inflationRate / 100 / 12;

  for (let m = 0; m <= params.timeHorizon; m++) {
    const isFirst = m === 0;
    const isLast = m === params.timeHorizon;

    // Inflation multiplier: compounds monthly from M0
    // Loan is fixed (locked at origination), upfront costs are M0 (no inflation).
    // Variable costs (insurance, fuel, service, ITV) inflate over time.
    const inflationMult = Math.pow(1 + monthlyInflation, m);

    // Loan: positive disbursement in M0, negative installments from M1 through loanTerm
    const loanPayment = isFirst
      ? params.loanAmount
      : m <= params.loanTerm ? -loan.monthlyPayment : 0;

    // Service: every 12 months starting at M12 (inflated)
    const service = m > 0 && m % 12 === 0 ? -(servicePerYear * inflationMult) : 0;

    // ITV: annually when car age >= 4 years (inflated)
    const carAgeAtMonth = carAge + m / 12;
    const itv =
      m > 0 && m % 12 === 0 && carAgeAtMonth >= 4 ? -(params.itvCost * inflationMult) : 0;

    // Residual value in last month, adjusted for mileage
    // Not inflated — depreciation curve already models future market value
    const residual = isLast
      ? depreciateValue(car.price, carAge, brandTier, yearsForward, totalKmAtEnd)
      : 0;

    const items = {
      downPayment: isFirst ? -car.price : 0,
      itp: isFirst ? -itp : 0,
      gestoria: isFirst ? -params.gestoriaFees : 0,
      loanPayment,
      insurance: m >= 1 ? -(insurancePerMonth * inflationMult) : 0,
      fuel: m >= 1 ? -(fuelPerMonth * inflationMult) : 0,
      service,
      itv,
      residual,
    };

    const total = Object.values(items).reduce((s, v) => s + v, 0);
    cumulative += total;

    months.push({ month: m, items, total, cumulative });
  }

  const monthlyDiscountRate = params.discountRate / 100 / 12;
  const npv = computeNPV(
    months.map((r) => r.total),
    monthlyDiscountRate
  );

  return { months, npv };
}

// --- Renting Cashflow ---

/**
 * Renting cashflow with auto-renewal and inflation.
 *
 * - If time horizon > renting period, the contract auto-renews.
 * - Each renewal period's fee is adjusted by inflation:
 *   fee_period_n = base_fee × (1 + inflationRate)^(years_elapsed)
 * - If the last period is incomplete (horizon doesn't end on a period boundary),
 *   an early termination penalty is applied in the last month.
 *
 * Early termination penalty (standard in Spanish renting):
 *   Remaining months in the contract × monthly fee × 50%.
 *   Most renting companies (ALD, Arval, LeasePlan) charge between 30-60%
 *   of remaining fees; 50% is a common middle ground.
 */
const EARLY_TERMINATION_PENALTY_RATE = 0.5;

export function computeRentingCashflow(
  params: FinancialParams
): RentingCashflowResult {
  const months = [];
  let cumulative = 0;

  const period = params.rentingPeriod;
  const baseFee = params.rentingFee;
  const annualInflation = params.inflationRate / 100;

  // Determine how many full and partial periods fit in the horizon
  const totalRentingMonths = params.timeHorizon; // renting covers the full horizon
  const lastMonthInHorizon = params.timeHorizon;

  for (let m = 0; m <= params.timeHorizon; m++) {
    let rentFee = 0;
    let earlyTermination = 0;

    if (m >= 1 && m <= totalRentingMonths) {
      // Which renewal period is this month in? (0-indexed)
      const periodIndex = Math.floor((m - 1) / period);
      // Years elapsed since start for inflation adjustment
      const yearsElapsed = periodIndex * (period / 12);
      const inflatedFee = baseFee * Math.pow(1 + annualInflation, yearsElapsed);

      rentFee = -Math.round(inflatedFee * 100) / 100;

      // Check if this is the last month AND it falls in an incomplete period
      if (m === lastMonthInHorizon) {
        const monthWithinPeriod = ((m - 1) % period) + 1; // 1-indexed position in current period
        if (monthWithinPeriod < period) {
          // Incomplete period — apply early termination penalty
          const remainingMonths = period - monthWithinPeriod;
          earlyTermination = -(remainingMonths * Math.abs(rentFee) * EARLY_TERMINATION_PENALTY_RATE);
          earlyTermination = Math.round(earlyTermination * 100) / 100;
        }
      }
    }

    const total = rentFee + earlyTermination;
    cumulative += total;
    months.push({ month: m, items: { rentFee, earlyTermination }, total, cumulative });
  }

  const monthlyDiscountRate = params.discountRate / 100 / 12;
  const npv = computeNPV(
    months.map((r) => r.total),
    monthlyDiscountRate
  );

  return { months, npv };
}
