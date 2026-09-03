import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ContactRound,
  Minus,
  PackageOpen,
  Pencil,
  Plus,
  Save,
  Search,
  ShoppingBag,
  Trash2,
  UserPlus,
  Users,
  UtensilsCrossed,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { dateTime, money, quantity } from "../lib/format";
import type { MenuItem, Order, OrderType } from "../types";
import { Badge, Button, EmptyState, Modal } from "./ui";

interface Customer {
  id: number;
  name: string;
  phone: string;
  notes: string | null;
}

interface EditableOrderLine {
  menu_item_id: number;
  name: string;
  unit_price: number;
  quantity: number;
  notes: string;
}

type CustomerMode = "guest" | "existing" | "new";

export function OrderEditModal({
  order,
  menu,
  close,
  save,
  pending,
  error,
}: {
  order: Order;
  menu: MenuItem[];
  close: () => void;
  save: (body: object) => void;
  pending: boolean;
  error: string;
}) {
  const [search, setSearch] = useState("");
  const [lines, setLines] = useState<Record<number, EditableOrderLine>>(() =>
    Object.fromEntries(
      order.items.map((line) => {
        const current = menu.find((item) => item.id === line.menu_item_id);
        return [
          line.menu_item_id,
          {
            menu_item_id: line.menu_item_id,
            name: line.name,
            unit_price: Number(current?.selling_price ?? line.unit_price),
            quantity: line.quantity,
            notes: line.notes || "",
          },
        ];
      }),
    ),
  );
  const [discount, setDiscount] = useState(String(order.is_staff_meal ? 0 : order.discount));
  const [payment, setPayment] = useState(order.payment_method);
  const [notes, setNotes] = useState(order.notes || "");
  const [orderType, setOrderType] = useState<OrderType>(order.order_type);
  const [takeawayPackageCount, setTakeawayPackageCount] = useState(
    Math.max(1, order.takeaway_package_count || 1),
  );
  const [customerMode, setCustomerMode] = useState<CustomerMode>(order.customer_id ? "existing" : "guest");
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(() =>
    order.customer_id
      ? { id: order.customer_id, name: order.customer_name, phone: "", notes: null }
      : null,
  );
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [customerError, setCustomerError] = useState("");
  const customers = useQuery({
    queryKey: ["customers", "order-editor", customerSearch],
    queryFn: () => api<Customer[]>(`/customers?search=${encodeURIComponent(customerSearch)}`),
    enabled: !order.is_staff_meal && customerMode === "existing" && !selectedCustomer,
  });

  const orderLines = Object.values(lines);
  const subtotal = orderLines.reduce((sum, line) => sum + line.unit_price * line.quantity, 0);
  const total = order.is_staff_meal ? 0 : Math.max(0, subtotal - Number(discount || 0));
  const candidates = menu
    .filter((item) => !search.trim() || item.name.toLowerCase().includes(search.trim().toLowerCase()))
    .slice(0, 60);
  const addItem = (item: MenuItem) => {
    if (!item.is_available && !lines[item.id]) return;
    setLines((current) => ({
      ...current,
      [item.id]: {
        menu_item_id: item.id,
        name: item.name,
        unit_price: Number(item.selling_price),
        quantity: (current[item.id]?.quantity || 0) + 1,
        notes: current[item.id]?.notes || "",
      },
    }));
  };
  const changeQuantity = (id: number, delta: number) =>
    setLines((current) => {
      const line = current[id];
      if (!line) return current;
      const next = { ...current };
      const nextQuantity = line.quantity + delta;
      if (nextQuantity <= 0) delete next[id];
      else next[id] = { ...line, quantity: nextQuantity };
      return next;
    });
  const submit = () => {
    const body: Record<string, unknown> = {
      items: orderLines.map((line) => ({
        menu_item_id: line.menu_item_id,
        quantity: line.quantity,
        notes: line.notes || null,
      })),
      discount: order.is_staff_meal ? 0 : Number(discount || 0),
      payment_method: order.is_staff_meal ? "other" : payment,
      notes: notes || null,
      order_type: orderType,
    };
    if (orderType === "takeaway") body.takeaway_package_count = takeawayPackageCount;
    if (!order.is_staff_meal) {
      if (customerMode === "guest") body.customer_id = null;
      if (customerMode === "existing") {
        if (!selectedCustomer) {
          setCustomerError("یک مشتری را از فهرست انتخاب کنید");
          return;
        }
        body.customer_id = selectedCustomer.id;
      }
      if (customerMode === "new") {
        if (!newCustomerName.trim() || !newCustomerPhone.trim()) {
          setCustomerError("نام و شماره تلفن مشتری جدید را کامل وارد کنید");
          return;
        }
        body.customer = {
          name: newCustomerName.trim(),
          phone: newCustomerPhone.trim(),
        };
      }
    }
    setCustomerError("");
    save(body);
  };

  return (
    <Modal open title={`ویرایش ${order.order_number}`} onClose={close} wide>
      <div className="edit-order-notice">
        <Pencil size={18} />
        <span>
          <strong>ویرایش امن سفارش ثبت‌شده</strong>
          <small>اختلاف مواد اولیه خودکار از انبار کسر یا بازگردانده می‌شود و همه تغییرات در گزارش فعالیت‌ها می‌ماند.</small>
        </span>
        {order.status === "completed" && <Badge tone="warning">اصلاح سفارش تکمیل‌شده</Badge>}
      </div>

      <section className={`edit-order-service ${orderType === "takeaway" ? "takeaway-selected" : ""}`}>
        <header><div><h3>نحوه تحویل سفارش</h3><p>تغییر این گزینه، ملزومات بیرون‌بر را دقیقاً از انبار کم یا به آن بازمی‌گرداند.</p></div>{orderType === "takeaway" && <Badge tone="warning">کسر خودکار بسته‌بندی</Badge>}</header>
        <div className="order-service-buttons">
          <button type="button" className={orderType === "dine_in" ? "active" : ""} onClick={() => setOrderType("dine_in")}><UtensilsCrossed /><span><strong>سرو داخل</strong><small>بدون بسته‌بندی</small></span></button>
          <button type="button" className={orderType === "takeaway" ? "active" : ""} onClick={() => setOrderType("takeaway")}><PackageOpen /><span><strong>بیرون‌بر</strong><small>با ملزومات انبار</small></span></button>
        </div>
        {orderType === "takeaway" && <div className="edit-takeaway-package-count"><span><strong>تعداد بسته بیرون‌بر</strong><small>مصرف تعریف‌شده برای هر بسته در این تعداد ضرب می‌شود.</small></span><div><button type="button" onClick={() => setTakeawayPackageCount((count) => Math.max(1, count - 1))}><Minus /></button><b>{quantity(takeawayPackageCount)}</b><button type="button" onClick={() => setTakeawayPackageCount((count) => Math.min(999, count + 1))}><Plus /></button></div></div>}
      </section>

      {!order.is_staff_meal && (
        <section className="edit-order-customer">
          <header>
            <span className="edit-customer-icon"><ContactRound /></span>
            <div>
              <h3>حساب مشتری سفارش</h3>
              <p>سفارش را مهمان نگه دارید، به مشتری موجود وصل کنید یا مشتری تازه بسازید.</p>
            </div>
          </header>
          <div className="customer-switch edit-customer-switch">
            <button
              type="button"
              className={customerMode === "guest" ? "active" : ""}
              onClick={() => { setCustomerMode("guest"); setSelectedCustomer(null); setCustomerError(""); }}
            >
              مهمان
            </button>
            <button
              type="button"
              className={customerMode === "existing" ? "active" : ""}
              onClick={() => { setCustomerMode("existing"); setCustomerError(""); }}
            >
              <Users size={15} /> مشتری موجود
            </button>
            <button
              type="button"
              className={customerMode === "new" ? "active" : ""}
              onClick={() => { setCustomerMode("new"); setSelectedCustomer(null); setCustomerError(""); }}
            >
              <UserPlus size={15} /> مشتری جدید
            </button>
          </div>
          {customerMode === "guest" && (
            <div className="edit-customer-status">این سفارش با عنوان «مهمان» ذخیره خواهد شد.</div>
          )}
          {customerMode === "existing" && (
            <div className="customer-picker edit-customer-picker">
              {selectedCustomer ? (
                <div className="selected-customer">
                  <span>{selectedCustomer.name.charAt(0)}</span>
                  <div><strong>{selectedCustomer.name}</strong><small>{selectedCustomer.phone || "مشتری فعلی سفارش"}</small></div>
                  <button type="button" onClick={() => setSelectedCustomer(null)} aria-label="انتخاب مشتری دیگر"><X size={16} /></button>
                </div>
              ) : (
                <>
                  <label className="search-box"><Search size={16} /><input value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="نام یا شماره تلفن مشتری…" /></label>
                  <div className="edit-customer-results">
                    {customers.data?.map((person) => (
                      <button type="button" key={person.id} onClick={() => { setSelectedCustomer(person); setCustomerError(""); }}>
                        <span>{person.name.charAt(0)}</span><div><strong>{person.name}</strong><small>{person.phone}</small></div>
                      </button>
                    ))}
                    {!customers.isLoading && !customers.data?.length && <small className="edit-customer-empty">مشتری پیدا نشد؛ از گزینه «مشتری جدید» استفاده کنید.</small>}
                  </div>
                </>
              )}
            </div>
          )}
          {customerMode === "new" && (
            <div className="new-customer edit-new-customer">
              <input value={newCustomerName} onChange={(event) => setNewCustomerName(event.target.value)} placeholder="نام مشتری" />
              <input value={newCustomerPhone} onChange={(event) => setNewCustomerPhone(event.target.value)} placeholder="شماره تلفن" inputMode="tel" />
              <small><UserPlus size={14} /> با ذخیره سفارش، این فرد خودکار به فهرست مشتریان افزوده می‌شود.</small>
            </div>
          )}
          {customerError && <div className="form-error">{customerError}</div>}
        </section>
      )}

      <div className="edit-order-layout">
        <section className="edit-menu-picker">
          <header>
            <div><h3>افزودن از منوی فروش</h3><small>برای افزودن، محصول را انتخاب کنید.</small></div>
            <label className="search-box"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی محصول…" /></label>
          </header>
          <div className="edit-menu-grid">
            {candidates.map((item) => (
              <button type="button" key={item.id} disabled={!item.is_available && !lines[item.id]} className={lines[item.id] ? "selected" : ""} onClick={() => addItem(item)}>
                <span><strong>{item.name}</strong><small>{item.category}</small></span><b>{money(item.selling_price)}</b>{lines[item.id] && <i>{quantity(lines[item.id].quantity)}</i>}
              </button>
            ))}
          </div>
        </section>
        <aside className="edit-order-cart">
          <header><div><h3>اقلام اصلاح‌شده</h3><small>{quantity(orderLines.reduce((count, line) => count + line.quantity, 0))} قلم</small></div><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong></header>
          <div className="edit-order-lines">
            {orderLines.length ? orderLines.map((line) => (
              <div key={line.menu_item_id} className="edit-order-line">
                <div className="line-top"><span><strong>{line.name}</strong><small>هر عدد {money(line.unit_price)}</small></span><b>{money(line.unit_price * line.quantity)}</b></div>
                <div className="line-controls">
                  <button type="button" onClick={() => changeQuantity(line.menu_item_id, -1)}>{line.quantity === 1 ? <Trash2 size={15} /> : <Minus size={15} />}</button>
                  <span>{quantity(line.quantity)}</span>
                  <button type="button" onClick={() => changeQuantity(line.menu_item_id, 1)}><Plus size={15} /></button>
                  <input value={line.notes} onChange={(event) => setLines((current) => ({ ...current, [line.menu_item_id]: { ...line, notes: event.target.value } }))} placeholder="توضیح قلم…" />
                </div>
              </div>
            )) : <EmptyState icon={<ShoppingBag />} title="سفارش بدون قلم است" text="حداقل یک محصول از منو اضافه کنید." />}
          </div>
          <div className="edit-order-options">
            {!order.is_staff_meal && <>
              <label><span>تخفیف</span><input type="number" min="0" max={subtotal} value={discount} onChange={(event) => setDiscount(event.target.value)} /></label>
              <label><span>روش پرداخت</span><select value={payment} onChange={(event) => setPayment(event.target.value as Order["payment_method"])}><option value="card">انتقال به کارت</option><option value="cash">نقدی</option><option value="online">آنلاین</option><option value="other">سایر</option></select></label>
            </>}
            <label className="wide"><span>توضیح کلی سفارش</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="اختیاری" /></label>
          </div>
          <div className={`edit-order-total ${order.is_staff_meal ? "staff-order-total" : ""}`}>
            <span><small>{order.is_staff_meal ? "ارزش منو" : "جمع اقلام"}</small><strong>{money(subtotal)}</strong></span>
            {!order.is_staff_meal && <span><small>مبلغ نهایی</small><strong>{money(total)}</strong></span>}
            {order.is_staff_meal && <span><small>قابل پرداخت</small><strong>بدون دریافت وجه</strong></span>}
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="edit-order-actions">
            <Button type="button" variant="secondary" onClick={close}>انصراف</Button>
            <Button type="button" disabled={pending || !orderLines.length || (!order.is_staff_meal && Number(discount || 0) > subtotal)} onClick={submit}><Save size={17} /> {pending ? "در حال ذخیره…" : "ذخیره و محاسبه مجدد"}</Button>
          </div>
        </aside>
      </div>
    </Modal>
  );
}

export function OrderDeleteModal({
  order,
  close,
  confirm,
  pending,
  error,
}: {
  order: Order | null;
  close: () => void;
  confirm: () => void;
  pending: boolean;
  error: string;
}) {
  if (!order) return null;
  return (
    <Modal open title="حذف کنترل‌شده سفارش" onClose={close}>
      <div className="delete-order-confirm">
        <span className="delete-order-icon"><AlertTriangle /></span>
        <div className="delete-order-heading">
          <small>شماره سفارش</small>
          <strong>{order.order_number}</strong>
          <p>{order.customer_name === "Guest" ? "مهمان" : order.customer_name} · {dateTime(order.created_at)}</p>
        </div>
        <div className="delete-order-impact">
          <strong>{order.status === "cancelled" ? "این سفارش قبلاً لغو و موجودی آن بازگردانده شده است." : "مواد مصرف‌شده این سفارش دقیقاً یک‌بار به انبار بازمی‌گردد."}</strong>
          <span>سفارش از تاریخچه روزانه، رسیدها و آمار فروش حذف می‌شود؛ نسخه حسابرسی آن برای بازیابی و پیگیری مدیر کل محفوظ می‌ماند.</span>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="delete-order-actions">
          <Button type="button" variant="secondary" onClick={close} disabled={pending}>انصراف</Button>
          <Button type="button" variant="danger" onClick={confirm} disabled={pending}><Trash2 size={17} /> {pending ? "در حال حذف…" : "تأیید حذف سفارش"}</Button>
        </div>
      </div>
    </Modal>
  );
}
