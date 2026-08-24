import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, MoreHorizontal, Plus, Search, ShieldCheck, UserCheck, UsersRound, UserX } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { dateTime, roleLabel } from "../lib/format";
import type { Role, User } from "../types";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";

const managerRoles: Role[] = ["storage_manager", "accounting_manager", "sales_manager", "kitchen_manager"];

export default function UsersPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [error, setError] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body: object }) => api<User>(path, { method, body }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["users"] }); setCreating(false); setEditing(null); setError(""); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره حساب کاربری انجام نشد"),
  });

  const filtered = useMemo(() => (users.data || []).filter((user) => {
    const term = search.toLowerCase();
    return (!role || user.role === role) && (!term || user.full_name.toLowerCase().includes(term) || user.username.toLowerCase().includes(term));
  }), [users.data, search, role]);

  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    mutation.mutate({ path: "/users", method: "POST", body: Object.fromEntries(form) });
  };

  const update = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = { full_name: form.get("full_name"), role: form.get("role"), is_active: form.get("is_active") === "true" };
    if (form.get("password")) body.password = form.get("password");
    mutation.mutate({ path: `/users/${editing.id}`, method: "PATCH", body });
  };

  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">هویت و سطح دسترسی</span><h1>کاربران سامانه</h1><p>برای هر مدیر حساب اختصاصی بسازید و مسئولیت‌ها را شفاف نگه دارید.</p></div><Button onClick={() => { setError(""); setCreating(true); }}><Plus size={18} /> افزودن مدیر</Button></header>
      <section className="summary-chips">
        <div><span className="chip-icon blue"><UsersRound /></span><span><strong>{users.data?.length || 0}</strong><small>کل حساب‌ها</small></span></div>
        <div><span className="chip-icon green"><UserCheck /></span><span><strong>{users.data?.filter((u) => u.is_active).length || 0}</strong><small>کاربران فعال</small></span></div>
        <div><span className="chip-icon amber"><ShieldCheck /></span><span><strong>{new Set(users.data?.filter((u) => u.role !== "root").map((u) => u.role)).size || 0}</strong><small>نقش‌های مدیریتی فعال</small></span></div>
      </section>
      <section className="panel table-panel">
        <div className="toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجوی نام یا نام کاربری…" /></label><select value={role} onChange={(e) => setRole(e.target.value)}><option value="">همه نقش‌ها</option>{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select></div>
        {users.isLoading ? <div className="center-loader"><Spinner /></div> : filtered.length ? <div className="responsive-table"><table><thead><tr><th>کاربر</th><th>نقش</th><th>وضعیت</th><th>آخرین ورود</th><th>تاریخ ایجاد</th><th /></tr></thead><tbody>{filtered.map((user) => <tr key={user.id}><td><div className="person-cell"><span>{user.full_name.charAt(0).toUpperCase()}</span><div><strong>{user.full_name}</strong><small>@{user.username}</small></div></div></td><td><Badge tone="info">{roleLabel[user.role]}</Badge></td><td><Badge tone={user.is_active ? "success" : "danger"}>{user.is_active ? "فعال" : "غیرفعال"}</Badge></td><td>{dateTime(user.last_login_at)}</td><td>{dateTime(user.created_at)}</td><td>{user.role !== "root" && <button className="icon-button" onClick={() => { setError(""); setEditing(user); }} aria-label="مدیریت کاربر"><MoreHorizontal size={19} /></button>}</td></tr>)}</tbody></table></div> : <EmptyState icon={<UserX />} title="کاربری پیدا نشد" text="فیلترها را تغییر دهید یا یک حساب مدیریتی جدید بسازید." />}
      </section>

      <Modal open={creating} title="ایجاد حساب مدیر" onClose={() => setCreating(false)}>
        <form className="form-grid" onSubmit={create}>
          <label className="field field-wide"><span>نام و نام خانوادگی</span><input name="full_name" required minLength={2} placeholder="مثلاً سارا احمدی" /></label>
          <label className="field"><span>نام کاربری</span><input name="username" required minLength={3} autoComplete="off" placeholder="sara.accounting" /></label>
          <label className="field"><span>نقش کاربر</span><select name="role" required defaultValue="accounting_manager">{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select></label>
          <label className="field field-wide"><span>رمز عبور موقت</span><input name="password" type="password" required minLength={8} autoComplete="new-password" placeholder="حداقل ۸ نویسه" /></label>
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setCreating(false)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ایجاد…" : "ایجاد حساب"}</Button></div>
        </form>
      </Modal>

      <Modal open={!!editing} title="مدیریت حساب کاربری" onClose={() => setEditing(null)}>
        {editing && <form className="form-grid" onSubmit={update}>
          <label className="field field-wide"><span>نام و نام خانوادگی</span><input name="full_name" required defaultValue={editing.full_name} /></label>
          <label className="field"><span>نقش کاربر</span><select name="role" defaultValue={editing.role}>{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select></label>
          <label className="field"><span>وضعیت حساب</span><select name="is_active" defaultValue={String(editing.is_active)}><option value="true">فعال</option><option value="false">غیرفعال</option></select></label>
          <label className="field field-wide"><span><KeyRound size={15} /> رمز عبور جدید <small>(برای حفظ رمز فعلی خالی بگذارید)</small></span><input name="password" type="password" minLength={8} autoComplete="new-password" placeholder="رمز جدید اختیاری" /></label>
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setEditing(null)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ذخیره…" : "ذخیره تغییرات"}</Button></div>
        </form>}
      </Modal>
    </div>
  );
}
