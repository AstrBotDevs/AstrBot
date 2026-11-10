import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AlipayPayModal } from "../components/AlipayPayModal";
import { ThinkingNote } from "../components/ThinkingNote";
import {
  fetchBillingPublicConfig,
  resolveAlipayQrUrl,
  type BillingPublicConfig,
  type FeedPlan,
} from "../lib/billing";
import { formatRiceG } from "../lib/rice";

function formatYuan(n: number) {
  return String(Math.trunc(n));
}

function parseIntegerYuan(raw: string, min: number): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number.parseInt(trimmed, 10);
  if (n < Math.ceil(min)) return null;
  if (n > 999) return null;
  return n;
}

export function PlansPage() {
  const navigate = useNavigate();
  const [config, setConfig] = useState<BillingPublicConfig | null>(null);
  const [customYuan, setCustomYuan] = useState("2");
  const [selected, setSelected] = useState<FeedPlan | "custom" | null>(null);
  const [payOpen, setPayOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchBillingPublicConfig().then((c) => {
      if (!cancelled) setConfig(c);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const minYuan = config?.min_yuan ?? 1;
  const gramsPerYuan = config?.rice_grams_per_yuan ?? 500;
  const plans = config?.feed_plans ?? [];
  const qrUrl = resolveAlipayQrUrl(config?.payment?.alipay_qr_url);
  const payHint = config?.payment?.pay_hint || "转账备注请填订单备注码，方便鱼咖对账～";

  const customAmount = useMemo(
    () => parseIntegerYuan(customYuan, minYuan),
    [customYuan, minYuan],
  );

  const customValid = customAmount !== null;
  const payYuan =
    selected && selected !== "custom"
      ? selected.yuan
      : selected === "custom" && customValid
        ? customAmount
        : null;
  const planId =
    selected && selected !== "custom" ? selected.id : undefined;

  return (
    <div className="feed-page">
      <header className="feed-hero">
        <img className="dafeiyu dafeiyu-hero" src="/dafeiyu/eating.webp" alt="大肥鱼在吃白饭" />
        <h2 className="feed-hero-title">大肥鱼电饭煲站</h2>
        <p className="feed-hero-sub">
          <strong>1 元 = {gramsPerYuan}g 白饭</strong> · 整数元起，最低 ¥{formatYuan(minYuan)} · 支付宝扫码
        </p>
      </header>

      <ThinkingNote seconds={2}>
        {"鱼片要给我添饭？\n一块钱也行，我不挑。多添点的话……我可以考虑少摸会儿鱼。"}
      </ThinkingNote>

      <h3 className="feed-section-title">添饭套餐</h3>
      <p className="muted feed-section-desc">三档饭量，名字是店里猫猫起的。也可以在下面自己填。</p>
      <div className="feed-grid">
        {plans.map((plan) => {
          const active = selected !== "custom" && selected?.id === plan.id;
          return (
            <button
              key={plan.id}
              type="button"
              className={`feed-card${active ? " feed-card-active" : ""}`}
              onClick={() => setSelected(plan)}
            >
              <span className="feed-card-badge">¥{plan.yuan}</span>
              <span className="feed-card-name">{plan.name}</span>
              <span className="feed-card-blurb">{plan.blurb}</span>
              <span className="feed-card-credit">{formatRiceG(plan.yuan * gramsPerYuan)}</span>
            </button>
          );
        })}
      </div>

      <article className="card feed-custom-card">
        <h3 className="feed-section-title">自己定饭量</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          填<strong>整数</strong>元就行。
        </p>
        <div className="feed-custom-row">
          <label className="feed-custom-label" htmlFor="custom-yuan">
            我想添（元）
          </label>
          <input
            id="custom-yuan"
            className="feed-custom-input"
            type="number"
            min={Math.ceil(minYuan)}
            step="1"
            inputMode="numeric"
            value={customYuan}
            onChange={(e) => {
              setCustomYuan(e.target.value);
              setSelected("custom");
            }}
            onFocus={() => setSelected("custom")}
          />
        </div>
        {selected === "custom" && !customValid ? (
          <p className="feed-warn">最少 ¥{formatYuan(minYuan)}，再少我就不起床了。</p>
        ) : null}
      </article>

      <div className="feed-checkout card">
        {payYuan !== null ? (
          <p className="feed-checkout-line">
            本次添饭 <strong>¥{formatYuan(payYuan)}</strong>
            <span className="feed-checkout-arrow"> → </span>
            <strong className="feed-checkout-credit">{formatRiceG(payYuan * gramsPerYuan)}</strong>
          </p>
        ) : (
          <p className="muted">先选一档，或者自己填个数。</p>
        )}
        <button
          type="button"
          className="btn-primary feed-pay-btn"
          disabled={payYuan === null}
          onClick={() => setPayOpen(true)}
        >
          {payYuan !== null ? "支付宝添饭" : "先选饭量"}
        </button>
        <p className="muted feed-footnote">
          付完款饭就进碗。还没登记的话记得去「接鱼回家」，不然我找不到你家门。
        </p>
      </div>

      {payYuan !== null ? (
        <AlipayPayModal
          open={payOpen}
          amountYuan={payYuan}
          planId={planId}
          qrUrl={qrUrl}
          payHint={payHint}
          onClose={() => setPayOpen(false)}
          onSuccess={() => {
            setPayOpen(false);
            navigate("/dashboard", { replace: true });
          }}
        />
      ) : null}
    </div>
  );
}
