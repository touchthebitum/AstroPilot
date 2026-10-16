'use strict';
const assert=require('node:assert/strict'),path=require('node:path');
function browserEnvironment(parent,{platform=process.platform}={}){
 const child={...parent};
 // On a disposable macOS Actions runner, Chrome's network service needs the
 // account HOME. Only the browser child gets it; app and browser profiles stay
 // isolated, and --user-data-dir still selects a fresh per-case browser profile.
 if(platform==='darwin' && parent.GITHUB_ACTIONS==='true'){
  assert(parent.BROWSER_NATIVE_HOME && path.posix.isAbsolute(parent.BROWSER_NATIVE_HOME),'Capture native runner HOME before application isolation');
  child.HOME=parent.BROWSER_NATIVE_HOME;
 }
 return child;
}
module.exports={browserEnvironment};
