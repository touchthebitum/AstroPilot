"use strict";
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {readDebuggerPort} = require('./devtools_port.cjs');
const ready = '49123\n/devtools/browser/test-browser';

test('startup race: absent, sharing lock, partial write, then ready', () => {
  const steps = [Object.assign(new Error('absent'), {code:'ENOENT'}),
    Object.assign(new Error('Windows sharing lock'), {code:'EBUSY'}),
    '49', '49123\n', ready];
  let calls = 0;
  const read = () => { const step = steps[calls++]; if (step instanceof Error) throw step; return step; };
  assert.equal(readDebuggerPort('unused', read), null);
  assert.equal(readDebuggerPort('unused', read), null);
  assert.equal(readDebuggerPort('unused', read), null);
  assert.equal(readDebuggerPort('unused', read), null);
  assert.equal(readDebuggerPort('unused', read), '49123');
  assert.equal(calls, 5);
});

test('a persistent Windows lock remains unready for the existing bounded waiter', () => {
  for (const code of ['EBUSY','EPERM','EACCES']) {
    assert.equal(readDebuggerPort('unused', () => {throw Object.assign(new Error(code), {code});}), null);
  }
});

test('unrelated filesystem failures are not swallowed', () => {
  const error = Object.assign(new Error('disk error'), {code:'EIO'});
  assert.throws(() => readDebuggerPort('unused', () => {throw error;}), value => value === error);
});

test('incomplete or invalid debugger endpoints cannot be used', () => {
  for (const value of ['', '123', '0\n/devtools/browser/id', '65536\n/devtools/browser/id',
    '12x\n/devtools/browser/id', '49123\n', '49123\n/arbitrary/path']) {
    assert.equal(readDebuggerPort('unused', () => value), null, value);
  }
});

test('reads a complete Windows CRLF file with the production filesystem reader', t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'nightmerit-debugger-'));
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}));
  const file = path.join(directory, 'DevToolsActivePort');
  assert.equal(readDebuggerPort(file), null);
  fs.writeFileSync(file, ready.replace('\n','\r\n'));
  assert.equal(readDebuggerPort(file), '49123');
});
