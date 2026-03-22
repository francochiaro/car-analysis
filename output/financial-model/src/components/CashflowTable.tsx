interface GenericMonth {
  month: number;
  items: Record<string, number>;
  total: number;
  cumulative: number;
}

interface GenericCashflowData {
  months: GenericMonth[];
  npv: number;
}

export interface RowDef {
  key: string;
  label: string;
  isSummary?: boolean;
}

interface CashflowTableProps {
  data: GenericCashflowData;
  title: string;
  rows: RowDef[];
}

export const purchaseRows: RowDef[] = [
  { key: "downPayment", label: "Car Purchase" },
  { key: "itp", label: "Transfer Tax (ITP)" },
  { key: "gestoria", label: "Gestoría" },
  { key: "loanPayment", label: "Loan (disbursement / installments)" },
  { key: "insurance", label: "Insurance" },
  { key: "fuel", label: "Fuel" },
  { key: "service", label: "Service" },
  { key: "itv", label: "ITV" },
  { key: "residual", label: "Residual Value" },
  { key: "total", label: "Monthly Total", isSummary: true },
  { key: "cumulative", label: "Cumulative Total", isSummary: true },
];

export const rentingRows: RowDef[] = [
  { key: "rentFee", label: "Monthly Rent Fee" },
  { key: "earlyTermination", label: "Early Termination Penalty" },
  { key: "total", label: "Monthly Total", isSummary: true },
  { key: "cumulative", label: "Cumulative Total", isSummary: true },
];

function formatCell(value: number): string {
  if (value === 0) return "—";
  const abs = Math.abs(Math.round(value));
  const formatted = abs.toLocaleString("es-ES");
  return value < 0 ? `−€${formatted}` : `€${formatted}`;
}

function cellColor(value: number): string {
  if (value === 0) return "text-text-muted";
  return value < 0 ? "text-negative" : "text-positive";
}

function getValue(key: string, month: GenericMonth): number {
  if (key === "total") return month.total;
  if (key === "cumulative") return month.cumulative;
  return month.items[key] ?? 0;
}

function getYearGroups(totalMonths: number): { label: string; span: number }[] {
  const groups: { label: string; span: number }[] = [];
  groups.push({ label: "M0", span: 1 });
  const remaining = totalMonths;
  const fullYears = Math.floor(remaining / 12);
  const leftover = remaining % 12;
  for (let y = 0; y < fullYears; y++) {
    groups.push({ label: `Y${y + 1}`, span: 12 });
  }
  if (leftover > 0) {
    groups.push({ label: `Y${fullYears + 1}`, span: leftover });
  }
  return groups;
}

export default function CashflowTable({ data, title, rows }: CashflowTableProps) {
  const months = data.months;
  const yearGroups = getYearGroups(months.length - 1);

  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold mb-3">{title}</h2>
      <div className="border border-border rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="border-collapse w-max min-w-full">
            <thead>
              <tr>
                <th className="sticky left-0 z-20 bg-surface-alt px-3 py-1.5 text-left text-xs font-medium text-text-muted border-b border-r border-border w-40 min-w-40" />
                {yearGroups.map((g, i) => (
                  <th
                    key={i}
                    colSpan={g.span}
                    className="bg-[#4f8cff33] px-1 py-1.5 text-center text-xs font-semibold text-accent border-b border-border"
                  >
                    {g.label}
                  </th>
                ))}
              </tr>
              <tr>
                <th className="sticky left-0 z-20 bg-surface px-3 py-1 text-left text-xs font-medium text-text-muted border-b border-r border-border w-40 min-w-40">
                  Item
                </th>
                {months.map((m) => (
                  <th
                    key={m.month}
                    className="bg-surface px-1 py-1 text-right text-[10px] font-mono text-text-muted border-b border-border min-w-[68px]"
                  >
                    M{m.month}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => {
                const isEven = ri % 2 === 0;
                const bgClass = row.isSummary
                  ? "bg-surface-alt"
                  : isEven
                    ? "bg-surface"
                    : "bg-bg";
                const fontWeight = row.isSummary ? "font-semibold" : "font-normal";

                return (
                  <tr key={row.key}>
                    <td
                      className={`sticky left-0 z-10 ${bgClass} px-3 py-1 text-xs ${fontWeight} text-text-secondary border-r border-border whitespace-nowrap`}
                    >
                      {row.label}
                    </td>
                    {months.map((m) => {
                      const val = getValue(row.key, m);
                      return (
                        <td
                          key={m.month}
                          className={`${bgClass} px-1 py-1 text-right text-xs font-mono ${cellColor(val)} whitespace-nowrap`}
                        >
                          {formatCell(val)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
