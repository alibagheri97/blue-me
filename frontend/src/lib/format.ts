export const money = (value: string | number | null | undefined) =>
  `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(Number(value || 0))} تومان`;

export const quantity = (value: string | number | null | undefined) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 3 }).format(Number(value || 0));

export const dateTime = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
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
