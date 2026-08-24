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
  "Movement would make stock negative": "این گردش، موجودی را منفی می‌کند.",
  "Unit cost is required when receiving stock": "هنگام ورود کالا، هزینه هر واحد الزامی است.",
  "This item already has a pending price request": "برای این کالا یک درخواست قیمت در انتظار وجود دارد.",
  "Price request has already been decided": "برای این درخواست قیمت قبلاً تصمیم‌گیری شده است.",
  "Customer not found": "مشتری پیدا نشد.",
  "A customer with this phone number already exists": "مشتری دیگری با این شماره تلفن ثبت شده است.",
  "One or more menu items are unavailable": "یک یا چند محصول منو در دسترس نیست.",
  "Discount cannot be greater than subtotal": "تخفیف نمی‌تواند بیشتر از جمع سفارش باشد.",
  "This menu item already has a recipe": "برای این محصول قبلاً دستور پخت ثبت شده است.",
  "Each ingredient can appear only once": "هر ماده اولیه فقط یک‌بار می‌تواند در دستور ثبت شود.",
  "One or more inventory ingredients do not exist": "یک یا چند ماده اولیه در انبار وجود ندارد.",
  "Required date cannot be in the past": "تاریخ نیاز نمی‌تواند در گذشته باشد.",
  "Request has already been decided": "برای این درخواست قبلاً تصمیم‌گیری شده است.",
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
