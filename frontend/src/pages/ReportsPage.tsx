import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Banknote, BarChart3, Boxes, CircleDollarSign, CircleEllipsis, Clock3, CreditCard, Globe2, Lightbulb, PackageSearch, ReceiptText, Sparkles, Target, WalletCards } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, Spinner } from "../components/ui";
import { DayOrdersHistory } from "../components/DayOrdersHistory";
import { api } from "../lib/api";
import { dateOnly, money, quantity } from "../lib/format";

interface ReportData {
  period: { days: number; start: string; end: string };
  kpis: { revenue: string; revenue_growth_percent: string; orders: number; average_order_value: string; estimated_cogs: string; purchase_spend: string; gross_profit: string; gross_margin_percent: string; known_customer_rate_percent: string; repeat_customers: number };
  payment_breakdown: PaymentBreakdown[];
  daily_sales: Array<{ date: string; revenue: string; orders: number; payment_breakdown: PaymentBreakdown[] }>;
  hourly_demand: Array<{ hour: number; revenue: string; orders: number }>;
  product_performance: Array<{ id: number; name: string; quantity: number; revenue: string; estimated_cost: string; gross_profit: string; margin_percent: string }>;
  category_performance: Array<{ category: string; revenue: string; quantity: number }>;
  inventory_health: { total_value: string; active_items: number; low_stock_items: number; automatic_purchase_needs: number; slow_moving_value: string; slow_moving_percent: string };
  insights: Array<{ tone: string; title: string; message: string }>;
}

interface PaymentBreakdown { method: "card" | "cash" | "online" | "other"; amount: string; orders: number; share_percent: string }

const palette = ["#2563eb", "#06b6d4", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444"];
const paymentMethods = [
  { method: "card", label: "انتقال به کارت", icon: CreditCard, tone: "blue" },
  { method: "cash", label: "نقدی", icon: Banknote, tone: "green" },
  { method: "online", label: "آنلاین", icon: Globe2, tone: "violet" },
  { method: "other", label: "سایر", icon: CircleEllipsis, tone: "amber" },
] as const;

export default function ReportsPage() {
  const [days, setDays] = useState(30);
  const report = useQuery({ queryKey: ["reports", days], queryFn: () => api<ReportData>(`/reports/overview?days=${days}`) });
  if (report.isLoading) return <div className="center-loader"><Spinner /></div>;
  if (!report.data) return <EmptyState icon={<AlertTriangle />} title="گزارش‌ها در دسترس نیستند" text="اتصال داده را بررسی و دوباره تلاش کنید." />;
  const data = report.data;
  const growth = Number(data.kpis.revenue_growth_percent);
  const peak = [...data.hourly_demand].sort((a, b) => Number(b.revenue) - Number(a.revenue))[0];

  return (
    <div className="page-stack reports-page">
      <header className="page-heading"><div><span className="eyebrow">هوش تجاری</span><h1>مرکز آمار و تحلیل</h1><p>فروش، سود و تمام محاسبات روزانه بر پایه روز کاری ۰۵:۰۰ تا ۰۵:۰۰ انجام می‌شود.</p></div><select className="period-select" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={7}>۷ روز اخیر</option><option value={30}>۳۰ روز اخیر</option><option value={90}>۹۰ روز اخیر</option><option value={365}>۱۲ ماه اخیر</option></select></header>
      <section className="metric-grid report-metrics">
        <article className="metric-card metric-primary"><span className="metric-icon"><CircleDollarSign /></span><div><small>درآمد کل</small><strong>{money(data.kpis.revenue)}</strong><span className={growth >= 0 ? "trend-positive" : "trend-negative"}>{growth >= 0 ? <ArrowUpRight size={15}/> : <ArrowDownRight size={15}/>} {quantity(Math.abs(growth))}٪ نسبت به دوره قبل</span></div></article>
        <article className="metric-card"><span className="metric-icon mint"><ReceiptText /></span><div><small>تعداد سفارش</small><strong>{quantity(data.kpis.orders)}</strong><span>میانگین سفارش {money(data.kpis.average_order_value)}</span></div></article>
        <article className="metric-card"><span className="metric-icon violet"><Target /></span><div><small>سود ناخالص واقعی</small><strong>{money(data.kpis.gross_profit)}</strong><span>حاشیه {quantity(data.kpis.gross_margin_percent)}٪ · بهای ثبت‌شده هنگام فروش</span></div></article>
        <article className="metric-card"><span className="metric-icon amber"><Boxes /></span><div><small>ارزش موجودی</small><strong>{money(data.inventory_health.total_value)}</strong><span>خرید دوره {money(data.kpis.purchase_spend)}</span></div></article>
      </section>
      <section className="panel report-payment-panel">
        <header className="panel-header"><div><span className="payment-panel-icon"><WalletCards /></span><span><h2>تفکیک مبالغ دریافتی</h2><p>جمع واقعی روش‌های دریافت وجه در بازهٔ {dateOnly(data.period.start)} تا {dateOnly(data.period.end)}</p></span></div><strong>{money(data.kpis.revenue)}</strong></header>
        <div className="payment-breakdown-grid">
          {paymentMethods.map((entry) => {
            const summary = data.payment_breakdown.find((item) => item.method === entry.method);
            const Icon = entry.icon;
            return <article key={entry.method} className={`payment-method-card payment-${entry.tone}`}><span><Icon /></span><div><small>{entry.label}</small><strong>{money(summary?.amount || 0)}</strong><em>{quantity(summary?.orders || 0)} سفارش · {quantity(summary?.share_percent || 0)}٪ از دریافتی</em></div><i><b style={{ width: `${Number(summary?.share_percent || 0)}%` }} /></i></article>;
          })}
        </div>
      </section>
      <section className="analytics-grid">
        <article className="panel chart-panel sales-chart"><header className="panel-header"><div><h2>روند فروش</h2><p>درآمد و تعداد سفارش روزانه</p></div><BarChart3 size={20}/></header><ResponsiveContainer width="100%" height={300}><AreaChart data={data.daily_sales}><defs><linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563eb" stopOpacity={.32}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8edf4"/><XAxis dataKey="date" tickFormatter={(v) => dateOnly(String(v), { month: "short", day: "numeric" })} tick={{fontSize:11}} axisLine={false} tickLine={false}/><YAxis tick={{fontSize:11}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={(value) => dateOnly(String(value), { weekday: "long", month: "long", day: "numeric", year: "numeric" })} formatter={(value) => money(Number(value))}/><Area name="درآمد" type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2.5} fill="url(#salesFill)"/></AreaChart></ResponsiveContainer></article>
        <article className="panel insight-panel"><header className="panel-header"><div><h2>پیشنهادهای تصمیم‌گیری</h2><p>تحلیل خودکار داده‌های عملیاتی شما</p></div><Sparkles size={20}/></header><div className="insight-list">{data.insights.map((insight, index) => <div className={`insight insight-${insight.tone}`} key={index}><span>{insight.tone === "warning" || insight.tone === "critical" ? <AlertTriangle/> : insight.tone === "positive" ? <ArrowUpRight/> : <Lightbulb/>}</span><div><strong>{translateInsightTitle(insight.title)}</strong><p>{translateInsightMessage(insight.message)}</p></div></div>)}</div></article>
        <article className="panel chart-panel demand-chart"><header className="panel-header"><div><h2>تقاضا بر اساس ساعت</h2><p>{data.kpis.orders ? `ساعت اوج فروش حدود ${quantity(peak.hour)}:۰۰ است` : "در انتظار ثبت سفارش"}</p></div><Clock3 size={20}/></header><ResponsiveContainer width="100%" height={250}><BarChart data={data.hourly_demand}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8edf4"/><XAxis dataKey="hour" tickFormatter={(v) => `${quantity(v)}:۰۰`} tick={{fontSize:10}} axisLine={false} tickLine={false}/><YAxis tick={{fontSize:11}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={(v) => `${quantity(Number(v))}:۰۰`} formatter={(value) => money(Number(value))}/><Bar name="درآمد" dataKey="revenue" fill="#06b6d4" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer></article>
        <article className="panel chart-panel category-chart"><header className="panel-header"><div><h2>ترکیب درآمد</h2><p>سهم هر دسته از منو</p></div></header>{data.category_performance.length ? <div className="pie-wrap"><ResponsiveContainer width="55%" height={240}><PieChart><Pie data={data.category_performance} dataKey="revenue" nameKey="category" innerRadius={58} outerRadius={90} paddingAngle={3}>{data.category_performance.map((_, index) => <Cell key={index} fill={palette[index % palette.length]}/>)}</Pie><Tooltip formatter={(value) => money(Number(value))}/></PieChart></ResponsiveContainer><div className="chart-legend">{data.category_performance.slice(0,6).map((item,index) => <span key={item.category}><i style={{background:palette[index%palette.length]}}/><b>{item.category}</b><small>{money(item.revenue)}</small></span>)}</div></div> : <EmptyState icon={<PackageSearch/>} title="داده‌ای برای دسته‌بندی‌ها نیست" text="پس از ثبت سفارش، ترکیب درآمد نمایش داده می‌شود."/>}</article>
      </section>
      <section className="panel performance-table"><header className="panel-header"><div><h2>عملکرد محصولات</h2><p>درآمد، تعداد فروش، هزینه و حاشیه سود برآوردی</p></div></header>{data.product_performance.length ? <div className="responsive-table"><table><thead><tr><th>رتبه</th><th>محصول</th><th>تعداد فروش</th><th>درآمد</th><th>هزینه برآوردی</th><th>سود ناخالص</th><th>حاشیه سود</th></tr></thead><tbody>{data.product_performance.map((item,index) => <tr key={item.id}><td><span className={`rank rank-${index+1}`}>{quantity(index+1)}</span></td><td><strong>{item.name}</strong></td><td>{quantity(item.quantity)}</td><td>{money(item.revenue)}</td><td>{money(item.estimated_cost)}</td><td><strong>{money(item.gross_profit)}</strong></td><td><span className={`margin-value ${Number(item.margin_percent)<30 ? "low":""}`}>{quantity(item.margin_percent)}٪</span></td></tr>)}</tbody></table></div> : <EmptyState icon={<BarChart3/>} title="هنوز داده عملکردی وجود ندارد" text="محصولات منو را به دستور پخت متصل کنید و سفارش ثبت کنید تا حاشیه سود دقیق نمایش داده شود."/>}</section>
      <section className="inventory-health-strip"><div><span className="chip-icon blue"><Boxes/></span><span><small>کالاهای فعال</small><strong>{quantity(data.inventory_health.active_items)}</strong></span></div><div><span className="chip-icon amber"><AlertTriangle/></span><span><small>کالاهای کم‌موجودی</small><strong>{quantity(data.inventory_health.low_stock_items)}</strong></span></div><div><span className="chip-icon violet"><PackageSearch/></span><span><small>ارزش موجودی کم‌گردش</small><strong>{money(data.inventory_health.slow_moving_value)}</strong></span></div><div><span className="chip-icon green"><Target/></span><span><small>سفارش مشتریان شناخته‌شده</small><strong>{quantity(data.kpis.known_customer_rate_percent)}٪</strong></span></div></section>
      <DayOrdersHistory />
    </div>
  );
}

function translateInsightTitle(title: string): string {
  const labels: Record<string, string> = {
    "Revenue momentum": "رشد مناسب درآمد",
    "Revenue needs attention": "درآمد نیازمند توجه است",
    "Top revenue product": "محصول برتر از نظر درآمد",
    "Margin opportunity": "فرصت بهبود حاشیه سود",
    "Peak sales hour": "ساعت اوج فروش",
    "Stock risk": "ریسک کمبود موجودی",
    "Idle inventory": "موجودی کم‌گردش",
    "Start collecting signal": "شروع جمع‌آوری داده",
  };
  return labels[title] || title;
}

function translateInsightMessage(message: string): string {
  return message
    .replace(/Revenue grew ([\d.]+)% versus the previous period\./, "درآمد نسبت به دوره قبل $1٪ رشد کرده است.")
    .replace(/Revenue fell ([\d.]+)% versus the previous period\./, "درآمد نسبت به دوره قبل $1٪ کاهش یافته است.")
    .replace(/(.+) generated the most revenue in this period\./, "$1 بیشترین درآمد این دوره را ایجاد کرده است.")
    .replace(/(\d+) product\(s\) have an estimated gross margin below 30%\./, "$1 محصول حاشیه سود ناخالص برآوردی کمتر از ۳۰٪ دارد.")
    .replace(/Sales are strongest around (\d+):00; align staffing and preparation with this window\./, "فروش حوالی ساعت $1:۰۰ بیشترین مقدار را دارد؛ نیروی انسانی و آماده‌سازی را با این بازه هماهنگ کنید.")
    .replace(/(\d+) inventory item\(s\) are at or below their reorder level\./, "$1 کالا در نقطه سفارش یا پایین‌تر از آن قرار دارد.")
    .replace("Some inventory value has had no consumption in the last 30 days; consider purchasing adjustments.", "بخشی از ارزش موجودی در ۳۰ روز اخیر مصرفی نداشته است؛ برنامه خرید را بازبینی کنید.")
    .replace("Record orders and recipe costs to unlock sales and margin recommendations.", "برای دریافت پیشنهادهای فروش و سود، سفارش‌ها و هزینه دستورهای پخت را ثبت کنید.");
}
