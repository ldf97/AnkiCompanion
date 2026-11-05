'use strict';
const {contextBridge, ipcRenderer} = require('electron');

// Mirrors the narrowly scoped renderer -> main-process IPC used by Vortex.
contextBridge.exposeInMainWorld('companionUpdater', Object.freeze({
  state: () => ipcRenderer.invoke('updates:state'),
  check: () => ipcRenderer.invoke('updates:check'),
  download: () => ipcRenderer.invoke('updates:download'),
  install: () => ipcRenderer.invoke('updates:install'),
  openApp: () => ipcRenderer.invoke('updates:open-app'),
  subscribe: (callback) => {
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('updates:state-change', listener);
    return () => ipcRenderer.removeListener('updates:state-change', listener);
  }
}));
