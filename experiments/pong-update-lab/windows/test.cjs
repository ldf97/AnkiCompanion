'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {EventEmitter}=require('node:events'),vm=require('node:vm');
const code=fs.readFileSync(__dirname+'/main.js','utf8');
test('uses Vortex Electron updater, NSIS and separate Pong feed',()=>{
 const pkg=require('./package.json');
 assert.equal(pkg.build.win.target[0],'nsis');
 assert.equal(pkg.build.appId,'com.ankicompanion.ponglab');
 assert.match(code,/downloadUpdate\(\)/);
 assert.match(code,/quitAndInstall\(false,true\)/);
 assert.match(code,/releases\/download\/pong-update-lab\//);
 assert(!code.includes('AnkiCompanion.exe'));
});
test('the game contains a playable canvas and update button',()=>{
 const html=fs.readFileSync(__dirname+'/index.html','utf8');
 for(const x of ['<canvas','Check for update','Download update','Install and restart','requestAnimationFrame']){
   assert(html.includes(x),x);
 }
});
