const FACTORS: Record<string, Record<string, number>> = {
  "گرم": { "گرم": 1, "کیلوگرم": 1000 },
  "میلی‌لیتر": { "میلی‌لیتر": 1, "لیتر": 1000 },
  gram: { gram: 1, kilogram: 1000 },
  g: { g: 1, kg: 1000 },
  milliliter: { milliliter: 1, liter: 1000 },
  ml: { ml: 1, l: 1000 },
};

export function unitChoices(stockUnit?: string) {
  const base = stockUnit?.trim() || "عدد";
  return Object.keys(FACTORS[base] || { [base]: 1 });
}

export function unitFactor(stockUnit: string | undefined, enteredUnit: string) {
  const base = stockUnit?.trim() || enteredUnit;
  return FACTORS[base]?.[enteredUnit] ?? (base === enteredUnit ? 1 : 0);
}

export function stockAmount(quantity: string | number, enteredUnit: string, stockUnit?: string) {
  return Number(quantity || 0) * unitFactor(stockUnit, enteredUnit);
}

export function normalizedUnitPrice(
  totalPrice: string | number,
  quantity: string | number,
  enteredUnit: string,
  stockUnit?: string,
) {
  const amount = stockAmount(quantity, enteredUnit, stockUnit);
  return amount > 0 ? Number(totalPrice || 0) / amount : 0;
}
