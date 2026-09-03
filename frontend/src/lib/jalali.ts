export interface JalaliDateParts {
  year: number;
  month: number;
  day: number;
}

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
] as const;

export const JALALI_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"] as const;

const DAY_MS = 86_400_000;
const persianPartsFormatter = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", {
  timeZone: "UTC",
  year: "numeric",
  month: "numeric",
  day: "numeric",
});
const persianNumberFormatter = new Intl.NumberFormat("fa-IR", { useGrouping: false });

const validIsoDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value.slice(0, 10));

export function gregorianToJalali(value: string): JalaliDateParts | null {
  const iso = value.slice(0, 10);
  if (!validIsoDate(iso)) return null;
  const date = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(
    persianPartsFormatter
      .formatToParts(date)
      .filter((part) => ["year", "month", "day"].includes(part.type))
      .map((part) => [part.type, Number(part.value)]),
  );
  if (!parts.year || !parts.month || !parts.day) return null;
  return { year: parts.year, month: parts.month, day: parts.day };
}

function compareParts(left: JalaliDateParts, right: JalaliDateParts) {
  if (left.year !== right.year) return left.year - right.year;
  if (left.month !== right.month) return left.month - right.month;
  return left.day - right.day;
}

export function jalaliToGregorian(year: number, month: number, day: number): string | null {
  if (year < 1000 || year > 2000 || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const target = { year, month, day };
  let low = Math.floor(Date.UTC(year + 620, 0, 1) / DAY_MS);
  let high = Math.floor(Date.UTC(year + 622, 11, 31) / DAY_MS);

  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = new Date(middle * DAY_MS).toISOString().slice(0, 10);
    const converted = gregorianToJalali(candidate);
    if (!converted) return null;
    const comparison = compareParts(converted, target);
    if (comparison === 0) return candidate;
    if (comparison < 0) low = middle + 1;
    else high = middle - 1;
  }
  return null;
}

export function jalaliMonthLength(year: number, month: number) {
  if (month <= 6) return 31;
  if (month <= 11) return 30;
  return jalaliToGregorian(year, 12, 30) ? 30 : 29;
}

export function jalaliFirstWeekday(year: number, month: number) {
  const iso = jalaliToGregorian(year, month, 1);
  if (!iso) return 0;
  const weekday = new Date(`${iso}T12:00:00Z`).getUTCDay();
  return (weekday + 1) % 7;
}

export function formatJalaliNumeric(parts: JalaliDateParts) {
  const year = persianNumberFormatter.format(parts.year);
  const month = persianNumberFormatter.format(parts.month).padStart(2, "۰");
  const day = persianNumberFormatter.format(parts.day).padStart(2, "۰");
  return `${year}/${month}/${day}`;
}

export function persianNumber(value: number) {
  return persianNumberFormatter.format(value);
}
