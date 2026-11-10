import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export function RequireAdmin() {
  const { loading, isAdmin } = useAuth();
  if (loading) {
    return <div className="login-page muted">思考中…</div>;
  }
  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}
