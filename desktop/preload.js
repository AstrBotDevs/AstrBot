'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('astrbotDesktop', {
  isElectron: true,
  isElectronRuntime: () => ipcRenderer.invoke('astrbot-desktop:is-electron-runtime'),
  getBackendState: () => ipcRenderer.invoke('astrbot-desktop:get-backend-state'),
  restartBackend: (authToken) =>
    ipcRenderer.invoke('astrbot-desktop:restart-backend', authToken),
  stopBackend: () => ipcRenderer.invoke('astrbot-desktop:stop-backend'),
  onTrayRestartBackend: (callback) => {
    const listener = () => {
      if (typeof callback === 'function') {
        callback();
      }
    };
    ipcRenderer.on('astrbot-desktop:tray-restart-backend', listener);
    return () =>
      ipcRenderer.removeListener('astrbot-desktop:tray-restart-backend', listener);
  },
});
