export type Role =
  | "root"
  | "storage_manager"
  | "accounting_manager"
  | "sales_manager"
  | "kitchen_manager";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  is_active?: boolean;
  last_login_at?: string | null;
  created_at?: string;
}

export interface BrandConfig {
  app_name: string;
  business_name: string;
  tagline: string;
  primary_color: string;
  logo_url: string | null;
  locale: string;
  timezone: string;
  currency_label: string;
}

export interface Category {
  id: number;
  name: string;
  description: string | null;
  color: string;
}

export interface InventoryItem {
  id: number;
  sku: string;
  name: string;
  category_id: number | null;
  category: Category | null;
  unit: string;
  current_quantity: string;
  reorder_level: string;
  average_cost: string;
  last_purchase_price: string;
  selling_price: string;
  image_path: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MenuItem {
  id: number;
  name: string;
  category: string;
  selling_price: string;
  description: string | null;
  image_path: string | null;
  is_active: boolean;
}

export interface OrderItem {
  id: number;
  menu_item_id: number;
  name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  notes: string | null;
}

export interface Order {
  id: number;
  order_number: string;
  status: "confirmed" | "preparing" | "ready" | "completed" | "cancelled";
  customer_id: number | null;
  customer_name: string;
  subtotal: string;
  discount: string;
  total: string;
  payment_method: string;
  notes: string | null;
  created_by_id: number;
  created_at: string;
  items: OrderItem[];
}
