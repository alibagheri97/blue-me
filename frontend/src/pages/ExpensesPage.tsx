import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownLeft, ArrowUpLeft, Boxes, CalendarDays, ChevronLeft, ChevronRight, Download, FileSearch, Info, PackagePlus, Printer, ReceiptText, RotateCcw, Search, Store, TrendingUp, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { userHasSection } from "../lib/access";
import { api } from "../lib/api";
import { csvCell, type ExpenseItem, type ExpenseLine, type ExpenseOverview, type ExpensePrices, type ExpenseReceipt } from "../lib/expenses";
import { businessDate, dateOnly, dateTime, money, quantity } from "../lib/format";
import type { PurchaseReceipt } from "../types";

type Options = { items: { id: number; name: string; category_id: number | null; is_active: boolean }[]; categories: { id: number; name: string }[]; suppliers: string[] };
const compactMoney = (value: number) => new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export default function ExpensesPage() {
  const { user } = useAuth();
  const [days, setDays] = useState("30");
  const [start, setStart] = useState(businessDate(-29));
  const [end, setEnd] = useState(businessDate());
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [category, setCategory] = useState("");
  const [item, setItem] = useState("");
  const [supplier, setSupplier] = useState("all");
  const [source, setSource] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState("receipts");
  const [ranking, setRanking] = useState("cost");
  const [receipt, setReceipt] = useState<ExpenseReceipt | null>(null);
  const [priceItem, setPriceItem] = useState<ExpenseItem | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  useEffect(() => { const timer = setTimeout(() => { setTerm(search.trim()); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  const params = new URLSearchParams(days === "custom" ? { start_date: start, end_date: end } : { days });
  if (term) params.set("search", term);
  if (category) params.set("category_id", category);
  if (item) params.set("item_id", item);
  if (supplier !== "all") params.set("supplier", supplier === "unknown" ? "" : supplier);
  params.set("source", source);
  const filterKey = params.toString();
  const options = useQuery({ queryKey: ["expenses", "options"], queryFn: () => api<Options>("/expenses/options") });
  const report = useQuery({ queryKey: ["expenses", "overview", filterKey, status, page], queryFn: () => api<ExpenseOverview>(`/expenses?${filterKey}&receipt_status=${status}&page=${page}`) });
  const update = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(1); };
  const reset = () => { setSearch(""); setTerm(""); setCategory(""); setItem(""); setSupplier("all"); setSource("all"); setStatus("all"); setPage(1); };
  const data = report.data;
  const sortedItems = [...(data?.items || [])].sort((a, b) => ranking === "increase" ? Number(b.change_percent || 0) - Number(a.change_percent || 0) : Number(b.total_cost) - Number(a.total_cost));
  const exportCsv = async () => {
    setExporting(true); setExportError("");
    try {
      const result = await api<{ items: ExpenseLine[] }>(`/expenses/export?${filterKey}`);
      const rows: unknown[][] = [["روز کاری", "تاریخ خرید", "رسید", "منبع", "وضعیت", "فروشنده", "شماره فاکتور", "کالا", "مقدار خرید", "واحد خرید", "مقدار انبار", "واحد پایه", "مبلغ کالا (تومان)", "سهم هزینه و تخفیف (تومان)", "بهای نهایی (تومان)", "بهای واحد پایه (تومان)", "ثبت‌کننده", "توضیح"]];
      for (const r of result.items) rows.push([dateOnly(r.business_day), dateOnly(r.purchased_at), r.receipt_number, r.source === "purchase" ? "فاکتور خرید" : "ورود مستقیم", r.status === "posted" ? "قطعی" : "باطل‌شده؛ خارج از جمع", r.supplier_name, r.invoice_number, r.item_name, r.quantity, r.purchase_unit, r.stock_quantity, r.stock_unit, r.line_total, r.allocated_cost, r.landed_total, r.unit_cost, r.created_by, r.notes]);
      const url = URL.createObjectURL(new Blob(["\ufeff" + rows.map(row => row.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8;" }));
      const link = document.createElement("a"); link.href = url; link.download = `هزینه‌ها-${dateOnly(data?.period.start)}-${dateOnly(data?.period.end)}.csv`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setExportError("دریافت خروجی انجام نشد. دوباره تلاش کنید."); }
    finally { setExporting(false); }
  };

  return <div className="page-stack expenses-page">
    <header className="page-heading"><div><span className="eyebrow">کنترل خرید و بهای تأمین</span><h1>هزینه‌ها</h1><p>هر خرید، هر رسید و مسیر تغییر قیمت مواد اولیه؛ در یک نگاه.</p></div><div className="expense-heading-actions"><Button variant="secondary" onClick={exportCsv} disabled={!data || exporting}><Download size={17}/>{exporting ? "آماده‌سازی…" : "خروجی اکسل (CSV)"}</Button>{user && userHasSection(user, "purchases") && <Link className="button button-primary" to="/purchases"><PackagePlus size={17}/>ثبت ورودی کالا</Link>}</div></header>
    <section className="panel expense-filters">
      <div className="expense-period-row"><span><CalendarDays size={19}/><strong>بازه بررسی هزینه‌ها</strong></span><select value={days} onChange={e => update(setDays)(e.target.value)} aria-label="بازه هزینه‌ها"><option value="1">امروز</option><option value="7">۷ روز اخیر</option><option value="30">۳۰ روز اخیر</option><option value="90">۹۰ روز اخیر</option><option value="365">۱۲ ماه اخیر</option><option value="custom">بازه دلخواه / یک روز</option></select>{days === "custom" && <div className="expense-dates"><label><span>از تاریخ</span><JalaliDatePicker value={start} max={end} onChange={update(setStart)} ariaLabel="شروع بازه هزینه‌ها"/></label><label><span>تا تاریخ</span><JalaliDatePicker value={end} min={start} onChange={update(setEnd)} ariaLabel="پایان بازه هزینه‌ها"/></label></div>}</div>
      <div className="expense-filter-grid"><label className="expense-search"><Search size={18}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="جستجوی کالا، فروشنده یا شماره رسید…" aria-label="جستجوی هزینه‌ها"/></label><select value={category} onChange={e => { update(setCategory)(e.target.value); setItem(""); }} aria-label="دسته هزینه"><option value="">همه دسته‌های انبار</option><option value="0">بدون دسته‌بندی</option>{options.data?.categories.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select><select value={item} onChange={e => update(setItem)(e.target.value)} aria-label="کالای هزینه"><option value="">همه کالاها</option>{options.data?.items.filter(i => !category || String(i.category_id || 0) === category).map(i => <option value={i.id} key={i.id}>{i.name}{i.is_active ? "" : " (حذف‌شده)"}</option>)}</select><select value={supplier} onChange={e => update(setSupplier)(e.target.value)} aria-label="فروشنده هزینه"><option value="all">همه فروشندگان</option><option value="unknown">بدون فروشنده</option>{options.data?.suppliers.map(s => <option value={s} key={s}>{s}</option>)}</select><select value={source} onChange={e => update(setSource)(e.target.value)} aria-label="منبع هزینه"><option value="all">فاکتور و ورود مستقیم</option><option value="purchase">فقط فاکتور خرید</option><option value="manual">فقط ورود مستقیم انبار</option></select><button className="icon-button" title="پاک کردن فیلترها" aria-label="پاک کردن فیلترهای هزینه" onClick={reset}><RotateCcw size={18}/></button></div>
      <p className="expense-filter-note">{data ? `${dateOnly(data.period.start)} تا ${dateOnly(data.period.end)} · ` : ""}روز کاری ۰۵:۰۰ تا ۰۵:۰۰ تهران · فیلترها روی همه تحلیل‌ها اعمال می‌شوند.</p>
      {options.isError && <p className="form-error">فهرست فیلترها دریافت نشد. <button onClick={() => options.refetch()}>تلاش مجدد</button></p>}
    </section>
    {exportError && <div className="form-error" role="alert">{exportError}</div>}
    {report.isLoading && <div className="center-loader"><Spinner/></div>}
    {report.isError && <section className="panel"><EmptyState icon={<AlertTriangle/>} title="گزارش هزینه دریافت نشد" text="بازه باید بین ۱ تا ۳۶۵ روز باشد. اتصال را بررسی کنید و دوباره تلاش کنید."/><div className="form-actions"><Button onClick={() => report.refetch()}>تلاش مجدد</Button></div></section>}
    {data && <>
      <section className="metric-grid expense-metrics">
        <article className="metric-card expense-total"><span className="metric-icon"><Wallet/></span><div><small>بهای کل ورودی‌های قطعی</small><strong>{money(data.kpis.total_cost)}</strong><span>{quantity(data.kpis.posted_count)} سند · شامل هزینه جانبی و تخفیف</span></div></article>
        <article className="metric-card"><span className="metric-icon blue"><ReceiptText/></span><div><small>خرید با فاکتور</small><strong>{money(data.kpis.purchase_cost)}</strong><span>{quantity(data.kpis.purchase_count)} فاکتور قطعی</span></div></article>
        <article className="metric-card"><span className="metric-icon mint"><Boxes/></span><div><small>ورود مستقیم انبار</small><strong>{money(data.kpis.manual_cost)}</strong><span>{quantity(data.kpis.manual_count)} ورود بدون فاکتور خرید</span></div></article>
        <article className="metric-card"><span className="metric-icon amber"><TrendingUp/></span><div><small>کالاهای با افزایش قیمت</small><strong>{quantity(data.kpis.price_increases)} <em>کالا</em></strong><span>از {quantity(data.kpis.item_count)} کالا / واحد در این بازه</span></div></article>
      </section>
      <section className="expense-analytics">
        <article className="panel expense-chart"><header className="panel-header"><div><h2>روند هزینه خرید</h2><p>بهای ورودی‌های قطعی به تفکیک روز کاری · تومان</p></div><CalendarDays size={19}/></header>{data.kpis.posted_count ? <ResponsiveContainer width="100%" height={260}><AreaChart data={data.daily.map(d => ({ ...d, cost: Number(d.cost) }))} margin={{ top: 10, right: 12, left: 8, bottom: 0 }}><defs><linearGradient id="expenseFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0d9488" stopOpacity={.28}/><stop offset="100%" stopColor="#0d9488" stopOpacity={.02}/></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="3 4" stroke="#e8edf4"/><XAxis dataKey="date" tickFormatter={v => dateOnly(String(v), { month: "short", day: "numeric" })} axisLine={false} tickLine={false} minTickGap={30} tick={{ fontSize: 11 }}/><YAxis tickFormatter={compactMoney} axisLine={false} tickLine={false} tick={{ fontSize: 11 }}/><Tooltip labelFormatter={v => dateOnly(String(v))} formatter={v => [money(Number(v)), "هزینه"]}/><Area type="monotone" dataKey="cost" stroke="#0d9488" strokeWidth={3} fill="url(#expenseFill)" isAnimationActive={false}/></AreaChart></ResponsiveContainer> : <EmptyState icon={<ReceiptText/>} title="در این بازه خریدی ثبت نشده" text="بازه یا فیلترها را تغییر دهید؛ خرید جدید از ورودی کالا ثبت می‌شود."/>}</article>
        <article className="panel expense-composition"><header className="panel-header"><div><h2>سهم دسته‌های هزینه</h2><p>دسته فعلی کالاهای انبار</p></div><Boxes size={19}/></header><CostBars items={data.categories} total={Number(data.kpis.total_cost)}/></article>
      </section>
      <section className="panel expense-ledger">
        <header className="expense-ledger-header"><div className="expense-tabs" role="tablist" aria-label="نمای هزینه‌ها"><button role="tab" aria-selected={tab === "receipts"} className={tab === "receipts" ? "active" : ""} onClick={() => setTab("receipts")}><ReceiptText size={18}/>رسیدهای هزینه</button><button role="tab" aria-selected={tab === "prices"} className={tab === "prices" ? "active" : ""} onClick={() => setTab("prices")}><TrendingUp size={18}/>قیمت و خرید هر کالا</button></div>{tab === "receipts" ? <label className="expense-list-filter"><span>فقط فهرست رسیدها:</span><select value={status} onChange={e => update(setStatus)(e.target.value)} aria-label="وضعیت رسید هزینه"><option value="all">همه وضعیت‌ها</option><option value="posted">قطعی</option><option value="voided">باطل‌شده</option></select></label> : <select value={ranking} onChange={e => setRanking(e.target.value)} aria-label="مرتب‌سازی قیمت کالا"><option value="cost">بیشترین هزینه خرید</option><option value="increase">بیشترین درصد افزایش قیمت</option></select>}</header>
        {tab === "receipts" ? <>{data.receipts.items.length ? <div className="responsive-table"><table className="expense-table"><thead><tr><th>رسید / روز کاری</th><th>فروشنده و اقلام</th><th>ثبت‌کننده</th><th>مبلغ مطابق فیلتر</th><th>وضعیت</th><th>جزئیات</th></tr></thead><tbody>{data.receipts.items.map(r => <tr key={r.key}><td><strong dir="ltr">{r.receipt_number}</strong><small>{dateOnly(r.business_day)}</small><Badge>{r.source === "purchase" ? "فاکتور خرید" : "ورود مستقیم"}</Badge></td><td><strong>{r.supplier_name || "بدون فروشنده"}</strong><small>{r.item_names.join("، ")}{r.line_count > 3 ? " و…" : ""}</small>{r.invoice_number && <small>فاکتور فروشنده: {r.invoice_number}</small>}</td><td>{r.created_by}</td><td><strong className={r.status === "voided" ? "expense-voided" : ""}>{money(r.matched_cost)}</strong>{Number(r.total_cost) !== Number(r.matched_cost) && <small>کل رسید: {money(r.total_cost)}</small>}</td><td><Badge tone={r.status === "posted" ? "success" : "danger"}>{r.status === "posted" ? "قطعی" : "باطل‌شده"}</Badge></td><td><Button variant="ghost" onClick={() => setReceipt(r)} aria-label={`جزئیات ${r.receipt_number}`}><FileSearch size={17}/>مشاهده</Button></td></tr>)}</tbody></table></div> : <EmptyState icon={<FileSearch/>} title="رسیدی مطابق فیلتر پیدا نشد" text="فیلتر وضعیت، نام کالا یا بازه را تغییر دهید."/>}<Pagination page={page} total={data.receipts.total} pageSize={data.receipts.page_size} onChange={setPage}/></> : <><p className="expense-table-hint">مقایسه اولین و آخرین خرید قطعی همین بازه؛ قیمت‌ها شامل سهم تخفیف و هزینه جانبی هستند. برای تاریخچه دقیق، روی کالا بزنید.</p>{sortedItems.length ? <div className="responsive-table"><table className="expense-table"><thead><tr><th>کالا</th><th>مقدار خرید</th><th>هزینه کل</th><th>اولین قیمت / واحد</th><th>آخرین قیمت / واحد</th><th>تغییر قیمت</th><th>روند</th></tr></thead><tbody>{sortedItems.map(i => <tr key={`${i.item_id}-${i.unit}`}><td><strong>{i.name}</strong><small>{i.category}{!i.is_active ? " · حذف‌شده از انبار فعال" : ""}</small></td><td>{quantity(i.quantity)} {i.unit}<small>{quantity(i.purchases)} خرید</small></td><td><strong>{money(i.total_cost)}</strong></td><td>{money(i.first_price)}<small>هر {i.unit}</small></td><td>{money(i.last_price)}<small>هر {i.unit}</small></td><td><PriceChange count={i.purchases} value={i.change_percent}/></td><td><Button variant="ghost" onClick={() => setPriceItem(i)} aria-label={`روند قیمت ${i.name}`}><TrendingUp size={17}/>تاریخچه</Button></td></tr>)}</tbody></table></div> : <EmptyState icon={<Boxes/>} title="سابقه خریدی در این بازه نیست" text="خریدهای قطعی و ورود مستقیم برای مقایسه قیمت استفاده می‌شوند."/>}</>}
      </section>
      <section className="expense-bottom-grid"><article className="panel"><header className="panel-header"><div><h2>هزینه به تفکیک فروشنده</h2><p>برای شناخت تأمین‌کنندگان اصلی خرید</p></div><Store size={19}/></header><CostBars items={data.suppliers} total={Number(data.kpis.total_cost)}/></article><article className="panel expense-explainer"><span className="chip-icon blue"><Info/></span><h2>این عددها چه معنایی دارند؟</h2><p>مبلغ کالاها: <b>{money(data.kpis.goods_cost)}</b></p><p>خالص هزینه جانبی و تخفیف: <b>{money(data.kpis.net_adjustment)}</b></p><ul><li>{quantity(data.kpis.voided_count)} رسید باطل‌شده در جمع هزینه‌ها و روند قیمت حساب نشده است.</li><li>خرید موجودی، پرداخت نقدی یا هزینه مصرف‌شده نیست؛ وضعیت تسویه فروشنده در این بخش ادعا نمی‌شود.</li><li>سود فروش همچنان با هزینه مواد مصرف‌شده محاسبه می‌شود؛ مبلغ خرید دوباره از سود کم نمی‌شود.</li><li>با فیلتر کالا یا دسته، تنها سهم همان اقلام جمع می‌شود. جزئیات، کل فاکتور اصلی را نشان می‌دهد.</li></ul></article></section>
    </>}
    <ExpenseReceiptModal receipt={receipt} onClose={() => setReceipt(null)}/>
    {priceItem && <PriceHistoryModal key={`${priceItem.item_id}-${priceItem.unit}-${filterKey}`} item={priceItem} filters={filterKey} onClose={() => setPriceItem(null)} onReceipt={r => { setPriceItem(null); setReceipt(r); }}/>} 
  </div>;
}

function CostBars({ items, total }: { items: { name: string; cost: string }[]; total: number }) {
  return items.length ? <div className="expense-cost-bars">{items.map((i, index) => <div key={i.name}><span><i style={{ background: ["#0d9488", "#2563eb", "#8b5cf6", "#f59e0b", "#06b6d4"][index % 5] }}/><strong>{i.name}</strong><small>{quantity(total ? Number(i.cost) / total * 100 : 0)}٪</small></span><b>{money(i.cost)}</b><div className="expense-bar"><i style={{ width: `${total ? Math.min(100, Number(i.cost) / total * 100) : 0}%` }}/></div></div>)}</div> : <EmptyState icon={<Boxes/>} title="بدون داده" text="هزینه‌های قطعی این بازه اینجا نمایش داده می‌شوند."/>;
}

function PriceChange({ count, value }: { count: number; value: string | null | undefined }) {
  if (count < 2) return <Badge>اولین خرید بازه</Badge>;
  if (value === null || value === undefined) return <Badge>مبنای قیمت صفر</Badge>;
  const change = Number(value);
  return <span className={`expense-price-change ${change > 0 ? "up" : change < 0 ? "down" : "flat"}`}>{change > 0 ? <ArrowUpLeft size={15}/> : change < 0 ? <ArrowDownLeft size={15}/> : null}{quantity(Math.abs(change))}٪ {change > 0 ? "افزایش" : change < 0 ? "کاهش" : "بدون تغییر"}</span>;
}

function Pagination({ page, total, pageSize, onChange }: { page: number; total: number; pageSize: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="expense-pagination"><small>{quantity(total)} نتیجه · صفحه {quantity(page)} از {quantity(pages)}</small><span><Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="صفحه قبلی هزینه"><ChevronRight size={16}/></Button><Button variant="secondary" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="صفحه بعدی هزینه"><ChevronLeft size={16}/></Button></span></div>;
}

function ExpenseReceiptModal({ receipt, onClose }: { receipt: ExpenseReceipt | null; onClose: () => void }) {
  const detail = useQuery({ queryKey: ["expenses", "receipt", receipt?.id], queryFn: () => api<PurchaseReceipt>(`/expenses/receipts/${receipt!.id}`), enabled: receipt?.source === "purchase" });
  useEffect(() => { if (receipt) document.body.classList.add("printing-expense"); return () => document.body.classList.remove("printing-expense"); }, [receipt]);
  const r = detail.data;
  return <Modal open={!!receipt} title={`رسید هزینه · ${receipt?.receipt_number || ""}`} onClose={onClose} wide>{receipt && <div className="expense-receipt-detail">
    <div className="expense-receipt-title"><ReceiptText/><div><h2>{receipt.source === "purchase" ? "صورت خرید و ورودی انبار" : "سند ورود مستقیم انبار"}</h2><span dir="ltr">{receipt.receipt_number}</span></div><Badge tone={receipt.status === "posted" ? "success" : "danger"}>{receipt.status === "posted" ? "قطعی" : "باطل‌شده؛ خارج از هزینه"}</Badge></div>
    {receipt.source === "purchase" && detail.isLoading ? <Spinner/> : receipt.source === "purchase" && detail.isError ? <div className="form-error">جزئیات دریافت نشد. <Button variant="secondary" onClick={() => detail.refetch()}>تلاش مجدد</Button></div> : <>
      {receipt.source === "manual" && receipt.manual_line && <div className="expense-price-metrics"><span><small>کالا</small><strong>{receipt.item_names.join("، ")}</strong></span><span><small>مقدار ورود</small><strong>{quantity(receipt.manual_line.quantity)} {receipt.manual_line.unit}</strong></span><span><small>بهای هر {receipt.manual_line.unit}</small><strong>{money(receipt.manual_line.unit_cost)}</strong></span></div>}
      <div className="expense-receipt-meta"><span><small>فروشنده</small><strong>{receipt.supplier_name || "ثبت نشده"}</strong></span><span><small>تاریخ خرید</small><strong>{dateOnly(receipt.purchased_at)}</strong></span><span><small>روز کاری</small><strong>{dateOnly(receipt.business_day)}</strong></span><span><small>فاکتور فروشنده</small><strong>{receipt.invoice_number || "—"}</strong></span></div>
      {receipt.source === "purchase" && r ? <><div className="responsive-table"><table className="expense-table"><thead><tr><th>کالا</th><th>مقدار خرید</th><th>ورودی انبار</th><th>مبلغ کالا</th><th>سهم هزینه / تخفیف</th><th>بهای نهایی</th><th>قیمت واحد پایه</th></tr></thead><tbody>{r.lines.map(line => <tr key={line.id}><td><strong>{line.item_name}</strong></td><td>{quantity(line.quantity)} {line.purchase_unit}</td><td>{quantity(line.stock_quantity)} {line.stock_unit}</td><td>{money(line.line_total)}</td><td>{money(line.allocated_cost)}</td><td><strong>{money(line.landed_total)}</strong></td><td>{money(line.unit_cost)}<small>هر {line.stock_unit}</small></td></tr>)}</tbody></table></div><div className="expense-receipt-totals"><span>جمع کالاها <b>{money(r.subtotal)}</b></span><span>هزینه جانبی <b>{money(r.extra_cost)}</b></span><span>تخفیف <b>{money(r.discount)}</b></span><strong>بهای نهایی فاکتور <b>{money(r.total_cost)}</b></strong></div><p>ثبت توسط {r.created_by.full_name} · {dateTime(r.created_at)}</p>{r.notes && <p className="expense-note">{r.notes}</p>}{r.void_reason && <div className="danger-callout">علت ابطال: {r.void_reason} · {dateTime(r.voided_at)}</div>}</> : <><p className="expense-note">{receipt.item_names.join("، ")}</p><p>{receipt.notes}</p><div className="expense-receipt-totals"><strong>بهای ورودی ثبت‌شده <b>{money(receipt.total_cost)}</b></strong></div><p>ثبت توسط {receipt.created_by} · این سند از گردش مستقیم انبار استخراج شده و فاکتور خرید ندارد.</p></>}
      <div className="form-actions expense-no-print"><Button variant="secondary" onClick={onClose}>بستن</Button><Button onClick={() => window.print()}><Printer size={17}/>چاپ / ذخیره PDF</Button></div>
    </>}
  </div>}</Modal>;
}

function PriceHistoryModal({ item, filters, onClose, onReceipt }: { item: ExpenseItem; filters: string; onClose: () => void; onReceipt: (receipt: ExpenseReceipt) => void }) {
  const [page, setPage] = useState(1);
  const [largeUnit, setLargeUnit] = useState(false);
  const prices = useQuery({ queryKey: ["expenses", "prices", item.item_id, item.unit, filters, page], queryFn: () => api<ExpensePrices>(`/expenses/items/${item.item_id}/prices?${filters}&stock_unit=${encodeURIComponent(item.unit)}&page=${page}`) });
  const canScale = ["گرم", "gram", "g", "میلی‌لیتر", "milliliter", "ml"].includes(item.unit);
  const unit = largeUnit ? (["گرم", "gram", "g"].includes(item.unit) ? "کیلوگرم" : "لیتر") : item.unit;
  const factor = largeUnit ? 1000 : 1;
  const summary = prices.data?.summary;
  return <Modal open title={`تاریخچه قیمت · ${item.name}`} onClose={onClose} wide><div className="expense-price-history"><p className="expense-table-hint">خریدهای قطعی مطابق بازه و فیلترهای صفحه؛ مقایسه بر اساس بهای نهایی هر {unit}. نمودار، آخرین قیمت هر روز را نشان می‌دهد.</p>{canScale && <label className="expense-scale"><input type="checkbox" checked={largeUnit} onChange={e => setLargeUnit(e.target.checked)}/>نمایش قیمت به ازای هر {item.unit === "گرم" || item.unit === "g" || item.unit === "gram" ? "کیلوگرم" : "لیتر"}</label>}
    {prices.isLoading && <Spinner/>}{prices.isError && <div className="form-error">تاریخچه دریافت نشد. <Button onClick={() => prices.refetch()}>تلاش مجدد</Button></div>}
    {summary && prices.data && <><div className="expense-price-metrics"><span><small>کمترین قیمت / {unit}</small><strong>{money(Number(summary.min_price) * factor)}</strong></span><span><small>میانگین وزنی / {unit}</small><strong>{money(Number(summary.average_price) * factor)}</strong></span><span><small>آخرین قیمت / {unit}</small><strong>{money(Number(summary.last_price) * factor)}</strong></span><span><small>تغییر در این بازه</small><PriceChange count={summary.purchases} value={summary.change_percent}/></span></div><div className="expense-price-chart"><ResponsiveContainer width="100%" height={230}><AreaChart data={prices.data.daily.map(d => ({ ...d, price: Number(d.price) * factor }))}><CartesianGrid vertical={false} strokeDasharray="3 4"/><XAxis dataKey="date" tickFormatter={v => dateOnly(String(v), { month: "short", day: "numeric" })} tick={{ fontSize: 11 }} minTickGap={28}/><YAxis tickFormatter={compactMoney} tick={{ fontSize: 11 }}/><Tooltip labelFormatter={v => dateOnly(String(v))} formatter={v => [money(Number(v)), `هر ${unit}`]}/><Area type="stepAfter" dataKey="price" fill="#dbeafe" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 4 }} isAnimationActive={false}/></AreaChart></ResponsiveContainer></div><div className="responsive-table"><table className="expense-table"><thead><tr><th>روز کاری / فروشنده</th><th>مقدار خرید</th><th>بهای نهایی</th><th>قیمت هر {unit}</th><th>تغییر نسبت به خرید قبل</th><th>رسید</th></tr></thead><tbody>{prices.data.items.map(r => <tr key={`${r.source}-${r.line_id}`}><td>{dateOnly(r.business_day)}<small>{r.supplier_name || "بدون فروشنده"}</small></td><td>{quantity(r.quantity)} {r.purchase_unit}</td><td>{money(r.landed_total)}</td><td><strong>{money(Number(r.unit_cost) * factor)}</strong></td><td><PriceChange count={r.change === null ? 1 : 2} value={r.change_percent}/></td><td>{r.source === "purchase" ? <button className="expense-receipt-link" onClick={() => onReceipt({ key: `purchase:${r.source_id}`, source: "purchase", id: r.source_id, receipt_number: r.receipt_number, supplier_name: r.supplier_name, invoice_number: r.invoice_number, purchased_at: r.purchased_at, business_day: r.business_day, status: "posted", total_cost: r.landed_total, matched_cost: r.landed_total, line_count: 1, item_names: [r.item_name], created_by: r.created_by, notes: r.notes })}>{r.receipt_number}</button> : <Badge>ورود مستقیم</Badge>}</td></tr>)}</tbody></table></div><Pagination page={page} total={prices.data.total} pageSize={prices.data.page_size} onChange={setPage}/></>}
    {prices.data && !summary && <EmptyState icon={<TrendingUp/>} title="خریدی پیدا نشد" text="بازه یا فیلترهای انتخاب‌شده را تغییر دهید."/>}
  </div></Modal>;
}
