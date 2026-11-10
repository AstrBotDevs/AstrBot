import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ThinkingNote } from "../components/ThinkingNote";
import {
  fetchBinding,
  fetchWalletMe,
  saveBinding,
  type Binding,
} from "../lib/commerce";

export function BotBindPage() {
  const [canBind, setCanBind] = useState(false);
  const [binding, setBinding] = useState<Binding | null>(null);
  const [qqAppid, setQqAppid] = useState("");
  const [adapterId, setAdapterId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchWalletMe(), fetchBinding()])
      .then(([wallet, bind]) => {
        setCanBind(wallet.can_bind);
        setBinding(bind);
        if (bind) {
          setQqAppid(bind.qq_appid ?? "");
          setAdapterId(bind.adapter_id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveBinding({
        qq_appid: qqAppid.trim(),
        adapter_id: adapterId.trim(),
      });
      setBinding(saved);
      setMessage("登记好了。鱼咖接通以后，我就去你 QQ 里报到。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (!canBind && !binding) {
    return (
      <>
        <ThinkingNote seconds={2}>
          {"要接我回家？\n碗还是空的……没饭我是不会出门的。先添点饭，再来登记。"}
        </ThinkingNote>
        <article className="card bowl-card">
          <img className="dafeiyu dafeiyu-bowl" src="/dafeiyu/sulk.webp" alt="大肥鱼顶着空碗生闷气" />
          <div className="bowl-card-info">
            <h2 className="card-title">碗是空的</h2>
            <p className="muted">添过饭才能登记接鱼。</p>
            <Link to="/plans" className="btn-primary">
              去添饭
            </Link>
          </div>
        </article>
      </>
    );
  }

  return (
    <>
      <section className="alert feed-banner">
        先在{" "}
        <a href="https://q.qq.com" target="_blank" rel="noopener noreferrer">
          QQ 开放平台
        </a>{" "}
        创建机器人，再把 AppID 和实例 ID 填到这里，鱼咖帮你接通。
      </section>
      {binding ? (
        <article className="card">
          <h2 className="card-title">接鱼登记</h2>
          <p className="muted">
            状态：{binding.bind_status === "active" ? "已到家，在线" : "鱼咖接线中"}
          </p>
          <p>
            QQ AppID：<strong>{binding.qq_appid}</strong>
          </p>
          <p>
            实例 ID：<strong>{binding.adapter_id}</strong>
          </p>
          <p className="muted">扫码登录还在鱼咖后台接，接好后大肥鱼会在你的 QQ 里上线。</p>
        </article>
      ) : null}
      <article className="card">
        <h2 className="card-title">{binding ? "改登记信息" : "第一次接鱼"}</h2>
        {error ? <div className="alert alert-error">{error}</div> : null}
        {message ? <div className="alert feed-banner">{message}</div> : null}
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="qq-appid">QQ 机器人 AppID</label>
            <input
              id="qq-appid"
              required
              value={qqAppid}
              onChange={(e) => setQqAppid(e.target.value)}
              placeholder="开放平台里的 AppID"
            />
          </div>
          <div className="field">
            <label htmlFor="adapter-id">AstrBot 平台实例 ID</label>
            <input
              id="adapter-id"
              required
              value={adapterId}
              onChange={(e) => setAdapterId(e.target.value)}
              placeholder="例如 default_1906369614"
            />
            <p className="muted" style={{ marginTop: "0.35rem" }}>
              和运营后台里 QQ 适配器的 id 一致，用来记大肥鱼在你家吃了多少饭，不会算到别人头上。
            </p>
          </div>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "提交中…" : "保存登记"}
          </button>
        </form>
      </article>
    </>
  );
}
