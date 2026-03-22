interface CarNPV {
  label: string;
  purchaseNPV: number;
  rentingNPV: number;
}

interface NPVSummaryProps {
  cars: CarNPV[];
  discountRate: number;
}

function formatEuro(n: number): string {
  const abs = Math.abs(Math.round(n));
  const formatted = abs.toLocaleString("es-ES");
  return n < 0 ? `−€${formatted}` : `€${formatted}`;
}

function DeltaCard({ delta, purchaseWins }: { delta: number; purchaseWins: boolean }) {
  const deltaLabel = purchaseWins ? "Purchase is cheaper" : "Renting is cheaper";
  return (
    <div className={`rounded-lg border p-4 ${purchaseWins ? "bg-[#10b98115] border-positive" : "bg-[#ef444415] border-negative"}`}>
      <div className="text-xs text-text-muted mb-1">Delta</div>
      <div className={`font-mono text-lg font-semibold ${purchaseWins ? "text-positive" : "text-negative"}`}>
        {formatEuro(Math.abs(delta))}
      </div>
      <div className={`text-xs mt-1 ${purchaseWins ? "text-positive" : "text-negative"}`}>
        {deltaLabel}
      </div>
    </div>
  );
}

function SingleCarRow({ car }: { car: CarNPV }) {
  const delta = car.purchaseNPV - car.rentingNPV;
  const purchaseWins = delta > 0;

  return (
    <div className="grid grid-cols-3 gap-4 mb-3">
      <div className="bg-surface rounded-lg border border-border p-4">
        <div className="text-xs text-text-muted mb-1">Purchase NPV</div>
        <div className={`font-mono text-lg font-semibold ${car.purchaseNPV < 0 ? "text-negative" : "text-positive"}`}>
          {formatEuro(car.purchaseNPV)}
        </div>
      </div>
      <div className="bg-surface rounded-lg border border-border p-4">
        <div className="text-xs text-text-muted mb-1">Renting NPV</div>
        <div className={`font-mono text-lg font-semibold ${car.rentingNPV < 0 ? "text-negative" : "text-positive"}`}>
          {formatEuro(car.rentingNPV)}
        </div>
      </div>
      <DeltaCard delta={delta} purchaseWins={purchaseWins} />
    </div>
  );
}

export default function NPVSummary({ cars, discountRate }: NPVSummaryProps) {
  const isComparison = cars.length > 1;

  if (!isComparison) {
    return (
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-3">NPV Comparison</h2>
        <SingleCarRow car={cars[0]} />
        <p className="text-xs text-text-muted">
          NPV compares the total cost of each option in today's money, using a {discountRate}% annual discount rate.
        </p>
      </div>
    );
  }

  // Comparison mode — determine which car is the better purchase deal
  const car1 = cars[0];
  const car2 = cars[1];
  const purchaseBetter = car1.purchaseNPV > car2.purchaseNPV ? car1.label : car2.label;
  const purchaseDiff = Math.abs(car1.purchaseNPV - car2.purchaseNPV);

  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold mb-3">NPV Comparison</h2>

      {cars.map((car) => (
        <div key={car.label} className="mb-4">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">{car.label}</h3>
          <SingleCarRow car={car} />
        </div>
      ))}

      {/* Cross-car comparison */}
      <div className="bg-[#4f8cff15] border border-accent rounded-lg p-4 mb-3">
        <div className="text-xs text-text-muted mb-1">Best Purchase Deal</div>
        <div className="font-mono text-lg font-semibold text-accent">{purchaseBetter}</div>
        <div className="text-xs text-text-secondary mt-1">
          Saves {formatEuro(purchaseDiff)} in present value over the alternative
        </div>
      </div>

      <p className="text-xs text-text-muted">
        NPV compares the total cost of each option in today's money, using a {discountRate}% annual discount rate.
      </p>
    </div>
  );
}
