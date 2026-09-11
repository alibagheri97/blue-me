import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Boxes,
  Check,
  ChefHat,
  ClipboardList,
  ContactRound,
  KeyRound,
  LayoutDashboard,
  MoreHorizontal,
  PackagePlus,
  Plus,
  ReceiptText,
  Search,
  ShieldCheck,
  ShoppingCart,
  UserCheck,
  UsersRound,
  UserX,
  UtensilsCrossed,
  WalletCards,
} from "lucide-react";
import { useMemo, useState, type Dispatch, type FormEvent, type SetStateAction } from "react";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import {
  allSectionKeys,
  defaultSectionsForRole,
  effectiveSections,
  sectionDefinitions,
} from "../lib/access";
import { ApiError, api } from "../lib/api";
import { dateTime, roleLabel } from "../lib/format";
import type { Role, SectionKey, User } from "../types";

const managerRoles: Role[] = ["storage_manager", "accounting_manager", "sales_manager", "kitchen_manager"];
const sectionIcons = {
  dashboard: LayoutDashboard,
  staff: ContactRound,
  payroll: WalletCards,
  inventory: Boxes,
  purchases: PackagePlus,
  expenses: ReceiptText,
  menu: UtensilsCrossed,
  pos: ShoppingCart,
  kitchen: ChefHat,
  reports: BarChart3,
  audit: ClipboardList,
} satisfies Record<SectionKey, typeof LayoutDashboard>;

function sectionLabel(section: SectionKey) {
  return sectionDefinitions.find((item) => item.key === section)?.label || section;
}

function AccessEditor({
  role,
  sections,
  setSections,
}: {
  role: Role;
  sections: SectionKey[];
  setSections: Dispatch<SetStateAction<SectionKey[]>>;
}) {
  const toggle = (section: SectionKey) => setSections((current) => (
    current.includes(section)
      ? current.filter((item) => item !== section)
      : [...current, section]
  ));

  return (
    <section className="access-editor field-wide">
      <header className="access-editor-head">
        <div>
          <span className="access-editor-icon"><ShieldCheck /></span>
          <span><strong>دسترسی اختصاصی بخش‌ها</strong><small>هر دسترسی فقط برای همین حساب ذخیره می‌شود.</small></span>
        </div>
        <strong className="access-count">{sections.length.toLocaleString("fa-IR")} از {allSectionKeys.length.toLocaleString("fa-IR")}</strong>
      </header>
      <div className="access-quick-actions">
        <button type="button" onClick={() => setSections(defaultSectionsForRole(role))}>پیشنهاد نقش {roleLabel[role]}</button>
        <button type="button" onClick={() => setSections([...allSectionKeys])}>فعال‌سازی همه</button>
        <button type="button" className="danger" onClick={() => setSections([])}>حذف همه</button>
      </div>
      <div className="access-grid">
        {sectionDefinitions.map((section) => {
          const enabled = sections.includes(section.key);
          const Icon = sectionIcons[section.key];
          return (
            <button
              type="button"
              key={section.key}
              className={`access-card ${enabled ? "is-enabled" : ""} ${section.key === "inventory" ? "is-inventory" : ""}`}
              aria-pressed={enabled}
              onClick={() => toggle(section.key)}
            >
              <span className="access-card-icon"><Icon /></span>
              <span><strong>{section.label}</strong><small>{section.description}</small></span>
              <i>{enabled ? <Check /> : <Plus />}</i>
            </button>
          );
        })}
      </div>
      <p className="access-security-note"><ShieldCheck /> بخش «کاربران و دسترسی» برای امنیت سامانه فقط در اختیار مدیرکل می‌ماند.</p>
    </section>
  );
}

export default function UsersPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const [createRole, setCreateRole] = useState<Role>("accounting_manager");
  const [createSections, setCreateSections] = useState<SectionKey[]>(() => defaultSectionsForRole("accounting_manager"));
  const [editing, setEditing] = useState<User | null>(null);
  const [editRole, setEditRole] = useState<Role>("accounting_manager");
  const [editSections, setEditSections] = useState<SectionKey[]>([]);
  const [error, setError] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body: object }) => api<User>(path, { method, body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["users"] });
      setCreating(false);
      setEditing(null);
      setError("");
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره حساب کاربری انجام نشد"),
  });

  const filtered = useMemo(() => (users.data || []).filter((user) => {
    const term = search.toLowerCase();
    return (!role || user.role === role) && (!term || user.full_name.toLowerCase().includes(term) || user.username.toLowerCase().includes(term));
  }), [users.data, search, role]);

  const openCreate = () => {
    setError("");
    setCreateRole("accounting_manager");
    setCreateSections(defaultSectionsForRole("accounting_manager"));
    setCreating(true);
  };

  const openEdit = (user: User) => {
    setError("");
    setEditRole(user.role);
    setEditSections(effectiveSections(user));
    setEditing(user);
  };

  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    mutation.mutate({
      path: "/users",
      method: "POST",
      body: {
        full_name: form.get("full_name"),
        username: form.get("username"),
        password: form.get("password"),
        role: createRole,
        section_access: createSections,
      },
    });
  };

  const update = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      full_name: form.get("full_name"),
      role: editRole,
      is_active: form.get("is_active") === "true",
      section_access: editSections,
    };
    if (form.get("password")) body.password = form.get("password");
    mutation.mutate({ path: `/users/${editing.id}`, method: "PATCH", body });
  };

  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">هویت و سطح دسترسی</span><h1>کاربران سامانه</h1><p>نقش شغلی و صفحه‌های قابل استفاده هر نفر را مستقل و دقیق مدیریت کنید.</p></div><Button onClick={openCreate}><Plus size={18} /> افزودن مدیر</Button></header>
      <section className="summary-chips">
        <div><span className="chip-icon blue"><UsersRound /></span><span><strong>{users.data?.length || 0}</strong><small>کل حساب‌ها</small></span></div>
        <div><span className="chip-icon green"><UserCheck /></span><span><strong>{users.data?.filter((u) => u.is_active).length || 0}</strong><small>کاربران فعال</small></span></div>
        <div><span className="chip-icon amber"><ShieldCheck /></span><span><strong>{new Set(users.data?.filter((u) => u.role !== "root").map((u) => u.role)).size || 0}</strong><small>نقش‌های مدیریتی فعال</small></span></div>
      </section>
      <section className="panel table-panel">
        <div className="toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجوی نام یا نام کاربری…" /></label><select value={role} onChange={(e) => setRole(e.target.value)}><option value="">همه نقش‌ها</option>{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select></div>
        {users.isLoading ? <div className="center-loader"><Spinner /></div> : filtered.length ? <div className="responsive-table"><table><thead><tr><th>کاربر</th><th>نقش</th><th>دسترسی‌های فعال</th><th>وضعیت</th><th>آخرین ورود</th><th>تاریخ ایجاد</th><th /></tr></thead><tbody>{filtered.map((user) => {
          const access = effectiveSections(user);
          return <tr key={user.id}><td><div className="person-cell"><span>{user.full_name.charAt(0).toUpperCase()}</span><div><strong>{user.full_name}</strong><small>@{user.username}</small></div></div></td><td><Badge tone="info">{roleLabel[user.role]}</Badge></td><td><div className="user-access-summary">{access.slice(0, 3).map((section) => <span key={section}>{sectionLabel(section)}</span>)}{access.length > 3 && <b>+{(access.length - 3).toLocaleString("fa-IR")}</b>}{access.length === 0 && <em>بدون دسترسی</em>}</div></td><td><Badge tone={user.is_active ? "success" : "danger"}>{user.is_active ? "فعال" : "غیرفعال"}</Badge></td><td>{dateTime(user.last_login_at)}</td><td>{dateTime(user.created_at)}</td><td>{user.role !== "root" && <button className="icon-button" onClick={() => openEdit(user)} aria-label="مدیریت کاربر"><MoreHorizontal size={19} /></button>}</td></tr>;
        })}</tbody></table></div> : <EmptyState icon={<UserX />} title="کاربری پیدا نشد" text="فیلترها را تغییر دهید یا یک حساب مدیریتی جدید بسازید." />}
      </section>

      <Modal open={creating} title="ایجاد حساب مدیر و تعیین دسترسی" onClose={() => setCreating(false)} wide>
        <form className="form-grid" onSubmit={create}>
          <label className="field field-wide"><span>نام و نام خانوادگی</span><input name="full_name" required minLength={2} placeholder="مثلاً سارا احمدی" /></label>
          <label className="field"><span>نام کاربری</span><input name="username" required minLength={3} autoComplete="off" placeholder="sara.accounting" /></label>
          <label className="field"><span>نقش کاربر</span><select name="role" required value={createRole} onChange={(event) => { const nextRole = event.target.value as Role; setCreateRole(nextRole); setCreateSections(defaultSectionsForRole(nextRole)); }}>{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select><small>با تغییر نقش، دسترسی پیشنهادی همان نقش انتخاب می‌شود.</small></label>
          <label className="field field-wide"><span>رمز عبور موقت</span><input name="password" type="password" required minLength={8} autoComplete="new-password" placeholder="حداقل ۸ نویسه" /></label>
          <AccessEditor role={createRole} sections={createSections} setSections={setCreateSections} />
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setCreating(false)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ایجاد…" : "ایجاد حساب"}</Button></div>
        </form>
      </Modal>

      <Modal open={!!editing} title="مدیریت حساب و دسترسی اختصاصی" onClose={() => setEditing(null)} wide>
        {editing && <form className="form-grid" onSubmit={update}>
          <label className="field field-wide"><span>نام و نام خانوادگی</span><input name="full_name" required defaultValue={editing.full_name} /></label>
          <label className="field"><span>نقش کاربر</span><select name="role" value={editRole} onChange={(event) => setEditRole(event.target.value as Role)}>{managerRoles.map((item) => <option value={item} key={item}>{roleLabel[item]}</option>)}</select><small>تغییر نقش، انتخاب‌های اختصاصی فعلی را پاک نمی‌کند.</small></label>
          <label className="field"><span>وضعیت حساب</span><select name="is_active" defaultValue={String(editing.is_active)}><option value="true">فعال</option><option value="false">غیرفعال</option></select></label>
          <label className="field field-wide"><span><KeyRound size={15} /> رمز عبور جدید <small>(برای حفظ رمز فعلی خالی بگذارید)</small></span><input name="password" type="password" minLength={8} autoComplete="new-password" placeholder="رمز جدید اختیاری" /></label>
          <AccessEditor role={editRole} sections={editSections} setSections={setEditSections} />
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setEditing(null)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ذخیره…" : "ذخیره تغییرات"}</Button></div>
        </form>}
      </Modal>
    </div>
  );
}
