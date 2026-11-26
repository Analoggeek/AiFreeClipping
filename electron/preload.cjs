const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  token: () => ipcRenderer.sendSync('app:token'),
  apiBase: () => ipcRenderer.sendSync('app:api-base'),
  platform: () => process.platform,
  arch: () => process.arch,
  selectFiles: (filters) => ipcRenderer.invoke('dialog:files', filters),
  selectDirectory: () => ipcRenderer.invoke('dialog:directory'),
  openPath: (target) => ipcRenderer.invoke('shell:open', target),
  openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
  revealPath: (target) => ipcRenderer.invoke('shell:reveal', target),
  appInfo: () => ipcRenderer.invoke('app:info'),
  onProgress: (callback) => {
    ipcRenderer.on('backend:status', (_event, value) => callback(value));
    return () => ipcRenderer.removeAllListeners('backend:status');
  },
});
