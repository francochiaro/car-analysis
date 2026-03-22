export const fuelMonthly: Record<string, number> = {
  Electric: 38,
  PHEV: 55,
  Hybrid: 84,
  "Mild Hybrid": 126,
  Diesel: 109,
  Gasoline: 136,
};

export const insuranceMonthly: Record<string, number> = {
  Toyota: 42,
  Hyundai: 42,
  Kia: 42,
  Skoda: 42,
  Volkswagen: 46,
  VW: 46,
  CUPRA: 46,
  Mazda: 46,
  Mitsubishi: 46,
  BMW: 58,
  Audi: 58,
  Volvo: 58,
  Lexus: 58,
  Tesla: 50,
  Mercedes: 67,
  "Alfa Romeo": 75,
};

export const hpSurchargeThreshold = 200;
export const hpSurchargeAmount = 8;

export const serviceAnnual: Record<string, number> = {
  Tesla: 100,
  Toyota: 250,
  Lexus: 250,
  Hyundai: 250,
  Kia: 250,
  Mazda: 300,
  Mitsubishi: 300,
  Volkswagen: 350,
  VW: 350,
  Skoda: 350,
  CUPRA: 350,
  Volvo: 350,
  BMW: 400,
  Audi: 400,
  Mercedes: 400,
  "Alfa Romeo": 400,
};

export const serviceAnnualEV: Record<string, number> = {
  Tesla: 100,
  Kia: 150,
  Hyundai: 150,
  Volkswagen: 150,
  CUPRA: 150,
  BMW: 200,
  Volvo: 200,
  Lexus: 200,
  Mercedes: 200,
};

export const premiumBrands = ["BMW", "Audi", "Volvo", "Lexus", "Mercedes"];

export function getInsuranceMonthly(make: string, hp: number): number {
  const base = insuranceMonthly[make] ?? 50;
  const surcharge = hp >= hpSurchargeThreshold ? hpSurchargeAmount : 0;
  return base + surcharge;
}

export function getFuelMonthly(fuelType: string): number {
  return fuelMonthly[fuelType] ?? 120;
}

export function getServiceAnnual(make: string, fuelType: string): number {
  if (fuelType === "Electric") {
    return serviceAnnualEV[make] ?? 150;
  }
  return serviceAnnual[make] ?? 350;
}

export function getBrandTier(make: string): "premium" | "standard" {
  return premiumBrands.includes(make) ? "premium" : "standard";
}

/**
 * Estimates a default renting monthly fee based on the car's characteristics.
 *
 * Heuristic:
 * 1. Base = 1.5% of car price (a €20k car → €300/mo base)
 * 2. Premium brand surcharge: +15% (higher insurance & service baked into renting)
 * 3. Electric/PHEV discount: -10% (lower fuel & maintenance in renting deals)
 * 4. High HP (≥200) surcharge: +€30/mo (insurance component)
 * 5. Km allowance adjustment: renting quotes assume ~15k km/yr.
 *    Below 10k → -10%, above 20k → +10%, above 30k → +20%.
 * 6. Floor: €200/mo, Cap: €800/mo
 *
 * This is an estimate — real renting quotes vary by provider, term, and km allowance.
 */
export function estimateRentingFee(
  price: number,
  make: string,
  fuelType: string,
  hp: number,
  annualKm: number = 15000
): number {
  let fee = price * 0.015;

  if (premiumBrands.includes(make)) {
    fee *= 1.15;
  }

  if (fuelType === "Electric" || fuelType === "PHEV") {
    fee *= 0.90;
  }

  if (hp >= 200) {
    fee += 30;
  }

  // Km allowance: renting prices scale linearly with mileage.
  // Base reference is 15k km/yr. Each 5k km difference adjusts fee by ~5%.
  const kmRatio = annualKm / 15000;
  fee *= 0.7 + 0.3 * kmRatio; // at 15k → ×1.0, at 5k → ×0.8, at 30k → ×1.3

  return Math.round(Math.min(800, Math.max(200, fee)));
}

/**
 * Term discount: longer renting contracts get cheaper monthly fees.
 * Based on typical Spanish renting provider pricing:
 *   12 months: +20% (short-term premium)
 *   24 months: +8%
 *   36 months: baseline (0%)
 *   48 months: -5%
 *   60 months: -10%
 *   72+ months: -12%
 * Interpolated linearly between brackets.
 */
function termMultiplier(periodMonths: number): number {
  if (periodMonths <= 12) return 1.20;
  if (periodMonths <= 24) return 1.20 - (periodMonths - 12) / 12 * 0.12; // 1.20 → 1.08
  if (periodMonths <= 36) return 1.08 - (periodMonths - 24) / 12 * 0.08; // 1.08 → 1.00
  if (periodMonths <= 48) return 1.00 - (periodMonths - 36) / 12 * 0.05; // 1.00 → 0.95
  if (periodMonths <= 60) return 0.95 - (periodMonths - 48) / 12 * 0.05; // 0.95 → 0.90
  return 0.88;
}

export function estimateRentingFeeWithTerm(
  price: number,
  make: string,
  fuelType: string,
  hp: number,
  annualKm: number = 15000,
  periodMonths: number = 48
): number {
  // Get the base estimate (at 36-month baseline)
  const base = estimateRentingFee(price, make, fuelType, hp, annualKm);
  return Math.round(Math.min(800, Math.max(200, base * termMultiplier(periodMonths))));
}

export const RENTING_FEE_HEURISTIC_EXPLANATION =
  "Estimated as ~1.5% of car price, +15% for premium brands, −10% for EV/PHEV, +€30 for ≥200HP. Km scales linearly (15k baseline; 5k → −20%, 30k → +30%). Term discount: shorter contracts cost more, longer ones less. Floor €200, cap €800.";
