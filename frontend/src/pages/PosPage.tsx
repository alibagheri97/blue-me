import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChefHat, ClipboardCheck, Minus, Plus, Printer, ReceiptText, Search, Settings2, ShoppingBag, Trash2, UserPlus, Users, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api, assetUrl } from "../lib/api";
import { dateTime, money, quantity, statusLabel } from "../lib/format";
import type { MenuItem, Order } from "../types";

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

export default function PosPage() {
  const { user, brand } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("همه");
  const [cart, setCart] = useState<Record<number, CartLine>>({});
  const [customerMode, setCustomerMode] = useState<"guest" | "existing" | "new">("guest");
  const [customerSearch, setCustomerSearch] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [discount, setDiscount] = useState("0");
  const [payment, setPayment] = useState("card");
  const [orderNotes, setOrderNotes] = useState("");
  const [activeOrder, setActiveOrder] = useState<Order | null>(null);
  const [receipt, setReceipt] = useState<ReceiptState | null>(null);
  const [error, setError] = useState("");

  async function openReceipt(order: Order, mode: "customer" | "kitchen") {
    try {
      const document = await api<ReceiptDocument>(`/orders/${order.id}/receipt`);
      setReceipt({ document, mode });
    } catch (reason) {
      const receiptError = reason as ApiError;
      setError(receiptError.message || "دریافت نسخه چاپی رسید انجام نشد");
    }
  }

  const menu = useQuery({ queryKey: ["menu", "pos", "visible"], queryFn: () => api<MenuItem[]>("/menu-items?active=true") });
  const customers = useQuery({ queryKey: ["customers", customerSearch], queryFn: () => api<Customer[]>(`/customers?search=${encodeURIComponent(customerSearch)}`), enabled: customerMode === "existing" });
  const orders = useQuery({ queryKey: ["orders-today"], queryFn: () => api<Order[]>(`/orders?day=${new Date().toISOString().slice(0, 10)}&limit=100`), refetchInterval: 20_000 });
  const orderMutation = useMutation({
    mutationFn: (body: object) => api<Order>("/orders", { method: "POST", body }),
    onSuccess: (order) => {
      setError("");
      setCart({}); setDiscount("0"); setCustomer(null); setCustomerMode("guest"); setOrderNotes(""); setActiveOrder(order); void openReceipt(order, "customer");
      client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["inventory"] }); client.invalidateQueries({ queryKey: ["menu", "pos"] });
    },
    onError: (reason) => { const err = reason as ApiError; if (typeof err.detail === "object" && err.detail && "items" in err.detail) setError(`موجودی مواد اولیه کافی نیست: ${(err.detail as {items: string[]}).items.join("، ")}`); else setError(err.message || "ثبت سفارش انجام نشد"); },
  });
  const statusMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api<Order>(`/orders/${id}/status`, { method: "PATCH", body: { status } }), onSuccess: () => client.invalidateQueries({ queryKey: ["orders-today"] }) });

  const categories = ["همه", ...new Set(menu.data?.map((item) => item.category) || [])];
  const filteredMenu = menu.data?.filter((item) => (category === "همه" || item.category === category) && (!search || item.name.toLowerCase().includes(search.toLowerCase()))) || [];
  const lines = Object.values(cart);
  const subtotal = lines.reduce((sum, line) => sum + Number(line.item.selling_price) * line.quantity, 0);
  const total = Math.max(0, subtotal - Number(discount || 0));

  const add = (item: MenuItem) => { if (!item.is_available) return; setCart((current) => ({ ...current, [item.id]: { item, quantity: (current[item.id]?.quantity || 0) + 1, notes: current[item.id]?.notes || "" } })); };
  const changeQty = (id: number, delta: number) => setCart((current) => { const next = { ...current }; const line = next[id]; if (!line) return current; const quantity = line.quantity + delta; if (quantity <= 0) delete next[id]; else next[id] = { ...line, quantity }; return next; });
  const submitOrder = () => {
    if (!lines.length) return;
    const body: Record<string, unknown> = { items: lines.map((line) => ({ menu_item_id: line.item.id, quantity: line.quantity, notes: line.notes || null })), discount: Number(discount || 0), payment_method: payment, notes: orderNotes || null };
    if (customerMode === "existing" && customer) body.customer_id = customer.id;
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
          <div className="customer-switch"><button className={customerMode === "guest" ? "active" : ""} onClick={() => setCustomerMode("guest")}>مهمان</button><button className={customerMode === "existing" ? "active" : ""} onClick={() => setCustomerMode("existing")}><Users size={15} /> مشتری</button><button className={customerMode === "new" ? "active" : ""} onClick={() => setCustomerMode("new")}><UserPlus size={15} /> جدید</button></div>
          {customerMode === "existing" && <div className="customer-picker"><label className="search-box"><Search size={16} /><input value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} placeholder="نام یا شماره تلفن…" /></label>{customer && <div className="selected-customer"><span>{customer.name.charAt(0)}</span><div><strong>{customer.name}</strong><small>{customer.phone}</small></div><button onClick={() => setCustomer(null)}><X size={16}/></button></div>}{!customer && customers.data?.map((person) => <button key={person.id} onClick={() => setCustomer(person)}><span>{person.name.charAt(0)}</span><div><strong>{person.name}</strong><small>{person.phone}</small></div></button>)}</div>}
          {customerMode === "new" && <div className="new-customer"><input id="new-customer-name" placeholder="نام مشتری" /><input id="new-customer-phone" placeholder="شماره تلفن" inputMode="tel" /></div>}
          <div className="cart-lines">{lines.length ? lines.map((line) => <div className="cart-line" key={line.item.id}><div className="line-top"><div><strong>{line.item.name}</strong><small>هر عدد {money(line.item.selling_price)}</small></div><strong>{money(Number(line.item.selling_price) * line.quantity)}</strong></div><div className="line-controls"><button onClick={() => changeQty(line.item.id, -1)}>{line.quantity === 1 ? <Trash2 size={15} /> : <Minus size={15} />}</button><span>{quantity(line.quantity)}</span><button onClick={() => changeQty(line.item.id, 1)}><Plus size={15} /></button><input value={line.notes} onChange={(e) => setCart((current) => ({ ...current, [line.item.id]: { ...line, notes: e.target.value } }))} placeholder="توضیح برای آشپزخانه…" /></div></div>) : <EmptyState icon={<ShoppingBag />} title="سبد سفارش خالی است" text="برای افزودن، یک محصول از منو انتخاب کنید." />}</div>
          <div className="cart-options"><label><span>تخفیف</span><input value={discount} onChange={(e) => setDiscount(e.target.value)} type="number" min="0" step="0.01" /></label><label><span>روش پرداخت</span><select value={payment} onChange={(e) => setPayment(e.target.value)}><option value="card">کارت‌خوان</option><option value="cash">نقدی</option><option value="online">آنلاین</option><option value="other">سایر</option></select></label><input value={orderNotes} onChange={(e) => setOrderNotes(e.target.value)} placeholder="توضیح کلی سفارش (اختیاری)" /></div>
          <div className="cart-totals"><span><small>جمع اقلام</small><strong>{money(subtotal)}</strong></span><span><small>تخفیف</small><strong>− {money(discount)}</strong></span><span className="grand-total"><small>مبلغ نهایی</small><strong>{money(total)}</strong></span></div>
          {error && <div className="form-error">{error}</div>}
          <Button className="place-order" disabled={!lines.length || orderMutation.isPending} onClick={submitOrder}>{orderMutation.isPending ? "در حال ثبت سفارش…" : <><Check size={19} /> ثبت سفارش · {money(total)}</>}</Button>
        </aside>
      </div>

      <section className="panel orders-today"><header className="panel-header"><div><h2>سفارش‌های امروز</h2><p>هر سفارش را از ثبت تا تکمیل دنبال کنید.</p></div></header>{orders.data?.length ? <div className="order-board">{orders.data.map((order) => <button key={order.id} className="order-ticket" onClick={() => setActiveOrder(order)}><div><strong>{order.order_number}</strong><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></div><h3>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</h3><p>{order.items.map((item) => `${quantity(item.quantity)}× ${item.name}`).join(" · ")}</p><footer><span>{dateTime(order.created_at)}</span><strong>{money(order.total)}</strong></footer></button>)}</div> : <EmptyState icon={<ClipboardCheck />} title="امروز سفارشی ثبت نشده" text="سفارش‌های جدید به‌صورت زنده اینجا نمایش داده می‌شوند." />}</section>

      <OrderModal order={activeOrder} close={() => setActiveOrder(null)} print={(mode) => activeOrder && void openReceipt(activeOrder, mode)} changeStatus={(status) => activeOrder && statusMutation.mutate({ id: activeOrder.id, status })} />
      <ReceiptModal receipt={receipt} brand={brand} close={() => setReceipt(null)} />
    </div>
  );
}

function OrderModal({ order, close, print, changeStatus }: { order: Order | null; close: () => void; print: (mode: "customer" | "kitchen") => void; changeStatus: (status: string) => void }) {
  if (!order) return null;
  const next: Record<string, { label: string; value: string } | undefined> = { confirmed: { label: "شروع آماده‌سازی", value: "preparing" }, preparing: { label: "اعلام آماده تحویل", value: "ready" }, ready: { label: "تکمیل سفارش", value: "completed" } };
  return <Modal open title={order.order_number} onClose={close}><div className="order-detail-head"><div><small>مشتری</small><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong><span>{dateTime(order.created_at)}</span></div><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></div><div className="order-detail-lines">{order.items.map((line) => <div key={line.id}><span>{quantity(line.quantity)} × {line.name}{line.notes && <small>{line.notes}</small>}</span><strong>{money(line.line_total)}</strong></div>)}</div><div className="order-detail-total"><span>مبلغ نهایی</span><strong>{money(order.total)}</strong></div><div className="receipt-actions"><Button variant="secondary" onClick={() => print("kitchen")}><ChefHat size={17} /> فیش آشپزخانه</Button><Button variant="secondary" onClick={() => print("customer")}><Printer size={17} /> رسید مشتری</Button></div>{next[order.status] && <Button className="full-button" onClick={() => changeStatus(next[order.status]!.value)}>{next[order.status]!.label}</Button>}</Modal>;
}

function ReceiptModal({ receipt, brand, close }: { receipt: ReceiptState | null; brand: { business_name: string; logo_url: string | null }; close: () => void }) {
  if (!receipt) return null;
  const { document, mode } = receipt;
  const { order, quote } = document;
  const profile = mode === "kitchen" ? document.kitchen_copy : document.customer_copy;
  return <Modal open title={profile.title} onClose={close}>
    <div className={`receipt receipt-mode-${mode}`} id="printable-receipt" dir="rtl">
      <header className="receipt-header">
        {brand.logo_url && <img src={brand.logo_url} alt="" />}
        <span className="receipt-copy-label">{mode === "kitchen" ? "فیش آماده‌سازی" : "رسید رسمی فروش"}</span>
        <h2>{mode === "kitchen" ? "آشپزخانه" : brand.business_name}</h2>
        <div className="receipt-order-number"><small>شماره سفارش</small><strong>{order.order_number}</strong></div>
        <p>{dateTime(order.created_at)}</p>
      </header>
      <div className="receipt-customer"><span>مشتری</span><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong></div>
      {mode === "customer" && <div className="receipt-columns"><span>شرح سفارش</span><strong>مبلغ</strong></div>}
      <div className="receipt-lines">{order.items.map((line) => <div key={line.id}><span className="receipt-line-main"><b>{line.name}</b>{mode === "customer" && <small>{quantity(line.quantity)} عدد × {money(line.unit_price)}</small>}{mode === "kitchen" && <small className="kitchen-quantity">تعداد: {quantity(line.quantity)}</small>}{line.notes && <em>توضیح مهم: {line.notes}</em>}</span>{mode === "customer" && <strong>{money(line.line_total)}</strong>}</div>)}</div>
      {mode === "customer" && <div className="receipt-summary"><span>جمع اقلام <b>{money(order.subtotal)}</b></span><span>تخفیف <b>{money(order.discount)}</b></span><span className="receipt-grand-total">مبلغ نهایی <b>{money(order.total)}</b></span><small>روش پرداخت: {statusLabel[order.payment_method]}</small></div>}
      {mode === "kitchen" && order.notes && <div className="kitchen-order-note"><span>توضیح کلی سفارش</span><strong>{order.notes}</strong></div>}
      <figure className="receipt-quote">
        <figcaption>یک جمله برای امروز</figcaption>
        <blockquote>«{quote.body}»</blockquote>
        <cite>— {quote.author}</cite>
      </figure>
      <footer><strong>{mode === "customer" ? "از انتخاب شما سپاسگزاریم" : "با دقت آماده و کنترل شود"}</strong><span>{mode === "customer" ? "به امید دیدار دوباره" : "کنترل نهایی پیش از تحویل"}</span><small>{order.order_number}</small></footer>
    </div>
    <div className="receipt-print-note">چاپ حرفه‌ای ۸۰ میلی‌متری · فونت فارسی فوق‌پررنگ · کنتراست خالص سیاه‌وسفید</div>
    <Button className="full-button print-trigger" onClick={() => window.print()}><Printer size={18} /> چاپ {profile.title}</Button>
  </Modal>;
}
