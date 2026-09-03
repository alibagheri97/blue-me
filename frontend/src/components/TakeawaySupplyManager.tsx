import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleDollarSign,
  PackageCheck,
  PackageOpen,
  Pencil,
  Plus,
  Scale,
  Search,
  Trash2,
  Warehouse,
  X,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { money, quantity } from "../lib/format";
import type { InventoryItem, TakeawaySupply } from "../types";
import { Badge, Button, EmptyState, Modal, Spinner } from "./ui";

export function TakeawaySupplyManager({
  open,
  close,
  inventory,
}: {
  open: boolean;
  close: () => void;
  inventory: InventoryItem[];
}) {
  const client = useQueryClient();
  const [inventoryItemId, setInventoryItemId] = useState("");
  const [inventorySearch, setInventorySearch] = useState("");
  const [quantityPerPackage, setQuantityPerPackage] = useState("1");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editQuantity, setEditQuantity] = useState("1");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const supplies = useQuery({
    queryKey: ["takeaway-supplies"],
    queryFn: () => api<TakeawaySupply[]>("/takeaway-supplies"),
    enabled: open,
  });
  const matchingInventory = useQuery({
    queryKey: ["inventory", "takeaway-options", inventorySearch],
    queryFn: () =>
      api<{ items: InventoryItem[] }>(
        `/inventory/items?page_size=100&active=true&search=${encodeURIComponent(inventorySearch.trim())}`,
      ),
    enabled: open && inventorySearch.trim().length > 0,
  });
  const configuredIds = useMemo(
    () => new Set((supplies.data || []).map((supply) => supply.inventory_item_id)),
    [supplies.data],
  );
  const inventoryOptions = useMemo(() => {
    const options = new Map<number, InventoryItem>();
    inventory.forEach((item) => options.set(item.id, item));
    matchingInventory.data?.items.forEach((item) => options.set(item.id, item));
    supplies.data?.forEach((supply) =>
      options.set(supply.inventory_item.id, supply.inventory_item),
    );
    return [...options.values()].sort((a, b) => a.name.localeCompare(b.name, "fa"));
  }, [inventory, matchingInventory.data, supplies.data]);
  const normalizedSearch = inventorySearch.trim().toLowerCase();
  const availableInventory = inventoryOptions.filter(
    (item) =>
      item.is_active &&
      !configuredIds.has(item.id) &&
      (!normalizedSearch ||
        item.name.toLowerCase().includes(normalizedSearch) ||
        item.sku.toLowerCase().includes(normalizedSearch)),
  );
  const totalPackageCost = (supplies.data || []).reduce(
    (sum, supply) => sum + Number(supply.calculated_cost),
    0,
  );
  const maximumPackages = supplies.data?.length
    ? Math.min(...supplies.data.map((supply) => supply.max_packages_available))
    : 0;

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["takeaway-supplies"] });
    client.invalidateQueries({ queryKey: ["inventory"] });
  };
  const save = useMutation({
    mutationFn: ({
      path,
      method,
      body,
    }: {
      path: string;
      method: "POST" | "PATCH";
      body: object;
    }) => api<TakeawaySupply>(path, { method, body }),
    onSuccess: () => {
      setError("");
      setInventoryItemId("");
      setInventorySearch("");
      setQuantityPerPackage("1");
      setEditingId(null);
      refresh();
    },
    onError: (reason) =>
      setError(
        reason instanceof ApiError
          ? reason.message
          : "ذخیره اقلام بیرون‌بر انجام نشد",
      ),
  });
  const remove = useMutation({
    mutationFn: (id: number) =>
      api<void>(`/takeaway-supplies/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setError("");
      setDeletingId(null);
      refresh();
    },
    onError: (reason) =>
      setError(
        reason instanceof ApiError
          ? reason.message
          : "حذف کالای بیرون‌بر انجام نشد",
      ),
  });

  const addSupply = (event: FormEvent) => {
    event.preventDefault();
    if (!inventoryItemId || Number(quantityPerPackage) <= 0) return;
    save.mutate({
      path: "/takeaway-supplies",
      method: "POST",
      body: {
        inventory_item_id: Number(inventoryItemId),
        quantity_per_package: quantityPerPackage,
      },
    });
  };
  const updateSupply = (event: FormEvent, supplyId: number) => {
    event.preventDefault();
    if (Number(editQuantity) <= 0) return;
    save.mutate({
      path: `/takeaway-supplies/${supplyId}`,
      method: "PATCH",
      body: { quantity_per_package: editQuantity },
    });
  };

  return (
    <Modal open={open} title="بسته‌بندی و ملزومات بیرون‌بر" onClose={close} wide>
      <div className="takeaway-manager">
        <section className="takeaway-manager-hero">
          <span><PackageOpen /></span>
          <div>
            <small>کسر خودکار از انبار</small>
            <h3>محتویات هر بسته بیرون‌بر</h3>
            <p>
              ظرف، خلال دندان، دستمال و هر کالای مصرفی را از انبار انتخاب کنید.
              با ثبت سفارش بیرون‌بر، مقدار تنظیم‌شده در تعداد بسته ضرب می‌شود.
            </p>
          </div>
        </section>

        <div className="takeaway-manager-stats">
          <div><PackageCheck /><span><small>اقلام تنظیم‌شده</small><strong>{quantity(supplies.data?.length || 0)}</strong></span></div>
          <div><CircleDollarSign /><span><small>هزینه فعلی هر بسته</small><strong>{money(totalPackageCost)}</strong></span></div>
          <div><Warehouse /><span><small>حداکثر بسته قابل آماده‌سازی</small><strong>{supplies.data?.length ? quantity(maximumPackages) : "—"}</strong></span></div>
        </div>

        <form className="takeaway-add-form" onSubmit={addSupply}>
          <label className="field takeaway-inventory-select">
            <span>کالای انبار</span>
            <div className="takeaway-inventory-search">
              <Search />
              <input
                value={inventorySearch}
                onChange={(event) => {
                  setInventorySearch(event.target.value);
                  setInventoryItemId("");
                }}
                placeholder="جست‌وجوی نام یا کد کالا…"
              />
            </div>
            <select
              value={inventoryItemId}
              onChange={(event) => setInventoryItemId(event.target.value)}
              required
            >
              <option value="">انتخاب ظرف یا ملزومات…</option>
              {availableInventory.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · موجودی {quantity(item.current_quantity)} {item.unit}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>مصرف در هر بسته</span>
            <div className="takeaway-quantity-input">
              <Scale />
              <input
                type="number"
                min="0.001"
                step="0.001"
                value={quantityPerPackage}
                onChange={(event) => setQuantityPerPackage(event.target.value)}
                required
              />
              <small>
                {inventoryOptions.find((item) => item.id === Number(inventoryItemId))?.unit || "واحد"}
              </small>
            </div>
          </label>
          <Button
            type="submit"
            disabled={save.isPending || !inventoryItemId || Number(quantityPerPackage) <= 0}
          >
            <Plus size={17} /> افزودن به بسته
          </Button>
        </form>

        {!availableInventory.length && inventoryOptions.length > 0 && !matchingInventory.isFetching && (
          <div className="takeaway-all-configured">
            <Check /> {normalizedSearch ? "کالای فعال دیگری با این جست‌وجو پیدا نشد." : "همه کالاهای فعال انبار در فهرست هستند؛ برای کالای تازه ابتدا آن را در انبار بسازید."}
          </div>
        )}
        {error && <div className="form-error">{error}</div>}

        <section className="takeaway-supply-list">
          {supplies.isLoading ? (
            <div className="center-loader"><Spinner /></div>
          ) : supplies.data?.length ? (
            supplies.data.map((supply, index) => (
              <article key={supply.id}>
                <span className="takeaway-supply-number">{quantity(index + 1)}</span>
                <div className="takeaway-supply-main">
                  <div>
                    <strong>{supply.inventory_item.name}</strong>
                    <Badge tone={supply.max_packages_available > 0 ? "success" : "danger"}>
                      {supply.max_packages_available > 0
                        ? `${quantity(supply.max_packages_available)} بسته موجود`
                        : "ناموجود"}
                    </Badge>
                  </div>
                  <small>
                    موجودی انبار: {quantity(supply.inventory_item.current_quantity)} {supply.inventory_item.unit}
                    {" · "}هزینه هر بسته: {money(supply.calculated_cost)}
                  </small>
                </div>
                {editingId === supply.id ? (
                  <form
                    className="takeaway-inline-edit"
                    onSubmit={(event) => updateSupply(event, supply.id)}
                  >
                    <input
                      type="number"
                      min="0.001"
                      step="0.001"
                      value={editQuantity}
                      onChange={(event) => setEditQuantity(event.target.value)}
                      autoFocus
                    />
                    <span>{supply.inventory_item.unit} / بسته</span>
                    <button type="submit" title="ذخیره" disabled={save.isPending}><Check /></button>
                    <button type="button" title="انصراف" onClick={() => setEditingId(null)}><X /></button>
                  </form>
                ) : (
                  <div className="takeaway-supply-value">
                    <span><strong>{quantity(supply.quantity_per_package)}</strong><small>{supply.inventory_item.unit} / بسته</small></span>
                    <button
                      type="button"
                      title="ویرایش مقدار"
                      onClick={() => {
                        setEditingId(supply.id);
                        setEditQuantity(supply.quantity_per_package);
                        setDeletingId(null);
                        setError("");
                      }}
                    ><Pencil /></button>
                    {deletingId === supply.id ? (
                      <span className="takeaway-delete-confirm">
                        <button type="button" onClick={() => remove.mutate(supply.id)} disabled={remove.isPending}>حذف</button>
                        <button type="button" onClick={() => setDeletingId(null)}>خیر</button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="danger"
                        title="حذف از بسته"
                        onClick={() => {
                          setDeletingId(supply.id);
                          setEditingId(null);
                        }}
                      ><Trash2 /></button>
                    )}
                  </div>
                )}
              </article>
            ))
          ) : (
            <EmptyState
              icon={<PackageOpen />}
              title="هنوز ملزومات بیرون‌بر تنظیم نشده"
              text="یک کالای موجود در انبار مانند ظرف آلومینیومی یا خلال دندان را اضافه کنید."
            />
          )}
        </section>
      </div>
    </Modal>
  );
}
