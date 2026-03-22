import { useState, useMemo, useEffect } from "react";
import { useCarData } from "./hooks/useCarData";
import { useFinancialParams } from "./hooks/useFinancialParams";
import { computeCashflow, frenchAmortization } from "./lib/financial";
import { getBrandTier, getInsuranceMonthly, getFuelMonthly, getServiceAnnual } from "./lib/costModel";
import CashflowTable, { purchaseRows, rentingRows } from "./components/CashflowTable";
import NPVSummary from "./components/NPVSummary";
import ParametersPanel from "./components/ParametersPanel";
import CarPicker from "./components/CarPicker";
import type { CarData, FinancialParams } from "./types";

function formatNumber(n: number): string {
  return n.toLocaleString("es-ES");
}

function ParamsSummary({ params }: { params: FinancialParams }) {
  const loan = frenchAmortization(params.loanAmount, params.interestRate, params.loanTerm);
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs font-mono bg-surface border border-border rounded-lg px-4 py-3 mb-6">
      <span className="text-text-muted">Loan:</span>
      <span className="text-text-primary">€{formatNumber(params.loanAmount)} @ {params.interestRate}% · {params.loanTerm}mo · <span className="text-accent">€{formatNumber(Math.round(loan.monthlyPayment))}/mo</span></span>
      <span className="text-border">|</span>
      <span className="text-text-muted">Rent:</span>
      <span className="text-text-primary">€{formatNumber(params.rentingFee)}/mo · {params.rentingPeriod}mo</span>
      <span className="text-border">|</span>
      <span className="text-text-muted">Horizon:</span>
      <span className="text-text-primary">{Math.round(params.timeHorizon / 12)}yr ({params.timeHorizon}mo)</span>
      <span className="text-border">|</span>
      <span className="text-text-muted">NPV rate:</span>
      <span className="text-text-primary">{params.discountRate}%</span>
      <span className="text-border">|</span>
      <span className="text-text-muted">Inflation:</span>
      <span className="text-text-primary">{params.inflationRate}%</span>
      {!params.platformIncludesTaxes && (
        <>
          <span className="text-border">|</span>
          <span className="text-text-muted">ITP:</span>
          <span className="text-text-primary">{params.itpRate}%</span>
          <span className="text-text-muted">Gest:</span>
          <span className="text-text-primary">€{formatNumber(params.gestoriaFees)}</span>
        </>
      )}
      {params.platformIncludesTaxes && (
        <>
          <span className="text-border">|</span>
          <span className="text-green">Taxes included</span>
        </>
      )}
    </div>
  );
}

function CarHeader({ car, label }: { car: CarData; label?: string }) {
  const brandTier = getBrandTier(car.make);
  const insurance = getInsuranceMonthly(car.make, car.hp);
  const fuel = getFuelMonthly(car.fuel);
  const service = getServiceAnnual(car.make, car.fuel);

  return (
    <div className="flex gap-5 items-start mb-6 bg-surface rounded-lg p-5 border border-border">
      {car.image && (
        <img
          src={car.image}
          alt={`${car.make} ${car.model}`}
          className="w-48 h-32 object-cover rounded"
        />
      )}
      <div className="flex-1 min-w-0">
        {label && <div className="text-xs text-accent font-semibold mb-1">{label}</div>}
        <h1 className="text-xl font-semibold mb-1">
          {car.make} {car.model}
          {car.variant && (
            <span className="text-text-secondary font-normal ml-2 text-base">
              {car.variant}
            </span>
          )}
        </h1>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-text-secondary mt-2">
          <span>{car.year}</span>
          <span className="font-mono text-text-primary font-semibold">
            €{formatNumber(car.price)}
          </span>
          <span>{formatNumber(car.mileage)} km</span>
          <span>{car.fuel}</span>
          <span>{car.hp} HP</span>
          <span>{car.transmission}</span>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-muted mt-3">
          <span>Tier: {brandTier}</span>
          <span>Insurance: €{insurance}/mo</span>
          <span>Fuel: €{fuel}/mo</span>
          <span>Service: €{service}/yr</span>
        </div>
      </div>
    </div>
  );
}

function App() {
  const { car, allCars, insuranceMonthly, fuelMonthly, serviceAnnual } =
    useCarData();
  const { params, setParam, purchaseCashflow, rentingCashflow } = useFinancialParams(car);
  const [comparisonCar, setComparisonCar] = useState<CarData | null>(null);

  // Compute comparison car's cashflow with the same params
  const comparisonCashflow = useMemo(() => {
    if (!comparisonCar) return null;
    return computeCashflow(comparisonCar, params);
  }, [comparisonCar, params]);

  // Set page title
  useEffect(() => {
    if (car) {
      document.title = `Financial Model — ${car.make} ${car.model}`;
    } else {
      document.title = "Car Financial Model";
    }
  }, [car]);

  // Back URL from params or history.back
  const backUrl = new URLSearchParams(window.location.search).get("backUrl");

  if (!car) {
    return (
      <div className="min-h-screen bg-bg text-text-primary flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold mb-2">No car data provided</h1>
          <p className="text-text-secondary text-sm">
            Open this page from the Car Showcase or add URL params:
            <br />
            <code className="font-mono text-xs text-accent">
              ?make=BMW&model=Serie+5&variant=520dA+Touring&year=2020&price=23290&mileage=109186&fuel=Diesel&hp=190
            </code>
          </p>
          {backUrl && (
            <a href={backUrl} className="inline-block mt-4 text-sm text-accent hover:underline">
              &larr; Back to Showcase
            </a>
          )}
        </div>
      </div>
    );
  }

  const carLabel = (c: CarData) => `${c.make} ${c.model}${c.variant ? ` ${c.variant}` : ""} (${c.year})`;

  // Build NPV cars array
  const npvCars = [];
  if (purchaseCashflow) {
    npvCars.push({
      label: carLabel(car),
      purchaseNPV: purchaseCashflow.npv,
      rentingNPV: rentingCashflow.npv,
    });
  }
  if (comparisonCar && comparisonCashflow) {
    npvCars.push({
      label: carLabel(comparisonCar),
      purchaseNPV: comparisonCashflow.npv,
      rentingNPV: rentingCashflow.npv,
    });
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary p-6 print:p-2">
      <ParametersPanel
        params={params}
        setParam={setParam}
        insuranceMonthly={insuranceMonthly}
        fuelMonthly={fuelMonthly}
        serviceAnnual={serviceAnnual}
        carMake={car.make}
        carFuel={car.fuel}
        carHp={car.hp}
        carPrice={car.price}
      />

      {/* Back to Showcase */}
      <div className="mb-4 flex items-center gap-4 print:hidden">
        <button
          onClick={() => backUrl ? window.location.href = backUrl : window.history.back()}
          className="text-sm text-accent hover:underline"
        >
          &larr; Back to Showcase
        </button>
        {car.link && (
          <a
            href={car.link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-text-muted hover:text-text-secondary"
          >
            View on {car.platform || "platform"} &rarr;
          </a>
        )}
      </div>

      {/* Primary Car */}
      <CarHeader car={car} label={comparisonCar ? "Primary Car" : undefined} />

      {/* Parameters at a glance */}
      <ParamsSummary params={params} />

      {purchaseCashflow && (
        <CashflowTable data={purchaseCashflow} title="Purchase Scenario" rows={purchaseRows} />
      )}

      <CashflowTable data={rentingCashflow} title="Renting Scenario" rows={rentingRows} />

      {/* Comparison Car */}
      {comparisonCar && comparisonCashflow && (
        <>
          <CarHeader car={comparisonCar} label="Comparison Car" />
          <CashflowTable data={comparisonCashflow} title={`Purchase Scenario — ${carLabel(comparisonCar)}`} rows={purchaseRows} />
          <CashflowTable data={rentingCashflow} title={`Renting Scenario — ${carLabel(comparisonCar)}`} rows={rentingRows} />
        </>
      )}

      {/* NPV Summary */}
      {npvCars.length > 0 && (
        <NPVSummary cars={npvCars} discountRate={params.discountRate} />
      )}

      {/* Car Picker */}
      {allCars.length > 0 && (
        <CarPicker
          cars={allCars}
          primaryCar={car}
          selectedCar={comparisonCar}
          onSelect={setComparisonCar}
        />
      )}
    </div>
  );
}

export default App;
