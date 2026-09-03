import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { Spinner } from "./components/ui";
import { AppLayout } from "./components/AppLayout";
import type { Role } from "./types";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const StaffPage = lazy(() => import("./pages/StaffPage"));
const PayrollPage = lazy(() => import("./pages/PayrollPage"));
const InventoryPage = lazy(() => import("./pages/InventoryPage"));
const PurchasesPage = lazy(() => import("./pages/PurchasesPage"));
const MenuPage = lazy(() => import("./pages/MenuPage"));
const PosPage = lazy(() => import("./pages/PosPage"));
const KitchenPage = lazy(() => import("./pages/KitchenPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));

function roleHome(role: Role) {
  if (role === "kitchen_manager") return "/kitchen";
  if (role === "storage_manager") return "/inventory";
  if (role === "sales_manager") return "/menu";
  return "/";
}

function RoleRoute({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const { user } = useAuth();
  return user && roles.includes(user.role) ? children : <Navigate to={user ? roleHome(user.role) : "/"} replace />;
}

function RoleHome() {
  const { user } = useAuth();
  return <Navigate to={user ? roleHome(user.role) : "/"} replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loader"><Spinner /></div>;
  if (!user) return <Suspense fallback={<div className="app-loader"><Spinner /></div>}><Routes><Route path="*" element={<LoginPage />} /></Routes></Suspense>;

  return (
    <Suspense fallback={<div className="center-loader"><Spinner /></div>}><Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<RoleRoute roles={["root", "accounting_manager"]}><DashboardPage /></RoleRoute>} />
        <Route path="/users" element={<RoleRoute roles={["root"]}><UsersPage /></RoleRoute>} />
        <Route path="/staff" element={<RoleRoute roles={["root", "accounting_manager"]}><StaffPage /></RoleRoute>} />
        <Route path="/payroll" element={<RoleRoute roles={["root"]}><PayrollPage /></RoleRoute>} />
        <Route path="/inventory" element={<RoleRoute roles={["root", "storage_manager"]}><InventoryPage /></RoleRoute>} />
        <Route path="/purchases" element={<RoleRoute roles={["root", "storage_manager", "accounting_manager"]}><PurchasesPage /></RoleRoute>} />
        <Route path="/menu" element={<RoleRoute roles={["root", "accounting_manager", "sales_manager"]}><MenuPage /></RoleRoute>} />
        <Route path="/pos" element={<RoleRoute roles={["root", "accounting_manager"]}><PosPage /></RoleRoute>} />
        <Route path="/kitchen" element={<RoleRoute roles={["root", "kitchen_manager"]}><KitchenPage /></RoleRoute>} />
        <Route path="/reports" element={<RoleRoute roles={["root", "accounting_manager"]}><ReportsPage /></RoleRoute>} />
        <Route path="/audit" element={<RoleRoute roles={["root"]}><AuditPage /></RoleRoute>} />
        <Route path="*" element={<RoleHome />} />
      </Route>
    </Routes></Suspense>
  );
}
