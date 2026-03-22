export interface CarData {
  make: string;
  model: string;
  variant: string;
  year: number;
  price: number;
  mileage: number;
  fuel: string;
  hp: number;
  transmission: string;
  platform: string;
  image: string;
  link: string;
}

export interface FinancialParams {
  loanAmount: number;
  interestRate: number;
  loanTerm: number;
  rentingFee: number;
  rentingPeriod: number;
  timeHorizon: number;
  discountRate: number;
  annualKm: number;
  itpRate: number;
  gestoriaFees: number;
  itvCost: number;
  platformIncludesTaxes: boolean;
  inflationRate: number;
}

export interface AmortizationRow {
  month: number;
  payment: number;
  principal: number;
  interest: number;
  balance: number;
}

export interface AmortizationResult {
  monthlyPayment: number;
  schedule: AmortizationRow[];
}

export interface CashflowItems {
  [key: string]: number;
  downPayment: number;
  itp: number;
  gestoria: number;
  loanPayment: number;
  insurance: number;
  fuel: number;
  service: number;
  itv: number;
  residual: number;
}

export interface CashflowMonth {
  month: number;
  items: CashflowItems;
  total: number;
  cumulative: number;
}

export interface CashflowResult {
  months: CashflowMonth[];
  npv: number;
}

export interface RentingCashflowMonth {
  month: number;
  items: { rentFee: number; earlyTermination: number };
  total: number;
  cumulative: number;
}

export interface RentingCashflowResult {
  months: RentingCashflowMonth[];
  npv: number;
}

export type BrandTier = 'premium' | 'standard';
