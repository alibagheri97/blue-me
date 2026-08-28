export const money = (value: string | number | null | undefined) =>
  `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(Number(value || 0))} تومان`;

export const quantity = (value: string | number | null | undefined) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 3 }).format(Number(value || 0));

export const BUSINESS_TIME_ZONE = "Asia/Tehran";

const apiDate = (value: string) => {
  const hasExplicitZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasExplicitZone || !value.includes("T") ? value : `${value}Z`);
};

const isoDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: BUSINESS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export const businessDate = (offsetDays = 0) => {
  const now = new Date();
  const parts = Object.fromEntries(
    isoDateFormatter
      .formatToParts(now)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  const date = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day) + offsetDays, 12));
  return date.toISOString().slice(0, 10);
};

export const businessHour = () =>
  Number(new Intl.DateTimeFormat("en-US", { timeZone: BUSINESS_TIME_ZONE, hour: "2-digit", hourCycle: "h23" }).format(new Date()));

export const dateOnly = (
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
) => {
  if (!value) return "—";
  const plainDate = value.slice(0, 10);
  return new Intl.DateTimeFormat("fa-IR", { ...options, timeZone: BUSINESS_TIME_ZONE }).format(
    new Date(`${plainDate}T12:00:00Z`),
  );
};

export const timeOnly = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("fa-IR", {
        timeZone: BUSINESS_TIME_ZONE,
        hour: "2-digit",
        minute: "2-digit",
      }).format(apiDate(value))
    : "—";

export const dateTime = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("fa-IR", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: BUSINESS_TIME_ZONE,
      }).format(apiDate(value))
    : "—";

export const roleLabel: Record<string, string> = {
  root: "مدیر کل",
  storage_manager: "مدیر انبار",
  accounting_manager: "مدیر حسابداری",
  sales_manager: "مدیر فروش",
  kitchen_manager: "مدیر آشپزخانه",
};

export const statusLabel: Record<string, string> = {
  pending: "در انتظار",
  approved: "تأیید شده",
  rejected: "رد شده",
  confirmed: "ثبت شده",
  preparing: "در حال آماده‌سازی",
  ready: "آماده تحویل",
  completed: "تکمیل شده",
  cancelled: "لغو شده",
  fulfilled: "تأمین شده",
  automatic: "خودکار",
  manual: "دستی",
  receive: "ورود کالا",
  adjust: "اصلاح موجودی",
  waste: "ضایعات",
  sale: "مصرف فروش",
  consume: "مصرف",
  low: "کم",
  normal: "عادی",
  high: "زیاد",
  urgent: "فوری",
  card: "کارت‌خوان",
  cash: "نقدی",
  online: "آنلاین",
  other: "سایر",
};
