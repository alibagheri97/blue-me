import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Clock3,
  History,
  Link2,
  MoreHorizontal,
  Plus,
  Search,
  Soup,
  UserCheck,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { AttendancePanel } from "../components/AttendancePanel";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../lib/api";
import { dateTime, money, quantity, roleLabel, statusLabel } from "../lib/format";
import type { Order, StaffMember, User } from "../types";

function staffPosition(member: StaffMember) {
  return member.position || (member.user ? roleLabel[member.user.role] : "بدون عنوان شغلی");
}

export default function StaffPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const isRoot = user?.role === "root";
  const [params, setParams] = useSearchParams();
  const activeTab = isRoot && params.get("tab") === "attendance" ? "attendance" : "staff";
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<StaffMember | null>(null);
  const [historyMember, setHistoryMember] = useState<StaffMember | null>(null);
  const [error, setError] = useState("");

  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => api<StaffMember[]>("/staff"),
    enabled: activeTab === "staff",
  });
  const users = useQuery({
    queryKey: ["users", "staff-link"],
    queryFn: () => api<User[]>("/users"),
    enabled: isRoot && activeTab === "staff",
  });
  const history = useQuery({
    queryKey: ["staff-orders", historyMember?.id],
    queryFn: () => api<Order[]>(`/staff/${historyMember!.id}/orders?limit=200`),
    enabled: historyMember !== null,
  });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: object }) =>
      api<StaffMember>(path, { method, body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["staff"] });
      setCreating(false);
      setEditing(null);
      setError("");
    },
    onError: (reason) =>
      setError(reason instanceof ApiError ? reason.message : "ذخیره اطلاعات پرسنل انجام نشد"),
  });

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (staff.data || []).filter((member) => {
      const matchesStatus = !status || String(member.is_active) === status;
      const matchesSearch =
        !term ||
        member.name.toLowerCase().includes(term) ||
        member.phone?.toLowerCase().includes(term) ||
        member.position?.toLowerCase().includes(term) ||
        member.user?.username.toLowerCase().includes(term);
      return matchesStatus && matchesSearch;
    });
  }, [staff.data, search, status]);

  const totalMeals = (staff.data || []).reduce((sum, member) => sum + member.meal_count, 0);
  const totalMenuValue = (staff.data || []).reduce(
    (sum, member) => sum + Number(member.menu_value),
    0,
  );
  const totalCost = (staff.data || []).reduce(
    (sum, member) => sum + Number(member.estimated_cost),
    0,
  );

  const save = (event: FormEvent<HTMLFormElement>, member?: StaffMember) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const linkedUser = String(form.get("user_id") || "");
    mutation.mutate({
      path: member ? `/staff/${member.id}` : "/staff",
      method: member ? "PATCH" : "POST",
      body: {
        name: String(form.get("name") || "").trim(),
        phone: String(form.get("phone") || "").trim() || null,
        position: String(form.get("position") || "").trim() || null,
        user_id: linkedUser ? Number(linkedUser) : null,
        notes: String(form.get("notes") || "").trim() || null,
        is_active: form.get("is_active") !== "false",
      },
    });
  };

  const availableUsers = (member?: StaffMember) => {
    const linkedIds = new Set(
      (staff.data || [])
        .filter((item) => item.id !== member?.id && item.user_id !== null)
        .map((item) => item.user_id),
    );
    return (users.data || []).filter((item) => !linkedIds.has(item.id));
  };

  return (
    <div className="page-stack staff-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">{activeTab === "attendance" ? "ثبت دقیق شیفت و حضور" : "حساب غذای پرسنلی"}</span>
          <h1>{activeTab === "attendance" ? "حضور و غیاب پرسنل" : "پرسنل و مصرف داخلی"}</h1>
          <p>{activeTab === "attendance" ? "ورود، خروج، افراد حاضر و مدت کارکرد هر همکار با تاریخچه کامل و قابل پیگیری." : "غذای هر همکار به حساب خودش ثبت و از انبار کم می‌شود، اما وارد فروش، سود و آمار مشتریان نمی‌شود."}</p>
        </div>
        {isRoot && activeTab === "staff" && (
          <Button onClick={() => { setError(""); setCreating(true); }}>
            <Plus size={18} /> افزودن پرسنل
          </Button>
        )}
      </header>

      {isRoot && <div className="tabs staff-tabs"><button className={activeTab === "staff" ? "active" : ""} onClick={() => setParams({})}><UsersRound size={17} /> دفتر پرسنل و غذا</button><button className={activeTab === "attendance" ? "active" : ""} onClick={() => setParams({ tab: "attendance" })}><Clock3 size={17} /> حضور و غیاب</button></div>}

      {activeTab === "staff" ? <>

      <section className="summary-chips staff-summary">
        <div><span className="chip-icon blue"><UsersRound /></span><span><strong>{quantity(staff.data?.filter((item) => item.is_active).length || 0)}</strong><small>پرسنل فعال</small></span></div>
        <div><span className="chip-icon green"><Soup /></span><span><strong>{quantity(totalMeals)}</strong><small>غذای ثبت‌شده</small></span></div>
        <div><span className="chip-icon amber"><WalletCards /></span><span><strong>{money(totalMenuValue)}</strong><small>ارزش منو؛ خارج از فروش</small></span></div>
        <div><span className="chip-icon violet"><BadgeCheck /></span><span><strong>{money(totalCost)}</strong><small>هزینه مواد مصرفی</small></span></div>
      </section>

      <section className="info-callout staff-accounting-note">
        <BadgeCheck size={18} />
        <span><strong>تفکیک کامل حسابداری</strong> سفارش پرسنلی فقط در همین دفتر داخلی دیده می‌شود؛ موجودی و لیست خرید را به‌روز می‌کند ولی KPI فروش و حاشیه سود را تغییر نمی‌دهد.</span>
      </section>

      <section className="panel table-panel">
        <div className="toolbar">
          <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="نام، سمت، تلفن یا نام کاربری…" /></label>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">همه وضعیت‌ها</option>
            <option value="true">فعال</option>
            <option value="false">غیرفعال</option>
          </select>
        </div>
        {staff.isLoading ? <div className="center-loader"><Spinner /></div> : filtered.length ? (
          <div className="responsive-table"><table><thead><tr><th>پرسنل</th><th>اتصال سامانه</th><th>تعداد غذا</th><th>ارزش منو</th><th>هزینه مواد</th><th>آخرین غذا</th><th>وضعیت</th><th /></tr></thead><tbody>
            {filtered.map((member) => <tr key={member.id}>
              <td><div className="person-cell"><span>{member.name.charAt(0)}</span><div><strong>{member.name}{member.is_current_user && <em>خودم</em>}</strong><small>{staffPosition(member)}{member.phone ? ` · ${member.phone}` : ""}</small></div></div></td>
              <td>{member.user ? <span className="staff-user-link"><Link2 size={14} /> @{member.user.username}<small>{roleLabel[member.user.role]}</small></span> : <Badge>بدون ورود</Badge>}</td>
              <td><strong>{quantity(member.meal_count)}</strong></td>
              <td>{money(member.menu_value)}</td>
              <td>{money(member.estimated_cost)}</td>
              <td>{dateTime(member.last_meal_at)}</td>
              <td><Badge tone={member.is_active ? "success" : "danger"}>{member.is_active ? "فعال" : "غیرفعال"}</Badge></td>
              <td><div className="staff-actions"><button className="icon-button" onClick={() => setHistoryMember(member)} title="مشاهده حساب غذا"><History size={18} /></button>{isRoot && <button className="icon-button" onClick={() => { setError(""); setEditing(member); }} title="ویرایش پرسنل"><MoreHorizontal size={18} /></button>}</div></td>
            </tr>)}
          </tbody></table></div>
        ) : <EmptyState icon={<UserCheck />} title="پرسنلی پیدا نشد" text="فیلترها را تغییر دهید یا یک پرسنل جدید ثبت کنید." />}
      </section>

      <Modal open={creating} title="افزودن پرسنل" onClose={() => setCreating(false)}>
        <StaffForm users={availableUsers()} error={error} pending={mutation.isPending} submit={(event) => save(event)} cancel={() => setCreating(false)} />
      </Modal>
      <Modal open={editing !== null} title="ویرایش حساب پرسنل" onClose={() => setEditing(null)}>
        {editing && <StaffForm member={editing} users={availableUsers(editing)} error={error} pending={mutation.isPending} submit={(event) => save(event, editing)} cancel={() => setEditing(null)} />}
      </Modal>
      <Modal open={historyMember !== null} title={`حساب غذای ${historyMember?.name || "پرسنل"}`} onClose={() => setHistoryMember(null)} wide>
        {historyMember && <div className="staff-history">
          <div className="staff-history-summary"><span><small>غذاهای معتبر</small><strong>{quantity(historyMember.meal_count)}</strong></span><span><small>ارزش منو</small><strong>{money(historyMember.menu_value)}</strong></span><span><small>هزینه مواد</small><strong>{money(historyMember.estimated_cost)}</strong></span><Badge tone="violet">خارج از آمار فروش</Badge></div>
          {history.isLoading ? <div className="center-loader"><Spinner /></div> : history.data?.length ? <div className="staff-history-list">{history.data.map((order) => {
            const cost = order.items.reduce((sum, item) => sum + Number(item.line_cost), 0);
            return <article key={order.id} className={order.status === "cancelled" ? "cancelled" : ""}><div><strong>{order.order_number}</strong><Badge tone={order.status === "cancelled" ? "danger" : "info"}>{statusLabel[order.status]}</Badge></div><p>{order.items.map((item) => `${quantity(item.quantity)}× ${item.name}`).join(" · ")}</p><footer><span>{dateTime(order.created_at)}</span><span>ارزش منو <b>{money(order.subtotal)}</b></span><span>هزینه مواد <b>{money(cost)}</b></span></footer></article>;
          })}</div> : <EmptyState icon={<Soup />} title="هنوز غذای پرسنلی ثبت نشده" text="در صندوق، حالت «پرسنل» را انتخاب و سفارش را به نام این شخص ثبت کنید." />}
        </div>}
      </Modal>
      </> : <AttendancePanel />}
    </div>
  );
}

function StaffForm({ member, users, error, pending, submit, cancel }: { member?: StaffMember; users: User[]; error: string; pending: boolean; submit: (event: FormEvent<HTMLFormElement>) => void; cancel: () => void }) {
  return <form className="form-grid" onSubmit={submit}>
    <label className="field field-wide"><span>نام و نام خانوادگی</span><input name="name" required minLength={2} defaultValue={member?.name || ""} placeholder="مثلاً علی رضایی" /></label>
    <label className="field"><span>سمت</span><input name="position" defaultValue={member?.position || ""} placeholder="مثلاً صندوق‌دار" /></label>
    <label className="field"><span>شماره تلفن <small>(اختیاری)</small></span><input name="phone" inputMode="tel" defaultValue={member?.phone || ""} placeholder="۰۹۱۲…" /></label>
    <label className="field field-wide"><span><Link2 size={15} /> اتصال به حساب کاربری <small>(برای انتخاب «خودم»)</small></span><select name="user_id" defaultValue={member?.user_id || ""}><option value="">بدون حساب ورود</option>{users.map((item) => <option key={item.id} value={item.id}>{item.full_name} · @{item.username} · {roleLabel[item.role]}</option>)}</select></label>
    {member && <label className="field field-wide"><span>وضعیت</span><select name="is_active" defaultValue={String(member.is_active)}><option value="true">فعال و قابل انتخاب در صندوق</option><option value="false">غیرفعال</option></select></label>}
    <label className="field field-wide"><span>یادداشت</span><textarea name="notes" rows={3} defaultValue={member?.notes || ""} placeholder="توضیحات داخلی اختیاری…" /></label>
    {error && <div className="form-error field-wide">{error}</div>}
    <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={cancel}>انصراف</Button><Button type="submit" disabled={pending}>{pending ? "در حال ذخیره…" : "ذخیره پرسنل"}</Button></div>
  </form>;
}
