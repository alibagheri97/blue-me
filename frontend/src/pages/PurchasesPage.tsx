import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  Boxes,
  CalendarDays,
  Check,
  CheckCircle2,
  CircleDollarSign,
  FileText,
  Minus,
  PackagePlus,
  Plus,
  ReceiptText,
  Search,
  ShoppingBasket,
  Store,
  Trash2,
  Truck,
  Undo2,
} from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api, assetUrl } from "../lib/api";
import { businessDate, dateOnly, dateTime, money, quantity } from "../lib/format";
import { stockAmount, unitChoices, unitFactor } from "../lib/units";
import type { Category, InventoryItem, PurchaseReceipt } from "../types";

interface DraftLine {
  key: number;
  inventory_item_id: string;
  quantity: string;
  purchase_unit: string;
  conversion_factor: string;
  line_total: string;
}

const lineForItem = (item: InventoryItem): DraftLine => ({
  key: item.id,
  inventory_item_id: String(item.id),
  quantity: item.purchase_quantity || "1",
  purchase_unit: item.purchase_unit || item.unit,
  conversion_factor: String(unitFactor(item.unit, item.purchase_unit || item.unit) || 1),
  line_total: Number(item.purchase_total_price || 0) > 0 ? item.purchase_total_price : "",
});

export default function PurchasesPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const purchaseFormRef = useRef<HTMLFormElement>(null);
  const [historySearch, setHistorySearch] = useState("");
  const [itemSearch, setItemSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<number | "all">("all");
  const [quickItemOpen, setQuickItemOpen] = useState(false);
  const [activeReceipt, setActiveReceipt] = useState<PurchaseReceipt | null>(null);
  const [voiding, setVoiding] = useState(false);
  const [error, setError] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [discount, setDiscount] = useState("0");
  const [extraCost, setExtraCost] = useState("0");
  const [quickUnit, setQuickUnit] = useState("عدد");
  const [quickPurchaseUnit, setQuickPurchaseUnit] = useState("عدد");
  const [quickSellingUnit, setQuickSellingUnit] = useState("عدد");

  const inventory = useQuery({
    queryKey: ["inventory", "purchase-picker"],
    queryFn: () => api<{ items: InventoryItem[]; total: number }>("/inventory/items?page_size=100&active=true"),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/inventory/categories"),
  });
  const purchases = useQuery({
    queryKey: ["purchases", historySearch],
    queryFn: () => api<{ items: PurchaseReceipt[]; total: number }>(`/purchases?page_size=50&search=${encodeURIComponent(historySearch)}`),
  });

  const resetCart = () => {
    setLines([]);
    setDiscount("0");
    setExtraCost("0");
    setError("");
    purchaseFormRef.current?.reset();
  };
  const invalidate = () => {
    client.invalidateQueries({ queryKey: ["purchases"] });
    client.invalidateQueries({ queryKey: ["inventory"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
    client.invalidateQueries({ queryKey: ["daily-needs"] });
    client.invalidateQueries({ queryKey: ["notifications"] });
  };
  const createReceipt = useMutation({
    mutationFn: (body: object) => api<PurchaseReceipt>("/purchases", { method: "POST", body }),
    onSuccess: (receipt) => {
      invalidate();
      resetCart();
      setActiveReceipt(receipt);
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ثبت فاکتور انجام نشد"),
  });
  const createItem = useMutation({
    mutationFn: (body: object) => api<InventoryItem>("/inventory/items", { method: "POST", body }),
    onSuccess: (item) => {
      client.setQueryData<{ items: InventoryItem[]; total: number }>(["inventory", "purchase-picker"], (current) => ({
        items: [...(current?.items || []), item].sort((first, second) => first.name.localeCompare(second.name, "fa")),
        total: (current?.total || 0) + 1,
      }));
      setLines((current) => current.some((line) => line.inventory_item_id === String(item.id)) ? current : [...current, lineForItem(item)]);
      setQuickItemOpen(false);
      setError("");
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ایجاد کالا انجام نشد"),
  });
  const voidReceipt = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => api<PurchaseReceipt>(`/purchases/${id}/void`, { method: "POST", body: { reason } }),
    onSuccess: (receipt) => { invalidate(); setActiveReceipt(receipt); setVoiding(false); setError(""); },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ابطال فاکتور انجام نشد"),
  });

  const subtotal = useMemo(() => lines.reduce((sum, line) => sum + Number(line.line_total || 0), 0), [lines]);
  const finalTotal = Math.max(0, subtotal + Number(extraCost || 0) - Number(discount || 0));
  const shownReceipts = purchases.data?.items || [];
  const pageSpend = shownReceipts.filter((receipt) => receipt.status === "posted").reduce((sum, receipt) => sum + Number(receipt.total_cost), 0);
  const pageUnits = shownReceipts.filter((receipt) => receipt.status === "posted").reduce((sum, receipt) => sum + receipt.lines.reduce((lineSum, line) => lineSum + Number(line.stock_quantity), 0), 0);
  const selectedLineByItem = useMemo(() => new Map(lines.map((line) => [Number(line.inventory_item_id), line])), [lines]);
  const visibleItems = useMemo(() => {
    const term = itemSearch.trim().toLocaleLowerCase("fa");
    return (inventory.data?.items || []).filter((item) => {
      const matchesCategory = categoryFilter === "all" || item.category_id === categoryFilter;
      const matchesTerm = !term || item.name.toLocaleLowerCase("fa").includes(term) || item.sku.toLocaleLowerCase("fa").includes(term);
      return matchesCategory && matchesTerm;
    });
  }, [categoryFilter, inventory.data?.items, itemSearch]);

  const updateLine = (key: number, patch: Partial<DraftLine>) => setLines((current) => current.map((line) => line.key === key ? { ...line, ...patch } : line));
  const addItem = (item: InventoryItem) => {
    setError("");
    setLines((current) => {
      const selected = current.find((line) => line.inventory_item_id === String(item.id));
      if (!selected) return [...current, lineForItem(item)];
      return current.map((line) => line.key === selected.key ? { ...line, quantity: String(Number(line.quantity || 0) + 1) } : line);
    });
  };
  const adjustQuantity = (line: DraftLine, delta: number) => {
    const next = Number(line.quantity || 0) + delta;
    if (next <= 0) {
      setLines((current) => current.filter((candidate) => candidate.key !== line.key));
      return;
    }
    updateLine(line.key, { quantity: String(next) });
  };
  const selectPurchaseUnit = (line: DraftLine, value: string) => {
    const item = inventory.data?.items.find((candidate) => candidate.id === Number(line.inventory_item_id));
    updateLine(line.key, { purchase_unit: value, conversion_factor: String(unitFactor(item?.unit, value) || 1) });
  };
  const submitReceipt = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!lines.length) {
      setError("ابتدا حداقل یک کالا را از شبکه انتخاب کنید");
      return;
    }
    if (lines.some((line) => Number(line.quantity) <= 0 || Number(line.conversion_factor) <= 0 || line.line_total === "" || Number(line.line_total) < 0)) {
      setError("مقدار، واحد و مبلغ همه کالاهای انتخاب‌شده را کامل کنید");
      return;
    }
    createReceipt.mutate({
      supplier_name: form.get("supplier_name") || null,
      invoice_number: form.get("invoice_number") || null,
      purchased_at: `${form.get("purchased_at")}T12:00:00`,
      discount,
      extra_cost: extraCost,
      notes: form.get("notes") || null,
      lines: lines.map(({ inventory_item_id, quantity: bought, purchase_unit, conversion_factor, line_total }) => ({
        inventory_item_id: Number(inventory_item_id),
        quantity: bought,
        purchase_unit,
        conversion_factor,
        line_total,
      })),
    });
  };
  const submitQuickItem = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    createItem.mutate({
      name: form.get("name"),
      sku: form.get("sku") || `NEW-${Date.now().toString().slice(-8)}`,
      category_id: form.get("category_id") ? Number(form.get("category_id")) : null,
      unit: form.get("unit"),
      reorder_level: 0,
      target_stock_level: 0,
      auto_reorder_enabled: false,
      purchase_quantity: form.get("purchase_quantity"),
      purchase_unit: form.get("purchase_unit"),
      purchase_price: form.get("purchase_price") || 0,
      selling_quantity: form.get("selling_quantity"),
      selling_unit: form.get("selling_unit"),
      selling_price: form.get("selling_price") || 0,
    });
  };

  return <div className="page-stack purchases-page">
    <header className="page-heading">
      <div><span className="eyebrow">انتخاب سریع، ثبت یک‌جای ورودی</span><h1>ورودی کالا</h1><p>کالاها را از شبکه انتخاب کنید، مقدار و مبلغ را وارد کنید و همه را با یک کلیک به انبار بسپارید.</p></div>
      <Button variant="secondary" onClick={() => { setError(""); setQuickItemOpen(true); }}><PackagePlus size={18} /> ساخت کالای جدید</Button>
    </header>

    <section className="summary-chips purchase-summary">
      <div><span className="chip-icon blue"><ReceiptText /></span><span><strong>{quantity(purchases.data?.total || 0)}</strong><small>فاکتور ثبت‌شده</small></span></div>
      <div><span className="chip-icon green"><CircleDollarSign /></span><span><strong>{money(pageSpend)}</strong><small>خرید نمایش‌داده‌شده</small></span></div>
      <div><span className="chip-icon amber"><ArrowDownToLine /></span><span><strong>{quantity(pageUnits)}</strong><small>واحد افزوده به انبار</small></span></div>
      <div><span className="chip-icon violet"><ShoppingBasket /></span><span><strong>{quantity(lines.length)}</strong><small>قلم در سبد ورودی</small></span></div>
    </section>

    <form ref={purchaseFormRef} className="purchase-entry-workspace" onSubmit={submitReceipt}>
      <section className="panel purchase-catalog-panel">
        <header className="purchase-catalog-head">
          <div><span className="step-number">۱</span><div><h2>کالاها را انتخاب کنید</h2><p>هر بار کلیک روی کارت، یک واحد به سبد ورودی اضافه می‌کند.</p></div></div>
          <Button type="button" variant="secondary" onClick={() => { setError(""); setQuickItemOpen(true); }}><Plus size={16} /> کالای جدید</Button>
        </header>

        <div className="purchase-meta-strip">
          <label className="field"><span>تاریخ خرید</span><input name="purchased_at" type="date" defaultValue={businessDate()} required /></label>
          <label className="field"><span>فروشنده</span><input name="supplier_name" placeholder="مثلاً پخش مرکزی" /></label>
          <label className="field"><span>شماره فاکتور</span><input name="invoice_number" placeholder="اختیاری" /></label>
        </div>

        <div className="purchase-catalog-toolbar">
          <label className="search-box"><Search size={17} /><input value={itemSearch} onChange={(event) => setItemSearch(event.target.value)} placeholder="جست‌وجوی نام یا کد کالا…" /></label>
          <div className="purchase-category-pills">
            <button type="button" className={categoryFilter === "all" ? "active" : ""} onClick={() => setCategoryFilter("all")}>همه</button>
            {categories.data?.map((category) => <button type="button" key={category.id} className={categoryFilter === category.id ? "active" : ""} onClick={() => setCategoryFilter(category.id)}>{category.name}</button>)}
          </div>
        </div>

        {inventory.isLoading ? <div className="center-loader"><Spinner /></div> : visibleItems.length ? <div className="purchase-product-grid">
          {visibleItems.map((item) => {
            const selected = selectedLineByItem.get(item.id);
            return <button
              type="button"
              key={item.id}
              className={`purchase-product-card${selected ? " selected" : ""}`}
              onClick={() => addItem(item)}
              aria-pressed={!!selected}
              aria-label={`افزودن ${item.name} به سبد ورودی`}
            >
              <span className="purchase-product-visual">
                {item.image_path ? <img src={assetUrl(item.image_path)} alt="" /> : <Boxes />}
                <i className="purchase-card-add">{selected ? <Check /> : <Plus />}</i>
              </span>
              <span className="purchase-product-copy">
                <small>{item.category?.name || "بدون دسته‌بندی"}</small>
                <strong>{item.name}</strong>
                <em>{item.sku}</em>
              </span>
              <span className="purchase-product-stats">
                <span><small>موجودی فعلی</small><b>{quantity(item.current_quantity)} {item.unit}</b></span>
                <span><small>آخرین خرید</small><b>{quantity(item.purchase_quantity)} {item.purchase_unit} · {money(item.purchase_total_price)}</b></span>
              </span>
              <span className="purchase-click-hint">{selected ? `${quantity(selected.quantity)} ${selected.purchase_unit} در سبد · کلیک برای +۱` : "کلیک برای افزودن"}</span>
            </button>;
          })}
        </div> : <EmptyState icon={<Search />} title="کالایی پیدا نشد" text="عبارت جست‌وجو یا دسته‌بندی را تغییر دهید؛ یا یک کالای جدید بسازید." />}
      </section>

      <aside className="panel purchase-cart-panel">
        <header className="purchase-cart-head">
          <div><span className="step-number">۲</span><div><h2>سبد ورودی</h2><p>{lines.length ? `${quantity(lines.length)} قلم برای ثبت نهایی` : "منتظر انتخاب کالا"}</p></div></div>
          {lines.length > 0 && <button type="button" className="clear-purchase-cart" onClick={() => { setLines([]); setError(""); }}>پاک‌کردن</button>}
        </header>

        <div className="purchase-cart-scroll">
        {lines.length ? <div className="purchase-cart-lines">{lines.map((line, index) => {
          const item = inventory.data?.items.find((candidate) => candidate.id === Number(line.inventory_item_id));
          const stockAdded = stockAmount(line.quantity, line.purchase_unit, item?.unit) || Number(line.quantity || 0) * Number(line.conversion_factor || 0);
          const unitCost = stockAdded > 0 ? Number(line.line_total || 0) / stockAdded : 0;
          return <article className="purchase-cart-line" key={line.key}>
            <header>
              <span className="cart-line-number">{quantity(index + 1)}</span>
              <div><strong>{item?.name}</strong><small>{item?.category?.name || "بدون دسته‌بندی"} · واحد انبار: {item?.unit}</small></div>
              <button type="button" onClick={() => setLines((current) => current.filter((candidate) => candidate.key !== line.key))} aria-label={`حذف ${item?.name}`}><Trash2 /></button>
            </header>
            <div className="purchase-cart-controls">
              <label className="cart-quantity-field"><span>مقدار خرید</span><div><button type="button" onClick={() => adjustQuantity(line, -1)}><Minus /></button><input value={line.quantity} onChange={(event) => updateLine(line.key, { quantity: event.target.value })} type="number" min="0.001" step="0.001" required /><button type="button" onClick={() => adjustQuantity(line, 1)}><Plus /></button></div></label>
              <label><span>واحد</span><select value={line.purchase_unit} onChange={(event) => selectPurchaseUnit(line, event.target.value)}>{Array.from(new Set([...unitChoices(item?.unit), line.purchase_unit])).map((unit) => <option key={unit}>{unit}</option>)}</select></label>
              <label className="cart-line-price"><span>مبلغ کل خرید</span><div><input value={line.line_total} onChange={(event) => updateLine(line.key, { line_total: event.target.value })} type="number" min="0" step="1" placeholder="مثلاً ۱۵۵۰۰۰" required /><small>تومان</small></div></label>
            </div>
            <footer><span><ArrowDownToLine /> ورود به انبار: <b>{quantity(stockAdded)} {item?.unit}</b></span>{unitCost > 0 && <span>بهای هر {item?.unit}: <b>{money(unitCost)}</b></span>}</footer>
          </article>;
        })}</div> : <div className="purchase-cart-empty"><span><ShoppingBasket /></span><strong>سبد هنوز خالی است</strong><p>از شبکه روبه‌رو روی کالاها کلیک کنید؛ اینجا مقدار، واحد و قیمت هرکدام را تنظیم خواهید کرد.</p></div>}

        <div className="purchase-cart-summary">
          <div className="purchase-adjustments">
            <label className="field"><span>هزینه جانبی</span><input value={extraCost} onChange={(event) => setExtraCost(event.target.value)} type="number" min="0" step="1" /></label>
            <label className="field"><span>تخفیف فاکتور</span><input value={discount} onChange={(event) => setDiscount(event.target.value)} type="number" min="0" step="1" /></label>
            <label className="field field-wide"><span>یادداشت</span><textarea name="notes" rows={2} placeholder="حمل، کیفیت، نحوه پرداخت و…" /></label>
          </div>
          <div className="purchase-total-card">
            <span><small>جمع اقلام</small><strong>{money(subtotal)}</strong></span>
            <span><small>هزینه جانبی</small><strong>+ {money(extraCost)}</strong></span>
            <span><small>تخفیف</small><strong>− {money(discount)}</strong></span>
            <span className="purchase-grand"><small>بهای نهایی ورودی</small><strong>{money(finalTotal)}</strong></span>
          </div>
          <div className="purchase-final-note"><CheckCircle2 /> موجودی و میانگین بها فقط پس از تأیید نهایی و در یک تراکنش ثبت می‌شوند.</div>
        </div>
        </div>
        <div className="purchase-cart-action">
          {error && <div className="form-error">{error}</div>}
          <Button className="purchase-submit-button" type="submit" disabled={!lines.length || createReceipt.isPending}>
            <PackagePlus size={18} /> {createReceipt.isPending ? "در حال ثبت در انبار…" : `ثبت نهایی و افزودن ${quantity(lines.length)} قلم به انبار`}
          </Button>
        </div>
      </aside>
    </form>

    <section className="panel purchase-history">
      <header className="panel-header"><div><h2>دفتر ورود کالا</h2><p>هر فاکتور، ردیف‌های خرید، بهای نهایی و کاربر ثبت‌کننده قابل پیگیری است.</p></div><label className="search-box"><Search size={17} /><input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="شماره فاکتور، فروشنده یا مرجع…" /></label></header>
      {purchases.isLoading ? <div className="center-loader"><Spinner /></div> : shownReceipts.length ? <div className="purchase-list">{shownReceipts.map((receipt) => <button key={receipt.id} onClick={() => { setError(""); setActiveReceipt(receipt); }} className={receipt.status === "voided" ? "voided" : ""}>
        <span className="purchase-icon"><FileText /></span><span className="purchase-main"><strong>{receipt.receipt_number}</strong><small>{receipt.supplier_name || "فروشنده ثبت نشده"} · {receipt.invoice_number ? `فاکتور ${receipt.invoice_number}` : "بدون شماره مرجع"}</small></span>
        <span><small>تاریخ خرید</small><strong>{dateOnly(receipt.purchased_at)}</strong></span><span><small>اقلام</small><strong>{quantity(receipt.lines.length)} ردیف</strong></span><span><small>مبلغ نهایی</small><strong>{money(receipt.total_cost)}</strong></span><Badge tone={receipt.status === "posted" ? "success" : "danger"}>{receipt.status === "posted" ? "ثبت قطعی" : "باطل‌شده"}</Badge>
      </button>)}</div> : <EmptyState icon={<Truck />} title="هنوز ورودی کالایی ثبت نشده" text="اولین خرید را از شبکه بالا ثبت کنید تا موجودی و بهای تمام‌شده خودکار به‌روز شود." />}
    </section>

    <Modal open={quickItemOpen} title="ساخت سریع کالای انبار" onClose={() => setQuickItemOpen(false)} wide><form className="form-grid" onSubmit={submitQuickItem}>
      <label className="field"><span>نام کالا</span><input name="name" required autoFocus /></label><label className="field"><span>کد کالا <small>(اختیاری)</small></span><input name="sku" placeholder="خودکار ساخته می‌شود" /></label>
      <label className="field"><span>دسته‌بندی</span><select name="category_id"><option value="">بدون دسته‌بندی</option>{categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label className="field"><span>واحد پایه موجودی</span><select name="unit" value={quickUnit} onChange={(event) => { const next = event.target.value; setQuickUnit(next); setQuickPurchaseUnit(next); setQuickSellingUnit(next); }}><option>عدد</option><option>گرم</option><option>میلی‌لیتر</option></select></label>
      <section className="quick-item-pricing field-wide"><article><strong>روش معمول خرید</strong><div><input aria-label="مقدار خرید" name="purchase_quantity" type="number" min="0.001" step="0.001" defaultValue="1" required /><select aria-label="واحد خرید" name="purchase_unit" value={quickPurchaseUnit} onChange={(event) => setQuickPurchaseUnit(event.target.value)}>{unitChoices(quickUnit).map((unit) => <option key={unit}>{unit}</option>)}</select><span>با مبلغ</span><input aria-label="مبلغ خرید" name="purchase_price" type="number" min="0" step="1" defaultValue="0" required /><b>تومان</b></div></article><article><strong>روش فروش</strong><div><input aria-label="مقدار فروش" name="selling_quantity" type="number" min="0.001" step="0.001" defaultValue="1" required /><select aria-label="واحد فروش" name="selling_unit" value={quickSellingUnit} onChange={(event) => setQuickSellingUnit(event.target.value)}>{unitChoices(quickUnit).map((unit) => <option key={unit}>{unit}</option>)}</select><span>با مبلغ</span><input aria-label="مبلغ فروش" name="selling_price" type="number" min="0" step="1" defaultValue="0" required /><b>تومان</b></div></article></section>
      {error && <div className="form-error field-wide">{error}</div>}<div className="form-actions field-wide"><Button type="button" variant="secondary" onClick={() => setQuickItemOpen(false)}>انصراف</Button><Button type="submit" disabled={createItem.isPending}>ساخت و افزودن به سبد</Button></div>
    </form></Modal>

    <Modal open={!!activeReceipt} title={activeReceipt?.receipt_number || "جزئیات فاکتور"} onClose={() => { setActiveReceipt(null); setVoiding(false); }} wide>{activeReceipt && <div className="receipt-detail">
      <div className="receipt-detail-head"><span><Store /><div><small>فروشنده</small><strong>{activeReceipt.supplier_name || "ثبت نشده"}</strong></div></span><span><CalendarDays /><div><small>تاریخ خرید</small><strong>{dateOnly(activeReceipt.purchased_at)}</strong></div></span><span><FileText /><div><small>مرجع فروشنده</small><strong>{activeReceipt.invoice_number || "—"}</strong></div></span><Badge tone={activeReceipt.status === "posted" ? "success" : "danger"}>{activeReceipt.status === "posted" ? "ثبت قطعی" : "باطل‌شده"}</Badge></div>
      <div className="receipt-lines-table"><div className="receipt-table-head"><span>کالا</span><span>خرید</span><span>ورود انبار</span><span>مبلغ ردیف</span><span>سهم هزینه</span><span>بهای هر واحد</span></div>{activeReceipt.lines.map((line) => <div key={line.id}><strong>{line.item_name}</strong><span>{quantity(line.quantity)} {line.purchase_unit}</span><span>{quantity(line.stock_quantity)} {line.stock_unit}</span><span>{money(line.line_total)}</span><span>{Number(line.allocated_cost) >= 0 ? "+" : ""}{money(line.allocated_cost)}</span><span>{money(line.unit_cost)}</span></div>)}</div>
      <div className="receipt-detail-total"><span>جمع اقلام <b>{money(activeReceipt.subtotal)}</b></span><span>هزینه جانبی <b>{money(activeReceipt.extra_cost)}</b></span><span>تخفیف <b>{money(activeReceipt.discount)}</b></span><span>بهای نهایی <strong>{money(activeReceipt.total_cost)}</strong></span></div>
      <p className="receipt-meta">ثبت توسط {activeReceipt.created_by.full_name} در {dateTime(activeReceipt.created_at)}{activeReceipt.notes ? ` · ${activeReceipt.notes}` : ""}</p>
      {activeReceipt.status === "voided" && <div className="danger-callout">علت ابطال: {activeReceipt.void_reason}</div>}
      {voiding && <form className="void-form" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); voidReceipt.mutate({ id: activeReceipt.id, reason: String(form.get("reason")) }); }}><label className="field"><span>دلیل ابطال</span><textarea name="reason" minLength={3} required autoFocus /></label>{error && <div className="form-error">{error}</div>}<div className="form-actions"><Button type="button" variant="secondary" onClick={() => setVoiding(false)}>انصراف</Button><Button type="submit" variant="danger" disabled={voidReceipt.isPending}>تأیید ابطال و برگشت موجودی</Button></div></form>}
      {!voiding && activeReceipt.status === "posted" && user?.role === "root" && <div className="form-actions"><Button variant="danger" onClick={() => setVoiding(true)}><Undo2 size={17} /> ابطال کنترل‌شده فاکتور</Button></div>}
    </div>}</Modal>
  </div>;
}
