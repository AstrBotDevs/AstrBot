import { useEffect, useState } from "react";

import { createOrder, markOrderPaid, type Order } from "../lib/commerce";

type AlipayPayModalProps = {
  open: boolean;
  amountYuan: number;
  planId?: string;
  qrUrl: string;
  payHint: string;
  onClose: () => void;
  onSuccess: (order: Order) => void;
};

type PayStep = "intro" | "memo" | "scan";

const STATUS_ZH: Record<string, string> = {
  pending: "等你扫码",
  user_marked: "用户声明已支付，鱼咖核对中",
  confirmed: "已入账，已发粮",
  rejected: "未通过",
};

export function AlipayPayModal({
  open,
  amountYuan,
  planId,
  qrUrl,
  payHint,
  onClose,
  onSuccess,
}: AlipayPayModalProps) {
  const [order, setOrder] = useState<Order | null>(null);
  const [step, setStep] = useState<PayStep>("intro");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [qrBroken, setQrBroken] = useState(false);

  useEffect(() => {
    if (!open) {
      setOrder(null);
      setStep("intro");
      setError(null);
      setCopied(false);
      setQrBroken(false);
    }
  }, [open]);

  if (!open) return null;

  const yuan = Math.trunc(amountYuan);

  async function startPay() {
    setLoading(true);
    setError(null);
    try {
      const created = await createOrder(amountYuan, planId);
      setOrder(created);
      setStep("memo");
    } catch (err) {
      setError(err instanceof Error ? err.message : "下单失败");
    } finally {
      setLoading(false);
    }
  }

  async function copyMemo() {
    if (!order) return;
    try {
      await navigator.clipboard.writeText(order.memo_code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("复制失败，请长按备注码手动复制");
    }
  }

  async function confirmTransfer() {
    if (!order) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await markOrderPaid(order.id);
      setOrder(updated);
      if (updated.status === "confirmed") {
        onSuccess(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <article className="card modal-card pay-modal">
        <h2 className="card-title">支付宝添饭 ¥{yuan}</h2>

        {step !== "intro" ? (
          <ol className="pay-steps" aria-label="付款步骤">
            <li className={step === "memo" ? "pay-step-active" : "pay-step-done"}>
              1 复制备注码
            </li>
            <li className={step === "scan" ? "pay-step-active" : undefined}>2 扫码转账</li>
          </ol>
        ) : null}

        {step === "intro" ? (
          <>
            <p className="muted">
              先帮你生成订单和备注码，再分两步：复制备注 → 扫码转 ¥{yuan}。
            </p>
            {error ? <div className="alert alert-error">{error}</div> : null}
            <button type="button" className="btn-primary" disabled={loading} onClick={startPay}>
              {loading ? "生成中…" : "生成付款单"}
            </button>
            <button type="button" className="btn-text" onClick={onClose}>
              先不了
            </button>
          </>
        ) : null}

        {step === "memo" && order ? (
          <>
            <p className="feed-checkout-line">
              应付 <strong>¥{yuan}</strong>
            </p>
            <p className="muted pay-step-lead">先把备注码复制好，下一步再打开支付宝扫码～</p>
            <div className="memo-copy-box">
              <span className="memo-copy-label">备注码</span>
              <code className="memo-copy-code">{order.memo_code}</code>
              <button type="button" className="btn-tonal memo-copy-btn" onClick={copyMemo}>
                {copied ? "已复制" : "复制备注码"}
              </button>
            </div>
            <p className="muted">{payHint}</p>
            {error ? <div className="alert alert-error">{error}</div> : null}
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setQrBroken(false);
                setStep("scan");
              }}
            >
              下一步：扫码转账
            </button>
            <button type="button" className="btn-text" onClick={onClose}>
              先不了
            </button>
          </>
        ) : null}

        {step === "scan" && order ? (
          <>
            <p className="feed-checkout-line">
              转 <strong>¥{yuan}</strong>，备注填 <strong>{order.memo_code}</strong>
            </p>
            <p className="muted">{payHint}</p>
            {qrUrl && !qrBroken ? (
              <img
                className="alipay-qr"
                src={qrUrl}
                alt="支付宝收款码"
                onError={() => setQrBroken(true)}
              />
            ) : (
              <p className="feed-warn">
                收款码加载失败：请确认 public 下有图片，或配置 VITE_ALIPAY_QR_URL=/收款码.jpg
              </p>
            )}
            <p className="muted">状态：{STATUS_ZH[order.status] ?? order.status}</p>
            {error ? <div className="alert alert-error">{error}</div> : null}
            {order.status !== "confirmed" ? (
              <button
                type="button"
                className="btn-primary"
                disabled={loading}
                onClick={confirmTransfer}
              >
                {loading ? "提交中…" : "我已转完，喊鱼咖收一下"}
              </button>
            ) : (
              <p className="badge badge-ok">饭到碗里了</p>
            )}
            <button type="button" className="btn-text" onClick={() => setStep("memo")}>
              返回上一步
            </button>
            <button type="button" className="btn-text" onClick={onClose}>
              关闭
            </button>
          </>
        ) : null}
      </article>
    </div>
  );
}
