'use strict';
const {app, BrowserWindow, ipcMain} = require('electron');
const {autoUpdater} = require('electron-updater');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// Vortex pattern: Electron's updater owns release download, staged state and
// NSIS installation. This launcher keeps Python for Anki itself, NOT updates.
let updateWindow = null;
let studyProcess = null;
let state = {stage:'idle', message:'Ready to check GitHub', version:app.getVersion(), percent:0};
let busy = false;
let downloadRequestedDuringCheck = false;

// Persist short, sanitized update stages for users reporting silent failures.
function logUpdate(stage, message) {
  try {
    const file = path.join(app.getPath('userData'), 'update-diagnostics.log');
    fs.mkdirSync(path.dirname(file), {recursive:true});
    if (fs.existsSync(file) && fs.statSync(file).size > 128 * 1024) {
      fs.renameSync(file, file + '.previous');
    }
    fs.appendFileSync(file, new Date().toISOString() + ' | ' + stage + ' | ' +
      String(message).replace(/[\\r\\n]+/g, ' ').slice(0, 500) + '\\n');
  } catch (_) { /* Logging must never break the updater. */ }
}
// A one-time handoff acknowledgement prevents the study GUI from quitting
// before the Electron updater window exists on slower Windows systems.
function acknowledgeUpdateWindow(argv) {
  const match = argv.find(x => /^--updates-request=[0-9a-f]{32}$/.test(x));
  if (!match) return;
  const nonce = match.slice('--updates-request='.length);
  const marker = path.join(app.getPath('temp'), 'ankicompanion-updates-' + nonce + '.ready');
  try {
    fs.writeFileSync(marker, 'ready', {flag:'wx'});
  } catch (error) {
    logUpdate('handoff-error', error.message);
  }
}

function publish(stage, message, extra = {}) {
  state = { ...state, ...extra, stage, message };
  logUpdate(stage, message);
  if (updateWindow && !updateWindow.isDestroyed()) {
    updateWindow.webContents.send('updates:state-change', state);
  }
}
function studyExecutable() {
  return path.join(process.resourcesPath, 'desktop', 'AnkiCompanion.exe');
}
function startStudy() {
  if (studyProcess && studyProcess.exitCode === null) return;
  const executable = studyExecutable();
  if (!fs.existsSync(executable)) {
    publish('error', 'Windows study application missing: ' + executable);
    showUpdates();
    return;
  }
  studyProcess = spawn(executable, [], {cwd:path.dirname(executable), stdio:'ignore', windowsHide:false});
  studyProcess.once('error', (err) => {
    studyProcess = null;
    publish('error', 'Could not start the study app: ' + err.message);
    showUpdates();
  });
  studyProcess.once('exit', () => {
    studyProcess = null;
    if (!updateWindow || updateWindow.isDestroyed()) app.quit();
  });
}
function showUpdates(argv = []) {
  if (updateWindow && !updateWindow.isDestroyed()) {
    updateWindow.show();
    updateWindow.focus();
    acknowledgeUpdateWindow(argv);
    return;
  }
  updateWindow = new BrowserWindow({
    width:540, height:440, resizable:false, title:'AnkiCompanion Updates',
    webPreferences:{
      preload:path.join(__dirname,'preload.js'),
      nodeIntegration:false, contextIsolation:true, sandbox:false
    }
  });
  updateWindow.setMenuBarVisibility(false);
  updateWindow.loadFile(path.join(__dirname,'updates.html'));
  updateWindow.webContents.once('did-finish-load', () => {
    updateWindow?.webContents.send('updates:state-change',state);
    acknowledgeUpdateWindow(argv);
    checkForUpdate().catch((error) => publish('error', 'Check failed: ' + error.message));
  });
  updateWindow.webContents.on('did-fail-load', (_event, code, description) => {
    publish('error', 'Updater window failed to load: ' + code + ' ' + description);
  });
  updateWindow.on('closed', () => {
    updateWindow = null;
    if (!studyProcess) app.quit();
  });
}
// Same generic GitHub metadata channel and electron-updater calls as the
// successfully updated Pong experiment and the Vortex updater.
autoUpdater.setFeedURL({
  provider:'generic',
  url:'https://github.com/ldf97/AnkiCompanion/releases/latest/download/',
  useMultipleRangeRequest:false
});
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = false;
autoUpdater.disableWebInstaller = true;
autoUpdater.allowDowngrade = false;
autoUpdater.on('checking-for-update', () => publish('checking','Checking GitHub Releases…'));
autoUpdater.on('update-available', (info) =>
  publish('available','Version '+info.version+' is available.', {targetVersion:info.version,percent:0}));
autoUpdater.on('update-not-available', () =>
  publish('current','AnkiCompanion '+app.getVersion()+' is up to date.',{percent:0}));
autoUpdater.on('download-progress', (progress) =>
  publish('downloading','Downloading update…', {percent:Math.floor(progress.percent)}));
autoUpdater.on('update-downloaded', (info) =>
  publish('downloaded','Version '+info.version+' is verified and ready to install.',{percent:100}));
autoUpdater.on('error', (error) => publish('error','Update error: '+error.message));

async function checkForUpdate() {
  if (busy) return state;
  if (!app.isPackaged) {
    publish('error','Updates are only available in the installed Windows application.');
    return state;
  }
  busy = true;
  try {
    await autoUpdater.checkForUpdates();
  } catch (error) {
    publish('error','GitHub check failed: '+error.message);
  } finally {
    busy = false;
    // update-available can fire before checkForUpdates() settles. Honor the
    // pending download instead of silently discarding the button/test action.
    const shouldDownload = downloadRequestedDuringCheck && state.stage === 'available';
    downloadRequestedDuringCheck = false;
    if (shouldDownload) setImmediate(() => downloadUpdate().catch(
      error => publish('error', 'Queued update download failed: ' + error.message)));
  }
  return state;
}
async function downloadUpdate() {
  if (busy) {
    if (state.stage === 'available') downloadRequestedDuringCheck = true;
    return state;
  }
  if (state.stage !== 'available') return state;
  busy = true;
  publish('downloading','Downloading update…',{percent:0});
  try {
    // Vortex uses the same electron-updater call (not a Python HTTP downloader).
    await autoUpdater.downloadUpdate();
  } catch (error) {
    publish('error','Update download failed: '+error.message);
  } finally {busy = false;}
  return state;
}
function installUpdate() {
  if (state.stage !== 'downloaded' || !app.isPackaged) return state;
  publish('installing','Applying verified update and restarting…');
  // Keep the same proven execution path as Pong: electron-updater owns
  // process shutdown, NSIS replacement and application restart.
  // User study data is outside the replaceable installation directory.
  try {
    autoUpdater.quitAndInstall(false,true);
  } catch (error) {
    publish('error','Update installation failed: '+error.message);
  }
  return state;
}
ipcMain.handle('updates:state', () => state);
ipcMain.handle('updates:check', checkForUpdate);
ipcMain.handle('updates:download', downloadUpdate);
ipcMain.handle('updates:install', installUpdate);
ipcMain.handle('updates:open-app', () => {
  startStudy();
  if (updateWindow && !updateWindow.isDestroyed()) updateWindow.close();
  return true;
});

const single = app.requestSingleInstanceLock();
if (!single) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => {
    if (argv.includes('--updates')) showUpdates(argv);
    else startStudy();
  });
  app.whenReady().then(() => {
    if (process.argv.includes('--updates')) showUpdates(process.argv);
    else startStudy();
  });
  app.on('window-all-closed', () => { if (!studyProcess) app.quit(); });
}
