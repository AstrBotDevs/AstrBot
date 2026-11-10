import { useEffect, useState } from "react";

import { fetchOrders, type Order } from "../lib/commerce";

const STATUS_ZH: Record<string, string> = {
  pending: "等你扫码",
  user_marked: "用户声明已支付，鱼咖核对中",
  confirmed: "已入账，已发粮",
  rejected: "未通过",
};

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOrders()
      .then(setOrders)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        每次添饭的单子都在这里，备注码用来和鱼咖对账。
      </p>
      {error ? <div className="alert alert-error">{error}</div> : null}
      <article className="card">
        <h2 className="card-title">添饭记录</h2>
        {orders.length === 0 ? (
          <p className="empty-state">还没添过饭。去电饭煲站添一碗？</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>金额</th>
                <th>备注码</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>{new Date(order.created_at).toLocaleString()}</td>
                  <td>¥{Number(order.amount_yuan).toFixed(2)}</td>
                  <td>{order.memo_code}</td>
                  <td>{STATUS_ZH[order.status] ?? order.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>
    </>
  );
}
