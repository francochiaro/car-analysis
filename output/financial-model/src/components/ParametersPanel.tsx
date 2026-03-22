import React, { useState } from "react";
import ReactDOM from "react-dom";
import type { FinancialParams } from "../types";
import { RENTING_FEE_HEURISTIC_EXPLANATION, estimateRentingFeeWithTerm } from "../lib/costModel";

interface ParametersPanelProps {
  params: FinancialParams;
  setParam: <K extends keyof FinancialParams>(key: K, value: FinancialParams[K]) => void;
  insuranceMonthly: number;
  fuelMonthly: number;
  serviceAnnual: number;
  carMake: string;
  carFuel: string;
  carHp: number;
  carPrice: number;
}

function Tooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = React.useRef<HTMLSpanElement>(null);

  const handleEnter = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setPos({
        top: rect.bottom + 6,
        left: Math.max(8, rect.left - 240),
      });
    }
    setShow(true);
  };

  return (
    <span className="inline-flex">
      <span
        ref={ref}
        className="cursor-help text-text-muted hover:text-accent"
        onMouseEnter={handleEnter}
        onMouseLeave={() => setShow(false)}
      >
        ⓘ
      </span>
      {show &&
        ReactDOM.createPortal(
          <div
            className="w-64 p-2 bg-bg border border-border rounded text-xs text-text-secondary shadow-lg pointer-events-none"
            style={{ position: "fixed", top: pos.top, left: pos.left, zIndex: 9999 }}
          >
            {text}
          </div>,
          document.body
        )}
    </span>
  );
}

function NumericInput({
  label,
  value,
  onChange,
  step = 1,
  prefix,
  suffix,
  tooltip,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  prefix?: string;
  suffix?: string;
  tooltip?: string;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs text-text-secondary flex items-center gap-1">
        {label}
        {tooltip && <Tooltip text={tooltip} />}
      </span>
      <div className="flex items-center gap-1 mt-0.5">
        {prefix && <span className="text-xs text-text-muted">{prefix}</span>}
        <input
          type="number"
          value={value}
          step={step}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
          className={`w-full bg-bg border border-border rounded px-2 py-1 text-sm font-mono text-text-primary focus:border-accent focus:outline-none ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}
        />
        {suffix && <span className="text-xs text-text-muted">{suffix}</span>}
      </div>
    </label>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="text-xs font-semibold text-accent uppercase tracking-wide mt-4 mb-2 first:mt-0 border-b border-border pb-1">
      {title}
    </div>
  );
}

function ToggleInput({
  label,
  checked,
  onChange,
  tooltip,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  tooltip?: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent w-3.5 h-3.5"
      />
      <span className="text-xs text-text-secondary flex items-center gap-1">
        {label}
        {tooltip && <Tooltip text={tooltip} />}
      </span>
    </label>
  );
}

export default function ParametersPanel({
  params,
  setParam,
  insuranceMonthly,
  fuelMonthly,
  serviceAnnual,
  carMake,
  carFuel,
  carHp,
  carPrice,
}: ParametersPanelProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="print:hidden">
      {/* Toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed top-4 right-4 z-50 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-colors"
      >
        {open ? "✕ Close" : "⚙ Parameters"}
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-80 bg-surface border-l border-border z-50 overflow-y-auto transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="p-4 pt-14">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Financial Parameters</h2>

          <SectionHeader title="General" />
          <div className="space-y-2">
            <NumericInput
              label="Time Horizon"
              value={params.timeHorizon}
              onChange={(v) => setParam("timeHorizon", v)}
              step={1}
              suffix="mo"
              tooltip="Total analysis period. At the end, the car is sold at its depreciated residual value (purchase) or the renting contract is terminated. If the horizon doesn't align with the renting period, an early termination penalty applies."
            />
            <NumericInput
              label="Discount Rate"
              value={params.discountRate}
              onChange={(v) => setParam("discountRate", v)}
              step={0.5}
              suffix="%"
              tooltip="Annual rate to discount future cashflows to present value (NPV). Represents the opportunity cost of money — what you'd earn investing it elsewhere."
            />
            <NumericInput
              label="Inflation Rate"
              value={params.inflationRate}
              onChange={(v) => setParam("inflationRate", v)}
              step={0.5}
              suffix="%"
              tooltip="Annual inflation applied to all variable costs. Purchase: insurance, fuel, service, and ITV increase over time (loan installment is fixed). Renting: monthly fee is adjusted on each contract renewal. Does NOT affect upfront costs (M0) or residual value."
            />
            <NumericInput
              label="Annual Km"
              value={params.annualKm}
              onChange={(v) => setParam("annualKm", v)}
              step={1000}
              suffix="km"
              tooltip="Expected yearly driving distance. Impacts fuel cost (scales proportionally), residual value (high km = faster depreciation), and renting fee estimate."
            />
          </div>

          <SectionHeader title="Loan" />
          <div className="space-y-2">
            <NumericInput
              label="Loan Amount"
              value={params.loanAmount}
              onChange={(v) => setParam("loanAmount", v)}
              step={500}
              prefix="€"
              tooltip="Amount financed via bank loan. The rest (car price minus this) is paid upfront as down payment in M0."
            />
            <NumericInput
              label="Interest Rate (APR)"
              value={params.interestRate}
              onChange={(v) => setParam("interestRate", v)}
              step={0.5}
              suffix="%"
              tooltip="Annual percentage rate for the French credit. Higher rate → higher monthly installment and more total interest paid."
            />
            <NumericInput
              label="Loan Term"
              value={params.loanTerm}
              onChange={(v) => setParam("loanTerm", v)}
              step={1}
              suffix="mo"
              tooltip="Number of months to repay the loan. Longer term → lower monthly payment but more total interest."
            />
          </div>

          <SectionHeader title="Renting" />
          <div className="space-y-2">
            <NumericInput
              label="Monthly Fee"
              value={params.rentingFee}
              onChange={(v) => setParam("rentingFee", v)}
              step={25}
              prefix="€"
              tooltip={RENTING_FEE_HEURISTIC_EXPLANATION}
            />
            <NumericInput
              label="Contract Period"
              value={params.rentingPeriod}
              onChange={(v) => setParam("rentingPeriod", v)}
              step={1}
              suffix="mo"
              tooltip="Duration of each renting contract. If shorter than the time horizon, the contract auto-renews with inflation adjustment. An incomplete final period incurs an early termination penalty (~50% of remaining monthly fees)."
            />
            <button
              onClick={() => {
                const estimated = estimateRentingFeeWithTerm(
                  carPrice, carMake, carFuel, carHp,
                  params.annualKm, params.rentingPeriod
                );
                setParam("rentingFee", estimated);
              }}
              className="w-full text-xs py-1.5 px-3 rounded bg-accent/10 border border-accent/30 text-accent hover:bg-accent/20 transition-colors"
            >
              Estimate fee from car & renting params
            </button>
          </div>

          <SectionHeader title="Taxes & Fees" />
          <div className="space-y-2">
            <ToggleInput
              label="Platform includes taxes"
              checked={params.platformIncludesTaxes}
              onChange={(v) => setParam("platformIncludesTaxes", v)}
              tooltip="Clicars and Flexicar include ITP and gestoría in the listed price. Disable this for private purchases where you pay taxes separately."
            />
            <NumericInput
              label="ITP Rate"
              value={params.itpRate}
              onChange={(v) => setParam("itpRate", v)}
              step={0.5}
              suffix="%"
              disabled={params.platformIncludesTaxes}
              tooltip="Impuesto de Transmisiones Patrimoniales — transfer tax on used car purchases. Applied to the car price as an upfront cost in M0."
            />
            <NumericInput
              label="Gestoría"
              value={params.gestoriaFees}
              onChange={(v) => setParam("gestoriaFees", v)}
              step={50}
              prefix="€"
              disabled={params.platformIncludesTaxes}
              tooltip="Administrative fee for handling the ownership transfer paperwork. One-time upfront cost in M0."
            />
            <NumericInput
              label="ITV Cost"
              value={params.itvCost}
              onChange={(v) => setParam("itvCost", v)}
              step={5}
              prefix="€"
              suffix="/yr"
              tooltip="Annual vehicle inspection (Inspección Técnica de Vehículos). Required once the car is 4+ years old. Applied yearly in the cashflow."
            />
          </div>

          <SectionHeader title="Cost Model (read-only)" />
          <div className="space-y-1 text-xs text-text-muted">
            <div className="flex justify-between">
              <span>Insurance</span>
              <span className="font-mono">€{insuranceMonthly}/mo</span>
            </div>
            <div className="flex justify-between">
              <span>Fuel</span>
              <span className="font-mono">€{fuelMonthly}/mo</span>
            </div>
            <div className="flex justify-between">
              <span>Service</span>
              <span className="font-mono">€{serviceAnnual}/yr</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
