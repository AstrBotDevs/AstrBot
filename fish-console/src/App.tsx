import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { RequireAdmin } from "./components/RequireAdmin";
import { RequireAuth } from "./components/RequireAuth";
import { AdminOrdersPage } from "./pages/AdminOrdersPage";
import { AppLayout } from "./layouts/AppLayout";
import { BotBindPage } from "./pages/BotBindPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { OrdersPage } from "./pages/OrdersPage";
import { PlansPage } from "./pages/PlansPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TicketsPage } from "./pages/TicketsPage";
import { UsagePage } from "./pages/UsagePage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/plans" element={<PlansPage />} />
            <Route path="/bot" element={<BotBindPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/tickets" element={<TicketsPage />} />
            <Route element={<RequireAdmin />}>
              <Route path="/admin/orders" element={<AdminOrdersPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
