'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readDebuggerPort} = require('./debugger_port.cjs');
test('Windows sharing lock and incomplete file can settle before browser startup deadline', () => {
  const results = [Object.assign(new Error('locked'), {code:'EBUSY'}), '4321', '4321\r\n/devtools/browser/test\r\n'];
  const read = () => {const result=results.shift();if(result instanceof Error)throw result;return result;};
  assert.equal(readDebuggerPort('owned-chrome-profile/DevToolsActivePort', read), false);
  assert.equal(readDebuggerPort('owned-chrome-profile/DevToolsActivePort', read), false);
  assert.equal(readDebuggerPort('owned-chrome-profile/DevToolsActivePort', read), '4321');
});
test('only transient startup errors are retried', () => {
  for (const code of ['ENOENT','EBUSY','EACCES','EPERM'])
    assert.equal(readDebuggerPort('file', () => {throw Object.assign(new Error(code),{code});}), false);
  assert.throws(() => readDebuggerPort('file', () => {throw Object.assign(new Error('disk'),{code:'EIO'});}), /disk/);
});
test('partial or invalid debugger endpoint is never used', () => {
  for (const value of ['', '0\n/devtools/browser/a', '65536\n/devtools/browser/a', '12a\n/devtools/browser/a', '1234\n/devtools/browser/'])
    assert.equal(readDebuggerPort('file', () => value), false);
});
