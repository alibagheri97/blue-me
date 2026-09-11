import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ShieldOff } from "lucide-react";
import { useAuth } from "./context/AuthContext";
import { EmptyState, Spinner } from "./components/ui";
import { AppLayout } from "./components/AppLayout";
import { homeForUser, userHasSection } from "./lib/access";
import type { SectionKey } from "./types";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const StaffPage = lazy(() => import("./pages/StaffPage"));
const PayrollPage = lazy(() => import("./pages/PayrollPage"));
const InventoryPage = lazy(() => import("./pages/InventoryPage"));
const PurchasesPage = lazy(() => import("./pages/PurchasesPage"));
const ExpensesPage = lazy(() => import("./pages/ExpensesPage"));
const MenuPage = lazy(() => import("./pages/MenuPage"));
const PosPage = lazy(() => import("./pages/PosPage"));
const KitchenPage = lazy(() => import("./pages/KitchenPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));

function SectionRoute({ section, children }: { section: SectionKey; children: React.ReactNode }) {
  const { user } = useAuth();
  return user && userHasSection(user, section) ? children : <Navigate to={user ? homeForUser(user) : "/"} replace />;
}

function RootRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return user?.role === "root" ? children : <Navigate to={user ? homeForUser(user) : "/"} replace />;
}

function UserHome() {
  const { user } = useAuth();
  return <Navigate to={user ? homeForUser(user) : "/"} replace />;
}

function NoAccessPage() {
  return <section className="panel no-access-panel"><EmptyState icon={<ShieldOff />} title="بخشی برای این حساب فعال نیست" text="مدیرکل می‌تواند از بخش کاربران، دسترسی صفحه‌های موردنیاز شما را فعال کند." /></section>;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loader"><Spinner /></div>;
  if (!user) return <Suspense fallback={<div className="app-loader"><Spinner /></div>}><Routes><Route path="*" element={<LoginPage />} /></Routes></Suspense>;

  return (
    <Suspense fallback={<div className="center-loader"><Spinner /></div>}><Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<SectionRoute section="dashboard"><DashboardPage /></SectionRoute>} />
        <Route path="/users" element={<RootRoute><UsersPage /></RootRoute>} />
        <Route path="/staff" element={<SectionRoute section="staff"><StaffPage /></SectionRoute>} />
        <Route path="/payroll" element={<SectionRoute section="payroll"><PayrollPage /></SectionRoute>} />
        <Route path="/inventory" element={<SectionRoute section="inventory"><InventoryPage /></SectionRoute>} />
        <Route path="/purchases" element={<SectionRoute section="purchases"><PurchasesPage /></SectionRoute>} />
        <Route path="/expenses" element={<SectionRoute section="expenses"><ExpensesPage /></SectionRoute>} />
        <Route path="/menu" element={<SectionRoute section="menu"><MenuPage /></SectionRoute>} />
        <Route path="/pos" element={<SectionRoute section="pos"><PosPage /></SectionRoute>} />
        <Route path="/kitchen" element={<SectionRoute section="kitchen"><KitchenPage /></SectionRoute>} />
        <Route path="/reports" element={<SectionRoute section="reports"><ReportsPage /></SectionRoute>} />
        <Route path="/audit" element={<SectionRoute section="audit"><AuditPage /></SectionRoute>} />
        <Route path="/no-access" element={<NoAccessPage />} />
        <Route path="*" element={<UserHome />} />
      </Route>
    </Routes></Suspense>
  );
}
