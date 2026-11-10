import { useEffect, useState, type FormEvent } from "react";

import { createTicket, fetchTickets, type Ticket } from "../lib/commerce";

export function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function reload() {
    fetchTickets()
      .then(setTickets)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }

  useEffect(() => {
    reload();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createTicket(subject.trim(), body.trim());
      setSubject("");
      setBody("");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        大肥鱼不理人、饭没到碗、账对不上……跟鱼咖说一声。
      </p>
      {error ? <div className="alert alert-error">{error}</div> : null}
      <article className="card">
        <h2 className="card-title">新留言</h2>
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="ticket-subject">主题</label>
            <input
              id="ticket-subject"
              required
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="例如：接鱼登记好了但没回复"
            />
          </div>
          <div className="field">
            <label htmlFor="ticket-body">想说啥</label>
            <textarea
              id="ticket-body"
              required
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              style={{ width: "100%", font: "inherit", padding: "0.55rem 0.75rem" }}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "发送中…" : "发给鱼咖"}
          </button>
        </form>
      </article>
      <article className="card">
        <h2 className="card-title">以前的留言</h2>
        {tickets.length === 0 ? (
          <p className="muted">还没有留言～</p>
        ) : (
          <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {tickets.map((t) => (
              <li key={t.id} style={{ marginBottom: "0.75rem" }}>
                <strong>{t.subject}</strong> · {t.status}
                <br />
                <span className="muted">{new Date(t.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </article>
    </>
  );
}
