'use strict';
const {app, BrowserWindow, ipcMain} = require('electron');
const {autoUpdater} = require('electron-updater');
const path = require('node:path');

// Vortex's updater pathway: generic GitHub feed -> checkForUpdates ->
// downloadUpdate -> SHA512-checked staged NSIS -> quitAndInstall.
// Pong has a separate mutable prerelease channel; never use the main app's latest release.
const FEED = 'https://github.com/ldf97/AnkiCompanion/releases/download/pong-update-lab/';
let window;
let state = {stage:'idle', message:'Click Check for updates.', percent:0, version:app.getVersion()};
let busy = false;
let downloadedVersion = null;

function setState(stage, message, more={}) {
  state={...state,...more,stage,message};
  if (window && !window.isDestroyed()) window.webContents.send('updater:state',state);
}
autoUpdater.setFeedURL({provider:'generic',url:FEED,useMultipleRangeRequest:false});
autoUpdater.autoDownload=false;
autoUpdater.autoInstallOnAppQuit=false;
autoUpdater.allowDowngrade=false;
autoUpdater.disableWebInstaller=true;
autoUpdater.on('checking-for-update',()=>setState('checking','Checking Pong release channel…'));
autoUpdater.on('update-available',info=>setState('available','Version '+info.version+' is available.',{availableVersion:info.version}));
autoUpdater.on('update-not-available',()=>setState('current','You have the latest Pong version.',{availableVersion:null}));
autoUpdater.on('download-progress',p=>setState('downloading','Downloading updated Pong…',{percent:Math.floor(p.percent)}));
autoUpdater.on('update-downloaded',info=>{
  downloadedVersion=info.version;
  setState('staged','Update '+info.version+' downloaded and verified. Ready to install.',{percent:100});
});
autoUpdater.on('error',err=>setState('error','Update error: '+err.message));

async function check(){
  if (busy) return state;
  if (!app.isPackaged) return setState('error','Update checks require the installed EXE.');
  busy=true;
  try {await autoUpdater.checkForUpdates();}
  catch(e){setState('error','Could not check GitHub: '+e.message);}
  finally {busy=false;}
  return state;
}
async function download(){
  if (busy || state.stage !== 'available') return state;
  busy=true;
  setState('downloading','Downloading updated Pong…',{percent:0});
  try {await autoUpdater.downloadUpdate();}
  catch(e){setState('error','Could not download update: '+e.message);}
  finally {busy=false;}
  return state;
}
function install(){
  if (!app.isPackaged || state.stage!=='staged' || !downloadedVersion) return state;
  setState('installing','Replacing Pong and restarting…');
  try {autoUpdater.quitAndInstall(false,true);}
  catch(e){setState('error','Could not run installer: '+e.message);}
  return state;
}
ipcMain.handle('updater:check',check);
ipcMain.handle('updater:download',download);
ipcMain.handle('updater:install',install);
ipcMain.handle('updater:state',()=>state);

const single=app.requestSingleInstanceLock();
if(!single) app.quit();
else {
  app.on('second-instance',()=>{if(window){window.show();window.focus();}});
  app.whenReady().then(()=>{
    window=new BrowserWindow({
      width:750,height:670,minWidth:610,minHeight:540,title:'Pong Update Lab',
      backgroundColor:'#0e1324',
      webPreferences:{preload:path.join(__dirname,'preload.js'),nodeIntegration:false,contextIsolation:true,sandbox:true}
    });
    window.setMenuBarVisibility(false);
    window.loadFile(path.join(__dirname,'index.html'));
    window.webContents.on('did-finish-load',()=>window?.webContents.send('updater:state',state));
    window.on('closed',()=>{window=null;});
  });
  app.on('window-all-closed',()=>app.quit());
}
