import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  Clock3,
  DoorOpen,
  LogIn,
  LogOut,
  Search,
  Timer,
  UserCheck,
  UsersRound,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { businessDate, dateTime, quantity } from "../lib/format";
import type { AttendanceOverview, AttendanceRecord } from "../types";
import { Badge, EmptyState, Spinner } from "./ui";

function rangeStart(days: number) {
  return businessDate(-days + 1);
}

function durationLabel(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${quantity(rest)} دقیقه`;
  if (!rest) return `${quantity(hours)} ساعت`;
  return `${quantity(hours)} ساعت و ${quantity(rest)} دقیقه`;
}

function staffPosition(record: AttendanceRecord) {
  return record.staff_member.position || "بدون عنوان شغلی";
}

export function AttendancePanel() {
  const [days, setDays] = useState(30);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"" | "open" | "closed">("");
  const dateFrom = rangeStart(days);
  const dateTo = businessDate();
  const overview = useQuery({
    queryKey: ["attendance", "overview", dateFrom, dateTo],
    queryFn: () => api<AttendanceOverview>(`/attendance?date_from=${dateFrom}&date_to=${dateTo}&limit=1000`),
    refetchInterval: 30_000,
  });
  const records = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (overview.data?.items || []).filter((record) => {
      const matchesStatus = !status || (status === "open" ? record.is_open : !record.is_open);
      const matchesSearch = !term || record.staff_member.name.toLowerCase().includes(term) || record.staff_member.position?.toLowerCase().includes(term);
      return matchesStatus && matchesSearch;
    });
  }, [overview.data?.items, search, status]);
  const present = overview.data?.items.filter((record) => record.is_open) || [];

  if (overview.isLoading) return <div className="center-loader"><Spinner /></div>;
  if (!overview.data) return <EmptyState icon={<Clock3 />} title="اطلاعات حضور در دسترس نیست" text="اتصال سامانه را بررسی و دوباره تلاش کنید." />;
  const data = overview.data;

  return <div className="attendance-workspace">
    <section className="summary-chips attendance-summary">
      <div><span className="chip-icon green"><UserCheck /></span><span><strong>{quantity(data.present_count)}</strong><small>حاضر در مجموعه</small></span></div>
      <div><span className="chip-icon blue"><LogIn /></span><span><strong>{quantity(data.check_ins_today)}</strong><small>ورود ثبت‌شده امروز</small></span></div>
      <div><span className="chip-icon amber"><LogOut /></span><span><strong>{quantity(data.completed_today)}</strong><small>خروج ثبت‌شده امروز</small></span></div>
      <div><span className="chip-icon violet"><Timer /></span><span><strong>{durationLabel(data.worked_minutes_today)}</strong><small>مجموع حضور امروز</small></span></div>
    </section>

    <section className="panel attendance-present-panel">
      <header className="panel-header"><div><h2>افراد حاضر</h2><p>شیفت‌های باز و در حال محاسبه به‌صورت زنده</p></div><Badge tone={present.length ? "success" : "neutral"}>{quantity(present.length)} نفر</Badge></header>
      {present.length ? <div className="attendance-present-list">{present.map((record) => <article key={record.id}><span className="attendance-avatar">{record.staff_member.name.charAt(0)}</span><div><strong>{record.staff_member.name}</strong><small>{staffPosition(record)}</small></div><span><small>زمان ورود</small><b>{dateTime(record.checked_in_at)}</b></span><span><small>مدت حضور</small><b>{durationLabel(record.duration_minutes)}</b></span><i /></article>)}</div> : <EmptyState icon={<DoorOpen />} title="در حال حاضر کسی ورود ثبت‌شده ندارد" text="پس از ثبت ورود همکاران، وضعیت زنده آن‌ها اینجا نمایش داده می‌شود." />}
    </section>

    <section className="panel attendance-history-panel">
      <header className="panel-header"><div><h2>دفتر رویدادهای حضور و غیاب</h2><p>هر ورود و خروج با زمان دقیق، مدت حضور و حساب کاربری ثبت‌کننده ذخیره می‌شود.</p></div><span className="attendance-live"><i /> به‌روزرسانی خودکار</span></header>
      <div className="toolbar attendance-toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی نام یا سمت…" /></label><label className="select-with-icon"><CalendarDays size={16} /><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>۷ روز اخیر</option><option value={30}>۳۰ روز اخیر</option><option value={90}>۹۰ روز اخیر</option><option value={365}>یک سال اخیر</option></select></label><select value={status} onChange={(event) => setStatus(event.target.value as "" | "open" | "closed")}><option value="">همه رویدادها</option><option value="open">حاضر / شیفت باز</option><option value="closed">خروج ثبت‌شده</option></select></div>
      {records.length ? <div className="responsive-table"><table><thead><tr><th>پرسنل</th><th>ورود</th><th>خروج</th><th>چک‌لیست شروع / پایان</th><th>مدت حضور</th><th>وضعیت</th></tr></thead><tbody>{records.map((record) => { const entryCount = record.checklist_completions.filter((item) => item.phase === "entry").length; const exitCount = record.checklist_completions.filter((item) => item.phase === "exit").length; return <tr key={record.id}><td><div className="person-cell"><span>{record.staff_member.name.charAt(0)}</span><div><strong>{record.staff_member.name}</strong><small>{staffPosition(record)}</small></div></div></td><td><span className="attendance-time-cell check-in-time"><LogIn size={15} />{dateTime(record.checked_in_at)}</span></td><td>{record.checked_out_at ? <span className="attendance-time-cell check-out-time"><LogOut size={15} />{dateTime(record.checked_out_at)}</span> : <span className="attendance-open-label">هنوز حاضر است</span>}</td><td><span className="attendance-checklist-badges">{entryCount ? <Badge tone="success">شروع: {entryCount.toLocaleString("fa-IR")}</Badge> : <Badge>شروع: بدون مورد</Badge>}{exitCount ? <Badge tone="info">پایان: {exitCount.toLocaleString("fa-IR")}</Badge> : <Badge>{record.is_open ? "پایان: در انتظار" : "پایان: بدون مورد"}</Badge>}</span></td><td><strong>{durationLabel(record.duration_minutes)}</strong></td><td><Badge tone={record.is_open ? "success" : "neutral"}>{record.is_open ? "حاضر" : "خروج ثبت شد"}</Badge></td></tr>; })}</tbody></table></div> : <EmptyState icon={<UsersRound />} title="رویدادی با این فیلتر پیدا نشد" text="بازه زمانی، وضعیت یا عبارت جست‌وجو را تغییر دهید." />}
    </section>
  </div>;
}
