'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('astrbotDesktop', {
  isElectron: true,
  isElectronRuntime: () => ipcRenderer.invoke('astrbot-desktop:is-electron-runtime'),
  getBackendState: () => ipcRenderer.invoke('astrbot-desktop:get-backend-state'),
  restartBackend: () => ipcRenderer.invoke('astrbot-desktop:restart-backend'),
  stopBackend: () => ipcRenderer.invoke('astrbot-desktop:stop-backend'),
});
