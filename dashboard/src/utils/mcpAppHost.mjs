// Deliberately limited MCP Apps host: bundled views and reviewed text messages.
export const APP_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

export function appDocument(html) {
  return `<meta http-equiv="Content-Security-Policy" content="${APP_CSP}">${html}`;
}

export function createAppHost({ source, send, arguments: args, result, propose, resize, theme = 'light' }) {
  let initialized = false;
  let ready = false;
  let pendingId;
  const reply = (id, value) => send({ jsonrpc: '2.0', id, result: value });
  const reject = (id, code, message) => send({ jsonrpc: '2.0', id, error: { code, message } });
  const notify = (method, params) => send({ jsonrpc: '2.0', method, params });

  function receive(event) {
    // Opaque sandbox origins all serialize as "null"; source identity is essential.
    if (event.source !== source() || event.origin !== 'null') return;
    const data = event.data;
    if (!data || data.jsonrpc !== '2.0' || typeof data.method !== 'string') return;
    const hasId = typeof data.id === 'string' || (typeof data.id === 'number' && Number.isFinite(data.id));
    const params = data.params || {};
    if (data.method === 'ui/initialize' && hasId) {
      if (initialized || params.protocolVersion !== '2026-01-26' || typeof params.appInfo?.name !== 'string') {
        reject(data.id, -32602, 'Unsupported initialization');
        return;
      }
      initialized = true;
      reply(data.id, {
        protocolVersion: '2026-01-26',
        hostInfo: { name: 'AstrBot', version: '1.0.0' },
        hostCapabilities: { sandbox: { permissions: {}, csp: {} } },
        hostContext: { theme, displayMode: 'inline', availableDisplayModes: ['inline'] },
      });
    } else if (data.method === 'ui/notifications/initialized' && initialized && !ready && !hasId) {
      ready = true;
      notify('ui/notifications/tool-input', { arguments: args });
      notify('ui/notifications/tool-result', result);
    } else if (!ready) {
      if (hasId) reject(data.id, -32000, 'Initialize the app first');
    } else if (data.method === 'ui/notifications/size-changed' && !hasId) {
      if (Number.isFinite(params.height)) resize(Math.min(800, Math.max(160, params.height)));
    } else if (data.method === 'ui/message' && hasId) {
      const blocks = params.content;
      if (params.role !== 'user' || !Array.isArray(blocks) || !blocks.length || blocks.some(b => b?.type !== 'text' || typeof b.text !== 'string')) {
        reject(data.id, -32602, 'Only user text messages are supported');
        return;
      }
      const text = blocks.map(b => b.text).join('\n').trim();
      if (!text || text.length > 10000 || pendingId !== undefined) {
        reject(data.id, -32000, 'Message is empty, too large, or awaiting review');
        return;
      }
      pendingId = data.id;
      propose(text);
    } else if (hasId) {
      reject(data.id, -32601, 'This host does not support that operation');
    }
  }

  function settle(accepted) {
    if (pendingId === undefined) return;
    if (accepted) reply(pendingId, {});
    else reject(pendingId, -32000, 'Message declined');
    pendingId = undefined;
  }
  return { receive, settle };
}
