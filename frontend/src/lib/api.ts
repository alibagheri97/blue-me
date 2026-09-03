const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const rawMessage =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" && detail && "message" in detail
          ? String((detail as { message: unknown }).message)
          : "Something went wrong";
    super(translateError(rawMessage));
    this.status = status;
    this.detail = detail;
  }
}

const errorTranslations: Record<string, string> = {
  "Something went wrong": "خطایی رخ داد؛ دوباره تلاش کنید.",
  "Authentication required": "برای ادامه وارد حساب کاربری شوید.",
  "Invalid or expired session": "نشست شما منقضی یا نامعتبر است؛ دوباره وارد شوید.",
  "Account is unavailable": "این حساب کاربری در دسترس نیست.",
  "Insufficient permission": "شما اجازه انجام این عملیات را ندارید.",
  "Invalid username or password": "نام کاربری یا رمز عبور نادرست است.",
  "Username already exists": "این نام کاربری قبلاً ثبت شده است.",
  "Inventory item not found": "کالای انبار پیدا نشد.",
  "Category already exists": "این دسته‌بندی قبلاً ثبت شده است.",
  "SKU already exists": "این کد کالا قبلاً ثبت شده است.",
  "Category does not exist": "دسته‌بندی انتخاب‌شده وجود ندارد.",
  "Menu category not found": "دسته‌بندی منو پیدا نشد.",
  "Menu category already exists": "این دسته‌بندی منو قبلاً ثبت شده است.",
  "Menu category name already exists": "این نام برای دسته‌بندی دیگری استفاده شده است.",
  "Move menu items before deleting this category": "پیش از حذف دسته، محصولات آن را به دسته دیگری منتقل کنید.",
  "Move the items in this category before deleting it": "پیش از حذف دسته، کالاهای آن را به دسته دیگری منتقل کنید.",
  "Target stock must be greater than the reorder level when automatic shopping is enabled": "برای خرید خودکار، موجودی هدف باید بیشتر از نقطه سفارش باشد.",
  "Movement would make stock negative": "این گردش، موجودی را منفی می‌کند.",
  "Unit cost is required when receiving stock": "هنگام ورود کالا، هزینه هر واحد الزامی است.",
  "This item already has a pending price request": "برای این کالا یک درخواست قیمت در انتظار وجود دارد.",
  "Price request has already been decided": "برای این درخواست قیمت قبلاً تصمیم‌گیری شده است.",
  "Customer not found": "مشتری پیدا نشد.",
  "Order not found": "سفارش پیدا نشد یا قبلاً حذف شده است.",
  "A cancelled order cannot be edited": "سفارش لغوشده قابل ویرایش نیست.",
  "A staff meal cannot be reassigned to a customer": "غذای پرسنلی را نمی‌توان به حساب مشتری منتقل کرد.",
  "A customer with this phone number already exists": "مشتری دیگری با این شماره تلفن ثبت شده است.",
  "One or more menu items are unavailable": "یک یا چند محصول منو در دسترس نیست.",
  "Menu items need a recipe or direct inventory link": "یک یا چند محصول منو هنوز دستور پخت یا اتصال مستقیم به انبار ندارد.",
  "Inventory item for direct sale is unavailable": "کالای انتخاب‌شده برای فروش مستقیم در دسترس نیست.",
  "Remove the recipe before linking a direct inventory item": "پیش از اتصال مستقیم به انبار، دستور پخت این محصول را حذف کنید.",
  "This menu item is linked directly to inventory and cannot also have a recipe": "این محصول مستقیماً به انبار متصل است و نمی‌تواند هم‌زمان دستور پخت داشته باشد.",
  "Discount cannot be greater than subtotal": "تخفیف نمی‌تواند بیشتر از جمع سفارش باشد.",
  "This menu item already has a recipe": "برای این محصول قبلاً دستور پخت ثبت شده است.",
  "Selected menu item already has a recipe": "برای محصول انتخاب‌شده قبلاً مواد مصرفی ثبت شده است.",
  "Menu item not found": "محصول منو پیدا نشد.",
  "Recipe not found": "فرمول مواد مصرفی پیدا نشد.",
  "Recipe units must match inventory units": "واحد مواد مصرفی باید دقیقاً با واحد اصلی انبار یکسان باشد.",
  "Insufficient ingredients": "موجودی یک یا چند ماده اولیه برای این سفارش کافی نیست.",
  "Each ingredient can appear only once": "هر ماده اولیه فقط یک‌بار می‌تواند در دستور ثبت شود.",
  "One or more inventory ingredients do not exist": "یک یا چند ماده اولیه در انبار وجود ندارد.",
  "Required date cannot be in the past": "تاریخ نیاز نمی‌تواند در گذشته باشد.",
  "Request has already been decided": "برای این درخواست قبلاً تصمیم‌گیری شده است.",
  "One or more inventory items are unavailable": "یک یا چند کالای فاکتور در انبار در دسترس نیست.",
  "Purchase receipt not found": "فاکتور ورودی پیدا نشد.",
  "Purchase receipt is already voided": "این فاکتور قبلاً باطل شده است.",
  "Allocated line cost cannot be negative": "هزینه نهایی یکی از ردیف‌ها نمی‌تواند منفی باشد.",
  "Discount cannot exceed the receipt value": "تخفیف نمی‌تواند از ارزش کل فاکتور بیشتر باشد.",
  "Each inventory item can appear only once per receipt": "هر کالا فقط یک‌بار می‌تواند در هر فاکتور ثبت شود.",
  "Notification not found": "اعلان پیدا نشد.",
  "Complete your required check-in checklist first": "ابتدا همه موارد چک‌لیست ثبت ورود را تکمیل کنید.",
  "Complete the checklist after checking in": "ورود ثبت شده است؛ اکنون همه موارد چک‌لیست شروع کار را تکمیل کنید.",
  "All required check-in checklist items must be completed": "برای ثبت ورود باید همه موارد چک‌لیست را تأیید کنید.",
  "All required entry checklist items must be completed": "همه موارد چک‌لیست شروع کار باید تأیید شوند.",
  "All required checkout checklist items must be completed": "برای ثبت خروج باید همه موارد چک‌لیست پایان کار را تأیید کنید.",
  "Check in before completing the checklist": "ابتدا ورود خود را ثبت کنید.",
  "Entry checklist is already completed": "چک‌لیست شروع این شیفت قبلاً تکمیل شده است.",
  "Check-in checklist item not found": "مورد چک‌لیست ثبت ورود پیدا نشد.",
  "Checklist user not found": "کاربر انتخاب‌شده برای چک‌لیست پیدا نشد یا غیرفعال است.",
  "Checklist item already exists": "این مورد قبلاً در چک‌لیست این کاربر ثبت شده است.",
  "Staff profile is inactive": "پروفایل پرسنلی این کاربر غیرفعال است.",
  "Takeaway supply not found": "کالای بسته‌بندی بیرون‌بر پیدا نشد.",
  "Takeaway inventory item is unavailable": "کالای انتخاب‌شده برای بسته‌بندی در انبار فعال نیست.",
  "This inventory item is already a takeaway supply": "این کالا قبلاً به بسته‌بندی بیرون‌بر اضافه شده است.",
  "Dine-in orders cannot have takeaway packages": "برای سفارش سرو داخل نمی‌توان تعداد بسته بیرون‌بر ثبت کرد.",
  "Staff member not found": "پرسنل انتخاب‌شده پیدا نشد.",
  "Profit share percentage cannot exceed 100": "درصد سهم سود نمی‌تواند بیشتر از ۱۰۰ باشد.",
  "Points cannot be zero": "امتیاز نمی‌تواند صفر باشد.",
  "A payroll statement already exists for this period": "برای این پرسنل و بازه، صورت‌حساب قبلاً ثبت شده است.",
  "Payroll statement not found": "صورت‌حساب پیدا نشد.",
  "Payroll statement is already paid": "این صورت‌حساب قبلاً پرداخت شده است.",
  "Invalid payroll period": "بازه محاسبه حقوق معتبر نیست.",
  "Payroll period is too large": "بازه محاسبه حقوق بیش از حد طولانی است.",
};

function translateError(message: string): string {
  return errorTranslations[message] || message;
}

export async function api<T>(
  path: string,
  options: Omit<RequestInit, "body"> & { body?: BodyInit | object | null } = {},
): Promise<T> {
  const token = localStorage.getItem("blue-me-token");
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body === "object") {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, body: body as BodyInit });
  if (response.status === 401 && path !== "/auth/login") {
    localStorage.removeItem("blue-me-token");
    window.dispatchEvent(new Event("blue-me-session-expired"));
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail ?? payload;
    } catch {
      // Preserve the HTTP status text when the body is not JSON.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function assetUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//.test(path)) return path;
  return path;
}
