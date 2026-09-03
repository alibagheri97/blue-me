import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Check, ChefHat, CircleCheckBig, ClipboardCheck, ContactRound, Minus, PackageOpen, Pencil, Plus, Printer, ReceiptText, Search, Settings2, ShoppingBag, Trash2, UserPlus, Users, UtensilsCrossed, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api, assetUrl } from "../lib/api";
import { businessDate, dateTime, money, quantity, roleLabel, statusLabel } from "../lib/format";
import type { MenuItem, Order, OrderType, StaffMember, TakeawaySupply } from "../types";
import { OrderDeleteModal, OrderEditModal } from "../components/OrderManagement";

interface Customer { id: number; name: string; phone: string; notes: string | null }
interface CartLine { item: MenuItem; quantity: number; notes: string }
interface ReceiptPrintProfile {
  title: string;
  paper_width_mm: number;
  monochrome: boolean;
  high_contrast: boolean;
  font_weight: number;
  minimum_font_size_pt: number;
}
interface ReceiptDocument {
  order: Order;
  quote: { body: string; author: string };
  customer_copy: ReceiptPrintProfile & { show_prices: boolean; footer: string };
  kitchen_copy: ReceiptPrintProfile & { show_prices: boolean; highlight_notes: boolean };
}
interface ReceiptState { document: ReceiptDocument; mode: "customer" | "kitchen" }

function staffPosition(member: StaffMember) {
  return member.position || (member.user ? roleLabel[member.user.role] : "پرسنل");
}

export default function PosPage() {
  const { user, brand } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("همه");
  const [cart, setCart] = useState<Record<number, CartLine>>({});
  const [customerMode, setCustomerMode] = useState<"guest" | "existing" | "staff" | "new">("guest");
  const [customerSearch, setCustomerSearch] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [staffSearch, setStaffSearch] = useState("");
  const [staffMember, setStaffMember] = useState<StaffMember | null>(null);
  const [discount, setDiscount] = useState("0");
  const [payment, setPayment] = useState("card");
  const [orderNotes, setOrderNotes] = useState("");
  const [orderType, setOrderType] = useState<OrderType>("dine_in");
  const [takeawayPackageCount, setTakeawayPackageCount] = useState(1);
  const [activeOrder, setActiveOrder] = useState<Order | null>(null);
  const [completedOrder, setCompletedOrder] = useState<Order | null>(null);
  const [editingOrder, setEditingOrder] = useState<Order | null>(null);
  const [deletingOrder, setDeletingOrder] = useState<Order | null>(null);
  const [receipt, setReceipt] = useState<ReceiptState | null>(null);
  const [quickReceipt, setQuickReceipt] = useState<ReceiptState | null>(null);
  const [printingMode, setPrintingMode] = useState<"customer" | "kitchen" | null>(null);
  const [completionError, setCompletionError] = useState("");
  const [error, setError] = useState("");
  const [editError, setEditError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const clearQuickReceipt = useCallback(() => setQuickReceipt(null), []);

  async function openReceipt(order: Order, mode: "customer" | "kitchen") {
    try {
      const document = await api<ReceiptDocument>(`/orders/${order.id}/receipt`);
      setReceipt({ document, mode });
    } catch (reason) {
      const receiptError = reason as ApiError;
      setError(receiptError.message || "دریافت نسخه چاپی رسید انجام نشد");
    }
  }

  async function printReceiptNow(order: Order, mode: "customer" | "kitchen") {
    setCompletionError("");
    setPrintingMode(mode);
    try {
      const document = await api<ReceiptDocument>(`/orders/${order.id}/receipt`);
      setQuickReceipt({ document, mode });
    } catch (reason) {
      const receiptError = reason as ApiError;
      setCompletionError(receiptError.message || "آماده‌سازی نسخه چاپی انجام نشد");
    } finally {
      setPrintingMode(null);
    }
  }

  const menu = useQuery({ queryKey: ["menu", "pos", "visible"], queryFn: () => api<MenuItem[]>("/menu-items?active=true") });
  const customers = useQuery({ queryKey: ["customers", customerSearch], queryFn: () => api<Customer[]>(`/customers?search=${encodeURIComponent(customerSearch)}`), enabled: customerMode === "existing" });
  const staff = useQuery({ queryKey: ["staff", "pos", staffSearch], queryFn: () => api<StaffMember[]>(`/staff?active=true&search=${encodeURIComponent(staffSearch)}`), enabled: customerMode === "staff" });
  const takeawaySupplies = useQuery({ queryKey: ["takeaway-supplies"], queryFn: () => api<TakeawaySupply[]>("/takeaway-supplies") });
  const orders = useQuery({ queryKey: ["orders-today"], queryFn: () => api<Order[]>(`/orders?day=${businessDate()}&limit=100`), refetchInterval: 20_000 });
  const orderMutation = useMutation({
    mutationFn: (body: object) => api<Order>("/orders", { method: "POST", body }),
    onSuccess: (order) => {
      setError("");
      setCompletionError("");
      setCart({}); setDiscount("0"); setCustomer(null); setStaffMember(null); setCustomerMode("guest"); setOrderNotes(""); setOrderType("dine_in"); setTakeawayPackageCount(1); setCompletedOrder(order);
      client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["kitchen-orders"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["inventory"] }); client.invalidateQueries({ queryKey: ["menu", "pos"] }); client.invalidateQueries({ queryKey: ["takeaway-supplies"] });
    },
    onError: (reason) => { const err = reason as ApiError; if (typeof err.detail === "object" && err.detail && "items" in err.detail) setError(`موجودی مواد اولیه کافی نیست: ${(err.detail as {items: string[]}).items.join("، ")}`); else setError(err.message || "ثبت سفارش انجام نشد"); },
  });
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => api<Order>(`/orders/${id}`, { method: "PATCH", body }),
    onSuccess: (order) => {
      setEditError(""); setEditingOrder(null); setActiveOrder(order);
      client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["inventory"] }); client.invalidateQueries({ queryKey: ["menu", "pos"] }); client.invalidateQueries({ queryKey: ["kitchen-orders"] });
    },
    onError: (reason) => { const err = reason as ApiError; if (typeof err.detail === "object" && err.detail && "items" in err.detail) setEditError(`موجودی برای این ویرایش کافی نیست: ${(err.detail as {items: string[]}).items.join("، ")}`); else setEditError(err.message || "ویرایش سفارش انجام نشد"); },
  });
  const statusMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api<Order>(`/orders/${id}/status`, { method: "PATCH", body: { status } }), onSuccess: (order) => { setActiveOrder(order); client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["kitchen-orders"] }); }, onError: (reason) => setError((reason as ApiError).message || "تغییر وضعیت سفارش انجام نشد") });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api<void>(`/orders/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setDeletingOrder(null); setDeleteError("");
      client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["orders-history"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["reports"] }); client.invalidateQueries({ queryKey: ["inventory"] }); client.invalidateQueries({ queryKey: ["menu"] }); client.invalidateQueries({ queryKey: ["kitchen-orders"] }); client.invalidateQueries({ queryKey: ["staff"] });
    },
    onError: (reason) => setDeleteError(reason instanceof ApiError ? reason.message : "حذف سفارش انجام نشد"),
  });

  const categories = ["همه", ...new Set(menu.data?.map((item) => item.category) || [])];
  const filteredMenu = menu.data?.filter((item) => (category === "همه" || item.category === category) && (!search || item.name.toLowerCase().includes(search.toLowerCase()))) || [];
  const lines = Object.values(cart);
  const subtotal = lines.reduce((sum, line) => sum + Number(line.item.selling_price) * line.quantity, 0);
  const isStaffMeal = customerMode === "staff";
  const total = isStaffMeal ? 0 : Math.max(0, subtotal - Number(discount || 0));

  const add = (item: MenuItem) => { if (!item.is_available) return; setCart((current) => ({ ...current, [item.id]: { item, quantity: (current[item.id]?.quantity || 0) + 1, notes: current[item.id]?.notes || "" } })); };
  const changeQty = (id: number, delta: number) => setCart((current) => { const next = { ...current }; const line = next[id]; if (!line) return current; const quantity = line.quantity + delta; if (quantity <= 0) delete next[id]; else next[id] = { ...line, quantity }; return next; });
  const submitOrder = () => {
    if (!lines.length) return;
    if (isStaffMeal && !staffMember) { setError("برای غذای پرسنلی، نام پرسنل را انتخاب کنید"); return; }
    const body: Record<string, unknown> = { items: lines.map((line) => ({ menu_item_id: line.item.id, quantity: line.quantity, notes: line.notes || null })), discount: isStaffMeal ? 0 : Number(discount || 0), payment_method: isStaffMeal ? "other" : payment, notes: orderNotes || null, order_type: orderType };
    if (orderType === "takeaway") body.takeaway_package_count = takeawayPackageCount;
    if (customerMode === "existing" && customer) body.customer_id = customer.id;
    if (customerMode === "staff" && staffMember) body.staff_member_id = staffMember.id;
    if (customerMode === "new") { const name = (document.getElementById("new-customer-name") as HTMLInputElement)?.value; const phone = (document.getElementById("new-customer-phone") as HTMLInputElement)?.value; if (!name || !phone) { setError("نام و شماره تلفن مشتری جدید را وارد کنید"); return; } body.customer = { name, phone }; }
    orderMutation.mutate(body);
  };

  return (
    <div className="page-stack pos-page">
      <header className="page-heading"><div><span className="eyebrow">ثبت سریع و دقیق سفارش</span><h1>سفارش‌ها و صندوق فروش</h1><p>محصولات این صندوق مستقیماً از گزینه «نمایش در منوی فروش» در مدیریت منو خوانده می‌شوند.</p></div>{user && ["root", "accounting_manager", "sales_manager"].includes(user.role) && <Button variant="secondary" onClick={() => navigate("/menu")}><Settings2 size={18} /> مدیریت منو</Button>}</header>
      <div className="pos-layout">
        <section className="panel product-browser">
          <div className="pos-search"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجو در منوی فروش…" /></label><span className="pos-menu-source"><Check size={14} /> فقط محصولات قابل نمایش در صندوق</span></div>
          <div className="category-pills">{categories.map((name) => <button key={name} className={category === name ? "active" : ""} onClick={() => setCategory(name)}>{name}</button>)}</div>
          {menu.isLoading ? <div className="center-loader"><Spinner /></div> : filteredMenu.length ? <div className="menu-grid">{filteredMenu.map((item) => <button className={`menu-card ${!item.is_available ? "unavailable" : ""}`} disabled={!item.is_available} key={item.id} onClick={() => add(item)}>{item.image_path ? <img src={assetUrl(item.image_path)} alt="" /> : <span className="menu-placeholder"><ShoppingBag /></span>}<div><strong>{item.name}</strong><small>{item.category}</small><b>{money(item.selling_price)}</b>{!item.is_available && <em>{item.recipe_configured ? "ناموجود" : "نیازمند تنظیم مواد"}</em>}</div>{cart[item.id] && <i>{quantity(cart[item.id].quantity)}</i>}</button>)}</div> : <EmptyState icon={<ShoppingBag />} title="محصولی برای فروش نمایش داده نشده" text="در مدیریت منو، محصول را کامل تنظیم و گزینه «نمایش در منوی فروش صندوق» را فعال کنید." />}
        </section>
        <aside className="panel cart-panel">
          <header className="cart-head"><div><span className="cart-number"><ReceiptText size={18} /></span><div><h2>سفارش جاری</h2><small>{quantity(lines.reduce((n, line) => n + line.quantity, 0))} قلم</small></div></div>{lines.length > 0 && <button onClick={() => setCart({})}>پاک کردن</button>}</header>
          <section className={`order-service-selector ${orderType === "takeaway" ? "takeaway-selected" : ""}`}>
            <header><span>نحوه تحویل سفارش</span>{orderType === "takeaway" && <Badge tone="warning">کسر ملزومات بسته‌بندی</Badge>}</header>
            <div className="order-service-buttons">
              <button type="button" className={orderType === "dine_in" ? "active" : ""} onClick={() => setOrderType("dine_in")}><UtensilsCrossed /><span><strong>سرو داخل</strong><small>بدون کسر بسته‌بندی</small></span></button>
              <button type="button" className={orderType === "takeaway" ? "active" : ""} onClick={() => setOrderType("takeaway")}><PackageOpen /><span><strong>بیرون‌بر</strong><small>کسر خودکار از انبار</small></span></button>
            </div>
            {orderType === "takeaway" && <div className="takeaway-order-options">
              <div className="takeaway-package-stepper"><span><strong>تعداد بسته</strong><small>مصرف هر قلم در این تعداد ضرب می‌شود</small></span><div><button type="button" onClick={() => setTakeawayPackageCount((count) => Math.max(1, count - 1))}><Minus /></button><b>{quantity(takeawayPackageCount)}</b><button type="button" onClick={() => setTakeawayPackageCount((count) => Math.min(999, count + 1))}><Plus /></button></div></div>
              {takeawaySupplies.data?.length ? <div className="takeaway-order-supplies"><small>از انبار کم می‌شود:</small><span>{takeawaySupplies.data.map((supply) => `${quantity(Number(supply.quantity_per_package) * takeawayPackageCount)} ${supply.inventory_item.unit} ${supply.inventory_item.name}`).join(" · ")}</span></div> : !takeawaySupplies.isLoading && <div className="takeaway-order-warning"><PackageOpen /><span><strong>ملزومات بیرون‌بر تعریف نشده</strong><small>از «مدیریت منو ← بسته‌بندی بیرون‌بر» ظرف و سایر اقلام را تنظیم کنید.</small></span></div>}
            </div>}
          </section>
          <div className="customer-switch"><button className={customerMode === "guest" ? "active" : ""} onClick={() => { setCustomerMode("guest"); setCustomer(null); setStaffMember(null); }}>مهمان</button><button className={customerMode === "existing" ? "active" : ""} onClick={() => { setCustomerMode("existing"); setStaffMember(null); }}><Users size={15} /> مشتری</button><button className={customerMode === "staff" ? "active staff-mode" : ""} onClick={() => { setCustomerMode("staff"); setCustomer(null); setDiscount("0"); }}><ContactRound size={15} /> پرسنل</button><button className={customerMode === "new" ? "active" : ""} onClick={() => { setCustomerMode("new"); setCustomer(null); setStaffMember(null); }}><UserPlus size={15} /> جدید</button></div>
          {customerMode === "existing" && <div className="customer-picker"><label className="search-box"><Search size={16} /><input value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} placeholder="نام یا شماره تلفن…" /></label>{customer && <div className="selected-customer"><span>{customer.name.charAt(0)}</span><div><strong>{customer.name}</strong><small>{customer.phone}</small></div><button onClick={() => setCustomer(null)}><X size={16}/></button></div>}{!customer && customers.data?.map((person) => <button key={person.id} onClick={() => setCustomer(person)}><span>{person.name.charAt(0)}</span><div><strong>{person.name}</strong><small>{person.phone}</small></div></button>)}</div>}
          {customerMode === "staff" && <div className="customer-picker staff-picker"><div className="staff-mode-note"><ContactRound size={17} /><span><strong>غذای پرسنلی</strong><small>موجودی کم می‌شود؛ فروش و سود بدون تغییر می‌ماند.</small></span></div><label className="search-box"><Search size={16} /><input value={staffSearch} onChange={(e) => setStaffSearch(e.target.value)} placeholder="جست‌وجوی نام یا سمت پرسنل…" /></label>{staffMember && <div className="selected-customer selected-staff"><span>{staffMember.name.charAt(0)}</span><div><strong>{staffMember.name}{staffMember.is_current_user && <em>خودم</em>}</strong><small>{staffPosition(staffMember)}</small></div><button onClick={() => setStaffMember(null)}><X size={16}/></button></div>}{!staffMember && staff.data?.map((person) => <button key={person.id} onClick={() => setStaffMember(person)}><span>{person.name.charAt(0)}</span><div><strong>{person.name}{person.is_current_user && <em>خودم</em>}</strong><small>{staffPosition(person)}{person.user ? ` · @${person.user.username}` : ""}</small></div></button>)}</div>}
          {customerMode === "new" && <div className="new-customer"><input id="new-customer-name" placeholder="نام مشتری" /><input id="new-customer-phone" placeholder="شماره تلفن" inputMode="tel" /></div>}
          <div className="cart-lines">{lines.length ? lines.map((line) => <div className="cart-line" key={line.item.id}><div className="line-top"><div><strong>{line.item.name}</strong><small>هر عدد {money(line.item.selling_price)}</small></div><strong>{money(Number(line.item.selling_price) * line.quantity)}</strong></div><div className="line-controls"><button onClick={() => changeQty(line.item.id, -1)}>{line.quantity === 1 ? <Trash2 size={15} /> : <Minus size={15} />}</button><span>{quantity(line.quantity)}</span><button onClick={() => changeQty(line.item.id, 1)}><Plus size={15} /></button><input value={line.notes} onChange={(e) => setCart((current) => ({ ...current, [line.item.id]: { ...line, notes: e.target.value } }))} placeholder="توضیح برای آشپزخانه…" /></div></div>) : <EmptyState icon={<ShoppingBag />} title="سبد سفارش خالی است" text="برای افزودن، یک محصول از منو انتخاب کنید." />}</div>
          <div className={`cart-options ${isStaffMeal ? "staff-cart-options" : ""}`}>{isStaffMeal ? <div className="staff-no-payment"><BadgeCheck size={18} /><span><strong>بدون دریافت وجه</strong><small>ارزش منو فقط در حساب داخلی پرسنل نگهداری می‌شود.</small></span></div> : <><label><span>تخفیف</span><input value={discount} onChange={(e) => setDiscount(e.target.value)} type="number" min="0" step="0.01" /></label><label><span>روش پرداخت</span><select value={payment} onChange={(e) => setPayment(e.target.value)}><option value="card">انتقال به کارت</option><option value="cash">نقدی</option><option value="online">آنلاین</option><option value="other">سایر</option></select></label></>}<input value={orderNotes} onChange={(e) => setOrderNotes(e.target.value)} placeholder={isStaffMeal ? "توضیح غذای پرسنلی (اختیاری)" : "توضیح کلی سفارش (اختیاری)"} /></div>
          <div className={`cart-totals ${isStaffMeal ? "staff-cart-totals" : ""}`}><span><small>{isStaffMeal ? "ارزش منو" : "جمع اقلام"}</small><strong>{money(subtotal)}</strong></span>{!isStaffMeal && <span><small>تخفیف</small><strong>− {money(discount)}</strong></span>}<span className="grand-total"><small>{isStaffMeal ? "قابل پرداخت" : "مبلغ نهایی"}</small><strong>{isStaffMeal ? "بدون دریافت وجه" : money(total)}</strong></span></div>
          {error && <div className="form-error">{error}</div>}
          <Button className={`place-order ${isStaffMeal ? "staff-place-order" : ""}`} disabled={!lines.length || orderMutation.isPending || (isStaffMeal && !staffMember)} onClick={submitOrder}>{orderMutation.isPending ? "در حال ثبت سفارش…" : isStaffMeal ? <><ContactRound size={19} /> ثبت غذای پرسنلی · بدون دریافت</> : <><Check size={19} /> ثبت سفارش · {money(total)}</>}</Button>
        </aside>
      </div>

      <section className="panel orders-today"><header className="panel-header"><div><h2>سفارش‌های امروز</h2><p>هر سفارش را از ثبت تا تکمیل دنبال کنید.</p></div></header>{orders.data?.length ? <div className="order-board">{orders.data.map((order) => <button key={order.id} className={`order-ticket ${order.is_staff_meal ? "staff-order-ticket" : ""} ${order.order_type === "takeaway" ? "takeaway-order-ticket" : ""}`} onClick={() => setActiveOrder(order)}><div><strong>{order.order_number}</strong><span className="order-ticket-badges">{order.order_type === "takeaway" && <Badge tone="warning"><PackageOpen size={13} /> بیرون‌بر · {quantity(order.takeaway_package_count)} بسته</Badge>}{order.is_staff_meal && <Badge tone="violet">پرسنلی</Badge>}<Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></span></div><h3>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</h3><p>{order.items.map((item) => `${quantity(item.quantity)}× ${item.name}`).join(" · ")}</p><footer><span>{dateTime(order.created_at)}</span><strong>{order.is_staff_meal ? "بدون دریافت" : money(order.total)}</strong></footer></button>)}</div> : <EmptyState icon={<ClipboardCheck />} title="امروز سفارشی ثبت نشده" text="سفارش‌های جدید به‌صورت زنده اینجا نمایش داده می‌شوند." />}</section>

      <OrderCompleteModal order={completedOrder} printingMode={printingMode} error={completionError} print={(mode) => completedOrder && void printReceiptNow(completedOrder, mode)} close={() => { setCompletedOrder(null); setCompletionError(""); setQuickReceipt(null); }} />
      <OrderModal order={activeOrder} close={() => setActiveOrder(null)} print={(mode) => activeOrder && void openReceipt(activeOrder, mode)} changeStatus={(status) => activeOrder && statusMutation.mutate({ id: activeOrder.id, status })} edit={() => { if (activeOrder) { setEditError(""); setEditingOrder(activeOrder); setActiveOrder(null); } }} remove={() => { if (activeOrder) { setDeleteError(""); setDeletingOrder(activeOrder); setActiveOrder(null); } }} />
      {editingOrder && <OrderEditModal key={editingOrder.id} order={editingOrder} menu={menu.data || []} close={() => { setEditingOrder(null); setEditError(""); }} save={(body) => editMutation.mutate({ id: editingOrder.id, body })} pending={editMutation.isPending} error={editError} />}
      <OrderDeleteModal order={deletingOrder} close={() => { setDeletingOrder(null); setDeleteError(""); }} confirm={() => deletingOrder && deleteMutation.mutate(deletingOrder.id)} pending={deleteMutation.isPending} error={deleteError} />
      <ReceiptModal receipt={receipt} brand={brand} close={() => setReceipt(null)} />
      <AutoPrintReceipt receipt={quickReceipt} brand={brand} clear={clearQuickReceipt} />
    </div>
  );
}

function OrderCompleteModal({ order, printingMode, error, print, close }: { order: Order | null; printingMode: "customer" | "kitchen" | null; error: string; print: (mode: "customer" | "kitchen") => void; close: () => void }) {
  if (!order) return null;
  const sentToKitchen = ["confirmed", "preparing", "ready"].includes(order.status);
  return <Modal open title="سفارش با موفقیت ثبت شد" onClose={close}>
    <div className="order-complete-step">
      <div className="order-complete-icon"><CircleCheckBig /></div>
      <div className="order-complete-heading"><span>شماره سفارش</span><strong>{order.order_number}</strong><small>{order.customer_name === "Guest" ? "مهمان" : order.customer_name} · {order.is_staff_meal ? "بدون دریافت وجه" : money(order.total)}</small>{order.order_type === "takeaway" && <Badge tone="warning"><PackageOpen size={14} /> بیرون‌بر · {quantity(order.takeaway_package_count)} بسته</Badge>}</div>
      <div className={`order-workflow-result ${sentToKitchen ? "sent-to-kitchen" : "completed-directly"}`}><ChefHat /><span><strong>{sentToKitchen ? "به آشپزخانه ارسال شد" : "سفارش تکمیل شد"}</strong><small>{sentToKitchen ? "حالت آشپزخانه روشن است و سفارش اکنون در صف آماده‌سازی قرار دارد." : "حالت آشپزخانه خاموش است؛ سفارش بدون مراحل سه‌گانه با موفقیت تکمیل شد."}</small></span></div>
      <div className="order-complete-actions">
        <Button variant="secondary" disabled={printingMode !== null} onClick={() => print("customer")}><Printer size={22} /><span><strong>{printingMode === "customer" ? "در حال آماده‌سازی…" : order.is_staff_meal ? "چاپ برگه پرسنلی" : "چاپ رسید مشتری"}</strong><small>چاپ مستقیم، بدون اسکرول</small></span></Button>
        <Button variant="secondary" disabled={printingMode !== null} onClick={() => print("kitchen")}><ChefHat size={22} /><span><strong>{printingMode === "kitchen" ? "در حال آماده‌سازی…" : "چاپ فیش آشپزخانه"}</strong><small>نسخه خوانا برای آماده‌سازی</small></span></Button>
      </div>
      {error && <div className="form-error">{error}</div>}
      <Button className="order-complete-done" disabled={printingMode !== null} onClick={close}><Check size={19} /> تمام</Button>
    </div>
  </Modal>;
}

function OrderModal({ order, close, print, changeStatus, edit, remove }: { order: Order | null; close: () => void; print: (mode: "customer" | "kitchen") => void; changeStatus: (status: string) => void; edit: () => void; remove: () => void }) {
  if (!order) return null;
  const next: Record<string, { label: string; value: string } | undefined> = { confirmed: { label: "شروع آماده‌سازی", value: "preparing" }, preparing: { label: "اعلام آماده تحویل", value: "ready" }, ready: { label: "تکمیل سفارش", value: "completed" } };
  return <Modal open title={order.order_number} onClose={close}><div className="order-detail-head"><div><small>{order.is_staff_meal ? "پرسنل" : "مشتری"}</small><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong><span>{dateTime(order.created_at)}</span></div><div className="order-detail-badges">{order.order_type === "takeaway" && <Badge tone="warning"><PackageOpen size={13} /> بیرون‌بر · {quantity(order.takeaway_package_count)} بسته</Badge>}{order.is_staff_meal && <Badge tone="violet">غذای پرسنلی</Badge>}<Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></div></div><div className="order-detail-lines">{order.items.map((line) => <div key={line.id}><span>{quantity(line.quantity)} × {line.name}{line.notes && <small>{line.notes}</small>}</span><strong>{order.is_staff_meal ? quantity(line.quantity) : money(line.line_total)}</strong></div>)}</div><div className={`order-detail-total ${order.is_staff_meal ? "staff-order-total" : ""}`}><span>{order.is_staff_meal ? "نوع ثبت" : "مبلغ نهایی"}</span><strong>{order.is_staff_meal ? "مصرف داخلی · بدون دریافت وجه" : money(order.total)}</strong></div>{order.status !== "cancelled" && <Button variant="secondary" className="full-button order-edit-trigger" onClick={edit}><Pencil size={17} /> ویرایش اقلام و اطلاعات سفارش</Button>}<div className="receipt-actions"><Button variant="secondary" onClick={() => print("kitchen")}><ChefHat size={17} /> فیش آشپزخانه</Button><Button variant="secondary" onClick={() => print("customer")}><Printer size={17} /> {order.is_staff_meal ? "برگه پرسنلی" : "رسید مشتری"}</Button></div>{next[order.status] && <Button className="full-button" onClick={() => changeStatus(next[order.status]!.value)}>{next[order.status]!.label}</Button>}<Button variant="danger" className="full-button order-delete-trigger" onClick={remove}><Trash2 size={17} /> حذف کنترل‌شده سفارش</Button></Modal>;
}

function ReceiptContent({ receipt, brand }: { receipt: ReceiptState; brand: { business_name: string; logo_url: string | null } }) {
  const { document, mode } = receipt;
  const { order, quote } = document;
  const showPrices = mode === "customer" && document.customer_copy.show_prices;
  return <div className={`receipt receipt-mode-${mode}`} id="printable-receipt" dir="rtl">
      <header className="receipt-header">
        {brand.logo_url && <img src={brand.logo_url} alt="" />}
        <span className="receipt-copy-label">{mode === "kitchen" ? "فیش آماده‌سازی" : order.is_staff_meal ? "مصرف داخلی" : "شاورماچی"}</span>
        <h2>{mode === "kitchen" ? "آشپزخانه" : order.is_staff_meal ? "غذای پرسنلی" : brand.business_name}</h2>
        <div className="receipt-order-number"><small>شماره سفارش</small><strong>{order.order_number}</strong></div>
        <div className={`receipt-service-type ${order.order_type === "takeaway" ? "is-takeaway" : "is-dine-in"}`}>
          {order.order_type === "takeaway" ? <PackageOpen /> : <UtensilsCrossed />}
          <span><small>نوع تحویل</small><strong>{order.order_type === "takeaway" ? `بیرون‌بر · ${quantity(order.takeaway_package_count)} بسته` : "سرو داخل"}</strong></span>
        </div>
        <p>{dateTime(order.created_at)}</p>
      </header>
      <div className="receipt-customer"><span>{order.is_staff_meal ? "پرسنل" : "مشتری"}</span><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong></div>
      {showPrices && <div className="receipt-columns"><span>شرح سفارش</span><strong>مبلغ</strong></div>}
      <div className="receipt-lines">{order.items.map((line) => <div key={line.id}><span className="receipt-line-main"><b>{line.name}</b>{mode === "customer" && <small>{quantity(line.quantity)} عدد{showPrices ? ` × ${money(line.unit_price)}` : ""}</small>}{mode === "kitchen" && <small className="kitchen-quantity">تعداد: {quantity(line.quantity)}</small>}{line.notes && <em>توضیح مهم: {line.notes}</em>}</span>{showPrices && <strong>{money(line.line_total)}</strong>}</div>)}</div>
      {showPrices && <div className="receipt-summary"><span>جمع اقلام <b>{money(order.subtotal)}</b></span><span>تخفیف <b>{money(order.discount)}</b></span><span className="receipt-grand-total">مبلغ نهایی <b>{money(order.total)}</b></span><small>روش پرداخت: {statusLabel[order.payment_method]}</small></div>}
      {mode === "customer" && order.is_staff_meal && <div className="staff-receipt-note"><strong>بدون دریافت وجه</strong><span>مصرف داخلی پرسنل · خارج از فروش، درآمد و سود</span></div>}
      {mode === "kitchen" && order.notes && <div className="kitchen-order-note"><span>توضیح کلی سفارش</span><strong>{order.notes}</strong></div>}
      <figure className="receipt-quote">
        <figcaption>یک جمله برای امروز</figcaption>
        <blockquote>«{quote.body}»</blockquote>
        <cite>— {quote.author}</cite>
      </figure>
      <footer><strong>{mode === "customer" ? document.customer_copy.footer : "با دقت آماده و کنترل شود"}</strong><span>{mode === "customer" ? order.is_staff_meal ? "ثبت‌شده در حساب پرسنل" : "به امید دیدار دوباره" : "کنترل نهایی پیش از تحویل"}</span><small>{order.order_number}</small></footer>
    </div>;
}

function ReceiptModal({ receipt, brand, close }: { receipt: ReceiptState | null; brand: { business_name: string; logo_url: string | null }; close: () => void }) {
  if (!receipt) return null;
  const profile = receipt.mode === "kitchen" ? receipt.document.kitchen_copy : receipt.document.customer_copy;
  return <Modal open title={profile.title} onClose={close}>
    <ReceiptContent receipt={receipt} brand={brand} />
    <div className="receipt-print-note">چاپ حرفه‌ای ۸۰ میلی‌متری · فونت فارسی فوق‌پررنگ · کنتراست خالص سیاه‌وسفید</div>
    <Button className="full-button print-trigger" onClick={() => window.print()}><Printer size={18} /> چاپ {profile.title}</Button>
  </Modal>;
}

function AutoPrintReceipt({ receipt, brand, clear }: { receipt: ReceiptState | null; brand: { business_name: string; logo_url: string | null }; clear: () => void }) {
  useEffect(() => {
    if (!receipt) return;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clear();
    };
    const printTimer = window.setTimeout(() => window.print(), 80);
    const fallbackTimer = window.setTimeout(finish, 120_000);
    window.addEventListener("afterprint", finish);
    return () => {
      window.clearTimeout(printTimer);
      window.clearTimeout(fallbackTimer);
      window.removeEventListener("afterprint", finish);
    };
  }, [receipt, clear]);

  if (!receipt) return null;
  return <div className="auto-print-receipt" aria-hidden="true"><ReceiptContent receipt={receipt} brand={brand} /></div>;
}
