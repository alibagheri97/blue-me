import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Award,
  BadgeDollarSign,
  Banknote,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Coins,
  MinusCircle,
  Percent,
  PlusCircle,
  Save,
  ShieldCheck,
  Sparkles,
  Target,
  UserRoundCheck,
  WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { Badge, Button, EmptyState, Spinner } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { businessDate, dateOnly, dateTime, money, quantity } from "../lib/format";
import type {
  CompensationType,
  PayrollCalculation,
  PayrollStatement,
  PointPolicy,
  PointSource,
  StaffPointEntry,
} from "../types";

const pointSourceLabel: Record<PointSource, string> = {
  manual: "امتیاز مدیریتی",
  check_in: "ثبت ورود",
  entry_checklist: "چک‌لیست شروع",
  check_out: "ثبت خروج",
  exit_checklist: "چک‌لیست پایان",
  work_hours: "ساعات حضور",
};

const currentDate = businessDate();
const currentMonthStart = `${currentDate.slice(0, 8)}01`;

function durationLabel(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${quantity(hours)} ساعت و ${quantity(rest)} دقیقه` : `${quantity(rest)} دقیقه`;
}

export default function PayrollPage() {
  const client = useQueryClient();
  const [periodStart, setPeriodStart] = useState(currentMonthStart);
  const [periodEnd, setPeriodEnd] = useState(currentDate);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const calculations = useQuery({
    queryKey: ["payroll", "calculations", periodStart, periodEnd],
    queryFn: () => api<PayrollCalculation[]>(`/payroll/calculations?period_start=${periodStart}&period_end=${periodEnd}`),
    enabled: Boolean(periodStart && periodEnd && periodStart <= periodEnd),
  });
  const policy = useQuery({ queryKey: ["payroll", "policy"], queryFn: () => api<PointPolicy>("/payroll/policy") });
  const points = useQuery({
    queryKey: ["payroll", "points", selectedId],
    queryFn: () => api<StaffPointEntry[]>(`/payroll/points?staff_member_id=${selectedId}&limit=300`),
    enabled: selectedId !== null,
  });
  const statements = useQuery({ queryKey: ["payroll", "statements"], queryFn: () => api<PayrollStatement[]>("/payroll/statements?limit=300") });

  useEffect(() => {
    if (selectedId === null && calculations.data?.length) setSelectedId(calculations.data[0].staff_member.id);
  }, [calculations.data, selectedId]);

  const selected = calculations.data?.find((item) => item.staff_member.id === selectedId) || null;
  const totals = useMemo(() => (calculations.data || []).reduce((acc, item) => ({
    payable: acc.payable + Number(item.payable_total),
    points: acc.points + item.points_total,
    minutes: acc.minutes + item.worked_minutes,
  }), { payable: 0, points: 0, minutes: 0 }), [calculations.data]);
  const periodStatement = statements.data?.find((item) => item.staff_member_id === selectedId && item.period_start === periodStart && item.period_end === periodEnd);

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["payroll"] });
    client.invalidateQueries({ queryKey: ["notifications"] });
  };
  const contractMutation = useMutation({
    mutationFn: ({ staffId, body }: { staffId: number; body: object }) => api(`/payroll/staff/${staffId}/compensation`, { method: "PATCH", body }),
    onSuccess: () => { setError(""); setMessage("قرارداد پرداخت با موفقیت ذخیره شد."); refresh(); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره قرارداد انجام نشد"),
  });
  const pointMutation = useMutation({
    mutationFn: (body: object) => api("/payroll/points", { method: "POST", body }),
    onSuccess: () => { setError(""); setMessage("امتیاز جدید در دفتر عملکرد ثبت شد."); refresh(); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ثبت امتیاز انجام نشد"),
  });
  const policyMutation = useMutation({
    mutationFn: (body: object) => api("/payroll/policy", { method: "PATCH", body }),
    onSuccess: () => { setError(""); setMessage("قواعد امتیازدهی خودکار به‌روزرسانی شد."); refresh(); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره قواعد انجام نشد"),
  });
  const statementMutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => api(path, { method: "POST", body }),
    onSuccess: () => { setError(""); setMessage("وضعیت صورت‌حساب با موفقیت ثبت شد."); refresh(); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ثبت صورت‌حساب انجام نشد"),
  });

  const saveContract = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    contractMutation.mutate({
      staffId: selected.staff_member.id,
      body: {
        pay_type: form.get("pay_type") as CompensationType,
        pay_rate: Number(form.get("pay_rate") || 0),
        point_value: Number(form.get("point_value") || 0),
      },
    });
  };
  const addPoints = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedId) return;
    const form = new FormData(event.currentTarget);
    pointMutation.mutate({ staff_member_id: selectedId, points: Number(form.get("points")), reason: String(form.get("reason") || "").trim() });
    event.currentTarget.reset();
  };
  const savePolicy = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    policyMutation.mutate({
      check_in_points: Number(form.get("check_in_points")),
      entry_checklist_points: Number(form.get("entry_checklist_points")),
      check_out_points: Number(form.get("check_out_points")),
      exit_checklist_points: Number(form.get("exit_checklist_points")),
      work_hour_points: Number(form.get("work_hour_points")),
    });
  };

  if (calculations.isLoading) return <div className="center-loader"><Spinner /></div>;

  return <div className="page-stack payroll-page">
    <header className="page-heading payroll-heading"><div><span className="eyebrow">مدیریت منصفانه، شفاف و انگیزشی</span><h1>حقوق، سهم سود و امتیاز پرسنل</h1><p>هر همکار دقیقاً یک نوع پرداخت دارد: حقوق ثابت یا درصد از سود. عملکرد مثبت و منفی نیز با دفتر امتیاز قابل‌پیگیری روی مبلغ همان دوره اعمال می‌شود.</p></div><span className="payroll-secure"><ShieldCheck /><span><strong>فقط مدیر کل</strong><small>اطلاعات مالی محرمانه</small></span></span></header>

    <section className="payroll-period-bar"><div><CalendarDays /><span><strong>دوره محاسبه</strong><small>روز کاری از ساعت ۰۵:۰۰ تا ۰۵:۰۰ محاسبه می‌شود</small></span></div><label><span>از تاریخ</span><JalaliDatePicker value={periodStart} max={periodEnd} onChange={(next) => { setMessage(""); setPeriodStart(next); }} ariaLabel="شروع دوره به تاریخ شمسی" /></label><label><span>تا تاریخ</span><JalaliDatePicker value={periodEnd} min={periodStart} onChange={(next) => { setMessage(""); setPeriodEnd(next); }} ariaLabel="پایان دوره به تاریخ شمسی" /></label></section>

    {message && <div className="payroll-message success"><CheckCircle2 />{message}<button onClick={() => setMessage("")}>×</button></div>}
    {error && <div className="payroll-message error"><MinusCircle />{error}<button onClick={() => setError("")}>×</button></div>}

    <section className="payroll-summary-grid">
      <article><span className="blue"><WalletCards /></span><div><small>جمع قابل پرداخت دوره</small><strong>{money(totals.payable)}</strong></div></article>
      <article><span className="violet"><Coins /></span><div><small>سود مبنای سهم</small><strong>{money(calculations.data?.[0]?.profit_basis || 0)}</strong></div></article>
      <article><span className={totals.points < 0 ? "red" : "green"}><Sparkles /></span><div><small>خالص امتیاز تیم</small><strong>{totals.points > 0 ? "+" : ""}{quantity(totals.points)}</strong></div></article>
      <article><span className="amber"><Clock3 /></span><div><small>مجموع حضور دوره</small><strong>{durationLabel(totals.minutes)}</strong></div></article>
    </section>

    {calculations.data?.length ? <section className="payroll-workspace">
      <aside className="payroll-staff-list"><header><UserRoundCheck /><div><strong>پرسنل</strong><small>{quantity(calculations.data.length)} قرارداد پرداخت</small></div></header><div>{calculations.data.map((item) => <button key={item.staff_member.id} className={selectedId === item.staff_member.id ? "active" : ""} onClick={() => { setSelectedId(item.staff_member.id); setMessage(""); setError(""); }}><span className="payroll-avatar">{item.staff_member.name.charAt(0)}</span><span><strong>{item.staff_member.name}</strong><small>{item.staff_member.position || "بدون عنوان شغلی"}</small></span><span className="payroll-staff-meta"><Badge tone={item.staff_member.pay_type === "salary" ? "info" : "violet"}>{item.staff_member.pay_type === "salary" ? "حقوق" : "سهم سود"}</Badge><b className={item.points_total < 0 ? "negative" : ""}>{item.points_total > 0 ? "+" : ""}{quantity(item.points_total)}</b></span></button>)}</div></aside>

      {selected && <main className="payroll-detail">
        <header className="payroll-person-head"><span className="payroll-person-avatar">{selected.staff_member.name.charAt(0)}</span><div><small>پرونده پرداخت و عملکرد</small><h2>{selected.staff_member.name}</h2><p>{selected.staff_member.position || "بدون عنوان شغلی"} {selected.staff_member.user ? `· @${selected.staff_member.user.username}` : "· بدون حساب ورود"}</p></div><Badge tone={selected.staff_member.is_active ? "success" : "danger"}>{selected.staff_member.is_active ? "فعال" : "غیرفعال"}</Badge></header>

        <div className="payroll-performance-grid"><article><Target /><span><small>امتیاز خالص</small><strong className={selected.points_total < 0 ? "negative" : "positive"}>{selected.points_total > 0 ? "+" : ""}{quantity(selected.points_total)}</strong></span><small><b>+{quantity(selected.positive_points)}</b> / <em>{quantity(selected.negative_points)}</em></small></article><article><Clock3 /><span><small>ساعت حضور</small><strong>{durationLabel(selected.worked_minutes)}</strong></span><small>{quantity(selected.attendance_count)} شیفت</small></article><article><CheckCircle2 /><span><small>چک‌لیست‌های کامل</small><strong>{quantity(selected.entry_checklists_completed + selected.exit_checklists_completed)}</strong></span><small>شروع {quantity(selected.entry_checklists_completed)} · پایان {quantity(selected.exit_checklists_completed)}</small></article></div>

        <form className="panel compensation-contract" key={`${selected.staff_member.id}-${selected.staff_member.pay_type}-${selected.staff_member.pay_rate}-${selected.staff_member.point_value}`} onSubmit={saveContract}><header><div><BadgeDollarSign /><span><strong>قرارداد پرداخت</strong><small>فقط یکی از دو روش قابل انتخاب است</small></span></div><Badge tone="warning">انحصاری</Badge></header><div className="pay-type-selector"><label><input type="radio" name="pay_type" value="salary" defaultChecked={selected.staff_member.pay_type === "salary"} /><span><Banknote /><strong>حقوق ثابت</strong><small>مبلغ ثابت برای دوره تسویه</small></span></label><label><input type="radio" name="pay_type" value="profit_share" defaultChecked={selected.staff_member.pay_type === "profit_share"} /><span><Percent /><strong>درصد از سود</strong><small>سهم از سود ناخالص واقعی دوره</small></span></label></div><div className="compensation-fields"><label><span>مبلغ حقوق یا درصد سهم</span><input name="pay_rate" type="number" min="0" step="0.01" defaultValue={selected.staff_member.pay_rate} required /><small>برای حقوق: تومان · برای سهم سود: عددی از ۰ تا ۱۰۰</small></label><label><span>ارزش هر امتیاز</span><input name="point_value" type="number" min="0" step="1" defaultValue={selected.staff_member.point_value} required /><small>تومان به‌ازای هر امتیاز مثبت یا منفی</small></label><Button type="submit" disabled={contractMutation.isPending}><Save /> {contractMutation.isPending ? "در حال ذخیره…" : "ذخیره قرارداد"}</Button></div></form>

        <section className="payroll-formula"><div><small>{selected.staff_member.pay_type === "salary" ? "حقوق ثابت" : `${quantity(selected.staff_member.pay_rate)}٪ از سود دوره`}</small><strong>{money(selected.base_compensation)}</strong></div><i>+</i><div><small>اثر {quantity(selected.points_total)} امتیاز</small><strong className={Number(selected.points_adjustment) < 0 ? "negative" : "positive"}>{Number(selected.points_adjustment) > 0 ? "+" : ""}{money(selected.points_adjustment)}</strong></div><i>=</i><div className="payroll-payable"><small>قابل پرداخت</small><strong>{money(selected.payable_total)}</strong></div><Button disabled={statementMutation.isPending || Boolean(periodStatement)} onClick={() => statementMutation.mutate({ path: "/payroll/statements", body: { staff_member_id: selected.staff_member.id, period_start: periodStart, period_end: periodEnd } })}>{periodStatement ? <CheckCircle2 /> : <Save />}{periodStatement ? "صورت‌حساب ثبت شده" : "ثبت صورت‌حساب دوره"}</Button></section>

        <div className="payroll-bottom-grid"><form className="panel manual-point-form" onSubmit={addPoints}><header><Award /><div><strong>امتیاز مدیریتی</strong><small>فقط مدیر می‌تواند امتیاز دلخواه ثبت کند</small></div></header><label><span>امتیاز مثبت یا منفی</span><div className="signed-point-input"><PlusCircle /><input name="points" type="number" min="-1000" max="1000" step="1" required placeholder="مثلاً ۱۰ یا ‎-۵" /><MinusCircle /></div></label><label><span>دلیل شفاف و قابل پیگیری</span><textarea name="reason" minLength={3} maxLength={500} required rows={3} placeholder="مثلاً تحویل دقیق شیفت یا عدم انجام وظیفه…" /></label><Button type="submit" disabled={pointMutation.isPending}><Sparkles /> {pointMutation.isPending ? "در حال ثبت…" : "ثبت در دفتر امتیاز"}</Button></form>

        <section className="panel point-ledger"><header><div><Sparkles /><span><strong>دفتر امتیاز</strong><small>رویدادهای خودکار و مدیریتی</small></span></div><Badge>{quantity(points.data?.length || 0)} رویداد</Badge></header>{points.isLoading ? <div className="center-loader"><Spinner /></div> : points.data?.length ? <div>{points.data.map((entry) => <article key={entry.id}><span className={entry.points > 0 ? "positive" : "negative"}>{entry.points > 0 ? "+" : ""}{quantity(entry.points)}</span><div><strong>{entry.reason}</strong><small>{pointSourceLabel[entry.source]}{entry.created_by ? ` · ${entry.created_by.full_name}` : " · خودکار"}</small></div><time>{dateTime(entry.created_at)}</time></article>)}</div> : <EmptyState icon={<Sparkles />} title="هنوز امتیازی ثبت نشده" text="ورود، خروج، ساعات حضور و امتیازهای مدیریتی اینجا ثبت می‌شوند." />}</section></div>
      </main>}
    </section> : <EmptyState icon={<UserRoundCheck />} title="پرسنلی برای محاسبه وجود ندارد" text="ابتدا در بخش پرسنل، همکاران را ثبت یا حساب کاربری آن‌ها را متصل کنید." />}

    {policy.data && <form className="panel point-policy" key={policy.data.updated_at} onSubmit={savePolicy}><header><span><Target /></span><div><span className="eyebrow">موتور انگیزشی خودکار</span><h2>قواعد دریافت امتیاز</h2><p>امتیاز هر رویداد را تنظیم کنید؛ مقدار صفر یعنی آن رویداد امتیازی ایجاد نمی‌کند.</p></div><Button type="submit" disabled={policyMutation.isPending}><Save /> {policyMutation.isPending ? "در حال ذخیره…" : "ذخیره قواعد"}</Button></header><div><label><LogInIcon /><span>ثبت ورود</span><input name="check_in_points" type="number" min="0" max="100" defaultValue={policy.data.check_in_points} /></label><label><CheckCircle2 /><span>چک‌لیست شروع</span><input name="entry_checklist_points" type="number" min="0" max="100" defaultValue={policy.data.entry_checklist_points} /></label><label><LogOutIcon /><span>ثبت خروج</span><input name="check_out_points" type="number" min="0" max="100" defaultValue={policy.data.check_out_points} /></label><label><CheckCircle2 /><span>چک‌لیست پایان</span><input name="exit_checklist_points" type="number" min="0" max="100" defaultValue={policy.data.exit_checklist_points} /></label><label><Clock3 /><span>هر ساعت کامل حضور</span><input name="work_hour_points" type="number" min="0" max="100" defaultValue={policy.data.work_hour_points} /></label></div></form>}

    <section className="panel payroll-statements"><header><div><WalletCards /><span><h2>دفتر صورت‌حساب‌ها و تسویه</h2><p>هر محاسبه به‌صورت snapshot ذخیره می‌شود تا تغییرات بعدی قرارداد، سابقه را تغییر ندهد.</p></span></div><Badge>{quantity(statements.data?.length || 0)} صورت‌حساب</Badge></header>{statements.isLoading ? <div className="center-loader"><Spinner /></div> : statements.data?.length ? <div className="responsive-table"><table><thead><tr><th>پرسنل</th><th>دوره</th><th>نوع پرداخت</th><th>پایه</th><th>امتیاز</th><th>قابل پرداخت</th><th>وضعیت</th><th /></tr></thead><tbody>{statements.data.map((item) => <tr key={item.id}><td><strong>{item.staff_member.name}</strong><small>{item.staff_member.position || "—"}</small></td><td>{dateOnly(item.period_start)} تا {dateOnly(item.period_end)}</td><td><Badge tone={item.pay_type === "salary" ? "info" : "violet"}>{item.pay_type === "salary" ? "حقوق ثابت" : `${quantity(item.pay_rate)}٪ سود`}</Badge></td><td>{money(item.base_compensation)}</td><td><span className={item.points_total < 0 ? "negative" : "positive"}>{item.points_total > 0 ? "+" : ""}{quantity(item.points_total)}</span></td><td><strong>{money(item.payable_total)}</strong></td><td><Badge tone={item.status === "paid" ? "success" : "warning"}>{item.status === "paid" ? "پرداخت شد" : "پیش‌نویس"}</Badge></td><td>{item.status === "draft" && <Button variant="secondary" disabled={statementMutation.isPending} onClick={() => statementMutation.mutate({ path: `/payroll/statements/${item.id}/pay` })}><Banknote /> ثبت پرداخت</Button>}</td></tr>)}</tbody></table></div> : <EmptyState icon={<WalletCards />} title="هنوز صورت‌حسابی ثبت نشده" text="از پرونده هر پرسنل، محاسبه دوره را بررسی و به‌عنوان صورت‌حساب ذخیره کنید." />}</section>
  </div>;
}

function LogInIcon() {
  return <span className="policy-direction">←</span>;
}

function LogOutIcon() {
  return <span className="policy-direction">→</span>;
}
