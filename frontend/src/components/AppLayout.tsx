import {
  BarChart3,
  Boxes,
  ChefHat,
  ChevronDown,
  CircleUserRound,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  ShoppingCart,
  UsersRound,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { roleLabel } from "../lib/format";
import type { Role } from "../types";

const nav = [
  { to: "/", label: "نمای کلی", icon: LayoutDashboard, roles: ["root", "storage_manager", "accounting_manager", "sales_manager", "kitchen_manager"] },
  { to: "/users", label: "کاربران و دسترسی", icon: UsersRound, roles: ["root"] },
  { to: "/inventory", label: "مدیریت انبار", icon: Boxes, roles: ["root", "storage_manager"] },
  { to: "/pos", label: "سفارش و صندوق", icon: ShoppingCart, roles: ["root", "accounting_manager", "sales_manager"] },
  { to: "/kitchen", label: "آشپزخانه", icon: ChefHat, roles: ["root", "kitchen_manager"] },
  { to: "/reports", label: "آمار و تحلیل", icon: BarChart3, roles: ["root"] },
  { to: "/audit", label: "گزارش فعالیت‌ها", icon: ClipboardList, roles: ["root"] },
] as const;

export function AppLayout() {
  const { user, brand, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  if (!user) return null;
  const visibleNav = nav.filter((item) => (item.roles as readonly Role[]).includes(user.role));

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="mobile-overlay" onClick={() => setSidebarOpen(false)} aria-label="بستن منو" />}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-logo">
            {brand.logo_url ? <img src={brand.logo_url} alt="" /> : <span>B</span>}
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
          <div className="profile-wrap">
            <button className="profile-button" onClick={() => setProfileOpen(!profileOpen)}>
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
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  );
}
