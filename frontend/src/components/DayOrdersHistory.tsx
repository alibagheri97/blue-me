import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Banknote,
  CalendarDays,
  CircleEllipsis,
  CircleDollarSign,
  ClipboardList,
  ContactRound,
  CreditCard,
  Globe2,
  PackageOpen,
  Pencil,
  ReceiptText,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api } from "../lib/api";
import { businessDate, dateTime, money, quantity, statusLabel } from "../lib/format";
import type { MenuItem, Order } from "../types";
import { JalaliDatePicker } from "./JalaliDatePicker";
import { OrderDeleteModal, OrderEditModal } from "./OrderManagement";
import { Badge, EmptyState, Spinner } from "./ui";

const paymentMethods = [
  { method: "card", label: "انتقال به کارت", icon: CreditCard, tone: "blue" },
  { method: "cash", label: "نقدی", icon: Banknote, tone: "green" },
  { method: "online", label: "آنلاین", icon: Globe2, tone: "violet" },
  { method: "other", label: "سایر", icon: CircleEllipsis, tone: "amber" },
] as const;

export function DayOrdersHistory({ compact = false }: { compact?: boolean }) {
  const client = useQueryClient();
  const [day, setDay] = useState(businessDate());
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [editingOrder, setEditingOrder] = useState<Order | null>(null);
  const [deletingOrder, setDeletingOrder] = useState<Order | null>(null);
  const [editError, setEditError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const history = useQuery({
    queryKey: ["orders-history", day, search],
    queryFn: () => api<Order[]>(`/orders?day=${day}&search=${encodeURIComponent(search)}&limit=500`),
    refetchInterval: day === businessDate() ? 20_000 : false,
  });
  const menu = useQuery({
    queryKey: ["menu", "order-history-editor"],
    queryFn: () => api<MenuItem[]>("/menu-items?active=true"),
  });
  const invalidateOrders = () => {
    client.invalidateQueries({ queryKey: ["orders-history"] });
    client.invalidateQueries({ queryKey: ["orders-today"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
    client.invalidateQueries({ queryKey: ["reports"] });
    client.invalidateQueries({ queryKey: ["inventory"] });
    client.invalidateQueries({ queryKey: ["menu"] });
    client.invalidateQueries({ queryKey: ["kitchen-orders"] });
    client.invalidateQueries({ queryKey: ["staff"] });
  };
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => api<Order>(`/orders/${id}`, { method: "PATCH", body }),
    onSuccess: () => { setEditingOrder(null); setEditError(""); invalidateOrders(); },
    onError: (reason) => {
      const error = reason as ApiError;
      if (typeof error.detail === "object" && error.detail && "items" in error.detail) {
        setEditError(`موجودی برای این ویرایش کافی نیست: ${(error.detail as { items: string[] }).items.join("، ")}`);
      } else setEditError(error.message || "ویرایش سفارش انجام نشد");
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api<void>(`/orders/${id}`, { method: "DELETE" }),
    onSuccess: () => { setDeletingOrder(null); setDeleteError(""); invalidateOrders(); },
    onError: (reason) => setDeleteError(reason instanceof ApiError ? reason.message : "حذف سفارش انجام نشد"),
  });

  const filteredOrders = useMemo(
    () => (history.data || []).filter((order) => status === "all" || order.status === status),
    [history.data, status],
  );
  const completedSales = filteredOrders.filter((order) => !order.is_staff_meal && order.status !== "cancelled");
  const revenue = completedSales.reduce((sum, order) => sum + Number(order.total), 0);
  const knownCustomers = new Set(filteredOrders.filter((order) => order.customer_id).map((order) => order.customer_id)).size;
  const paymentBreakdown = paymentMethods.map((entry) => {
    const orders = completedSales.filter((order) => order.payment_method === entry.method);
    const amount = orders.reduce((sum, order) => sum + Number(order.total), 0);
    return { ...entry, amount, orders: orders.length, share: revenue > 0 ? amount / revenue * 100 : 0 };
  });

  return (
    <section className={`panel day-orders-history ${compact ? "day-orders-compact" : ""}`}>
      <header className="day-history-head">
        <div className="day-history-title">
          <span><ClipboardList /></span>
          <div><h2>تاریخچه سفارش‌های روز</h2><p>هر روز کاری از ساعت ۰۵:۰۰ تا ۰۵:۰۰ روز بعد محاسبه می‌شود</p></div>
        </div>
        <div className="day-history-toolbar">
          <label className="day-history-date"><CalendarDays /><JalaliDatePicker value={day} max={businessDate()} onChange={setDay} ariaLabel="روز سفارش‌ها به تاریخ شمسی" /></label>
          <label className="search-box"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="شماره سفارش یا مشتری…" /></label>
          <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="فیلتر وضعیت سفارش">
            <option value="all">همه وضعیت‌ها</option>
            <option value="confirmed">ثبت‌شده</option>
            <option value="preparing">در حال آماده‌سازی</option>
            <option value="ready">آماده تحویل</option>
            <option value="completed">تکمیل‌شده</option>
            <option value="cancelled">لغوشده</option>
          </select>
        </div>
      </header>

      <div className="day-history-summary">
        <div><span className="chip-icon blue"><ReceiptText /></span><span><small>سفارش نمایش‌داده‌شده</small><strong>{quantity(filteredOrders.length)}</strong></span></div>
        <div><span className="chip-icon green"><CircleDollarSign /></span><span><small>فروش مؤثر روز</small><strong>{money(revenue)}</strong></span></div>
        <div><span className="chip-icon violet"><Users /></span><span><small>مشتری شناخته‌شده</small><strong>{quantity(knownCustomers)}</strong></span></div>
        <div><span className="chip-icon amber"><ContactRound /></span><span><small>غذای پرسنلی</small><strong>{quantity(filteredOrders.filter((order) => order.is_staff_meal).length)}</strong></span></div>
      </div>

      <div className="day-payment-breakdown">
        <header><span><CircleDollarSign /></span><div><strong>تفکیک دریافتی این روز</strong><small>مبالغ مؤثر مطابق فیلترهای بالا؛ بدون غذای پرسنلی و سفارش لغوشده</small></div></header>
        <div>
          {paymentBreakdown.map((entry) => {
            const Icon = entry.icon;
            return <article key={entry.method} className={`payment-method-card payment-${entry.tone}`}><span><Icon /></span><div><small>{entry.label}</small><strong>{money(entry.amount)}</strong><em>{quantity(entry.orders)} سفارش · {quantity(entry.share)}٪</em></div><i><b style={{ width: `${entry.share}%` }} /></i></article>;
          })}
        </div>
      </div>

      {history.isLoading ? <div className="center-loader"><Spinner /></div> : filteredOrders.length ? (
        <div className="day-history-table-wrap">
          <table className="day-history-table">
            <thead><tr><th>سفارش</th><th>مشتری / حساب</th><th>اقلام</th><th>زمان</th><th>مبلغ</th><th>روش دریافت</th><th>وضعیت</th><th>عملیات</th></tr></thead>
            <tbody>
              {filteredOrders.map((order) => (
                <tr key={order.id}>
                  <td data-label="سفارش"><strong>{order.order_number}</strong><small>#{quantity(order.id)}</small>{order.order_type === "takeaway" && <Badge tone="warning"><PackageOpen size={13} /> بیرون‌بر · {quantity(order.takeaway_package_count)} بسته</Badge>}</td>
                  <td data-label="مشتری / حساب"><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong>{order.is_staff_meal && <Badge tone="violet">پرسنلی</Badge>}</td>
                  <td data-label="اقلام"><span className="day-history-items">{order.items.map((item) => `${quantity(item.quantity)}× ${item.name}`).join(" · ")}</span></td>
                  <td data-label="زمان"><span>{dateTime(order.created_at)}</span></td>
                  <td data-label="مبلغ"><strong>{order.is_staff_meal ? "بدون دریافت" : money(order.total)}</strong></td>
                  <td data-label="روش دریافت"><Badge tone={order.is_staff_meal ? "violet" : order.payment_method === "cash" ? "success" : order.payment_method === "online" ? "info" : "neutral"}>{order.is_staff_meal ? "داخلی" : statusLabel[order.payment_method]}</Badge></td>
                  <td data-label="وضعیت"><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge></td>
                  <td data-label="عملیات">
                    <div className="day-history-actions">
                      <button type="button" disabled={order.status === "cancelled"} onClick={() => { setEditError(""); setEditingOrder(order); }} title={order.status === "cancelled" ? "سفارش لغوشده قابل ویرایش نیست" : "ویرایش سفارش"}><Pencil /></button>
                      <button type="button" className="danger" onClick={() => { setDeleteError(""); setDeletingOrder(order); }} title="حذف سفارش"><Trash2 /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <EmptyState icon={<ReceiptText />} title="برای این روز سفارشی پیدا نشد" text="تاریخ، وضعیت یا عبارت جست‌وجو را تغییر دهید." />}

      {editingOrder && (
        <OrderEditModal
          key={editingOrder.id}
          order={editingOrder}
          menu={menu.data || []}
          close={() => { setEditingOrder(null); setEditError(""); }}
          save={(body) => editMutation.mutate({ id: editingOrder.id, body })}
          pending={editMutation.isPending}
          error={editError}
        />
      )}
      <OrderDeleteModal
        order={deletingOrder}
        close={() => { setDeletingOrder(null); setDeleteError(""); }}
        confirm={() => deletingOrder && deleteMutation.mutate(deletingOrder.id)}
        pending={deleteMutation.isPending}
        error={deleteError}
      />
    </section>
  );
}
