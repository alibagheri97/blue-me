export interface ExpenseReceipt {
  key: string; source: "purchase" | "manual"; id: number; receipt_number: string;
  supplier_name: string | null; invoice_number: string | null; purchased_at: string;
  business_day: string; status: "posted" | "voided"; total_cost: string; matched_cost: string;
  line_count: number; item_names: string[]; created_by: string; notes: string | null;
  manual_line?: { quantity: string; unit: string; unit_cost: string } | null;
}
export interface ExpenseItem {
  item_id: number; name: string; unit: string; category: string; is_active: boolean;
  total_cost: string; quantity: string; purchases: number; first_price: string; last_price: string;
  min_price: string; max_price: string; average_price: string; change: string;
  change_percent: string | null; last_date: string;
}
export interface ExpenseLine {
  source: "purchase" | "manual"; source_id: number; line_id: number; item_id: number; item_name: string;
  quantity: string; purchase_unit: string; stock_quantity: string; stock_unit: string;
  line_total: string; allocated_cost: string; landed_total: string; unit_cost: string;
  receipt_number: string; supplier_name: string | null; invoice_number: string | null;
  purchased_at: string; business_day: string; status: string; created_by: string; notes: string | null;
  change?: string | null; change_percent?: string | null;
}
export interface ExpenseOverview {
  period: { start: string; end: string; days: number };
  kpis: { total_cost: string; purchase_cost: string; manual_cost: string; goods_cost: string; net_adjustment: string;
    posted_count: number; purchase_count: number; manual_count: number; voided_count: number; item_count: number; price_increases: number };
  daily: { date: string; cost: string; purchase: string; manual: string }[];
  categories: { name: string; cost: string }[]; suppliers: { name: string; cost: string }[];
  items: ExpenseItem[];
  receipts: { items: ExpenseReceipt[]; total: number; page: number; page_size: number };
}
export interface ExpensePrices {
  summary: ExpenseItem | null; daily: { date: string; price: string }[];
  items: ExpenseLine[]; total: number; page: number; page_size: number;
}

// Prevent spreadsheet formulas in supplier/item names while preserving UTF-8 Farsi.
export function csvCell(value: unknown): string {
  let text = String(value ?? "");
  if (/^[\s]*[=+@\-\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}
