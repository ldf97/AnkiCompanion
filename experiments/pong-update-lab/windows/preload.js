'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('updates',Object.freeze({
  state:()=>ipcRenderer.invoke('updater:state'),
  check:()=>ipcRenderer.invoke('updater:check'),
  download:()=>ipcRenderer.invoke('updater:download'),
  install:()=>ipcRenderer.invoke('updater:install'),
  subscribe:cb=>{
    const fn=(_event,state)=>cb(state);
    ipcRenderer.on('updater:state',fn);
    return()=>ipcRenderer.removeListener('updater:state',fn);
  }
}));
