import { Check, ClipboardCheck, Clock3, LogIn, LogOut, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import type { AttendanceStatus, BrandConfig, User } from "../types";
import { Button, Spinner } from "./ui";

interface CheckInGateProps {
  status: AttendanceStatus;
  brand: BrandConfig;
  user: User;
  pending: boolean;
  error: string;
  onCheckIn: () => void;
  onComplete: (itemIds: number[]) => void;
  onLogout: () => void;
}

export function CheckInGate({ status, brand, user, pending, error, onCheckIn, onComplete, onLogout }: CheckInGateProps) {
  const [checked, setChecked] = useState<Set<number>>(() => new Set());
  const checkedIn = status.is_checked_in;
  const items = status.checklist_items;
  const completed = checked.size;
  const allChecked = items.length > 0 && completed === items.length;
  const progress = items.length ? Math.round((completed / items.length) * 100) : 0;
  const selectedIds = useMemo(() => [...checked], [checked]);

  const toggle = (itemId: number) => {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  return (
    <main className="check-in-gate-shell">
      <div className="check-in-gate-glow gate-glow-one" />
      <div className="check-in-gate-glow gate-glow-two" />
      <section className="check-in-gate-card">
        <header className="check-in-gate-header">
          <div className="gate-brand">
            <span className="gate-brand-logo">{brand.logo_url ? <img src={brand.logo_url} alt="" /> : brand.business_name.trim().charAt(0)}</span>
            <span><strong>{brand.business_name}</strong><small>سامانه مدیریت عملیات</small></span>
          </div>
          <button type="button" className="gate-logout" onClick={onLogout}><LogOut size={16} /> خروج از حساب</button>
        </header>

        <div className="check-in-gate-intro">
          <span className="gate-shield"><ShieldCheck /></span>
          <div><span className="eyebrow">{checkedIn ? "مرحله دوم · آماده‌سازی کار" : "مرحله اول · ثبت حضور"}</span><h1>{checkedIn ? `${user.full_name}، شروع شیفت را نهایی کنید` : `${user.full_name}، خوش آمدید`}</h1><p>{checkedIn ? "ورود شما با موفقیت ثبت شد. اکنون موارد اختصاصی شروع کار را انجام دهید و برای ورود به فضای کاری تأیید کنید." : "ابتدا زمان ورود خود را ثبت کنید. بلافاصله پس از ثبت موفق، چک‌لیست اختصاصی شروع کار نمایش داده می‌شود."}</p></div>
        </div>

        {checkedIn ? <>
          <div className="gate-check-in-success"><Check /><span><strong>ورود ثبت شد</strong><small>زمان حضور شما از همین لحظه در حال محاسبه است.</small></span></div>
          <div className="gate-progress-wrap">
            <div><span><ClipboardCheck size={17} /> پیشرفت چک‌لیست</span><strong>{completed.toLocaleString("fa-IR")} از {items.length.toLocaleString("fa-IR")}</strong></div>
            <div className="gate-progress"><i style={{ width: `${progress}%` }} /></div>
          </div>

          <div className="gate-checklist">
            {items.map((item, index) => {
              const active = checked.has(item.id);
              return (
                <button type="button" key={item.id} className={active ? "is-checked" : ""} onClick={() => toggle(item.id)} aria-pressed={active}>
                  <span className="gate-check-index">{active ? <Check /> : (index + 1).toLocaleString("fa-IR")}</span>
                  <span><strong>{item.title}</strong>{item.description && <small>{item.description}</small>}</span>
                  <i />
                </button>
              );
            })}
          </div>
        </> : <div className="gate-check-in-ready"><LogIn /><div><strong>ثبت ورود یک‌مرحله‌ای</strong><p>پس از تأیید، ساعت ورود ذخیره می‌شود و چک‌لیست شروع کار باز خواهد شد.</p></div><span>۱</span></div>}

        {error && <div className="form-error gate-error">{error}</div>}
        <div className="gate-action-row">
          <div><Clock3 /><span><strong>{checkedIn ? "تأیید قابل پیگیری" : "ثبت دقیق زمان ورود"}</strong><small>{checkedIn ? "موارد انجام‌شده همراه همین شیفت ذخیره می‌شوند." : "ساعت حضور و امتیاز ورود به‌صورت خودکار ثبت می‌شود."}</small></span></div>
          <Button className="gate-submit" disabled={(checkedIn && !allChecked) || pending} onClick={() => checkedIn ? onComplete(selectedIds) : onCheckIn()}>
            {checkedIn ? <ClipboardCheck size={18} /> : <LogIn size={18} />} {pending ? "در حال ثبت…" : checkedIn ? allChecked ? "تأیید چک‌لیست و ورود به سامانه" : "همه موارد را تأیید کنید" : "ثبت ورود و نمایش چک‌لیست"}
          </Button>
        </div>
      </section>
    </main>
  );
}

export function CheckInGateLoading({ brand }: { brand: BrandConfig }) {
  return <main className="check-in-gate-shell"><section className="check-in-gate-card gate-loading"><Spinner /><strong>در حال بررسی وضعیت ثبت ورود {brand.business_name}…</strong></section></main>;
}

export function CheckInGateError({ brand, retry, logout }: { brand: BrandConfig; retry: () => void; logout: () => void }) {
  return <main className="check-in-gate-shell"><section className="check-in-gate-card gate-loading"><span className="gate-shield"><ShieldCheck /></span><strong>وضعیت ثبت ورود دریافت نشد</strong><p>برای حفظ امنیت، تا بررسی وضعیت حضور امکان ورود به سامانه وجود ندارد.</p><div><Button onClick={retry}>تلاش دوباره</Button><Button variant="secondary" onClick={logout}>خروج از {brand.business_name}</Button></div></section></main>;
}
