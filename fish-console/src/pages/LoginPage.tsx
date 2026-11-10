import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { siteConfig } from "../config/site";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { email, login, loading: authLoading, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [inputEmail, setInputEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!authLoading && email) {
    return <Navigate to={isAdmin ? "/admin/orders" : "/dashboard"} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const signedIn = await login(inputEmail, password);
      navigate(signedIn.role === "admin" ? "/admin/orders" : "/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "没登进去，再试一次？");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading) {
    return <div className="login-page muted">思考中…</div>;
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <img className="dafeiyu dafeiyu-login" src="/dafeiyu/hello.webp" alt="大肥鱼" />
        <h1>{siteConfig.brandName}</h1>
        <p className="muted" style={{ textAlign: "center", marginBottom: "1.5rem" }}>
          鱼片来了？登录一下，我看看是谁在敲碗。
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="email">联系邮箱</label>
            <input
              id="email"
              type="email"
              placeholder="鱼片常用邮箱"
              required
              autoComplete="email"
              value={inputEmail}
              onChange={(e) => setInputEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">通行证</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={submitting}
          >
            {submitting ? "进门中…" : "进屋"}
          </button>
        </form>
        <p className="muted" style={{ textAlign: "center", marginTop: "1rem" }}>
          新来的鱼片？<Link to="/register">先报到</Link>
        </p>
      </div>
    </div>
  );
}
