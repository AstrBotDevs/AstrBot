// Deliberately limited MCP Apps host: bundled views and reviewed text messages.
export const APP_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

export function appDocument(html, nonce) {
  // A trusted outer frame relays standard MCP messages from an opaque inner app.
  // The app cannot read the per-view nonce or address the host as the relay window.
  const encoded = JSON.stringify({ html: `<meta http-equiv="Content-Security-Policy" content="${APP_CSP}">${html}`, nonce }).replace(/</g, '\\u003c');
  const relayCsp = APP_CSP.replace("frame-src 'none'", 'frame-src about:');
  return `<meta http-equiv="Content-Security-Policy" content="${relayCsp}">
<style>html,body,iframe{width:100%;height:100%;margin:0;border:0;display:block}</style>
<iframe id="app" title="MCP App content" sandbox="allow-scripts" referrerpolicy="no-referrer"></iframe>
<script>(()=>{const config=${encoded};const app=document.getElementById('app');
addEventListener('message',event=>{
 if(event.source===app.contentWindow && event.origin==='null'){
  parent.postMessage({nonce:config.nonce,message:event.data},'*');
 }else if(event.source===parent && event.data?.nonce===config.nonce){
  app.contentWindow.postMessage(event.data.message,'*');
 }
});app.srcdoc=config.html;})();</script>`;
}

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const keysOnly = (value, keys) => object(value) && Object.keys(value).every(key => keys.includes(key));

export function createAppHost({ source, nonce, send, arguments: args, result, propose, resize, theme = 'light' }) {
  let initialized = false;
  let ready = false;
  let pendingId;
  const reply = (id, value) => send({ jsonrpc: '2.0', id, result: value });
  const reject = (id, code, message) => send({ jsonrpc: '2.0', id, error: { code, message } });
  const notify = (method, params) => send({ jsonrpc: '2.0', method, params });

  function receive(event) {
    // Opaque sandbox origins all serialize as "null"; source identity is essential.
    if (event.source !== source() || event.origin !== 'null') return;
    const envelope = event.data;
    if (!keysOnly(envelope, ['nonce', 'message']) || envelope.nonce !== nonce || typeof nonce !== 'string' || !nonce) return;
    const data = envelope.message;
    if (!keysOnly(data, ['jsonrpc', 'id', 'method', 'params']) || data.jsonrpc !== '2.0' || typeof data.method !== 'string') return;
    try { if (JSON.stringify(data).length > 32768) return; } catch { return; }
    const hasId = typeof data.id === 'string' || (typeof data.id === 'number' && Number.isFinite(data.id));
    if (Object.hasOwn(data, 'id') && !hasId) return;
    const params = data.params === undefined ? {} : data.params;
    if (!object(params)) { if (hasId) reject(data.id, -32602, 'Invalid parameters'); return; }
    if (data.method === 'ui/initialize' && hasId) {
      if (initialized || !keysOnly(params, ['protocolVersion', 'appInfo', 'appCapabilities']) || params.protocolVersion !== '2026-01-26' || !keysOnly(params.appInfo, ['name', 'version']) || typeof params.appInfo.name !== 'string' || typeof params.appInfo.version !== 'string' || (params.appCapabilities !== undefined && !object(params.appCapabilities))) {
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
      if (!keysOnly(params, [])) return;
      ready = true;
      notify('ui/notifications/tool-input', { arguments: args });
      notify('ui/notifications/tool-result', result);
    } else if (!ready) {
      if (hasId) reject(data.id, -32000, 'Initialize the app first');
    } else if (data.method === 'ui/notifications/size-changed' && !hasId) {
      if (keysOnly(params, ['height', 'width']) && Number.isFinite(params.height) && (params.width === undefined || Number.isFinite(params.width))) resize(Math.min(800, Math.max(160, params.height)));
    } else if (data.method === 'ui/message' && hasId) {
      const blocks = params.content;
      if (!keysOnly(params, ['role', 'content']) || params.role !== 'user' || !Array.isArray(blocks) || !blocks.length || blocks.some(b => !keysOnly(b, ['type', 'text']) || b.type !== 'text' || typeof b.text !== 'string')) {
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
