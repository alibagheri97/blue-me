import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { Spinner } from "./components/ui";
import { AppLayout } from "./components/AppLayout";
import type { Role } from "./types";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const InventoryPage = lazy(() => import("./pages/InventoryPage"));
const PurchasesPage = lazy(() => import("./pages/PurchasesPage"));
const MenuPage = lazy(() => import("./pages/MenuPage"));
const PosPage = lazy(() => import("./pages/PosPage"));
const KitchenPage = lazy(() => import("./pages/KitchenPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));

function RoleRoute({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const { user } = useAuth();
  return user && roles.includes(user.role) ? children : <Navigate to="/" replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loader"><Spinner /></div>;
  if (!user) return <Suspense fallback={<div className="app-loader"><Spinner /></div>}><Routes><Route path="*" element={<LoginPage />} /></Routes></Suspense>;

  return (
    <Suspense fallback={<div className="center-loader"><Spinner /></div>}><Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/users" element={<RoleRoute roles={["root"]}><UsersPage /></RoleRoute>} />
        <Route path="/inventory" element={<RoleRoute roles={["root", "storage_manager"]}><InventoryPage /></RoleRoute>} />
        <Route path="/purchases" element={<RoleRoute roles={["root", "storage_manager"]}><PurchasesPage /></RoleRoute>} />
        <Route path="/menu" element={<RoleRoute roles={["root", "accounting_manager", "sales_manager", "kitchen_manager"]}><MenuPage /></RoleRoute>} />
        <Route path="/pos" element={<RoleRoute roles={["root", "accounting_manager", "sales_manager"]}><PosPage /></RoleRoute>} />
        <Route path="/kitchen" element={<RoleRoute roles={["root", "kitchen_manager"]}><KitchenPage /></RoleRoute>} />
        <Route path="/reports" element={<RoleRoute roles={["root"]}><ReportsPage /></RoleRoute>} />
        <Route path="/audit" element={<RoleRoute roles={["root"]}><AuditPage /></RoleRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes></Suspense>
  );
}
