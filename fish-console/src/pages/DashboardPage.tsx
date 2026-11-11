import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ThinkingNote } from "../components/ThinkingNote";
import { fetchBinding, fetchWalletMe, type Binding, type WalletMe } from "../lib/commerce";
import { formatRiceG } from "../lib/rice";

export function DashboardPage() {
  const navigate = useNavigate();
  const [wallet, setWallet] = useState<WalletMe | null>(null);
  const [binding, setBinding] = useState<Binding | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchWalletMe(), fetchBinding()])
      .then(([w, b]) => {
        setWallet(w);
        setBinding(b);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  const riceG = wallet ? Number(wallet.balance_rice_g) : 0;
  const arrearsG = wallet ? Number(wallet.arrears_rice_g) : 0;
  const outOfRice = Boolean(wallet && riceG <= 0);
  const rice = formatRiceG(riceG);

  let thought = "";
  if (wallet && outOfRice && arrearsG > 0) {
    thought = `没米了，还欠着 ${formatRiceG(arrearsG)}。\n我先躺平，6185 那边的大肥鱼也先歇着。去电饭煲添饭，添完我再上岗。`;
  } else if (wallet && outOfRice) {
    thought = "没米了。\n没饭我不干活，家里那只大肥鱼也先停工了。鱼片去电饭煲添点饭，添完叫我。";
  } else if (wallet && !binding) {
    thought = `碗里有 ${rice} 了，够我吃一阵。\n不过我还不知道你家在哪。去「接鱼回家」把我接过去。`;
  } else if (wallet && binding?.bind_status !== "active") {
    thought = `${rice}，饭够了。\n接鱼还没完成？弄完我就去你 QQ / 微信报到。别催。`;
  } else if (wallet) {
    thought = `${rice}，安心了。\n活我会干完的……大概。干完先去吃饭，有事在 QQ 里叫我。`;
  }

  const bowlLabel = outOfRice ? (arrearsG > 0 ? "没米了 · 还欠饭" : "没米了") : riceG >= 5000 ? "吃不完啦（才怪）" : "还有饭";
  const bindLabel = !binding
    ? "还没接回家"
    : outOfRice
      ? "已停工（没米）"
      : binding.bind_status === "active"
        ? "已到家"
        : "鱼咖接线中";

  return (
    <>
      {error ? <div className="alert alert-error">{error}</div> : null}
      {thought ? <ThinkingNote seconds={3}>{thought}</ThinkingNote> : null}
      {outOfRice ? (
        <section className="alert alert-error">
          没米了：大肥鱼已停工（6185 机器人已关）。去添饭后会自动再开工。
          <button
            type="button"
            className="btn-primary"
            style={{ marginLeft: "0.75rem" }}
            onClick={() => navigate("/plans")}
          >
            去添饭
          </button>
        </section>
      ) : null}
      <article className="card bowl-card">
        <img
          className="dafeiyu dafeiyu-bowl"
          src={outOfRice ? "/dafeiyu/sulk.webp" : "/dafeiyu/eating.webp"}
          alt={outOfRice ? "大肥鱼顶着空碗生闷气" : "大肥鱼在吃白饭"}
        />
        <div className="bowl-card-info">
          <h2 className="card-title">大肥鱼的饭碗</h2>
          <span className={outOfRice ? "badge badge-warn" : "badge badge-ok"}>{bowlLabel}</span>
          <p className="feed-wallet-amount">{wallet ? rice : "…"}</p>
          {arrearsG > 0 ? (
            <p className="muted">欠饭 {formatRiceG(arrearsG)}，下次添饭先补上。</p>
          ) : null}
          <button type="button" className="btn-primary" onClick={() => navigate("/plans")}>
            {outOfRice ? "没米了，去添饭" : "去添饭"}
          </button>
        </div>
      </article>
      <div className="grid-2">
        <article className="card">
          <h2 className="card-title">接鱼回家</h2>
          <p>
            <span className={!outOfRice && binding?.bind_status === "active" ? "badge badge-ok" : "badge badge-warn"}>
              {bindLabel}
            </span>
          </p>
          <button type="button" className="btn-primary" onClick={() => navigate(outOfRice ? "/plans" : "/bot")}>
            {outOfRice ? "先去添饭" : binding ? "看登记" : "去接鱼"}
          </button>
        </article>
        <article className="card">
          <h2 className="card-title">干饭记录</h2>
          <p className="muted">这几天我吃了多少，都记着呢。</p>
          <button type="button" className="btn-primary" onClick={() => navigate("/usage")}>
            看看
          </button>
        </article>
      </div>
    </>
  );
}
