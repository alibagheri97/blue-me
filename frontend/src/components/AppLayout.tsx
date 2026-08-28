import {
  BarChart3,
  Bell,
  Boxes,
  ChefHat,
  ChevronDown,
  CircleUserRound,
  ClipboardList,
  ContactRound,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  PackagePlus,
  ShoppingCart,
  UtensilsCrossed,
  UsersRound,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../lib/api";
import { dateTime, roleLabel, timeOnly } from "../lib/format";
import type { AttendanceStatus, Notification, Role } from "../types";

const nav = [
  { to: "/", label: "نمای کلی", icon: LayoutDashboard, roles: ["root", "accounting_manager"] },
  { to: "/users", label: "کاربران و دسترسی", icon: UsersRound, roles: ["root"] },
  { to: "/staff", label: "پرسنل، حضور و غذا", icon: ContactRound, roles: ["root", "accounting_manager"] },
  { to: "/inventory", label: "مدیریت انبار", icon: Boxes, roles: ["root", "storage_manager"] },
  { to: "/purchases", label: "ورودی کالا", icon: PackagePlus, roles: ["root", "storage_manager"] },
  { to: "/menu", label: "مدیریت منو", icon: UtensilsCrossed, roles: ["root", "accounting_manager", "sales_manager"] },
  { to: "/pos", label: "سفارش و صندوق", icon: ShoppingCart, roles: ["root", "accounting_manager"] },
  { to: "/kitchen", label: "آشپزخانه", icon: ChefHat, roles: ["root", "kitchen_manager"] },
  { to: "/reports", label: "آمار و تحلیل", icon: BarChart3, roles: ["root", "accounting_manager"] },
  { to: "/audit", label: "گزارش فعالیت‌ها", icon: ClipboardList, roles: ["root"] },
] as const;

function attendanceTime(value: string | undefined) {
  return value ? timeOnly(value) : "";
}

function attendanceDuration(minutes: number) {
  if (minutes < 60) return `${minutes.toLocaleString("fa-IR")} دقیقه`;
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return remaining ? `${hours.toLocaleString("fa-IR")}:${remaining.toLocaleString("fa-IR", { minimumIntegerDigits: 2 })} ساعت` : `${hours.toLocaleString("fa-IR")} ساعت`;
}

export function AppLayout() {
  const { user, brand, logout } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [attendanceError, setAttendanceError] = useState("");
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: Notification[]; unread_count: number }>("/notifications?limit=20"),
    refetchInterval: 30_000,
  });
  const readNotification = useMutation({
    mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const attendance = useQuery({
    queryKey: ["attendance", "me"],
    queryFn: () => api<AttendanceStatus>("/attendance/me"),
    enabled: Boolean(user),
    refetchInterval: 30_000,
  });
  const attendanceMutation = useMutation({
    mutationFn: (action: "check-in" | "check-out") => api<AttendanceStatus>(`/attendance/${action}`, { method: "POST" }),
    onSuccess: (data) => {
      setAttendanceError("");
      client.setQueryData(["attendance", "me"], data);
      client.invalidateQueries({ queryKey: ["attendance", "overview"] });
      client.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (reason) => setAttendanceError(reason instanceof ApiError ? reason.message : "ثبت حضور انجام نشد"),
  });
  if (!user) return null;
  const visibleNav = nav.filter((item) => (item.roles as readonly Role[]).includes(user.role));
  const isCheckedIn = attendance.data?.is_checked_in === true;
  const showAttendance = Boolean(attendance.data?.staff_member) && (attendance.data?.eligible === true || isCheckedIn);

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="mobile-overlay" onClick={() => setSidebarOpen(false)} aria-label="بستن منو" />}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-logo">
            {brand.logo_url ? <img src={brand.logo_url} alt="" /> : <span>{brand.business_name.trim().charAt(0) || "ش"}</span>}
          </div>
          <div><strong>{brand.business_name}</strong><small>{brand.app_name}</small></div>
          <button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)}><X size={20} /></button>
        </div>
        <nav className="sidebar-nav" aria-label="منوی اصلی">
          <span className="nav-caption">فضای کاری</span>
          {visibleNav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setSidebarOpen(false)}>
              <Icon size={19} strokeWidth={1.9} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="status-dot" />
          <div><strong>سامانه آنلاین است</strong><small>عملیات زنده</small></div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setSidebarOpen(true)}><Menu size={22} /></button>
          <div className="topbar-context"><span>فضای مدیریت عملیات</span><strong>{brand.tagline}</strong></div>
          <div className="topbar-actions">
            {showAttendance && <button type="button" className={`attendance-button ${isCheckedIn ? "checked-in" : "checked-out"} ${attendanceError ? "has-error" : ""}`} disabled={attendanceMutation.isPending || attendance.isLoading} onClick={() => attendanceMutation.mutate(isCheckedIn ? "check-out" : "check-in")} title={attendanceError || (isCheckedIn ? "ثبت پایان حضور و خروج" : "ثبت شروع حضور و ورود")}><span className="attendance-icon">{isCheckedIn ? <LogOut size={17} /> : <LogIn size={17} />}</span><span><strong>{attendanceMutation.isPending ? "در حال ثبت…" : isCheckedIn ? "ثبت خروج" : "ثبت ورود"}</strong><small>{attendanceError || (isCheckedIn ? `ورود ${attendanceTime(attendance.data?.current_session?.checked_in_at)}` : `${attendanceDuration(attendance.data?.worked_minutes_today || 0)} امروز`)}</small></span><i /></button>}
            <div className="notification-wrap">
              <button className="notification-button" onClick={() => { setNotificationsOpen(!notificationsOpen); setProfileOpen(false); }} aria-label="اعلان‌ها"><Bell size={20} />{(notifications.data?.unread_count || 0) > 0 && <i>{notifications.data?.unread_count}</i>}</button>
              {notificationsOpen && <div className="notification-menu"><header><div><strong>اعلان‌ها</strong><small>{notifications.data?.unread_count || 0} خوانده‌نشده</small></div>{(notifications.data?.unread_count || 0) > 0 && <button onClick={() => readAll.mutate()}>خواندن همه</button>}</header><div className="notification-list">{notifications.isLoading ? <span className="notification-empty">در حال دریافت…</span> : notifications.data?.items.length ? notifications.data.items.map((item) => <button key={item.id} className={item.is_read ? "read" : ""} onClick={() => { if (!item.is_read) readNotification.mutate(item.id); if (item.entity_type === "daily_need") navigate("/kitchen?tab=needs"); if (item.entity_type === "attendance") navigate("/staff?tab=attendance"); setNotificationsOpen(false); }}><span className="notification-dot" /><div><strong>{item.title}</strong><p>{item.message}</p><small>{dateTime(item.created_at)}</small></div></button>) : <span className="notification-empty">اعلان تازه‌ای ندارید</span>}</div></div>}
            </div>
            <div className="profile-wrap">
              <button className="profile-button" onClick={() => { setProfileOpen(!profileOpen); setNotificationsOpen(false); }}>
                <span className="avatar"><CircleUserRound size={21} /></span>
                <span className="profile-copy"><strong>{user.full_name}</strong><small>{roleLabel[user.role]}</small></span>
                <ChevronDown size={16} />
              </button>
              {profileOpen && (
                <div className="profile-menu">
                  <div><strong>@{user.username}</strong><small>{roleLabel[user.role]}</small></div>
                  <button onClick={logout}><LogOut size={17} /> خروج از حساب</button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  );
}
