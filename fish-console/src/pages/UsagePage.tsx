import { useEffect, useState } from "react";

import { ThinkingNote } from "../components/ThinkingNote";
import { fetchUsage, type UsageSummary } from "../lib/commerce";
import { formatRiceG } from "../lib/rice";

export function UsagePage() {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchUsage(7)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  return (
    <>
      {data ? (
        <ThinkingNote seconds={3}>
          {data.total_rice_g > 0
            ? `这 ${data.days} 天我一共吃了 ${formatRiceG(data.total_rice_g)}。\n都是干活吃掉的，不许心疼。`
            : "干饭记录……让我翻翻。\n嗯，这几天还没在你家吃过饭。"}
        </ThinkingNote>
      ) : null}
      {error ? <div className="alert alert-error">{error}</div> : null}
      {data && !data.bound ? (
        <article className="card">
          <p className="muted">还没登记接鱼，先去「接鱼回家」填 AppID 和实例 ID。</p>
        </article>
      ) : null}
      <article className="card">
        <h2 className="card-title">
          干饭记录{data ? `（近 ${data.days} 天）` : ""}
        </h2>
        {data && data.rows.length === 0 ? (
          <p className="muted">还没有干饭记录，或者饭量统计还没接上。</p>
        ) : null}
        {data && data.rows.length > 0 ? (
          <>
            <p className="feed-checkout-line">合计 {formatRiceG(data.total_rice_g)}</p>
            <table className="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>口味</th>
                  <th>吃掉</th>
                  <th>次数</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={`${row.date}-${row.model}`}>
                    <td>{row.date}</td>
                    <td>{row.model}</td>
                    <td>{formatRiceG(row.rice_g)}</td>
                    <td>{row.calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </article>
    </>
  );
}
