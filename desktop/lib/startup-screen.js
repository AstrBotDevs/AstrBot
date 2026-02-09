'use strict';

const fs = require('fs');

async function loadStartupScreen(mainWindow, { getAssetPath, startupTexts }) {
  if (!mainWindow) {
    return false;
  }
  let iconUrl = '';
  try {
    const iconBuffer = fs.readFileSync(getAssetPath('icon-no-shadow.svg'));
    iconUrl = `data:image/svg+xml;base64,${iconBuffer.toString('base64')}`;
  } catch {}

  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AstrBot</title>
  <style>
    :root {
      color-scheme: light dark;
      --primary: #3c96ca;
      --bg: #f9fafc;
      --surface: #ffffff;
      --text: #1b1c1d;
      --muted: #556170;
      --border: #eeeeee;
    }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Poppins", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--text);
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    .card {
      text-align: center;
      padding: 28px 30px 24px;
      border-radius: 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      width: min(360px, calc(100vw - 48px));
    }
    .logo {
      width: 64px;
      height: 64px;
      display: block;
      margin: 0 auto 12px;
    }
    .spinner {
      width: 32px;
      height: 32px;
      margin: 0 auto 14px;
      border: 3px solid rgba(60, 150, 202, 0.22);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 19px;
      font-weight: 700;
      letter-spacing: 0.01em;
    }
    p {
      margin: 0;
      line-height: 1.55;
      color: var(--muted);
      font-size: 14px;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --primary: #1677ff;
        --bg: #1d1d1d;
        --surface: #1f1f1f;
        --text: #ffffff;
        --muted: #c8c8cc;
        --border: #333333;
      }
      .card {
        box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
      }
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  </style>
</head>
<body>
  <div class="card">
    ${
      iconUrl
        ? `<img class="logo" src="${iconUrl}" alt="AstrBot logo" />`
        : '<div class="logo" aria-hidden="true"></div>'
    }
    <div class="spinner" aria-hidden="true"></div>
    <h1>${startupTexts.title}</h1>
    <p>${startupTexts.message}</p>
  </div>
</body>
</html>`;
  const startupUrl = `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
  await mainWindow.loadURL(startupUrl);
  return true;
}

module.exports = {
  loadStartupScreen,
};
