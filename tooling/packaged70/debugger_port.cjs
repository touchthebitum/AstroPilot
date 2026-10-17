'use strict';
const fs = require('node:fs');
// Chrome may create this file before releasing its Windows write handle.
// The caller retries within its existing startup deadline; unexpected I/O fails.
function readDebuggerPort(file, read = fs.readFileSync) {
  let lines;
  try { lines = read(file, 'utf8').split(/\r?\n/); }
  catch (error) {
    if (['ENOENT', 'EBUSY', 'EACCES', 'EPERM'].includes(error.code)) return false;
    throw error;
  }
  const port = lines[0];
  return /^\d+$/.test(port) && Number(port) > 0 && Number(port) <= 65535 &&
    /^\/devtools\/browser\/.+/.test(lines[1] || '') ? port : false;
}
module.exports = {readDebuggerPort};
