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

export interface StaffMember {
  id: number;
  name: string;
  phone: string | null;
  position: string | null;
  user_id: number | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  user: User | null;
  is_current_user: boolean;
  meal_count: number;
  menu_value: string;
  estimated_cost: string;
  last_meal_at: string | null;
}

export interface AttendanceStaff {
  id: number;
  name: string;
  position: string | null;
  user_id: number | null;
}

export interface AttendanceRecord {
  id: number;
  staff_member_id: number;
  checked_in_by_id: number;
  checked_out_by_id: number | null;
  checked_in_at: string;
  checked_out_at: string | null;
  duration_minutes: number;
  is_open: boolean;
  staff_member: AttendanceStaff;
  checklist_completions: AttendanceChecklistCompletion[];
}

export interface CheckInChecklistItem {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  phase: "entry" | "exit";
  sort_order: number;
  is_active: boolean;
  created_by_id: number;
  created_at: string;
  updated_at: string;
}

export interface AttendanceChecklistCompletion {
  checklist_item_id: number;
  title_snapshot: string;
  phase: "entry" | "exit";
  completed_at: string;
}

export interface AttendanceStatus {
  eligible: boolean;
  is_checked_in: boolean;
  staff_member: AttendanceStaff | null;
  current_session: AttendanceRecord | null;
  last_session: AttendanceRecord | null;
  worked_minutes_today: number;
  checklist_required: boolean;
  checklist_items: CheckInChecklistItem[];
  entry_allowed: boolean;
  entry_checklist_completed: boolean;
  checkout_checklist_required: boolean;
  checkout_checklist_items: CheckInChecklistItem[];
}

export type CompensationType = "salary" | "profit_share";

export interface PayrollStaff {
  id: number;
  name: string;
  position: string | null;
  user_id: number | null;
  is_active: boolean;
  pay_type: CompensationType;
  pay_rate: string;
  point_value: string;
  user: User | null;
}

export interface PointPolicy {
  check_in_points: number;
  entry_checklist_points: number;
  check_out_points: number;
  exit_checklist_points: number;
  work_hour_points: number;
  updated_at: string;
}

export type PointSource =
  | "manual"
  | "check_in"
  | "entry_checklist"
  | "check_out"
  | "exit_checklist"
  | "work_hours";

export interface StaffPointEntry {
  id: number;
  staff_member_id: number;
  points: number;
  source: PointSource;
  reason: string;
  attendance_record_id: number | null;
  created_by_id: number | null;
  created_by: User | null;
  created_at: string;
}

export interface PayrollCalculation {
  staff_member: PayrollStaff;
  period_start: string;
  period_end: string;
  profit_basis: string;
  base_compensation: string;
  points_total: number;
  positive_points: number;
  negative_points: number;
  point_value: string;
  points_adjustment: string;
  payable_total: string;
  worked_minutes: number;
  attendance_count: number;
  entry_checklists_completed: number;
  exit_checklists_completed: number;
}

export interface PayrollStatement {
  id: number;
  staff_member_id: number;
  period_start: string;
  period_end: string;
  pay_type: CompensationType;
  pay_rate: string;
  profit_basis: string;
  base_compensation: string;
  points_total: number;
  point_value: string;
  points_adjustment: string;
  payable_total: string;
  worked_minutes: number;
  attendance_count: number;
  entry_checklists_completed: number;
  exit_checklists_completed: number;
  status: "draft" | "paid";
  created_by_id: number;
  paid_by_id: number | null;
  created_at: string;
  paid_at: string | null;
  staff_member: PayrollStaff;
}

export interface MyPerformance {
  staff_member_id: number | null;
  eligible: boolean;
  period_start: string;
  period_end: string;
  total_points: number;
  positive_points: number;
  negative_points: number;
  worked_minutes: number;
  attendance_count: number;
  entry_checklists_completed: number;
  exit_checklists_completed: number;
}

export interface AttendanceOverview {
  date_from: string;
  date_to: string;
  present_count: number;
  check_ins_today: number;
  completed_today: number;
  worked_minutes_today: number;
  items: AttendanceRecord[];
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

export interface SystemSettings {
  kitchen_workflow_enabled: boolean;
  updated_at: string;
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
  target_stock_level: string;
  auto_reorder_enabled: boolean;
  average_cost: string;
  last_purchase_price: string;
  selling_price: string;
  purchase_quantity: string;
  purchase_unit: string;
  purchase_total_price: string;
  selling_quantity: string;
  selling_unit: string;
  selling_total_price: string;
  image_path: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type KitchenInventoryItem = Pick<
  InventoryItem,
  | "id"
  | "sku"
  | "name"
  | "category_id"
  | "category"
  | "unit"
  | "current_quantity"
  | "average_cost"
  | "image_path"
  | "description"
  | "is_active"
>;

export interface MenuItem {
  id: number;
  name: string;
  category: string;
  category_id: number | null;
  selling_price: string;
  inventory_item_id: number | null;
  stock_quantity_per_sale: string;
  description: string | null;
  image_path: string | null;
  is_active: boolean;
  calculated_cost: string;
  gross_profit: string;
  margin_percent: string;
  recipe_configured: boolean;
  is_available: boolean;
  max_available_quantity: number | null;
}

export type OrderType = "dine_in" | "takeaway";

export interface TakeawaySupply {
  id: number;
  inventory_item_id: number;
  quantity_per_package: string;
  calculated_cost: string;
  max_packages_available: number;
  inventory_item: InventoryItem;
  created_at: string;
  updated_at: string;
}

export type KitchenMenuItem = Pick<
  MenuItem,
  | "id"
  | "name"
  | "category"
  | "category_id"
  | "inventory_item_id"
  | "description"
  | "image_path"
  | "is_active"
  | "recipe_configured"
>;

export interface RecipeIngredient {
  id?: number;
  inventory_item_id: number;
  quantity: string;
  unit: string;
  inventory_item?: KitchenInventoryItem;
}

export interface Recipe {
  id: number;
  menu_item_id: number;
  yield_quantity: string;
  preparation_minutes: number;
  instructions: string;
  notes: string | null;
  menu_item: KitchenMenuItem;
  ingredients: RecipeIngredient[];
  calculated_cost: string;
}

export interface MenuCategory {
  id: number;
  name: string;
  description: string | null;
  color: string;
  sort_order: number;
  is_active: boolean;
}

export interface PurchaseLine {
  id: number;
  inventory_item_id: number;
  item_name: string;
  quantity: string;
  purchase_unit: string;
  conversion_factor: string;
  stock_quantity: string;
  stock_unit: string;
  line_total: string;
  allocated_cost: string;
  landed_total: string;
  unit_cost: string;
}

export interface PurchaseReceipt {
  id: number;
  receipt_number: string;
  supplier_name: string | null;
  invoice_number: string | null;
  purchased_at: string;
  subtotal: string;
  discount: string;
  extra_cost: string;
  total_cost: string;
  status: "posted" | "voided";
  notes: string | null;
  created_by_id: number;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
  created_by: User;
  lines: PurchaseLine[];
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface OrderItem {
  id: number;
  menu_item_id: number;
  name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  unit_cost: string;
  line_cost: string;
  notes: string | null;
}

export type PaymentMethod = "cash" | "card" | "online" | "other";

export interface Order {
  id: number;
  order_number: string;
  status: "confirmed" | "preparing" | "ready" | "completed" | "cancelled";
  customer_id: number | null;
  customer_name: string;
  staff_member_id: number | null;
  staff_name: string | null;
  is_staff_meal: boolean;
  order_type: OrderType;
  takeaway_package_count: number;
  takeaway_cost: string;
  subtotal: string;
  discount: string;
  total: string;
  payment_method: PaymentMethod;
  notes: string | null;
  created_by_id: number;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

export interface KitchenOrderItem {
  id: number;
  menu_item_id: number;
  name: string;
  quantity: number;
  notes: string | null;
}

export interface KitchenOrder {
  id: number;
  order_number: string;
  status: "confirmed" | "preparing" | "ready" | "completed" | "cancelled";
  customer_name: string;
  staff_member_id: number | null;
  staff_name: string | null;
  is_staff_meal: boolean;
  order_type: OrderType;
  takeaway_package_count: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  items: KitchenOrderItem[];
}
