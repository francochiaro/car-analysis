import { useState, useMemo } from "react";
import type { CarData } from "../types";

interface CarPickerProps {
  cars: CarData[];
  primaryCar: CarData;
  selectedCar: CarData | null;
  onSelect: (car: CarData | null) => void;
}

function formatNumber(n: number): string {
  return n.toLocaleString("es-ES");
}

function carLabel(car: CarData): string {
  return `${car.make} ${car.model}${car.variant ? ` ${car.variant}` : ""} (${car.year}) — €${formatNumber(car.price)}`;
}

function isSameCar(a: CarData, b: CarData): boolean {
  return a.make === b.make && a.model === b.model && a.variant === b.variant && a.year === b.year && a.price === b.price && a.platform === b.platform;
}

export default function CarPicker({ cars, primaryCar, selectedCar, onSelect }: CarPickerProps) {
  const [search, setSearch] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  const availableCars = useMemo(() => {
    return cars.filter((c) => !isSameCar(c, primaryCar));
  }, [cars, primaryCar]);

  const filtered = useMemo(() => {
    if (!search.trim()) return availableCars;
    const q = search.toLowerCase();
    return availableCars.filter((c) => carLabel(c).toLowerCase().includes(q));
  }, [availableCars, search]);

  if (availableCars.length === 0) return null;

  if (selectedCar) {
    return (
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <span className="text-sm text-text-secondary">Comparing with:</span>
          <span className="text-sm font-semibold text-text-primary">{carLabel(selectedCar)}</span>
          <button
            onClick={() => onSelect(null)}
            className="px-3 py-1 text-xs bg-[#ef444425] text-negative border border-negative rounded hover:bg-[#ef444440] transition-colors"
          >
            Remove comparison
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-8">
      <div className="relative max-w-xl">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full text-left px-4 py-2.5 bg-surface border border-border rounded-lg text-sm text-text-secondary hover:border-accent transition-colors"
        >
          Compare with another car ({availableCars.length} available)
        </button>

        {isOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => { setIsOpen(false); setSearch(""); }} />
            <div className="absolute top-full left-0 right-0 mt-1 z-40 bg-surface border border-border rounded-lg shadow-xl max-h-80 overflow-hidden flex flex-col">
              <div className="p-2 border-b border-border">
                <input
                  type="text"
                  placeholder="Search by make, model..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full px-3 py-1.5 bg-bg border border-border rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                  autoFocus
                />
              </div>
              <div className="overflow-y-auto">
                {filtered.length === 0 ? (
                  <div className="px-4 py-3 text-xs text-text-muted">No cars match your search</div>
                ) : (
                  filtered.map((car, i) => (
                    <button
                      key={`${car.platform}-${car.make}-${car.model}-${car.price}-${i}`}
                      onClick={() => {
                        onSelect(car);
                        setIsOpen(false);
                        setSearch("");
                      }}
                      className="w-full text-left px-4 py-2 text-sm text-text-primary hover:bg-surface-hover transition-colors border-b border-border last:border-b-0"
                    >
                      <span className="font-semibold">{car.make} {car.model}</span>
                      {car.variant && <span className="text-text-secondary ml-1">{car.variant}</span>}
                      <span className="text-text-muted ml-2">({car.year})</span>
                      <span className="font-mono ml-2 text-accent">€{formatNumber(car.price)}</span>
                      <span className="text-text-muted ml-2 text-xs">{car.fuel} · {formatNumber(car.mileage)} km</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
