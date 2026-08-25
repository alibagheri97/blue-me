import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChefHat, CirclePlus, ClipboardCheck, Minus, Plus, Printer, ReceiptText, Search, ShoppingBag, Trash2, UserPlus, Users, X } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api, assetUrl } from "../lib/api";
import { dateTime, money, quantity, statusLabel } from "../lib/format";
import type { MenuItem, Order } from "../types";

interface Customer { id: number; name: string; phone: string; notes: string | null }
interface CartLine { item: MenuItem; quantity: number; notes: string }

export default function PosPage() {
  const { user, brand } = useAuth();
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
  const [receipt, setReceipt] = useState<{ order: Order; mode: "customer" | "kitchen" } | null>(null);
  const [menuModal, setMenuModal] = useState<MenuItem | "new" | null>(null);
  const [error, setError] = useState("");
  const menu = useQuery({ queryKey: ["menu"], queryFn: () => api<MenuItem[]>("/menu-items?active=true") });
  const customers = useQuery({ queryKey: ["customers", customerSearch], queryFn: () => api<Customer[]>(`/customers?search=${encodeURIComponent(customerSearch)}`), enabled: customerMode === "existing" });
  const orders = useQuery({ queryKey: ["orders-today"], queryFn: () => api<Order[]>(`/orders?day=${new Date().toISOString().slice(0, 10)}&limit=100`), refetchInterval: 20_000 });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body: object }) => api<Order | MenuItem>(path, { method, body }),
    onSuccess: (result, variables) => {
      setError("");
      if (variables.path === "/orders") {
        const order = result as Order; setCart({}); setDiscount("0"); setCustomer(null); setCustomerMode("guest"); setOrderNotes(""); setActiveOrder(order); setReceipt({ order, mode: "customer" });
        client.invalidateQueries({ queryKey: ["orders-today"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); client.invalidateQueries({ queryKey: ["inventory"] });
      } else { setMenuModal(null); client.invalidateQueries({ queryKey: ["menu"] }); }
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
    mutation.mutate({ path: "/orders", method: "POST", body });
  };

  const saveMenu = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); const body = { name: form.get("name"), category: form.get("category"), selling_price: form.get("selling_price"), description: form.get("description") || null, is_active: true };
    mutation.mutate({ path: menuModal === "new" ? "/menu-items" : `/menu-items/${menuModal!.id}`, method: menuModal === "new" ? "POST" : "PATCH", body });
  };

  return (
    <div className="page-stack pos-page">
      <header className="page-heading"><div><span className="eyebrow">ثبت سریع و دقیق سفارش</span><h1>سفارش‌ها و صندوق فروش</h1><p>سریع در صندوق، دقیق در آشپزخانه و متصل به موجودی انبار.</p></div>{user && ["root", "accounting_manager", "sales_manager"].includes(user.role) && <Button variant="secondary" onClick={() => setMenuModal("new")}><CirclePlus size={18} /> محصول منو</Button>}</header>
      <div className="pos-layout">
        <section className="panel product-browser">
          <div className="pos-search"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجو در منو…" /></label></div>
          <div className="category-pills">{categories.map((name) => <button key={name} className={category === name ? "active" : ""} onClick={() => setCategory(name)}>{name}</button>)}</div>
          {menu.isLoading ? <div className="center-loader"><Spinner /></div> : filteredMenu.length ? <div className="menu-grid">{filteredMenu.map((item) => <button className={`menu-card ${!item.is_available ? "unavailable" : ""}`} disabled={!item.is_available} key={item.id} onClick={() => add(item)}>{item.image_path ? <img src={assetUrl(item.image_path)} alt="" /> : <span className="menu-placeholder"><ShoppingBag /></span>}<div><strong>{item.name}</strong><small>{item.category}</small><b>{money(item.selling_price)}</b>{!item.is_available && <em>ناموجود</em>}</div>{cart[item.id] && <i>{quantity(cart[item.id].quantity)}</i>}{user && ["root", "accounting_manager", "sales_manager"].includes(user.role) && <span className="menu-edit" onClick={(event) => { event.stopPropagation(); setMenuModal(item); }}>ویرایش</span>}</button>)}</div> : <EmptyState icon={<ShoppingBag />} title="محصولی در منو نیست" text="از بخش مدیریت منو، محصولات فروش را تعریف و به انبار متصل کنید." />}
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
          <Button className="place-order" disabled={!lines.length || mutation.isPending} onClick={submitOrder}>{mutation.isPending ? "در حال ثبت سفارش…" : <><Check size={19} /> ثبت سفارش · {money(total)}</>}</Button>
        </aside>
      </div>

      <section className="panel orders-today"><header className="panel-header"><div><h2>سفارش‌های امروز</h2><p>هر سفارش را از ثبت تا تکمیل دنبال کنید.</p></div></header>{orders.data?.length ? <div className="order-board">{orders.data.map((order) => <button key={order.id} className="order-ticket" onClick={() => setActiveOrder(order)}><div><strong>{order.order_number}</strong><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></div><h3>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</h3><p>{order.items.map((item) => `${quantity(item.quantity)}× ${item.name}`).join(" · ")}</p><footer><span>{dateTime(order.created_at)}</span><strong>{money(order.total)}</strong></footer></button>)}</div> : <EmptyState icon={<ClipboardCheck />} title="امروز سفارشی ثبت نشده" text="سفارش‌های جدید به‌صورت زنده اینجا نمایش داده می‌شوند." />}</section>

      <Modal open={menuModal !== null} title={menuModal === "new" ? "افزودن محصول منو" : "ویرایش محصول منو"} onClose={() => setMenuModal(null)}><form className="form-grid" onSubmit={saveMenu}><label className="field"><span>نام محصول</span><input name="name" required defaultValue={menuModal !== "new" && menuModal ? menuModal.name : ""} /></label><label className="field"><span>دسته‌بندی منو</span><input name="category" required defaultValue={menuModal !== "new" && menuModal ? menuModal.category : "عمومی"} /></label><label className="field field-wide"><span>قیمت فروش</span><input name="selling_price" required type="number" min="0" step="0.01" defaultValue={menuModal !== "new" && menuModal ? menuModal.selling_price : ""} /></label><label className="field field-wide"><span>توضیحات</span><textarea name="description" rows={3} defaultValue={menuModal !== "new" && menuModal ? menuModal.description || "" : ""} /></label>{error && <div className="form-error field-wide">{error}</div>}<div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setMenuModal(null)}>انصراف</Button><Button type="submit">ذخیره محصول</Button></div></form></Modal>
      <OrderModal order={activeOrder} close={() => setActiveOrder(null)} print={(mode) => activeOrder && setReceipt({ order: activeOrder, mode })} changeStatus={(status) => activeOrder && statusMutation.mutate({ id: activeOrder.id, status })} />
      <ReceiptModal receipt={receipt} brand={brand} close={() => setReceipt(null)} />
    </div>
  );
}

function OrderModal({ order, close, print, changeStatus }: { order: Order | null; close: () => void; print: (mode: "customer" | "kitchen") => void; changeStatus: (status: string) => void }) {
  if (!order) return null;
  const next: Record<string, { label: string; value: string } | undefined> = { confirmed: { label: "شروع آماده‌سازی", value: "preparing" }, preparing: { label: "اعلام آماده تحویل", value: "ready" }, ready: { label: "تکمیل سفارش", value: "completed" } };
  return <Modal open title={order.order_number} onClose={close}><div className="order-detail-head"><div><small>مشتری</small><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong><span>{dateTime(order.created_at)}</span></div><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></div><div className="order-detail-lines">{order.items.map((line) => <div key={line.id}><span>{quantity(line.quantity)} × {line.name}{line.notes && <small>{line.notes}</small>}</span><strong>{money(line.line_total)}</strong></div>)}</div><div className="order-detail-total"><span>مبلغ نهایی</span><strong>{money(order.total)}</strong></div><div className="receipt-actions"><Button variant="secondary" onClick={() => print("kitchen")}><ChefHat size={17} /> فیش آشپزخانه</Button><Button variant="secondary" onClick={() => print("customer")}><Printer size={17} /> رسید مشتری</Button></div>{next[order.status] && <Button className="full-button" onClick={() => changeStatus(next[order.status]!.value)}>{next[order.status]!.label}</Button>}</Modal>;
}

function ReceiptModal({ receipt, brand, close }: { receipt: { order: Order; mode: "customer" | "kitchen" } | null; brand: { business_name: string; logo_url: string | null }; close: () => void }) {
  const printable = useMemo(() => receipt, [receipt]);
  if (!printable) return null;
  const { order, mode } = printable;
  return <Modal open title={mode === "kitchen" ? "فیش آشپزخانه" : "رسید مشتری"} onClose={close}><div className={`receipt receipt-${mode}`} id="printable-receipt"><header>{brand.logo_url && <img src={brand.logo_url} alt="" />}<h2>{mode === "kitchen" ? "آشپزخانه" : brand.business_name}</h2><strong>{order.order_number}</strong><p>{dateTime(order.created_at)} · {order.customer_name === "Guest" ? "مهمان" : order.customer_name}</p></header><div className="receipt-lines">{order.items.map((line) => <div key={line.id}><span><b>{quantity(line.quantity)} ×</b> {line.name}{line.notes && <em>توضیح: {line.notes}</em>}</span>{mode === "customer" && <strong>{money(line.line_total)}</strong>}</div>)}</div>{mode === "customer" && <div className="receipt-summary"><span>جمع اقلام <b>{money(order.subtotal)}</b></span><span>تخفیف <b>{money(order.discount)}</b></span><span>مبلغ نهایی <b>{money(order.total)}</b></span><small>روش پرداخت: {statusLabel[order.payment_method]}</small></div>}{mode === "kitchen" && order.notes && <div className="kitchen-order-note">توضیح سفارش: {order.notes}</div>}<footer>{mode === "customer" ? "از خرید شما سپاسگزاریم" : "با دقت آماده شود"}</footer></div><Button className="full-button print-trigger" onClick={() => window.print()}><Printer size={18} /> چاپ {mode === "kitchen" ? "فیش آشپزخانه" : "رسید مشتری"}</Button></Modal>;
}
