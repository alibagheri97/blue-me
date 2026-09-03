import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, ListChecks, Pencil, Plus, Search, Trash2, UserRoundCheck, X } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../lib/api";
import { roleLabel } from "../lib/format";
import type { CheckInChecklistItem, User } from "../types";
import { Badge, Button, EmptyState, Spinner } from "./ui";

export function CheckInChecklistManager() {
  const client = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [phase, setPhase] = useState<"entry" | "exit">("entry");
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [editing, setEditing] = useState<CheckInChecklistItem | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editOrder, setEditOrder] = useState(0);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const users = useQuery({ queryKey: ["users", "check-in-checklists"], queryFn: () => api<User[]>("/users") });
  const activeUsers = useMemo(() => (users.data || []).filter((user) => user.is_active !== false), [users.data]);

  useEffect(() => {
    if (selectedUserId === null && activeUsers.length) setSelectedUserId(activeUsers[0].id);
  }, [activeUsers, selectedUserId]);

  const items = useQuery({
    queryKey: ["check-in-checklists", selectedUserId, phase],
    queryFn: () => api<CheckInChecklistItem[]>(`/attendance/checklists?user_id=${selectedUserId}&phase=${phase}`),
    enabled: selectedUserId !== null,
  });
  const selectedUser = activeUsers.find((user) => user.id === selectedUserId) || null;
  const filteredUsers = activeUsers.filter((user) => {
    const term = search.trim().toLowerCase();
    return !term || user.full_name.toLowerCase().includes(term) || user.username.toLowerCase().includes(term);
  });

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["check-in-checklists"] });
    client.invalidateQueries({ queryKey: ["attendance", "me"] });
  };
  const save = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: "POST" | "PATCH"; body: object }) => api<CheckInChecklistItem>(path, { method, body }),
    onSuccess: () => {
      setError(""); setNewTitle(""); setNewDescription(""); setEditing(null); refresh();
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره چک‌لیست انجام نشد"),
  });
  const remove = useMutation({
    mutationFn: (itemId: number) => api<void>(`/attendance/checklists/${itemId}`, { method: "DELETE" }),
    onSuccess: () => { setError(""); setDeletingId(null); refresh(); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "حذف مورد انجام نشد"),
  });

  const addItem = (event: FormEvent) => {
    event.preventDefault();
    if (!selectedUserId || !newTitle.trim()) return;
    save.mutate({ path: "/attendance/checklists", method: "POST", body: { user_id: selectedUserId, phase, title: newTitle, description: newDescription || null } });
  };
  const beginEdit = (item: CheckInChecklistItem) => {
    setEditing(item); setEditTitle(item.title); setEditDescription(item.description || ""); setEditOrder(item.sort_order); setDeletingId(null); setError("");
  };
  const updateItem = (event: FormEvent) => {
    event.preventDefault();
    if (!editing || !editTitle.trim()) return;
    save.mutate({ path: `/attendance/checklists/${editing.id}`, method: "PATCH", body: { title: editTitle, description: editDescription || null, sort_order: editOrder } });
  };

  return (
    <section className="panel checklist-manager">
      <header className="checklist-manager-head">
        <div className="checklist-manager-title"><span><ListChecks /></span><div><span className="eyebrow">کنترل کامل شروع و پایان شیفت</span><h2>چک‌لیست اختصاصی حضور پرسنل</h2><p>برای هر کاربر دو فهرست مستقل بسازید: یکی پس از ثبت ورود و دیگری درست پیش از ثبت خروج.</p></div></div>
        <div className="checklist-manager-stat"><ClipboardCheck /><span><strong>{(items.data?.length || 0).toLocaleString("fa-IR")}</strong><small>مورد فعال برای کاربر انتخاب‌شده</small></span></div>
      </header>

      <div className="checklist-phase-tabs"><button type="button" className={phase === "entry" ? "active" : ""} onClick={() => { setPhase("entry"); setEditing(null); setDeletingId(null); setError(""); }}><span>۱</span><strong>پس از ثبت ورود</strong><small>تا تکمیل این موارد، فضای کاری باز نمی‌شود</small></button><button type="button" className={phase === "exit" ? "active" : ""} onClick={() => { setPhase("exit"); setEditing(null); setDeletingId(null); setError(""); }}><span>۲</span><strong>پیش از ثبت خروج</strong><small>خروج نهایی بدون تحویل این موارد ممکن نیست</small></button></div>

      <div className="checklist-manager-grid">
        <aside className="checklist-user-picker">
          <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی پرسنل…" /></label>
          <div>{users.isLoading ? <Spinner /> : filteredUsers.map((user) => <button type="button" key={user.id} className={selectedUserId === user.id ? "active" : ""} onClick={() => { setSelectedUserId(user.id); setEditing(null); setDeletingId(null); setError(""); }}><span>{user.full_name.charAt(0)}</span><span><strong>{user.full_name}</strong><small>@{user.username}</small></span><Badge tone={user.role === "root" ? "violet" : "info"}>{roleLabel[user.role]}</Badge></button>)}</div>
        </aside>

        <div className="checklist-editor">
          {selectedUser ? <>
            <header className="checklist-selected-user"><span><UserRoundCheck /></span><div><small>{phase === "entry" ? "موارد شروع کار برای" : "موارد تحویل پایان کار برای"}</small><strong>{selectedUser.full_name}</strong><p>{roleLabel[selectedUser.role]} · @{selectedUser.username}</p></div><Badge tone={(items.data?.length || 0) ? "warning" : "neutral"}>{(items.data?.length || 0) ? phase === "entry" ? "ورود دومرحله‌ای" : "خروج مشروط" : "بدون محدودیت"}</Badge></header>

            <form className="checklist-add-form" onSubmit={addItem}>
              <label><span>عنوان مورد الزامی</span><input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} minLength={2} maxLength={200} required placeholder={phase === "entry" ? "مثلاً کنترل موجودی صندوق" : "مثلاً تحویل صندوق و خاموش‌کردن تجهیزات"} /></label>
              <label><span>توضیح کوتاه <small>(اختیاری)</small></span><input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} maxLength={500} placeholder="دقیقاً چه چیزی باید بررسی شود؟" /></label>
              <Button type="submit" disabled={save.isPending || !newTitle.trim()}><Plus size={17} /> افزودن</Button>
            </form>

            {error && <div className="form-error checklist-manager-error">{error}</div>}
            <div className="checklist-items-list">
              {items.isLoading ? <div className="center-loader"><Spinner /></div> : items.data?.length ? items.data.map((item, index) => editing?.id === item.id ? (
                <form className="checklist-item-edit" key={item.id} onSubmit={updateItem}>
                  <label><span>عنوان</span><input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} required minLength={2} maxLength={200} /></label>
                  <label><span>توضیح</span><input value={editDescription} onChange={(event) => setEditDescription(event.target.value)} maxLength={500} /></label>
                  <label className="checklist-order"><span>ترتیب</span><input type="number" min={0} max={9999} value={editOrder} onChange={(event) => setEditOrder(Number(event.target.value))} /></label>
                  <div><Button type="submit" disabled={save.isPending}>ذخیره</Button><Button type="button" variant="ghost" onClick={() => setEditing(null)}><X size={16} /> انصراف</Button></div>
                </form>
              ) : (
                <article className="checklist-item-row" key={item.id}>
                  <span className="checklist-item-number"><CheckCircle2 />{(index + 1).toLocaleString("fa-IR")}</span>
                  <div><strong>{item.title}</strong><small>{item.description || "بدون توضیح اضافی"}</small></div>
                  {deletingId === item.id ? <div className="checklist-delete-confirm"><span>حذف شود؟</span><button type="button" onClick={() => remove.mutate(item.id)} disabled={remove.isPending}>بله</button><button type="button" onClick={() => setDeletingId(null)}>خیر</button></div> : <div className="checklist-item-actions"><button type="button" onClick={() => beginEdit(item)} title="ویرایش"><Pencil /></button><button type="button" className="danger" onClick={() => { setDeletingId(item.id); setEditing(null); }} title="حذف"><Trash2 /></button></div>}
                </article>
              )) : <EmptyState icon={<ClipboardCheck />} title={`چک‌لیست ${phase === "entry" ? "شروع" : "پایان"} برای این کاربر تعریف نشده`} text={phase === "entry" ? "با افزودن اولین مورد، ابتدا ورود ثبت می‌شود و سپس دسترسی به تکمیل همه موارد وابسته خواهد بود." : "با افزودن اولین مورد، ثبت خروج کاربر به انجام کامل تحویل پایان شیفت وابسته می‌شود."} />}
            </div>
          </> : <EmptyState icon={<UserRoundCheck />} title="کاربری انتخاب نشده" text="یک کاربر فعال را برای مدیریت چک‌لیست انتخاب کنید." />}
        </div>
      </div>
    </section>
  );
}
