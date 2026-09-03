import { Check, ClipboardCheck, LogOut, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CheckInChecklistItem } from "../types";
import { Button, Modal } from "./ui";

interface CheckoutChecklistModalProps {
  open: boolean;
  items: CheckInChecklistItem[];
  pending: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (itemIds: number[]) => void;
}

export function CheckoutChecklistModal({ open, items, pending, error, onClose, onSubmit }: CheckoutChecklistModalProps) {
  const [checked, setChecked] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!open) setChecked(new Set());
  }, [open]);
  const selectedIds = useMemo(() => [...checked], [checked]);
  const allChecked = items.length > 0 && checked.size === items.length;
  const progress = items.length ? Math.round((checked.size / items.length) * 100) : 0;

  const toggle = (itemId: number) => {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  return <Modal open={open} title="چک‌لیست پایان شیفت" onClose={onClose} wide>
    <div className="checkout-checklist-modal">
      <header><span><ShieldCheck /></span><div><strong>قبل از ثبت خروج، پایان کار را تحویل دهید</strong><p>همه موارد زیر را انجام و تأیید کنید. پس از ثبت نهایی، ساعت خروج و امتیازهای این شیفت ذخیره می‌شوند.</p></div></header>
      <div className="checkout-progress"><span><ClipboardCheck /> {checked.size.toLocaleString("fa-IR")} از {items.length.toLocaleString("fa-IR")} مورد</span><strong>{progress.toLocaleString("fa-IR")}٪</strong><i><b style={{ width: `${progress}%` }} /></i></div>
      <div className="checkout-checklist-items">{items.map((item, index) => {
        const active = checked.has(item.id);
        return <button type="button" key={item.id} className={active ? "is-checked" : ""} onClick={() => toggle(item.id)} aria-pressed={active}><span>{active ? <Check /> : (index + 1).toLocaleString("fa-IR")}</span><div><strong>{item.title}</strong>{item.description && <small>{item.description}</small>}</div></button>;
      })}</div>
      {error && <div className="form-error">{error}</div>}
      <footer><Button variant="secondary" onClick={onClose} disabled={pending}>ادامه کار</Button><Button disabled={!allChecked || pending} onClick={() => onSubmit(selectedIds)}><LogOut size={18} /> {pending ? "در حال ثبت خروج…" : allChecked ? "ثبت نهایی خروج" : "همه موارد را انجام دهید"}</Button></footer>
    </div>
  </Modal>;
}
