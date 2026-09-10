import type { Role, SectionKey, User } from "../types";

export const sectionDefinitions: Array<{
  key: SectionKey;
  path: string;
  label: string;
  description: string;
}> = [
  { key: "dashboard", path: "/", label: "نمای کلی", description: "فروش روز، وضعیت عملیات و شاخص‌های اصلی" },
  { key: "staff", path: "/staff", label: "پرسنل و غذای پرسنلی", description: "فهرست پرسنل و حساب غذای کارکنان" },
  { key: "payroll", path: "/payroll", label: "حقوق و امتیاز", description: "قرارداد، امتیاز عملکرد و محاسبه پرداخت" },
  { key: "inventory", path: "/inventory", label: "مدیریت انبار", description: "کالاها، موجودی، قیمت‌ها و گردش انبار" },
  { key: "purchases", path: "/purchases", label: "ورودی کالا", description: "ثبت خرید و ورود اقلام به موجودی" },
  { key: "menu", path: "/menu", label: "مدیریت منو", description: "محصولات فروش، دسته‌ها و مواد مصرفی" },
  { key: "pos", path: "/pos", label: "سفارش و صندوق", description: "ثبت، ویرایش، حذف و چاپ سفارش‌ها" },
  { key: "kitchen", path: "/kitchen", label: "آشپزخانه", description: "صف سفارش، دستور پخت و نیازهای روزانه" },
  { key: "reports", path: "/reports", label: "آمار و تحلیل", description: "فروش، سود، پرداخت‌ها و تحلیل عملکرد" },
  { key: "audit", path: "/audit", label: "گزارش فعالیت‌ها", description: "ردیابی دقیق رویدادها و عملکرد کاربران" },
];

export const allSectionKeys = sectionDefinitions.map((section) => section.key);

const roleDefaults: Record<Role, SectionKey[]> = {
  root: allSectionKeys,
  storage_manager: ["inventory", "purchases"],
  accounting_manager: ["dashboard", "staff", "inventory", "purchases", "menu", "pos", "reports"],
  sales_manager: ["menu"],
  kitchen_manager: ["kitchen"],
};

const rolePreferredHome: Record<Role, SectionKey[]> = {
  root: ["dashboard"],
  storage_manager: ["inventory", "purchases"],
  accounting_manager: ["dashboard", "pos", "inventory"],
  sales_manager: ["menu"],
  kitchen_manager: ["kitchen"],
};

export function defaultSectionsForRole(role: Role): SectionKey[] {
  return [...roleDefaults[role]];
}

export function effectiveSections(user: User): SectionKey[] {
  if (user.role === "root") return [...allSectionKeys];
  return Array.isArray(user.section_access)
    ? user.section_access
    : defaultSectionsForRole(user.role);
}

export function userHasSection(user: User, section: SectionKey): boolean {
  return effectiveSections(user).includes(section);
}

export function homeForUser(user: User): string {
  const access = effectiveSections(user);
  const preferred = rolePreferredHome[user.role].find((section) => access.includes(section));
  const fallback = preferred || allSectionKeys.find((section) => access.includes(section));
  return sectionDefinitions.find((section) => section.key === fallback)?.path || "/no-access";
}
