import { useState, useMemo, useCallback } from "react";
import type { CarData, FinancialParams, CashflowResult, RentingCashflowResult } from "../types";
import { computeCashflow, computeRentingCashflow } from "../lib/financial";
import { estimateRentingFee } from "../lib/costModel";

function getDefaultParams(car: CarData | null): FinancialParams {
  const price = car?.price ?? 0;
  return {
    loanAmount: Math.round(price * 0.8),
    interestRate: 7,
    loanTerm: 60,
    rentingFee: car ? estimateRentingFee(price, car.make, car.fuel, car.hp) : 350,
    rentingPeriod: 48,
    timeHorizon: 48,
    discountRate: 5,
    annualKm: 15000,
    itpRate: 4,
    gestoriaFees: 300,
    itvCost: 40,
    platformIncludesTaxes: true,
    inflationRate: 2.5,
  };
}

export interface FinancialState {
  params: FinancialParams;
  setParam: <K extends keyof FinancialParams>(key: K, value: FinancialParams[K]) => void;
  purchaseCashflow: CashflowResult | null;
  rentingCashflow: RentingCashflowResult;
}

export function useFinancialParams(car: CarData | null): FinancialState {
  const [params, setParams] = useState<FinancialParams>(() =>
    getDefaultParams(car)
  );

  const setParam = useCallback(
    <K extends keyof FinancialParams>(key: K, value: FinancialParams[K]) => {
      setParams((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  // Effective params: zero out taxes if platform includes them
  const effectiveParams = useMemo(() => {
    if (params.platformIncludesTaxes) {
      return { ...params, itpRate: 0, gestoriaFees: 0 };
    }
    return params;
  }, [params]);

  const purchaseCashflow = useMemo(() => {
    if (!car) return null;
    return computeCashflow(car, effectiveParams);
  }, [car, effectiveParams]);

  const rentingCashflow = useMemo(
    () => computeRentingCashflow(effectiveParams),
    [effectiveParams]
  );

  return { params, setParam, purchaseCashflow, rentingCashflow };
}
