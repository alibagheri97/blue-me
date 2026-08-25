import { Calculator, Plus, Scale, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { money, quantity } from "../lib/format";
import type { InventoryItem, MenuItem, Recipe, RecipeIngredient } from "../types";
import { Badge, Button, Modal } from "./ui";

interface RecipeEditorProps {
  open: boolean;
  recipe: Recipe | null;
  initialMenuItemId?: number | null;
  lockMenuItem?: boolean;
  close: () => void;
  menu: MenuItem[];
  inventory: InventoryItem[];
  save: (body: object, id?: number) => void;
  pending: boolean;
  error: string;
}

export function RecipeEditor({
  open,
  recipe,
  initialMenuItemId = null,
  lockMenuItem = false,
  close,
  menu,
  inventory,
  save,
  pending,
  error,
}: RecipeEditorProps) {
  const [ingredients, setIngredients] = useState<RecipeIngredient[]>([]);
  const [ingredientSearch, setIngredientSearch] = useState("");
  const [menuItemId, setMenuItemId] = useState("");
  const [yieldQuantity, setYieldQuantity] = useState("1");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) return;
    setIngredients(recipe?.ingredients.map((line) => ({
      inventory_item_id: line.inventory_item_id,
      quantity: line.quantity,
      unit: line.inventory_item?.unit || line.unit,
    })) || []);
    setIngredientSearch("");
    setMenuItemId(String(recipe?.menu_item_id || initialMenuItemId || ""));
    setYieldQuantity(recipe?.yield_quantity || "1");
    setLocalError("");
  }, [initialMenuItemId, open, recipe]);

  const eligibleMenu = useMemo(() => menu.filter((item) => {
    if (item.inventory_item_id) return false;
    if (!item.recipe_configured) return true;
    return item.id === recipe?.menu_item_id || item.id === initialMenuItemId;
  }), [initialMenuItemId, menu, recipe?.menu_item_id]);
  const availableIngredients = useMemo(() => {
    const term = ingredientSearch.trim().toLocaleLowerCase("fa");
    return inventory.filter((item) => {
      if (ingredients.some((line) => line.inventory_item_id === item.id)) return false;
      return !term || item.name.toLocaleLowerCase("fa").includes(term) || item.sku.toLocaleLowerCase("fa").includes(term);
    }).slice(0, 8);
  }, [ingredientSearch, ingredients, inventory]);
  const selectedMenu = menu.find((item) => item.id === Number(menuItemId));
  const totalBatchCost = ingredients.reduce((total, line) => {
    const item = inventory.find((candidate) => candidate.id === line.inventory_item_id);
    return total + Number(line.quantity || 0) * Number(item?.average_cost || 0);
  }, 0);
  const costPerOutput = Number(yieldQuantity) > 0 ? totalBatchCost / Number(yieldQuantity) : 0;

  if (!open) return null;

  const addIngredient = (item: InventoryItem) => {
    setIngredients((current) => [...current, {
      inventory_item_id: item.id,
      quantity: "",
      unit: item.unit,
    }]);
    setIngredientSearch("");
    setLocalError("");
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!menuItemId) {
      setLocalError("محصول منو را انتخاب کنید");
      return;
    }
    if (!ingredients.length) {
      setLocalError("حداقل یک ماده اولیه از انبار اضافه کنید");
      return;
    }
    if (ingredients.some((line) => Number(line.quantity) <= 0)) {
      setLocalError("مقدار مصرف همه مواد اولیه باید بیشتر از صفر باشد");
      return;
    }
    const form = new FormData(event.currentTarget);
    save({
      menu_item_id: Number(menuItemId),
      yield_quantity: yieldQuantity,
      preparation_minutes: Number(form.get("preparation_minutes")),
      instructions: form.get("instructions") || "",
      notes: form.get("notes") || null,
      ingredients,
    }, recipe?.id);
  };

  return <Modal open title={recipe ? `مواد مصرفی · ${recipe.menu_item.name}` : `تعریف مواد مصرفی${selectedMenu ? ` · ${selectedMenu.name}` : ""}`} onClose={close} wide>
    <form className="recipe-editor recipe-output-editor" onSubmit={submit}>
      <div className="recipe-form-main">
        <div className="recipe-output-heading">
          <span><Scale /></span>
          <div><h3>فرمول خروجی منو</h3><p>سیستم مقدار مصرف هر سفارش را از روی این فرمول محاسبه و همان لحظه از انبار کم می‌کند.</p></div>
        </div>
        <div className="form-grid">
          <label className="field field-wide"><span>محصول منو</span><select value={menuItemId} onChange={(event) => setMenuItemId(event.target.value)} disabled={lockMenuItem || !!recipe} required><option value="" disabled>انتخاب محصول</option>{eligibleMenu.map((item) => <option key={item.id} value={item.id}>{item.name} · فروش {money(item.selling_price)}</option>)}</select></label>
          <label className="field"><span>این دستور برای چند عدد خروجی است؟</span><input value={yieldQuantity} onChange={(event) => setYieldQuantity(event.target.value)} type="number" min="0.001" step="0.001" required /></label>
          <label className="field"><span>زمان آماده‌سازی</span><div className="input-with-suffix"><input name="preparation_minutes" type="number" min="0" defaultValue={recipe?.preparation_minutes || 0} /><small>دقیقه</small></div></label>
        </div>
        <div className="recipe-deduction-note">
          <Calculator />
          <div><strong>مبنای کسر خودکار</strong><p>اگر خروجی را ۱ بگذارید، مقادیر روبه‌رو برای هر یک سفارش هستند. سفارش ۲ عدد، همه مقادیر را دو برابر کم می‌کند.</p></div>
        </div>
        <label className="field"><span>مراحل آماده‌سازی <small>(اختیاری)</small></span><textarea name="instructions" rows={5} defaultValue={recipe?.instructions || ""} placeholder="مراحل پخت، دما، ترتیب افزودن مواد و نکات آماده‌سازی…" /></label>
        <label className="field"><span>یادداشت آشپزخانه <small>(اختیاری)</small></span><textarea name="notes" rows={2} defaultValue={recipe?.notes || ""} /></label>
      </div>

      <aside className="ingredient-editor output-ingredient-editor">
        <header><div><h3>مواد مصرفی از انبار</h3><p>{quantity(ingredients.length)} ماده برای {quantity(yieldQuantity || 0)} خروجی</p></div><Badge tone="info">هزینه هر خروجی {money(costPerOutput)}</Badge></header>
        <label className="search-box"><Search size={17}/><input value={ingredientSearch} onChange={(event) => setIngredientSearch(event.target.value)} placeholder="مرغ، نان، نمک، پنیر…" /></label>
        <div className="ingredient-picker-results">{availableIngredients.length ? availableIngredients.map((item) => <button type="button" key={item.id} onClick={() => addIngredient(item)}><Plus /><span><strong>{item.name}</strong><small>موجودی {quantity(item.current_quantity)} {item.unit}</small></span><b>{item.unit}</b></button>) : <p>همه نتایج این جست‌وجو به دستور اضافه شده‌اند.</p>}</div>
        <div className="ingredient-lines output-ingredient-lines">{ingredients.map((line, index) => {
          const item = inventory.find((entry) => entry.id === line.inventory_item_id);
          const lineCost = Number(line.quantity || 0) * Number(item?.average_cost || 0);
          return <div key={line.inventory_item_id}>
            <div><strong>{item?.name || "کالای نامشخص"}</strong><small>موجودی {quantity(item?.current_quantity || 0)} {item?.unit} · هزینه {money(lineCost)}</small></div>
            <label><input aria-label={`مقدار مصرف ${item?.name}`} type="number" min="0.001" step="0.001" required value={line.quantity} placeholder="مقدار" onChange={(event) => setIngredients((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, quantity: event.target.value } : entry))} /><span>{item?.unit || line.unit}</span></label>
            <button type="button" aria-label={`حذف ${item?.name}`} onClick={() => setIngredients((current) => current.filter((_, entryIndex) => entryIndex !== index))}><Trash2 /></button>
          </div>;
        })}</div>
        {!ingredients.length && <div className="recipe-empty-ingredients"><Scale /><strong>مواد اولیه را انتخاب کنید</strong><p>برای نمونه: ۱۰۰ گرم مرغ، ۱ عدد نان، ۲ گرم نمک و ۲۰ گرم پنیر پیتزا.</p></div>}
      </aside>

      {(localError || error) && <div className="form-error recipe-error">{localError || error}</div>}
      <div className="form-actions recipe-actions"><Button type="button" variant="secondary" onClick={close}>انصراف</Button><Button type="submit" disabled={pending || !ingredients.length}>{pending ? "در حال ذخیره فرمول…" : "ذخیره مواد و فعال‌سازی کسر خودکار"}</Button></div>
    </form>
  </Modal>;
}
