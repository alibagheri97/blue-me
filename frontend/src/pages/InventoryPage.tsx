import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownToLine, Boxes, Camera, Check, ChevronRight, CircleDollarSign, Layers3, MoreHorizontal, PackageOpen, Plus, Search, SlidersHorizontal, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api, assetUrl } from "../lib/api";
import { dateTime, money, quantity, statusLabel } from "../lib/format";
import { normalizedUnitPrice, unitChoices } from "../lib/units";
import type { Category, InventoryItem, User } from "../types";

interface ItemPage { items: InventoryItem[]; total: number; page: number; page_size: number }
interface PriceRequest { id: number; item_id: number; price_type: "purchase" | "selling"; old_price: string; requested_price: string; package_quantity: string | null; package_unit: string | null; package_total_price: string | null; reason: string; status: "pending" | "approved" | "rejected" | "cancelled"; requested_by: User; created_at: string; item: InventoryItem; decision_note: string | null }
interface Movement { id: number; movement_type: string; quantity: string; unit_cost: string | null; quantity_before: string; quantity_after: string; reason: string; created_at: string }
interface ItemReport { stock_value: string; units_used_90d: string; average_daily_use: string; estimated_days_remaining: string | null; daily_activity: Array<{ date: string; received: string; used: string; waste: string }>; price_history: Array<{ date: string; price_type: "purchase" | "selling"; old_price: string; new_price: string }> }

export default function InventoryPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [tab, setTab] = useState<"stock" | "approvals">("stock");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [lowStock, setLowStock] = useState(false);
  const [itemForm, setItemForm] = useState<InventoryItem | "new" | null>(null);
  const [formUnit, setFormUnit] = useState("عدد");
  const [purchaseQuantity, setPurchaseQuantity] = useState("1");
  const [purchaseUnit, setPurchaseUnit] = useState("عدد");
  const [purchasePrice, setPurchasePrice] = useState("0");
  const [sellingQuantity, setSellingQuantity] = useState("1");
  const [sellingUnit, setSellingUnit] = useState("عدد");
  const [sellingPrice, setSellingPrice] = useState("0");
  const [movementItem, setMovementItem] = useState<InventoryItem | null>(null);
  const [detailItem, setDetailItem] = useState<InventoryItem | null>(null);
  const [categoryModal, setCategoryModal] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (itemForm === "new") {
      setFormUnit("عدد");
      setPurchaseQuantity("1");
      setPurchaseUnit("عدد");
      setPurchasePrice("0");
      setSellingQuantity("1");
      setSellingUnit("عدد");
      setSellingPrice("0");
    } else if (itemForm) {
      setFormUnit(itemForm.unit);
      setPurchaseQuantity(itemForm.purchase_quantity || "1");
      setPurchaseUnit(itemForm.purchase_unit || itemForm.unit);
      setPurchasePrice(itemForm.purchase_total_price || itemForm.last_purchase_price || "0");
      setSellingQuantity(itemForm.selling_quantity || "1");
      setSellingUnit(itemForm.selling_unit || itemForm.unit);
      setSellingPrice(itemForm.selling_total_price || itemForm.selling_price || "0");
    }
  }, [itemForm]);

  const params = new URLSearchParams({ page_size: "100", active: "true" });
  if (search) params.set("search", search);
  if (category) params.set("category_id", category);
  if (lowStock) params.set("low_stock", "true");
  const items = useQuery({ queryKey: ["inventory", search, category, lowStock], queryFn: () => api<ItemPage>(`/inventory/items?${params}`) });
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/inventory/categories") });
  const approvals = useQuery({ queryKey: ["price-requests"], queryFn: () => api<PriceRequest[]>("/inventory/price-requests"), enabled: tab === "approvals" });
  const invalidate = () => { client.invalidateQueries({ queryKey: ["inventory"] }); client.invalidateQueries({ queryKey: ["price-requests"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); };
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: object | FormData }) => api(path, { method, body }),
    onSuccess: () => { invalidate(); setItemForm(null); setMovementItem(null); setError(""); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "انجام عملیات ممکن نشد"),
  });

  const totalValue = useMemo(() => (items.data?.items || []).reduce((total, item) => total + Number(item.current_quantity) * Number(item.average_cost), 0), [items.data]);
  const lowCount = (items.data?.items || []).filter((item) => Number(item.current_quantity) <= Number(item.reorder_level)).length;

  const saveItem = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      sku: form.get("sku"), name: form.get("name"), category_id: form.get("category_id") ? Number(form.get("category_id")) : null,
      unit: form.get("unit"), reorder_level: form.get("reorder_level"), target_stock_level: form.get("target_stock_level"), auto_reorder_enabled: form.get("auto_reorder_enabled") === "on", description: form.get("description") || null,
      purchase_quantity: purchaseQuantity, purchase_unit: purchaseUnit, purchase_price: purchasePrice || 0,
      selling_quantity: sellingQuantity, selling_unit: sellingUnit, selling_price: sellingPrice || 0,
    };
    if (itemForm !== "new") body.price_change_reason = form.get("price_change_reason") || null;
    mutation.mutate({ path: itemForm === "new" ? "/inventory/items" : `/inventory/items/${itemForm!.id}`, method: itemForm === "new" ? "POST" : "PATCH", body });
  };

  const saveMovement = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!movementItem) return;
    const form = new FormData(event.currentTarget);
    mutation.mutate({ path: `/inventory/items/${movementItem.id}/movements`, method: "POST", body: { movement_type: form.get("movement_type"), quantity: form.get("quantity"), unit_cost: form.get("unit_cost") || null, reason: form.get("reason") } });
  };

  const decide = (id: number, status: "approved" | "rejected") => mutation.mutate({ path: `/inventory/price-requests/${id}/decision`, method: "POST", body: { status } });
  const pricingUnit = formUnit.trim() || "واحد پایه";
  const purchaseUnitPrice = normalizedUnitPrice(purchasePrice, purchaseQuantity, purchaseUnit, pricingUnit);
  const sellingUnitPrice = normalizedUnitPrice(sellingPrice, sellingQuantity, sellingUnit, pricingUnit);
  const changeBaseUnit = (nextUnit: string) => {
    setFormUnit(nextUnit);
    const choices = unitChoices(nextUnit);
    if (!choices.includes(purchaseUnit)) setPurchaseUnit(nextUnit);
    if (!choices.includes(sellingUnit)) setSellingUnit(nextUnit);
  };

  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">کنترل موجودی</span><h1>مدیریت انبار</h1><p>موجودی دقیق، سابقه هزینه، کنترل قیمت و گزارش اختصاصی هر کالا.</p></div><div className="heading-actions"><Button variant="secondary" onClick={() => setCategoryModal(true)}><Layers3 size={18} /> دسته‌بندی‌ها</Button><Button onClick={() => { setError(""); setItemForm("new"); }}><Plus size={18} /> کالای جدید</Button></div></header>
      <div className="tabs"><button className={tab === "stock" ? "active" : ""} onClick={() => setTab("stock")}>فهرست موجودی</button><button className={tab === "approvals" ? "active" : ""} onClick={() => setTab("approvals")}>تأیید قیمت‌ها {(approvals.data?.filter((item) => item.status === "pending").length || 0) > 0 && <span>{approvals.data?.filter((item) => item.status === "pending").length}</span>}</button></div>

      {tab === "stock" ? <>
        <section className="summary-chips inventory-summary">
          <div><span className="chip-icon blue"><Boxes /></span><span><strong>{quantity(items.data?.total || 0)}</strong><small>کالای فعال</small></span></div>
          <div><span className="chip-icon green"><CircleDollarSign /></span><span><strong>{money(totalValue)}</strong><small>ارزش موجودی نمایش‌داده‌شده</small></span></div>
          <div><span className="chip-icon amber"><AlertTriangle /></span><span><strong>{quantity(lowCount)}</strong><small>نیازمند تأمین</small></span></div>
        </section>
        <section className="panel catalogue-panel">
          <div className="toolbar inventory-toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجوی نام یا کد کالا…" /></label><select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">همه دسته‌بندی‌ها</option>{categories.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className={`filter-toggle ${lowStock ? "active" : ""}`} onClick={() => setLowStock(!lowStock)}><SlidersHorizontal size={17} /> فقط کم‌موجودی</button></div>
          {items.isLoading ? <div className="center-loader"><Spinner /></div> : items.data?.items.length ? <div className="inventory-grid">{items.data.items.map((item) => { const isLow = Number(item.current_quantity) <= Number(item.reorder_level); return <article className="inventory-card" key={item.id}>
            <button className="item-image" onClick={() => setDetailItem(item)}>{assetUrl(item.image_path) ? <img src={assetUrl(item.image_path)} alt="" /> : <PackageOpen size={30} />}{isLow && <Badge tone="danger">موجودی کم</Badge>}{item.auto_reorder_enabled && <Badge tone="info">خرید خودکار</Badge>}</button>
            <div className="item-card-body"><div className="item-title"><span style={{ background: item.category?.color || "#94a3b8" }} /><div><h3>{item.name}</h3><small>{item.sku} · {item.category?.name || "بدون دسته‌بندی"}</small></div><button className="icon-button" onClick={() => setDetailItem(item)}><MoreHorizontal size={19} /></button></div>
            <div className="item-quantities"><span><small>موجودی</small><strong>{quantity(item.current_quantity)} <i>{item.unit}</i></strong></span><span><small>آخرین خرید</small><strong>{quantity(item.purchase_quantity)} {item.purchase_unit}</strong><em>{money(item.purchase_total_price)}</em></span><span><small>قیمت فروش</small><strong>{quantity(item.selling_quantity)} {item.selling_unit}</strong><em>{money(item.selling_total_price)}</em></span></div>
            <div className="item-actions"><button onClick={() => { setError(""); setMovementItem(item); }}><ArrowDownToLine size={16} /> موجودی</button><button onClick={() => { setError(""); setItemForm(item); }}><CircleDollarSign size={16} /> قیمت</button><button onClick={() => { setError(""); setItemForm(item); }}>ویرایش <ChevronRight size={15} /></button></div></div>
          </article>; })}</div> : <EmptyState icon={<PackageOpen />} title="کالایی پیدا نشد" text="اولین کالا را بسازید یا فیلترها را تغییر دهید." />}
        </section>
      </> : <section className="panel approvals-panel">
        <header className="panel-header"><div><h2>کنترل تغییر قیمت</h2><p>هر پیشنهاد مدیر انبار تا زمان تصمیم مدیر کل، دقیق و قابل پیگیری می‌ماند.</p></div></header>
        {approvals.isLoading ? <div className="center-loader"><Spinner /></div> : approvals.data?.length ? <div className="approval-list">{approvals.data.map((request) => <article key={request.id} className="approval-row"><div className="approval-product"><div className="mini-product">{request.item.image_path ? <img src={assetUrl(request.item.image_path)} alt="" /> : <CircleDollarSign />}</div><div><strong>{request.item.name}</strong><small>{request.price_type === "purchase" ? "قیمت خرید" : "قیمت فروش"} · درخواست {request.requested_by.full_name}</small></div></div><div className="price-delta"><span><small>قیمت فعلی هر {request.item.unit}</small>{money(request.old_price)}</span><ArrowDownToLine size={18} /><span><small>پیشنهاد جدید</small><strong>{request.package_total_price !== null ? `${money(request.package_total_price)} برای ${quantity(request.package_quantity)} ${request.package_unit}` : `${money(request.requested_price)} برای هر ${request.item.unit}`}</strong></span></div><div className="approval-reason"><small>دلیل تغییر</small><span>{request.reason}</span><small>{dateTime(request.created_at)}</small></div><Badge tone={request.status === "approved" ? "success" : request.status === "rejected" || request.status === "cancelled" ? "danger" : "warning"}>{statusLabel[request.status]}</Badge>{request.status === "pending" && user?.role === "root" && <div className="approval-actions"><button className="approve" title="تأیید" onClick={() => decide(request.id, "approved")}><Check size={17} /></button><button className="reject" title="رد" onClick={() => decide(request.id, "rejected")}><X size={17} /></button></div>}</article>)}</div> : <EmptyState icon={<Check />} title="درخواست قیمتی وجود ندارد" text="در حال حاضر پیشنهاد قیمتی برای بررسی ثبت نشده است." />}
      </section>}

      <Modal open={itemForm !== null} title={itemForm === "new" ? "ایجاد کالای انبار" : "ویرایش کالای انبار"} onClose={() => setItemForm(null)} wide>
        <form className="form-grid" onSubmit={saveItem}>
          <label className="field"><span>نام کالا</span><input name="name" required defaultValue={itemForm !== "new" && itemForm ? itemForm.name : ""} /></label>
          <label className="field"><span>کد کالا</span><input name="sku" required defaultValue={itemForm !== "new" && itemForm ? itemForm.sku : ""} /></label>
          <label className="field"><span>دسته‌بندی</span><select name="category_id" defaultValue={itemForm !== "new" && itemForm ? itemForm.category_id || "" : ""}><option value="">بدون دسته‌بندی</option>{categories.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="field"><span>واحد پایه موجودی</span><select name="unit" required value={formUnit} onChange={(event) => changeBaseUnit(event.target.value)}>{!["عدد", "گرم", "میلی‌لیتر"].includes(formUnit) && <option value={formUnit}>{formUnit}</option>}<option value="عدد">عدد</option><option value="گرم">گرم</option><option value="میلی‌لیتر">میلی‌لیتر</option></select><small>موجودی و دستور پخت با این واحد محاسبه می‌شوند</small></label>
          <label className="field"><span>نقطه سفارش مجدد</span><input name="reorder_level" type="number" min="0" step="0.001" required defaultValue={itemForm !== "new" && itemForm ? itemForm.reorder_level : "0"} /></label>
          <label className="field"><span>موجودی هدف پس از خرید</span><input name="target_stock_level" type="number" min="0" step="0.001" required defaultValue={itemForm !== "new" && itemForm ? itemForm.target_stock_level : "0"} /><small>برای پیشنهاد مقدار خرید فردا</small></label>
          <label className="field toggle-field field-wide"><input name="auto_reorder_enabled" type="checkbox" defaultChecked={itemForm !== "new" && itemForm ? itemForm.auto_reorder_enabled : false} /><span>ساخت خودکار هشدار و ردیف خرید فردا هنگام رسیدن به حد سفارش</span></label>
          <section className="pricing-editor simple-pricing-editor field-wide">
            <header><div><span className="pricing-kicker">ساده و دقیق</span><h3>قیمت خرید و فروش</h3><p>فقط همان مقدار، واحد و مبلغی را بنویسید که روی فاکتور یا فروش دارید.</p></div><span className="unit-pill">واحد انبار: {pricingUnit}</span></header>
            <div className="simple-pricing-grid">
              <article className="price-package-card purchase-package-card"><header><span>خرید</span><small>مثلاً ۵ کیلوگرم گوشت با مبلغ کل فاکتور</small></header><div className="price-sentence"><input aria-label="مقدار خرید" value={purchaseQuantity} onChange={(event) => setPurchaseQuantity(event.target.value)} type="number" min="0.001" step="0.001" required /><select aria-label="واحد خرید" value={purchaseUnit} onChange={(event) => setPurchaseUnit(event.target.value)}>{unitChoices(pricingUnit).map((unit) => <option key={unit}>{unit}</option>)}</select><span>به مبلغ</span><input aria-label="مبلغ خرید" value={purchasePrice} onChange={(event) => setPurchasePrice(event.target.value)} type="number" min="0" step="1" required /><b>تومان</b></div><small className="normalized-price">معادل هر {pricingUnit}: <strong>{money(purchaseUnitPrice)}</strong></small></article>
              <article className="price-package-card selling-package-card"><header><span>فروش</span><small>مقدار قابل فروش و مبلغ آن را وارد کنید</small></header><div className="price-sentence"><input aria-label="مقدار فروش" value={sellingQuantity} onChange={(event) => setSellingQuantity(event.target.value)} type="number" min="0.001" step="0.001" required /><select aria-label="واحد فروش" value={sellingUnit} onChange={(event) => setSellingUnit(event.target.value)}>{unitChoices(pricingUnit).map((unit) => <option key={unit}>{unit}</option>)}</select><span>به مبلغ</span><input aria-label="مبلغ فروش" value={sellingPrice} onChange={(event) => setSellingPrice(event.target.value)} type="number" min="0" step="1" required /><b>تومان</b></div><small className="normalized-price">معادل هر {pricingUnit}: <strong>{money(sellingUnitPrice)}</strong></small></article>
              {itemForm !== "new" && <label className="field field-wide"><span>دلیل تغییر قیمت <small>{user?.role === "root" ? "(اختیاری)" : "(برای تأیید مدیر کل الزامی)"}</small></span><textarea name="price_change_reason" rows={2} placeholder="مثلاً تغییر قیمت تأمین‌کننده یا اصلاح قیمت‌گذاری" /></label>}
            </div>
            <div className="pricing-note"><CircleDollarSign size={18} /><span>{user?.role === "storage_manager" ? "اطلاعات کالا فوراً ذخیره می‌شود؛ تغییر قیمت خرید و فروش پس از تأیید مدیر کل اعمال خواهد شد." : "تغییر قیمت خرید، موجودی فعلی را ارزش‌گذاری مجدد می‌کند و روی سفارش‌های آینده اثر می‌گذارد؛ سوابق گذشته تغییر نمی‌کنند."}</span></div>
          </section>
          <label className="field field-wide"><span>توضیحات</span><textarea name="description" rows={3} defaultValue={itemForm !== "new" && itemForm ? itemForm.description || "" : ""} /></label>
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setItemForm(null)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ذخیره…" : user?.role === "storage_manager" && itemForm !== "new" ? "ذخیره و ارسال قیمت‌ها" : "ذخیره کالا"}</Button></div>
        </form>
      </Modal>

      <Modal open={!!movementItem} title={`ثبت گردش موجودی · ${movementItem?.name || ""}`} onClose={() => setMovementItem(null)}>
        {movementItem && <form className="form-grid" onSubmit={saveMovement}>
          <div className="current-stock field-wide"><span>موجودی فعلی</span><strong>{quantity(movementItem.current_quantity)} {movementItem.unit}</strong></div>
          <label className="field"><span>نوع گردش</span><select name="movement_type" defaultValue="receive"><option value="receive">ورود کالا</option><option value="adjust">اصلاح موجودی (+ یا −)</option><option value="waste">ضایعات / خرابی</option></select></label>
          <label className="field"><span>مقدار</span><input name="quantity" type="number" step="0.001" required placeholder="۰٫۰۰۰" /></label>
          <label className="field field-wide"><span>هزینه خرید هر واحد <small>(هنگام ورود الزامی)</small></span><input name="unit_cost" type="number" min="0" step="0.01" /></label>
          <label className="field field-wide"><span>دلیل / مرجع</span><textarea name="reason" minLength={3} required rows={3} placeholder="شماره فاکتور تأمین‌کننده، اصلاح شمارش انبار…" /></label>
          {error && <div className="form-error field-wide">{error}</div>}
          <div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setMovementItem(null)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>ثبت گردش</Button></div>
        </form>}
      </Modal>

      <ItemDetail item={detailItem} close={() => setDetailItem(null)} edit={() => { setItemForm(detailItem); setDetailItem(null); }} onUploaded={() => { invalidate(); }} />
      <CategoryManager open={categoryModal} close={() => setCategoryModal(false)} categories={categories.data || []} />
    </div>
  );
}

function ItemDetail({ item, close, edit, onUploaded }: { item: InventoryItem | null; close: () => void; edit: () => void; onUploaded: () => void }) {
  const [uploading, setUploading] = useState(false);
  const report = useQuery({ queryKey: ["item-report", item?.id], queryFn: () => api<ItemReport>(`/inventory/items/${item!.id}/report`), enabled: !!item });
  const movements = useQuery({ queryKey: ["movements", item?.id], queryFn: () => api<Movement[]>(`/inventory/items/${item!.id}/movements?limit=10`), enabled: !!item });
  const upload = async (file: File) => { if (!item) return; const form = new FormData(); form.append("image", file); setUploading(true); try { await api(`/inventory/items/${item.id}/image`, { method: "POST", body: form }); onUploaded(); } finally { setUploading(false); } };
  return <Modal open={!!item} title={item?.name || "جزئیات کالا"} onClose={close} wide>{item && <div className="item-detail">
    <aside className="detail-aside"><label className="detail-image">{item.image_path ? <img src={assetUrl(item.image_path)} alt="" /> : <PackageOpen size={44} />}<span><Camera size={17} /> {uploading ? "در حال بارگذاری…" : "تغییر تصویر"}</span><input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={uploading} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label><h3>{item.name}</h3><p>{item.description || "توضیحی برای این کالا ثبت نشده است."}</p><Button variant="secondary" onClick={edit}>ویرایش کالا</Button></aside>
    <div className="detail-main"><div className="detail-metrics"><span><small>موجودی</small><strong>{quantity(item.current_quantity)} {item.unit}</strong></span><span><small>ارزش موجودی</small><strong>{money(report.data?.stock_value)}</strong></span><span><small>مصرف ۹۰ روزه</small><strong>{quantity(report.data?.units_used_90d)}</strong></span><span><small>روزهای باقی‌مانده</small><strong>{report.data?.estimated_days_remaining ? quantity(report.data.estimated_days_remaining) : "—"}</strong></span></div>
    <section className="detail-chart"><header><h3>گردش موجودی</h3><small>ورودی و مصرف در ۹۰ روز اخیر</small></header>{report.isLoading ? <Spinner /> : report.data?.daily_activity.length ? <ResponsiveContainer width="100%" height={220}><AreaChart data={report.data.daily_activity}><defs><linearGradient id="received" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563eb" stopOpacity={.28}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0"/><XAxis dataKey="date" tick={{fontSize:11}} axisLine={false}/><YAxis tick={{fontSize:11}} axisLine={false}/><Tooltip/><Area name="ورودی" type="monotone" dataKey="received" stroke="#2563eb" fill="url(#received)"/><Area name="مصرف" type="monotone" dataKey="used" stroke="#f59e0b" fill="transparent"/></AreaChart></ResponsiveContainer> : <div className="mini-empty">پس از ثبت گردش کالا، نمودار اینجا نمایش داده می‌شود.</div>}</section>
    <section className="movement-history"><h3>آخرین گردش‌ها</h3>{movements.data?.map((move) => <div key={move.id}><Badge tone={move.movement_type === "receive" ? "success" : move.movement_type === "waste" ? "danger" : "info"}>{statusLabel[move.movement_type]}</Badge><span>{move.reason}</span><strong>{Number(move.quantity) > 0 ? "+" : ""}{quantity(move.quantity)}</strong><small>{dateTime(move.created_at)}</small></div>) || <Spinner />}</section></div>
  </div>}</Modal>;
}

function CategoryManager({ open, close, categories }: { open: boolean; close: () => void; categories: Category[] }) {
  const client = useQueryClient();
  const [error, setError] = useState("");
  const mutation = useMutation({ mutationFn: ({ path, method, body }: { path: string; method: string; body?: object }) => api(path, { method, body }), onSuccess: () => { client.invalidateQueries({ queryKey: ["categories"] }); setError(""); }, onError: (reason) => setError(reason instanceof ApiError ? reason.message : "عملیات دسته‌بندی انجام نشد") });
  useEffect(() => { if (!open) setError(""); }, [open]);
  const submit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = new FormData(e.currentTarget); mutation.mutate({ path: "/inventory/categories", method: "POST", body: { name: form.get("name"), description: form.get("description") || null, color: form.get("color") } }); e.currentTarget.reset(); };
  return <Modal open={open} title="دسته‌بندی‌های انبار" onClose={close}><div className="category-list editable-categories">{categories.map((category) => <div key={category.id}><span style={{ background: category.color }} /><div><strong>{category.name}</strong><small>{category.description || "بدون توضیح"}</small></div><button title="حذف دسته" onClick={() => mutation.mutate({ path: `/inventory/categories/${category.id}`, method: "DELETE" })}><Trash2 size={16} /></button></div>)}</div><form className="inline-category-form" onSubmit={submit}><label className="field"><span>دسته‌بندی جدید</span><input name="name" required placeholder="نام دسته‌بندی" /></label><label className="field color-field"><span>رنگ</span><input name="color" type="color" defaultValue="#2563eb" /></label><label className="field field-wide"><span>توضیحات</span><input name="description" placeholder="اختیاری" /></label>{error && <div className="form-error field-wide">{error}</div>}<Button type="submit" disabled={mutation.isPending}><Plus size={17} /> افزودن دسته</Button></form></Modal>;
}
