import { useMemo } from "react";
import type { CarData, BrandTier } from "../types";
import {
  getBrandTier,
  getInsuranceMonthly,
  getFuelMonthly,
  getServiceAnnual,
} from "../lib/costModel";

export interface CarDataResult {
  car: CarData | null;
  allCars: CarData[];
  brandTier: BrandTier;
  insuranceMonthly: number;
  fuelMonthly: number;
  serviceAnnual: number;
}

function parseCarsFromParam(params: URLSearchParams): CarData[] {
  const encoded = params.get("cars");
  if (!encoded) return [];
  try {
    const json = atob(encoded);
    const arr = JSON.parse(json);
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((c: Record<string, unknown>) => c.make && c.model && c.price)
      .map((c: Record<string, unknown>) => ({
        make: String(c.make ?? ""),
        model: String(c.model ?? ""),
        variant: String(c.variant ?? ""),
        year: Number(c.year) || 2020,
        price: Number(c.price) || 0,
        mileage: Number(c.mileage_km ?? c.mileage ?? 0),
        fuel: String(c.fuel_type ?? c.fuel ?? "Gasoline"),
        hp: Number(c.hp) || 150,
        transmission: String(c.transmission ?? "Manual"),
        platform: String(c.platform ?? ""),
        image: String(c.image_url ?? c.image ?? ""),
        link: String(c.url ?? c.link ?? ""),
      }));
  } catch {
    return [];
  }
}

function parseCarFromParams(params: URLSearchParams): CarData | null {
  const make = params.get("make");
  const model = params.get("model");
  const price = params.get("price");

  if (!make || !model || !price) return null;

  return {
    make,
    model,
    variant: params.get("variant") ?? "",
    year: Number(params.get("year")) || 2020,
    price: Number(price) || 0,
    mileage: Number(params.get("mileage")) || 0,
    fuel: params.get("fuel") ?? "Gasoline",
    hp: Number(params.get("hp")) || 150,
    transmission: params.get("transmission") ?? "Manual",
    platform: params.get("platform") ?? "",
    image: params.get("image") ?? "",
    link: params.get("link") ?? "",
  };
}

export function useCarData(): CarDataResult {
  return useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const car = parseCarFromParams(params);
    const allCars = parseCarsFromParam(params);

    if (!car) {
      return {
        car: null,
        allCars,
        brandTier: "standard" as BrandTier,
        insuranceMonthly: 0,
        fuelMonthly: 0,
        serviceAnnual: 0,
      };
    }

    return {
      car,
      allCars,
      brandTier: getBrandTier(car.make),
      insuranceMonthly: getInsuranceMonthly(car.make, car.hp),
      fuelMonthly: getFuelMonthly(car.fuel),
      serviceAnnual: getServiceAnnual(car.make, car.fuel),
    };
  }, []);
}
