import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fingerprint, inspectBuild, prepareBuild } from '../scripts/personal-build.mjs';

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'quantgraph-build-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const web = path.join(root, 'web');
  fs.mkdirSync(path.join(web, 'src'), { recursive: true });
  const write = (name, value) => { fs.mkdirSync(path.dirname(path.join(web, name)), { recursive: true }); fs.writeFileSync(path.join(web, name), value); };
  write('package.json', '{"version":"test"}'); write('package-lock.json', '{}'); write('src/app.ts', 'export const value = 1;');
  const calls = [];
  const run = (command, args, options) => {
    calls.push([command, args]);
    if (command === 'npm') { write('node_modules/.bin/vite', 'test'); write('node_modules/.bin/tsc', 'test'); }
    if (command.endsWith('/vite')) {
      const dist = args[args.indexOf('--outDir') + 1]; fs.mkdirSync(dist, { recursive: true });
      fs.writeFileSync(path.join(dist, 'index.html'), options.env.VITE_QUANTGRAPH_BUILD_ID);
    }
  };
  return { web, write, calls, run };
}

test('first build, verified reuse and forced build reuse dependencies', t => {
  const f = fixture(t);
  assert.equal(inspectBuild(f.web).status, 'MISSING');
  const built = prepareBuild(f.web, { run: f.run });
  assert.equal(built.reused, false); assert.equal(f.calls.length, 3);
  assert.equal(fs.readFileSync(path.join(f.web, 'dist/index.html'), 'utf8'), built.build_id);
  assert.equal(prepareBuild(f.web, { run: f.run }).reused, true); assert.equal(f.calls.length, 3);
  assert.equal(prepareBuild(f.web, { force: true, run: f.run }).reused, false);
  assert.equal(f.calls.filter(([c]) => c === 'npm').length, 1);
});
test('uncommitted source modifications, additions, deletions, generated/config/env inputs', t => {
  const f = fixture(t);
  prepareBuild(f.web, { run: f.run });
  for (const [name, value] of [['src/app.ts', 'changed'], ['src/new.ts', 'new'], ['generated/api.json', '{}'], ['vite.config.ts', 'config'], ['.env.production', 'VITE_EXAMPLE=1'], ['public/logo.svg', '<svg/>'], ['package.json', '{"version":"test2"}']]) {
    f.write(name, value); assert.equal(inspectBuild(f.web).status, 'STALE', name);
    prepareBuild(f.web, { run: f.run }); assert.equal(inspectBuild(f.web).status, 'CURRENT');
  }
  fs.unlinkSync(path.join(f.web, 'src/new.ts')); assert.equal(inspectBuild(f.web).status, 'STALE');
});
test('lock change installs once and rebuilds', t => {
  const f = fixture(t); prepareBuild(f.web, { run: f.run });
  f.write('package-lock.json', '{"lockfileVersion":3}');
  assert.equal(inspectBuild(f.web).status, 'STALE'); prepareBuild(f.web, { run: f.run });
  assert.equal(f.calls.filter(([c]) => c === 'npm').length, 2);
  prepareBuild(f.web, { run: f.run }); assert.equal(f.calls.filter(([c]) => c === 'npm').length, 2);
});
test('failed compilation preserves old output but refuses successful startup result', t => {
  const f = fixture(t); const old = prepareBuild(f.web, { run: f.run }); f.write('src/app.ts', 'bad code');
  assert.throws(() => prepareBuild(f.web, { run: () => { throw new Error('compile failed'); } }), /compile failed/);
  assert.equal(inspectBuild(f.web).status, 'STALE');
  assert.equal(fs.readFileSync(path.join(f.web, 'dist/index.html'), 'utf8'), old.build_id);
});
test('mid-build edit is rejected and existing build retained', t => {
  const f = fixture(t); const old = prepareBuild(f.web, { run: f.run }); f.write('src/app.ts', 'next');
  assert.throws(() => prepareBuild(f.web, { run: (...args) => { f.run(...args); f.write('src/race.ts', String(f.calls.length)); } }), /源码改变/);
  assert.equal(fs.readFileSync(path.join(f.web, 'dist/index.html'), 'utf8'), old.build_id);
});
test('tampered outputs cannot be reused, non-input logs do not change fingerprint', t => {
  const f = fixture(t); prepareBuild(f.web, { run: f.run });
  const before = fingerprint(f.web).fingerprint; f.write('test-results/trace.txt', 'a');
  assert.equal(fingerprint(f.web).fingerprint, before);
  f.write('dist/index.html', 'tampered'); assert.equal(inspectBuild(f.web).status, 'INVALID');
});
test('ambient NODE_ENV cannot change production output or omit build dependencies', t => {
  const f = fixture(t);
  const previous = process.env.NODE_ENV;
  t.after(() => { if (previous === undefined) delete process.env.NODE_ENV; else process.env.NODE_ENV = previous; });
  process.env.NODE_ENV = 'development';
  prepareBuild(f.web, { run: (command, args, options) => {
    if (command === 'npm') { assert.ok(args.includes('--include=dev')); assert.equal(options.env.NODE_ENV, 'development'); }
    else assert.equal(options.env.NODE_ENV, 'production');
    f.run(command, args, options);
  } });
  process.env.NODE_ENV = 'production';
  assert.equal(prepareBuild(f.web, { run: f.run }).reused, true);
});
