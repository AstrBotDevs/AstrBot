import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export function RequireAuth() {
  const { email, loading } = useAuth();
  if (loading) {
    return <div className="login-page muted">思考中…</div>;
  }
  if (!email) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
