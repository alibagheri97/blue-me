import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  ChefHat,
  CircleDollarSign,
  Layers3,
  Link2,
  PackageCheck,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { RecipeEditor } from "../components/RecipeEditor";
import { Badge, Button, EmptyState, Modal, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../lib/api";
import { money, quantity } from "../lib/format";
import type { InventoryItem, MenuCategory, MenuItem, Recipe } from "../types";

export default function MenuPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<"all" | "ready" | "draft" | "inactive">("all");
  const [editor, setEditor] = useState<MenuItem | "new" | null>(null);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [mode, setMode] = useState<"recipe" | "direct">("recipe");
  const [error, setError] = useState("");
  const [recipeError, setRecipeError] = useState("");
  const [recipeEditor, setRecipeEditor] = useState<{ menuItemId: number; recipe: Recipe | null } | null>(null);
  const canManageMenu = user?.role === "root" || user?.role === "accounting_manager" || user?.role === "sales_manager";
  const canManageRecipes = user?.role === "root" || user?.role === "kitchen_manager";

  const menu = useQuery({ queryKey: ["menu", "management"], queryFn: () => api<MenuItem[]>("/menu-items?include_inactive=true") });
  const categories = useQuery({ queryKey: ["menu-categories", "all"], queryFn: () => api<MenuCategory[]>("/menu-categories?active=false").then(async (inactive) => {
    const active = await api<MenuCategory[]>("/menu-categories?active=true");
    return [...active, ...inactive].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, "fa"));
  }) });
  const inventory = useQuery({ queryKey: ["inventory", "menu-link"], queryFn: () => api<{ items: InventoryItem[] }>("/inventory/items?page_size=100&active=true") });
  const recipes = useQuery({ queryKey: ["recipes"], queryFn: () => api<Recipe[]>("/kitchen/recipes"), enabled: canManageRecipes });
  const invalidate = () => { client.invalidateQueries({ queryKey: ["menu"] }); client.invalidateQueries({ queryKey: ["menu-categories"] }); client.invalidateQueries({ queryKey: ["recipes"] }); client.invalidateQueries({ queryKey: ["dashboard"] }); };
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: object }) => api<MenuItem>(path, { method, body }),
    onSuccess: (savedItem) => {
      client.setQueryData<MenuItem[]>(["menu", "management"], (current) => {
        const existing = current || [];
        return existing.some((item) => item.id === savedItem.id)
          ? existing.map((item) => item.id === savedItem.id ? savedItem : item)
          : [...existing, savedItem];
      });
      invalidate();
      setEditor(null);
      setError("");
      if (mode === "recipe" && canManageRecipes) {
        setRecipeError("");
        setRecipeEditor({ menuItemId: savedItem.id, recipe: recipes.data?.find((recipe) => recipe.menu_item_id === savedItem.id) || null });
      }
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "ذخیره منو انجام نشد"),
  });
  const recipeMutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body: object }) => api<Recipe>(path, { method, body }),
    onSuccess: () => { invalidate(); setRecipeEditor(null); setRecipeError(""); },
    onError: (reason) => setRecipeError(reason instanceof ApiError ? reason.message : "ذخیره مواد مصرفی انجام نشد"),
  });

  const items = useMemo(() => menu.data || [], [menu.data]);
  const filtered = items.filter((item) => {
    if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (category && item.category_id !== Number(category)) return false;
    if (status === "ready" && (!item.is_active || !item.recipe_configured)) return false;
    if (status === "draft" && item.recipe_configured) return false;
    if (status === "inactive" && item.is_active) return false;
    return true;
  });
  const ready = items.filter((item) => item.recipe_configured).length;
  const unavailable = items.filter((item) => item.is_active && !item.is_available).length;
  const averageMargin = useMemo(() => {
    const costed = items.filter((item) => item.recipe_configured && Number(item.selling_price) > 0);
    return costed.length ? costed.reduce((sum, item) => sum + Number(item.margin_percent), 0) / costed.length : 0;
  }, [items]);
  const recipeByMenuItem = useMemo(() => new Map((recipes.data || []).map((recipe) => [recipe.menu_item_id, recipe])), [recipes.data]);

  const openEditor = (item: MenuItem | "new") => {
    setError("");
    setEditor(item);
    setMode(item !== "new" && item.inventory_item_id ? "direct" : "recipe");
  };
  const openRecipeEditor = (item: MenuItem) => {
    setRecipeError("");
    setRecipeEditor({ menuItemId: item.id, recipe: recipeByMenuItem.get(item.id) || null });
  };
  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      name: form.get("name"),
      category_id: Number(form.get("category_id")),
      category: categories.data?.find((candidate) => candidate.id === Number(form.get("category_id")))?.name || "عمومی",
      selling_price: form.get("selling_price"),
      inventory_item_id: mode === "direct" && form.get("inventory_item_id") ? Number(form.get("inventory_item_id")) : null,
      stock_quantity_per_sale: mode === "direct" ? form.get("stock_quantity_per_sale") || 1 : 1,
      description: form.get("description") || null,
      is_active: form.get("is_active") === "on",
    };
    mutation.mutate({ path: editor === "new" ? "/menu-items" : `/menu-items/${editor!.id}`, method: editor === "new" ? "POST" : "PATCH", body });
  };

  return <div className="page-stack menu-management-page">
    <header className="page-heading"><div><span className="eyebrow">پل میان صندوق، آشپزخانه و انبار</span><h1>مدیریت منو و خروجی</h1><p>برای هر محصول، مواد مصرفی دقیق را تعریف کنید تا با ثبت سفارش خودکار از انبار کم شوند.</p></div>{canManageMenu && <div className="heading-actions"><Button variant="secondary" onClick={() => setCategoryOpen(true)}><Layers3 size={18} /> دسته‌بندی‌ها</Button><Button onClick={() => openEditor("new")}><Plus size={18} /> محصول منو</Button></div>}</header>
    <section className="summary-chips menu-summary">
      <div><span className="chip-icon blue"><Boxes /></span><span><strong>{quantity(items.length)}</strong><small>محصول منو</small></span></div>
      <div><span className="chip-icon green"><PackageCheck /></span><span><strong>{quantity(ready)}</strong><small>متصل به انبار</small></span></div>
      <div><span className="chip-icon amber"><AlertTriangle /></span><span><strong>{quantity(unavailable)}</strong><small>فعال اما ناموجود</small></span></div>
      <div><span className="chip-icon violet"><CircleDollarSign /></span><span><strong>{quantity(averageMargin)}٪</strong><small>میانگین حاشیه سود</small></span></div>
    </section>
    <section className="panel menu-catalogue">
      <div className="toolbar menu-toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی محصول منو…" /></label><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">همه دسته‌بندی‌ها</option>{categories.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option value="all">همه وضعیت‌ها</option><option value="ready">آماده فروش</option><option value="draft">نیازمند اتصال</option><option value="inactive">غیرفعال</option></select></div>
      {menu.isLoading ? <div className="center-loader"><Spinner /></div> : filtered.length ? <div className="menu-management-grid">{filtered.map((item) => {
        const recipe = recipeByMenuItem.get(item.id);
        return <article key={item.id} className={!item.is_active ? "inactive" : ""}>
          <div className="menu-product-top"><span className="menu-product-icon">{item.inventory_item_id ? <Link2 /> : <ChefHat />}</span><div><h3>{item.name}</h3><small>{item.category}</small></div>{canManageMenu && <button className="icon-button" title="ویرایش محصول" onClick={() => openEditor(item)}><Pencil size={17} /></button>}</div>
          <div className="menu-status-row"><Badge tone={item.recipe_configured ? "success" : "warning"}>{item.recipe_configured ? item.inventory_item_id ? "فروش مستقیم از انبار" : "مواد مصرفی تنظیم شده" : "نیازمند تعریف مواد مصرفی"}</Badge><Badge tone={!item.is_active ? "neutral" : item.is_available ? "info" : "danger"}>{!item.is_active ? "غیرفعال" : item.is_available ? `قابل فروش${item.max_available_quantity !== null ? `: ${quantity(item.max_available_quantity)}` : ""}` : "ناموجود"}</Badge></div>
          {recipe && <div className="menu-recipe-preview"><header><span>کسر از انبار برای هر سفارش</span><b>{quantity(recipe.ingredients.length)} ماده</b></header>{recipe.ingredients.slice(0, 4).map((line) => <span key={line.inventory_item_id}><small>{line.inventory_item?.name}</small><strong>{quantity(Number(line.quantity) / Number(recipe.yield_quantity))} {line.unit}</strong></span>)}{recipe.ingredients.length > 4 && <em>+ {quantity(recipe.ingredients.length - 4)} ماده دیگر</em>}</div>}
          {!recipe && !item.inventory_item_id && <div className="menu-recipe-missing"><ChefHat /><span><strong>فرمول مصرف تعریف نشده</strong><small>مرغ، نان، ادویه و سایر مواد این محصول را مشخص کنید.</small></span></div>}
          <div className="menu-finance-grid"><span><small>قیمت فروش</small><strong>{money(item.selling_price)}</strong></span><span><small>هزینه واقعی</small><strong>{money(item.calculated_cost)}</strong></span><span><small>سود ناخالص</small><strong className={Number(item.gross_profit) < 0 ? "negative" : "positive"}>{money(item.gross_profit)}</strong></span><span><small>حاشیه سود</small><strong>{quantity(item.margin_percent)}٪</strong></span></div>
          <div className="margin-track"><i style={{ width: `${Math.max(0, Math.min(100, Number(item.margin_percent)))}%` }} /></div>
          {canManageRecipes && !item.inventory_item_id && <Button variant={recipe ? "secondary" : "primary"} disabled={recipes.isLoading || recipes.isError} onClick={() => openRecipeEditor(item)}><ChefHat size={16} /> {recipes.isLoading ? "در حال دریافت فرمول…" : recipe ? "ویرایش مواد مصرفی" : "تعریف مواد مصرفی"}</Button>}
        </article>;
      })}</div> : <EmptyState icon={<Sparkles />} title="محصولی با این فیلتر پیدا نشد" text="محصول تازه بسازید یا فیلترهای منو را تغییر دهید." />}
    </section>

    <Modal open={editor !== null} title={editor === "new" ? "محصول جدید منو" : `ویرایش ${editor?.name || "محصول"}`} onClose={() => setEditor(null)} wide><form className="menu-editor-form" onSubmit={save}>
      <div className="form-grid"><label className="field"><span>نام محصول</span><input name="name" required defaultValue={editor !== "new" && editor ? editor.name : ""} /></label><label className="field"><span>دسته‌بندی منو</span><select name="category_id" required defaultValue={editor !== "new" && editor ? editor.category_id || "" : ""}><option value="">انتخاب دسته…</option>{categories.data?.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field"><span>قیمت فروش</span><input name="selling_price" type="number" min="0" step="1" required defaultValue={editor !== "new" && editor ? editor.selling_price : "0"} /></label><label className="field toggle-field"><input name="is_active" type="checkbox" defaultChecked={editor === "new" ? false : editor?.is_active} /><span>فعال و قابل نمایش در صندوق</span></label></div>
      <div className="menu-source-switch"><button type="button" className={mode === "recipe" ? "active" : ""} onClick={() => setMode("recipe")}><ChefHat /><span><strong>محصول آشپزخانه</strong><small>مواد طبق دستور پخت کم می‌شوند</small></span></button><button type="button" className={mode === "direct" ? "active" : ""} onClick={() => setMode("direct")}><Link2 /><span><strong>فروش مستقیم انبار</strong><small>مثل نوشابه و آب معدنی</small></span></button></div>
      {mode === "direct" ? <div className="form-grid source-fields"><label className="field field-wide"><span>کالای متصل در انبار</span><select name="inventory_item_id" required defaultValue={editor !== "new" && editor ? editor.inventory_item_id || "" : ""}><option value="">انتخاب کالا…</option>{inventory.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} · موجودی {quantity(item.current_quantity)} {item.unit}</option>)}</select></label><label className="field"><span>مقدار کسر در هر فروش</span><input name="stock_quantity_per_sale" type="number" min="0.001" step="0.001" required defaultValue={editor !== "new" && editor ? editor.stock_quantity_per_sale : "1"} /></label><div className="info-callout"><Link2 size={18} /> با هر سفارش، همین مقدار مستقیماً از کالای انتخاب‌شده کم می‌شود.</div></div> : <div className="info-callout recipe-hint"><ChefHat size={20} /> {canManageRecipes ? "پس از ذخیره محصول، پنجره تعریف مرغ، نان، ادویه و سایر مواد مصرفی خودکار باز می‌شود." : "مدیر کل یا مدیر آشپزخانه باید مواد مصرفی دقیق این محصول را ثبت کند."}</div>}
      <label className="field"><span>توضیحات محصول</span><textarea name="description" rows={3} defaultValue={editor !== "new" && editor ? editor.description || "" : ""} /></label>{error && <div className="form-error">{error}</div>}<div className="form-actions"><Button type="button" variant="secondary" onClick={() => setEditor(null)}>انصراف</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "در حال ذخیره…" : "ذخیره محصول منو"}</Button></div>
    </form></Modal>
    <RecipeEditor open={recipeEditor !== null} recipe={recipeEditor?.recipe || null} initialMenuItemId={recipeEditor?.menuItemId || null} lockMenuItem close={() => setRecipeEditor(null)} menu={items} inventory={inventory.data?.items || []} save={(body, id) => recipeMutation.mutate({ path: id ? `/kitchen/recipes/${id}` : "/kitchen/recipes", method: id ? "PUT" : "POST", body })} pending={recipeMutation.isPending} error={recipeError} />
    <MenuCategoryManager open={categoryOpen} close={() => setCategoryOpen(false)} categories={categories.data || []} />
  </div>;
}

function MenuCategoryManager({ open, close, categories }: { open: boolean; close: () => void; categories: MenuCategory[] }) {
  const client = useQueryClient();
  const [error, setError] = useState("");
  const mutation = useMutation({ mutationFn: ({ path, method, body }: { path: string; method: string; body?: object }) => api(path, { method, body }), onSuccess: () => { client.invalidateQueries({ queryKey: ["menu-categories"] }); setError(""); }, onError: (reason) => setError(reason instanceof ApiError ? reason.message : "عملیات دسته‌بندی انجام نشد") });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); mutation.mutate({ path: "/menu-categories", method: "POST", body: { name: form.get("name"), color: form.get("color"), description: form.get("description") || null, sort_order: categories.length * 10, is_active: true } }); event.currentTarget.reset(); };
  return <Modal open={open} title="دسته‌بندی‌های منو" onClose={close}><div className="category-list editable-categories">{categories.map((category) => <div key={category.id}><span style={{ background: category.color }} /><div><strong>{category.name}</strong><small>{category.description || "بدون توضیح"}</small></div><button title="حذف دسته" onClick={() => mutation.mutate({ path: `/menu-categories/${category.id}`, method: "DELETE" })}><Trash2 size={16} /></button></div>)}</div><form className="inline-category-form" onSubmit={submit}><label className="field"><span>دسته‌بندی جدید</span><input name="name" required /></label><label className="field color-field"><span>رنگ</span><input name="color" type="color" defaultValue="#2563eb" /></label><label className="field field-wide"><span>توضیحات</span><input name="description" /></label>{error && <div className="form-error field-wide">{error}</div>}<Button type="submit" disabled={mutation.isPending}><Plus size={17} /> افزودن دسته</Button></form></Modal>;
}
