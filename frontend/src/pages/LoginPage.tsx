import { ArrowRight, BarChart3, Boxes, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";
import { Button } from "../components/ui";

export default function LoginPage() {
  const { brand, login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitting(true);
    setError("");
    try {
      await login(String(form.get("username")), String(form.get("password")));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "ورود انجام نشد؛ دوباره تلاش کنید.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-showcase">
        <div className="showcase-brand">
          <div className="brand-logo brand-logo-large">
            {brand.logo_url ? <img src={brand.logo_url} alt="" /> : <span>{brand.business_name.trim().charAt(0) || "ش"}</span>}
          </div>
          <span>{brand.app_name}</span>
        </div>
        <div className="showcase-copy">
          <span className="eyebrow"><ShieldCheck size={15} /> یک مرکز مطمئن برای تمام عملیات</span>
          <h1>از صندوق تا انبار، همه‌چیز شفاف و یکپارچه.</h1>
          <p>سفارش‌ها، موجودی، دستور پخت، خرید، کاربران و عملکرد کسب‌وکار؛ همه به‌صورت زنده در کنار هم.</p>
          <div className="showcase-features">
            <span><Boxes size={20} /><b>موجودی لحظه‌ای</b><small>گردش هر کالا را ببینید</small></span>
            <span><BarChart3 size={20} /><b>تحلیل کاربردی</b><small>با داده واقعی تصمیم بگیرید</small></span>
          </div>
        </div>
        <div className="showcase-orb orb-one" /><div className="showcase-orb orb-two" />
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <span className="mobile-login-brand">{brand.business_name}</span>
          <div className="login-heading"><span className="eyebrow">ورود امن به سامانه</span><h2>خوش آمدید</h2><p>برای ورود به {brand.business_name} نام کاربری و رمز عبور خود را وارد کنید.</p></div>
          <label className="field"><span>نام کاربری</span><input name="username" autoComplete="username" autoFocus required placeholder="نام کاربری" /></label>
          <label className="field"><span>رمز عبور</span><span className="password-field"><input name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required placeholder="رمز عبور" /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-label="نمایش رمز عبور">{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span></label>
          {error && <div className="form-error">{error}</div>}
          <Button type="submit" disabled={submitting} className="login-submit">{submitting ? "در حال ورود…" : <>ورود به سامانه <ArrowRight size={18} /></>}</Button>
          <p className="login-help">دسترسی شما توسط مدیر کل سامانه مدیریت می‌شود.</p>
        </form>
      </section>
    </main>
  );
}
