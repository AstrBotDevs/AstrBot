import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { BusinessHoursNote } from "../components/BusinessHoursNote";
import { siteConfig } from "../config/site";
import { useAuth } from "../context/AuthContext";

export function RegisterPage() {
  const { email, register, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [inputEmail, setInputEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!authLoading && email) {
    return <Navigate to="/dashboard" replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("两遍通行证不一样哦");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await register(inputEmail, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "报到没成功，再试一下？");
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
        <p className="login-tagline muted">新来的鱼片？先报个到，通行证(密码)至少 8 位。</p>
        <BusinessHoursNote />
        {error ? <div className="alert alert-error">{error}</div> : null}
        <form className="login-form" onSubmit={onSubmit}>
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
            <label htmlFor="password">通行证(密码)</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="confirm">再输一遍</label>
            <input
              id="confirm"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary btn-block" disabled={submitting}>
            {submitting ? "盖章中…" : "报到并进屋"}
          </button>
        </form>
        <p className="login-footer muted">
          已是老鱼片？<Link to="/login">直接进屋</Link>
        </p>
      </div>
    </div>
  );
}
