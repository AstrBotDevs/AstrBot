import { useEffect, useState } from "react";

import { fetchProfile, type Profile } from "../lib/commerce";
import { formatRiceG } from "../lib/rice";

const WALLET_STATUS_ZH: Record<string, string> = {
  active: "正常",
  suspended_arrears: "饿晕了（欠饭）",
  suspended_manual: "暂停中",
};

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile()
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }

  if (!profile) {
    return <p className="muted">思考中…</p>;
  }

  return (
    <article className="card">
      <h2 className="card-title">鱼片小窝</h2>
      <p>
        邮箱：<strong>{profile.email}</strong>
      </p>
      <p>
        碗里还有：<strong>{formatRiceG(Number(profile.wallet.balance_rice_g))}</strong>
      </p>
      {Number(profile.wallet.arrears_rice_g) > 0 ? (
        <p className="muted">欠饭 {formatRiceG(Number(profile.wallet.arrears_rice_g))}</p>
      ) : null}
      <p className="muted">
        饭碗状态：{WALLET_STATUS_ZH[profile.wallet.status] ?? profile.wallet.status}
      </p>
      {profile.binding ? (
        <>
          <h3 className="feed-section-title">接回家的大肥鱼</h3>
          <p>AppID：{profile.binding.qq_appid}</p>
          <p>实例：{profile.binding.adapter_id}</p>
          <p className="muted">
            接线：{profile.binding.bind_status === "active" ? "已到家，在线" : "鱼咖接线中"}
          </p>
        </>
      ) : (
        <p className="muted">还没接大肥鱼回家。</p>
      )}
    </article>
  );
}
