import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import QRCode from "qrcode";

import { ThinkingNote } from "../components/ThinkingNote";
import {
  fetchBindMeta,
  fetchBinding,
  fetchWalletMe,
  manualBind,
  pollBindQr,
  startBindQr,
  type BindChannel,
  type Binding,
  type BindMeta,
} from "../lib/commerce";

type WizardPhase = "loading" | "empty" | "ready" | "polling" | "done" | "error";

const CHANNEL_LABEL: Record<BindChannel, string> = {
  qq: "QQ 官方机器人",
  weixin: "微信官方机器人",
};

export function BotBindPage() {
  const [canBind, setCanBind] = useState(false);
  const [binding, setBinding] = useState<Binding | null>(null);
  const [meta, setMeta] = useState<BindMeta | null>(null);
  const [phase, setPhase] = useState<WizardPhase>("loading");
  const [channel, setChannel] = useState<BindChannel>("qq");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [qqAppid, setQqAppid] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const pollTimer = useRef<number | null>(null);
  const expireTimer = useRef<number | null>(null);
  const stopped = useRef(false);

  function clearTimers() {
    if (pollTimer.current != null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
    if (expireTimer.current != null) {
      window.clearInterval(expireTimer.current);
      expireTimer.current = null;
    }
  }

  async function loadPage() {
    setError(null);
    try {
      const [wallet, bind, bindMeta] = await Promise.all([
        fetchWalletMe(),
        fetchBinding(),
        fetchBindMeta(),
      ]);
      setCanBind(wallet.can_bind);
      setBinding(bind);
      setMeta(bindMeta);
      if (bind?.bind_status === "active") {
        setPhase("done");
        return;
      }
      if (!wallet.can_bind) {
        setPhase("empty");
        return;
      }
      setPhase("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
      setPhase("error");
    }
  }

  useEffect(() => {
    void loadPage();
    return () => {
      stopped.current = true;
      clearTimers();
    };
  }, []);

  async function beginQr(nextChannel: BindChannel = channel) {
    clearTimers();
    setError(null);
    setChannel(nextChannel);
    setSubmitting(true);
    try {
      const started = await startBindQr(nextChannel);
      const dataUrl = await QRCode.toDataURL(started.qrcode, {
        width: 240,
        margin: 2,
        color: { dark: "#1f2b5c", light: "#ffffff" },
      });
      setQrDataUrl(dataUrl);
      setExpiresIn(started.expires_in);
      setPhase("polling");
      // Countdown is advisory only. Keep polling until AstrBot/QQ says
      // created|expired|error — users often spend minutes on the create form.
      expireTimer.current = window.setInterval(() => {
        setExpiresIn((prev) => (prev <= 0 ? 0 : prev - 1));
      }, 1000);
      schedulePoll(started.session_id, started.interval);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成二维码失败");
      setPhase("ready");
    } finally {
      setSubmitting(false);
    }
  }

  function schedulePoll(sid: string, seconds: number) {
    pollTimer.current = window.setTimeout(() => {
      void runPoll(sid, seconds);
    }, Math.max(seconds, 1) * 1000);
  }

  async function runPoll(sid: string, seconds: number) {
    if (stopped.current) return;
    try {
      const result = await pollBindQr(sid);
      if (result.status === "active" && result.binding) {
        clearTimers();
        setBinding(result.binding);
        setPhase("done");
        setQrDataUrl(null);
        return;
      }
      if (result.status === "expired") {
        clearTimers();
        setPhase("ready");
        setError(result.message || "二维码过期了，刷新后再扫。");
        setQrDataUrl(null);
        return;
      }
      if (result.status === "error") {
        clearTimers();
        setPhase("ready");
        setError(result.message || "扫码失败，请重试。");
        setQrDataUrl(null);
        return;
      }
      schedulePoll(sid, seconds);
    } catch (err) {
      clearTimers();
      setPhase("ready");
      setError(err instanceof Error ? err.message : "轮询失败");
      setQrDataUrl(null);
    }
  }

  async function onManualSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const saved = await manualBind({
        qq_appid: qqAppid.trim(),
        app_secret: appSecret.trim(),
      });
      setBinding(saved);
      setAppSecret("");
      setPhase("done");
      clearTimers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return <p className="muted">思考中…</p>;
  }

  if (phase === "empty" || (!canBind && !binding)) {
    return (
      <>
        <ThinkingNote seconds={2}>
          {"要接我回家？\n碗还是空的……没饭我是不会出门的。先添点饭，再来接我。"}
        </ThinkingNote>
        <article className="card bowl-card">
          <img className="dafeiyu dafeiyu-bowl" src="/dafeiyu/sulk.webp" alt="大肥鱼顶着空碗生闷气" />
          <div className="bowl-card-info">
            <h2 className="card-title">碗是空的</h2>
            <p className="muted">鱼咖确认收款、饭进碗之后，才能选 QQ 或微信接我回家。</p>
            <Link to="/plans" className="btn-primary">
              去添饭
            </Link>
          </div>
        </article>
      </>
    );
  }

  if (phase === "done" && binding) {
    const isWeixin = binding.channel === "weixin";
    return (
      <>
        <ThinkingNote seconds={2}>
          {isWeixin
            ? "到你家微信了。\n打开微信就能找我。别催，饭我还要吃。"
            : "到你家 QQ 了。\n手机 QQ → 联系人 → 机器人，就能找到我。头像想换去开放平台改。"}
        </ThinkingNote>
        <article className="card">
          <h2 className="card-title">已到家</h2>
          <p>
            <span className="badge badge-ok">在线</span>{" "}
            <span className="muted">
              {CHANNEL_LABEL[(binding.channel as BindChannel) || "qq"] || binding.channel}
            </span>
          </p>
          {binding.qq_appid ? (
            <p>
              {isWeixin ? "微信账号 ID" : "QQ AppID"}：<strong>{binding.qq_appid}</strong>
            </p>
          ) : null}
          {isWeixin ? (
            <ol className="bind-steps">
              <li>打开微信，在会话列表里找到大肥鱼，私聊试一句。</li>
              <li>头像若创建时没换成大肥鱼，之后往往改不了图，只能尽量改显示名。</li>
            </ol>
          ) : (
            <ol className="bind-steps">
              <li>
                手机 QQ 打开 <strong>联系人 → 机器人</strong>，找到大肥鱼，私聊试一句。
              </li>
              <li>
                头像或名称改不了时，前往{" "}
                <a href="https://q.qq.com" target="_blank" rel="noreferrer">
                  q.qq.com
                </a>{" "}
                处理。
              </li>
            </ol>
          )}
          {!isWeixin ? (
            <p className="muted">
              个人主体可能只能和创建者私聊，或只能进你是群主/管理员的群——这是 QQ 的限制。
            </p>
          ) : null}
        </article>
      </>
    );
  }

  function switchChannel(next: BindChannel) {
    if (next === channel && phase !== "polling") return;
    clearTimers();
    setQrDataUrl(null);
    setPhase("ready");
    setChannel(next);
    setError(null);
  }

  return (
    <>
      <ThinkingNote seconds={2}>
        {channel === "qq"
          ? "碗里有饭了，可以出门。\nQQ 这边按图文去 q.qq.com 建好，再把 AppID、AppSecret 填给我。"
          : "碗里有饭了，可以出门。\n微信这边扫一下码，我就过去蹭饭。"}
      </ThinkingNote>

      <section className="alert feed-banner">
        {channel === "qq" ? (
          <>
            QQ：按下方图文在{" "}
            <a href="https://q.qq.com" target="_blank" rel="noreferrer">
              q.qq.com
            </a>{" "}
            创建机器人，再把 AppID + AppSecret 填回本页接到大肥鱼。鱼咖只负责确认收款发饭。
          </>
        ) : (
          <>
            微信：现场生成专属二维码，每人每次一张、会过期。鱼咖只负责确认收款发饭。
          </>
        )}
      </section>

      {error ? <div className="alert alert-error">{error}</div> : null}

      {!meta?.astrbot_ready ? (
        <div className="alert alert-error">
          鱼咖接线服务还没配好（缺 AstrBot API Key）。配好之前接不了鱼，请找鱼咖。
        </div>
      ) : null}

      <article className="card">
        <h2 className="card-title">在哪里养鱼？</h2>
        <div className="bind-channel-row">
          <button
            type="button"
            className={channel === "qq" ? "btn-primary" : "btn-secondary"}
            disabled={submitting || !meta?.astrbot_ready}
            onClick={() => switchChannel("qq")}
          >
            QQ 官方机器人
          </button>
          <button
            type="button"
            className={channel === "weixin" ? "btn-primary" : "btn-secondary"}
            disabled={submitting || !meta?.astrbot_ready}
            onClick={() => switchChannel("weixin")}
          >
            微信官方机器人
          </button>
        </div>
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          当前：<strong>{CHANNEL_LABEL[channel]}</strong>
          {channel === "qq" ? "（图文教学 + 手填凭证）" : "（手机微信扫码）"}
        </p>
      </article>

      {channel === "qq" ? (
        <>
          <article className="card">
            <h2 className="card-title">QQ 图文教学</h2>
            <p className="muted">
              不走鱼咖扫码。按腾讯「创建机器人 → 获取 AppID → 绑 AI 服务」走完，再回到本页填凭证。
            </p>
            <div className="bind-guide-preview">
              <img src="/dafeiyu/hello.webp" alt="大肥鱼头像参考" />
              <p className="muted">
                推荐头像（创建时上传，可{" "}
                <a href="/dafeiyu/hello.webp" download="dafeiyu-avatar.webp">
                  下载这张图
                </a>
                ）
              </p>
            </div>
            <div className="bind-guide-figures">
              <figure className="bind-guide-figure">
                <img src="/guides/qq-bind/01-open-platform.png" alt="QQ 开放平台入口" />
                <figcaption>
                  1. 打开{" "}
                  <a href="https://q.qq.com" target="_blank" rel="noreferrer">
                    q.qq.com
                  </a>
                  ，点「去创建或管理我的 QQ 机器人」。
                </figcaption>
              </figure>
              <figure className="bind-guide-figure">
                <img src="/guides/qq-bind/02-my-bots.png" alt="我的机器人列表" />
                <figcaption>2. 在「我的机器人」点「+ 创建机器人」（已有号可直接点进卡片）。</figcaption>
              </figure>
              <figure className="bind-guide-figure">
                <img src="/guides/qq-bind/03-create-bot.png" alt="创建机器人账号" />
                <figcaption>
                  3. 把头像换成大肥鱼，昵称填好后点「创建机器人」。选好后若无法更改图片或名称，仍在
                  q.qq.com 处理。
                </figcaption>
              </figure>
              <figure className="bind-guide-figure">
                <img src="/guides/qq-bind/04-manual-params.png" alt="查看手动连接参数" />
                <figcaption>
                  4. 创建成功后选「其他机器人服务」→「查看手动连接参数」，复制 AppID +
                  AppSecret（Secret 二次查看会重置，立刻复制）。
                </figcaption>
              </figure>
            </div>
          </article>

          <article className="card">
            <h2 className="card-title">填入凭证，接到大肥鱼</h2>
            <p className="muted">
              把刚复制的 AppID + AppSecret 填进来并提交。提交成功本页会变成「已到家」；不填会「有壳无灵魂」。
            </p>
            <form onSubmit={onManualSubmit}>
              <div className="field">
                <label htmlFor="qq-appid">QQ 机器人 AppID</label>
                <input
                  id="qq-appid"
                  required
                  value={qqAppid}
                  onChange={(e) => setQqAppid(e.target.value)}
                  placeholder="开放平台里的 AppID"
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label htmlFor="qq-secret">AppSecret</label>
                <input
                  id="qq-secret"
                  required
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  placeholder="开放平台里的 AppSecret"
                  autoComplete="new-password"
                />
              </div>
              <button type="submit" className="btn-primary" disabled={submitting || !meta?.astrbot_ready}>
                {submitting ? "提交中…" : "用手填凭证接鱼回家"}
              </button>
            </form>
            {meta?.qq_egress_ip ? (
              <p className="muted" style={{ marginTop: "1rem" }}>
                若开放平台要填 IP 白名单，用：<strong>{meta.qq_egress_ip}</strong>
              </p>
            ) : null}
          </article>
        </>
      ) : (
        <>
          <article className="card">
            <h2 className="card-title">扫码接鱼</h2>
            {phase === "polling" && qrDataUrl ? (
              <div className="bind-qr-wrap">
                <img className="bind-qr" src={qrDataUrl} alt="接鱼二维码" />
                <p className="muted">
                  用手机微信扫码并确认。
                  {expiresIn > 0
                    ? `建议 ${expiresIn}s 内完成手机上的创建/授权。`
                    : "仍在等待微信侧结果；若手机已完成，请稍等本页变成「已到家」。"}
                </p>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting}
                  onClick={() => void beginQr("weixin")}
                >
                  刷新二维码
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={submitting}
                  onClick={() => {
                    clearTimers();
                    setPhase("ready");
                    setQrDataUrl(null);
                  }}
                >
                  取消扫码
                </button>
              </div>
            ) : (
              <div className="bind-qr-wrap">
                <p className="muted">点一下，现场生成你的专属微信接鱼码。</p>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={submitting || !meta?.astrbot_ready}
                  onClick={() => void beginQr("weixin")}
                >
                  {submitting ? "生成中…" : "生成微信官方机器人二维码"}
                </button>
              </div>
            )}
          </article>

          <article className="card">
            <h2 className="card-title">扫码后怎么做</h2>
            <p className="muted">扫完码会进微信侧页面（不是鱼咖页）。</p>
            <div className="bind-guide-preview">
              <img src="/dafeiyu/hello.webp" alt="大肥鱼头像参考" />
              <p className="muted">推荐头像（创建时上传）</p>
            </div>
            <ol className="bind-steps">
              <li>手机微信扫码并确认授权。</li>
              <li>
                若弹出创建/资料页：头像换成大肥鱼（可先下载{" "}
                <a href="/dafeiyu/hello.webp" download="dafeiyu-avatar.webp">
                  这张图
                </a>
                ），名称填「大肥鱼」或你喜欢的称呼。
              </li>
              <li>
                完成后<strong>不要关本页</strong>，等「已到家」再聊。
              </li>
            </ol>
          </article>
        </>
      )}
    </>
  );
}
