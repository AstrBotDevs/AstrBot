import { useCallback, useEffect, useState } from "react";

import {
  adminConfirmOrder,
  fetchAdminOrders,
  type AdminOrder,
} from "../lib/commerce";

const STATUS_ZH: Record<string, string> = {
  pending: "等你扫码",
  user_marked: "鱼咖核对中",
  confirmed: "已入账，已发粮",
  rejected: "未通过",
};

function statusPillClass(status: string): string {
  if (status === "user_marked") return "status-pill status-pill-review";
  if (status === "confirmed") return "status-pill status-pill-done";
  if (status === "pending") return "status-pill status-pill-wait";
  return "status-pill";
}

function formatYuan(v: string | number) {
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(v);
}

type EnsureModalProps = {
  order: AdminOrder;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

function EnsureModal({ order, busy, onClose, onConfirm }: EnsureModalProps) {
  const [amountOk, setAmountOk] = useState(false);
  const [memoOk, setMemoOk] = useState(false);
  const canEnsure = amountOk && memoOk;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <article className="card modal-card ensure-modal">
        <h2 className="card-title">核对到账</h2>
        <p className="muted ensure-lead">
          打开手机支付宝 → 账单，找到这笔转账，逐项打勾后再入账。
        </p>
        <dl className="ensure-facts">
          <dt>用户</dt>
          <dd>{order.user_email}</dd>
          <dt>支付宝应付</dt>
          <dd>
            <strong>¥{formatYuan(order.amount_yuan)}</strong>
          </dd>
          <dt>备注码</dt>
          <dd>
            <code className="memo-copy-code">{order.memo_code}</code>
          </dd>
          <dt>实际 APIKEY 额度</dt>
          <dd>
            <strong>¥{formatYuan(order.credit_yuan)}</strong> 确认后进该用户钱包
          </dd>
          <dt>用户状态</dt>
          <dd>{STATUS_ZH[order.status] ?? order.status}</dd>
        </dl>
        {order.status === "pending" ? (
          <p className="feed-warn">用户还没点「我已转完」，请确认支付宝里真的到账再勾选。</p>
        ) : null}
        <label className="ensure-check">
          <input
            type="checkbox"
            checked={amountOk}
            onChange={(e) => setAmountOk(e.target.checked)}
          />
          支付宝到账金额 = ¥{formatYuan(order.amount_yuan)}
        </label>
        <label className="ensure-check">
          <input
            type="checkbox"
            checked={memoOk}
            onChange={(e) => setMemoOk(e.target.checked)}
          />
          转账备注与备注码一致（{order.memo_code}）
        </label>
        <button
          type="button"
          className="btn-primary"
          disabled={!canEnsure || busy}
          onClick={onConfirm}
        >
          {busy ? "入账中…" : "已核实，确认入账"}
        </button>
        <button type="button" className="btn-text" disabled={busy} onClick={onClose}>
          先不处理
        </button>
      </article>
    </div>
  );
}

export function AdminOrdersPage() {
  const [filter, setFilter] = useState<string>("user_marked");
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [ensureOrder, setEnsureOrder] = useState<AdminOrder | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = await fetchAdminOrders(filter || undefined);
      setOrders(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmEnsured(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await adminConfirmOrder(id);
      setEnsureOrder(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "入账失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        鱼咖收银台：支付宝实收看「应付」；确认后按系数发放「实际 APIKEY 额度」到用户钱包（FISH_TOPUP_CREDIT_RATIO）。
      </p>
      {error ? <div className="alert alert-error">{error}</div> : null}
      <div className="admin-filter-row">
        <label htmlFor="status-filter">筛选状态</label>
        <select
          id="status-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="user_marked">鱼咖核对中</option>
          <option value="pending">等你扫码</option>
          <option value="confirmed">已入账，已发粮</option>
          <option value="">全部</option>
        </select>
        <button type="button" className="btn-text" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <article className="card">
        <h2 className="card-title">全站添饭单</h2>
        {orders.length === 0 ? (
          <p className="empty-state">暂无待处理订单；可切换筛选或点刷新。</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>用户</th>
                <th>支付宝应付</th>
                <th>实际 APIKEY 额度</th>
                <th>备注码</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>{new Date(o.created_at).toLocaleString()}</td>
                  <td>{o.user_email}</td>
                  <td>¥{formatYuan(o.amount_yuan)}</td>
                  <td>¥{formatYuan(o.credit_yuan)}</td>
                  <td>
                    <code className="memo-inline">{o.memo_code}</code>
                  </td>
                  <td>
                    <span className={statusPillClass(o.status)}>
                      {STATUS_ZH[o.status] ?? o.status}
                    </span>
                  </td>
                  <td>
                    {o.status !== "confirmed" ? (
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={busyId === o.id}
                        onClick={() => setEnsureOrder(o)}
                      >
                        核对入账
                      </button>
                    ) : (
                      <span className="status-pill status-pill-done">已核对</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>

      {ensureOrder ? (
        <EnsureModal
          order={ensureOrder}
          busy={busyId === ensureOrder.id}
          onClose={() => setEnsureOrder(null)}
          onConfirm={() => void confirmEnsured(ensureOrder.id)}
        />
      ) : null}
    </>
  );
}
