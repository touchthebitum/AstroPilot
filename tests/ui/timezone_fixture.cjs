// Mock HTTP UI tests still use the production timezone encoder and browser adapter.
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '../..');
const local = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.PYTHON_BINARY || (fs.existsSync(local) ? local : 'python');
const data = JSON.parse(execFileSync(python, ['-c',
  'from decision.timezone_authority import bundle_json; print(bundle_json())'], {cwd: root, encoding:'utf8'}));
module.exports = {timeHeaders:{'X-NightMerit-Time-Authority':data.id},
  timeData:'globalThis.NightMeritTimeData='+JSON.stringify(data)+';'};
