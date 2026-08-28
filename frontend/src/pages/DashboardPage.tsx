import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ChefHat, CircleDollarSign, Clock3, PackageCheck, Power, ReceiptText, Route, TrendingDown, TrendingUp, UsersRound } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { businessHour, dateTime, money, quantity, statusLabel } from "../lib/format";
import type { InventoryItem, Order } from "../types";
import { Badge, EmptyState, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";

interface Dashboard {
  sales_today: string;
  orders_today: number;
  average_order_value: string;
  low_stock_count: number;
  pending_price_approvals: number;
  pending_daily_needs: number;
  automatic_purchase_needs: number;
  unread_notifications: number;
  active_users: number;
  orders_in_kitchen: number;
  kitchen_workflow_enabled: boolean;
  sales_change_percent: string;
  recent_orders: Order[];
  low_stock_items: InventoryItem[];
}

export default function DashboardPage() {
  const { user, brand } = useAuth();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard"), refetchInterval: 30_000 });
  const settingsMutation = useMutation({
    mutationFn: (enabled: boolean) => api<{ kitchen_workflow_enabled: boolean }>("/settings", { method: "PATCH", body: { kitchen_workflow_enabled: enabled } }),
    onSuccess: (settings) => {
      client.setQueryData<Dashboard>(["dashboard"], (current) => current ? { ...current, kitchen_workflow_enabled: settings.kitchen_workflow_enabled, orders_in_kitchen: settings.kitchen_workflow_enabled ? current.orders_in_kitchen : 0 } : current);
      client.invalidateQueries({ queryKey: ["dashboard"] });
      client.invalidateQueries({ queryKey: ["system-settings"] });
      client.invalidateQueries({ queryKey: ["orders-today"] });
      client.invalidateQueries({ queryKey: ["kitchen-orders"] });
    },
  });
  if (query.isLoading) return <div className="center-loader"><Spinner /></div>;
  if (!query.data) return <EmptyState icon={<AlertTriangle />} title="داشبورد در دسترس نیست" text="اتصال سامانه را بررسی و صفحه را دوباره بارگذاری کنید." />;
  const data = query.data;
  const change = Number(data.sales_change_percent);
  const hour = businessHour();

  return (
    <div className="page-stack">
      <header className="page-heading dashboard-heading">
        <div><span className="eyebrow">نبض زنده کسب‌وکار</span><h1>{hour < 12 ? "صبح بخیر" : hour < 18 ? "وقت بخیر" : "عصر بخیر"}، {user?.full_name.split(" ")[0]}</h1><p>مهم‌ترین وضعیت‌ها و کارهای امروز {brand.business_name} را اینجا ببینید.</p></div>
        <div className="live-pill"><span /> زنده · به‌روزرسانی خودکار</div>
      </header>

      <section className="metric-grid">
        <article className="metric-card metric-primary"><span className="metric-icon"><CircleDollarSign /></span><div><small>فروش امروز</small><strong>{money(data.sales_today)}</strong><span className={change >= 0 ? "trend-positive" : "trend-negative"}>{change >= 0 ? <TrendingUp size={15} /> : <TrendingDown size={15} />}{quantity(Math.abs(change))}٪ نسبت به دیروز</span></div></article>
        <article className="metric-card"><span className="metric-icon mint"><ReceiptText /></span><div><small>سفارش‌های امروز</small><strong>{quantity(data.orders_today)}</strong><span>میانگین هر سفارش {money(data.average_order_value)}</span></div></article>
        <article className="metric-card"><span className="metric-icon amber"><PackageCheck /></span><div><small>هشدار موجودی</small><strong>{quantity(data.low_stock_count)}</strong><span>{quantity(data.automatic_purchase_needs)} پیشنهاد خودکار خرید فردا</span></div></article>
        <article className="metric-card"><span className="metric-icon violet"><ChefHat /></span><div><small>صف آشپزخانه</small><strong>{quantity(data.orders_in_kitchen)}</strong><span>{quantity(data.pending_daily_needs)} نیاز خرید · {quantity(data.unread_notifications)} اعلان تازه</span></div></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel recent-panel">
          <header className="panel-header"><div><h2>آخرین سفارش‌ها</h2><p>جدیدترین فعالیت‌های صندوق</p></div>{["root", "accounting_manager", "sales_manager"].includes(user!.role) && <Link to="/pos">ورود به صندوق <ArrowRight size={16} /></Link>}</header>
          {data.recent_orders.length ? <div className="order-list">{data.recent_orders.map((order) => <div className="order-row" key={order.id}><span className="order-avatar">{order.customer_name.charAt(0).toUpperCase()}</span><div className="order-main"><strong>{order.customer_name === "Guest" ? "مهمان" : order.customer_name}</strong><small>{order.order_number} · {dateTime(order.created_at)}</small></div><Badge tone={order.status === "cancelled" ? "danger" : order.status === "completed" ? "success" : "info"}>{statusLabel[order.status]}</Badge><strong className="order-total">{money(order.total)}</strong></div>)}</div> : <EmptyState icon={<ReceiptText />} title="هنوز سفارشی ثبت نشده" text="سفارش‌های جدید بلافاصله اینجا نمایش داده می‌شوند." />}
        </article>
        <aside className="panel attention-panel">
          <header className="panel-header"><div><h2>نیازمند توجه</h2><p>کالاهای کم‌موجودی به‌ترتیب فوریت</p></div>{["root", "storage_manager"].includes(user!.role) && <Link to="/inventory">مشاهده همه</Link>}</header>
          {data.low_stock_items.length ? <div className="attention-list">{data.low_stock_items.map((item) => { const percentage = Number(item.reorder_level) ? Math.max(0, Math.min(100, Number(item.current_quantity) / Number(item.reorder_level) * 100)) : 0; return <div className="attention-row" key={item.id}><div className="attention-title"><span style={{ background: item.category?.color || "#64748b" }} /><strong>{item.name}</strong><small>{quantity(item.current_quantity)} {item.unit} باقی مانده</small></div><div className="stock-meter"><span style={{ width: `${percentage}%` }} /></div></div>; })}</div> : <EmptyState icon={<PackageCheck />} title="وضعیت موجودی مناسب است" text="هیچ کالایی زیر نقطه سفارش نیست." />}
        </aside>
      </section>

      {user?.role === "root" && <section className="quick-strip"><div><UsersRound size={20} /><span><strong>{quantity(data.active_users)} کاربر فعال</strong><small>نقش‌ها و دسترسی‌ها تحت کنترل‌اند</small></span></div><div><Clock3 size={20} /><span><strong>{quantity(data.pending_daily_needs + data.pending_price_approvals)} تصمیم در انتظار</strong><small>برای ادامه روان کارها، درخواست‌ها را بررسی کنید</small></span></div><Link to={data.pending_price_approvals ? "/inventory" : "/kitchen"}>بررسی درخواست‌ها <ArrowRight size={16} /></Link></section>}

      {user?.role === "root" && <section className={`panel kitchen-mode-setting ${data.kitchen_workflow_enabled ? "is-enabled" : "is-disabled"}`}>
        <div className="setting-visual"><Route /></div>
        <div className="setting-copy"><span className="eyebrow">تنظیمات عملیات سفارش</span><h2>گردش سه‌مرحله‌ای آشپزخانه</h2><p>{data.kitchen_workflow_enabled ? "سفارش پس از ثبت وارد مراحل تأیید، آماده‌سازی و تحویل می‌شود." : "حالت آشپزخانه خاموش است؛ سفارش تازه همان لحظه پذیرفته و با وضعیت تکمیل‌شده ثبت می‌شود."}</p><small>{data.kitchen_workflow_enabled ? "با خاموش‌کردن، سفارش‌های فعال فعلی نیز تکمیل می‌شوند." : "کسر موجودی، رسید، گزارش و ثبت رویداد همچنان کاملاً فعال است."}</small></div>
        <button type="button" className="kitchen-mode-toggle" aria-pressed={data.kitchen_workflow_enabled} disabled={settingsMutation.isPending} onClick={() => settingsMutation.mutate(!data.kitchen_workflow_enabled)}><span><i /><strong>{settingsMutation.isPending ? "در حال ذخیره…" : data.kitchen_workflow_enabled ? "فعال" : "غیرفعال"}</strong></span><Power size={18} />{data.kitchen_workflow_enabled ? "خاموش کردن حالت آشپزخانه" : "فعال کردن حالت آشپزخانه"}</button>
        {settingsMutation.isError && <div className="form-error setting-error">ذخیره تنظیمات انجام نشد؛ دوباره تلاش کنید.</div>}
      </section>}
    </div>
  );
}
