"use strict";
// Chrome may create this file before releasing its Windows sharing lock.
const fs = require('node:fs');
const retryable = new Set(['ENOENT', 'EBUSY', 'EACCES', 'EPERM']);

function readDebuggerPort(file, readFile = fs.readFileSync) {
  let content;
  try {
    content = readFile(file, 'utf8');
  } catch (error) {
    if (retryable.has(error.code)) return null;
    throw error;
  }
  const [port, browserPath] = content.split(/\r?\n/);
  if (!/^[1-9]\d{0,4}$/.test(port) || Number(port) > 65535
      || !/^\/devtools\/browser\/[^\s/]+$/.test(browserPath || '')) return null;
  return port;
}

module.exports = {readDebuggerPort};
