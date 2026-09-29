/** Small, deterministic build check for the existing Vite app. */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const VERSION = 'quantgraph-web-build/v1';
const hash = (value) => createHash('sha256').update(value).digest('hex');
function files(directory, prefix = '') {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name, 'en')).flatMap((entry) => {
    if (entry.isSymbolicLink()) throw new Error(`构建输入不支持符号链接：${prefix}${entry.name}`);
    const name = prefix + entry.name;
    return entry.isDirectory() ? files(path.join(directory, entry.name), name + '/') : entry.isFile() ? [name] : [];
  });
}
export function fingerprint(web) {
  const selected = new Set();
  for (const directory of ['src', 'public', 'generated', 'scripts'])
    for (const name of files(path.join(web, directory))) selected.add(`${directory}/${name}`);
  for (const name of fs.readdirSync(web)) {
    if (name.endsWith('.tsbuildinfo')) continue;
    if (/\.(?:json|[cm]?js|ts|html|css)$/.test(name) || name === '.npmrc' || /^\.env(?:\.(?:local|production|production\.local))?$/.test(name)) {
      if (fs.statSync(path.join(web, name)).isFile()) selected.add(name);
    }
  }
  const inputs = [...selected].sort().map((name) => [name, hash(fs.readFileSync(path.join(web, name)))]);
  return { fingerprint: hash(inputs.map(([name, digest]) => `${name}\0${digest}\n`).join('')), inputs };
}
function outputHashes(dist) {
  return Object.fromEntries(files(dist).filter((name) => name !== 'build-info.json').sort().map((name) => [name, hash(fs.readFileSync(path.join(dist, name)))]));
}
export function inspectBuild(web) {
  const source = fingerprint(web);
  const manifest = path.join(web, 'dist/build-info.json');
  if (!fs.existsSync(manifest) || !fs.existsSync(path.join(web, 'dist/index.html')))
    return { status: 'MISSING', ...source };
  try {
    const info = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    if (info.schema_version !== VERSION || JSON.stringify(outputHashes(path.join(web, 'dist'))) !== JSON.stringify(info.outputs))
      return { status: 'INVALID', ...source };
    return { status: info.source_fingerprint === source.fingerprint ? 'CURRENT' : 'STALE', ...source, info };
  } catch { return { status: 'INVALID', ...source }; }
}
function execute(command, args, options) {
  const result = spawnSync(command, args, { ...options, stdio: 'inherit' });
  if (result.error || result.status !== 0) throw new Error(`前端步骤失败：${command} ${args.join(' ')}；未启动服务。`);
}
export function prepareBuild(web, { force = false, run = execute } = {}) {
  web = path.resolve(web);
  const before = inspectBuild(web);
  if (!force && before.status === 'CURRENT') return { reused: true, ...before.info };
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('前端构建需要 Node.js 22 或更新版本。');
  const lock = path.join(web, 'package-lock.json');
  if (!fs.existsSync(lock)) throw new Error('缺少 package-lock.json；不能确认依赖版本。');
  const dependencyStamp = path.join(web, 'node_modules/.quantgraph-dependencies.json');
  const dependencyHash = hash(fs.readFileSync(path.join(web, 'package.json')) + '\0' + fs.readFileSync(lock) + '\0' + process.versions.node.split('.')[0]);
  let installed;
  try { installed = JSON.parse(fs.readFileSync(dependencyStamp, 'utf8')).fingerprint; } catch { /* Initial install must be verified. */ }
  if (installed !== dependencyHash || !fs.existsSync(path.join(web, 'node_modules/.bin/vite')) || !fs.existsSync(path.join(web, 'node_modules/.bin/tsc'))) {
    run('npm', ['ci', '--include=dev'], { cwd: web, env: { ...process.env, NODE_ENV: 'development' } });
    fs.mkdirSync(path.dirname(dependencyStamp), { recursive: true });
    fs.writeFileSync(dependencyStamp, JSON.stringify({ fingerprint: dependencyHash }));
  }
  const stagingParent = path.resolve(web, '../.artifacts/frontend-builds');
  fs.mkdirSync(stagingParent, { recursive: true });
  const staging = fs.mkdtempSync(path.join(stagingParent, 'build-'));
  const dist = path.join(staging, 'dist');
  const source = fingerprint(web);
  const info = {
    schema_version: VERSION, source_fingerprint: source.fingerprint,
    build_id: source.fingerprint.slice(0, 16), built_at: new Date().toISOString(),
    app_version: JSON.parse(fs.readFileSync(path.join(web, 'package.json'))).version,
    node_version: process.versions.node,
  };
  const env = { ...process.env, NODE_ENV: 'production', VITE_QUANTGRAPH_BUILD_ID: info.build_id, VITE_QUANTGRAPH_BUILD_AT: info.built_at };
  run(path.join(web, 'node_modules/.bin/tsc'), ['-b'], { cwd: web, env });
  run(path.join(web, 'node_modules/.bin/vite'), ['build', '--outDir', dist, '--emptyOutDir'], { cwd: web, env });
  if (!fs.existsSync(path.join(dist, 'index.html'))) throw new Error('构建未产生 index.html；未启动服务。');
  if (fingerprint(web).fingerprint !== source.fingerprint) throw new Error('构建过程中源码改变，请重新启动；不会发布不对应的页面。');
  info.outputs = outputHashes(dist);
  fs.writeFileSync(path.join(dist, 'build-info.json'), JSON.stringify(info, null, 2));
  const destination = path.join(web, 'dist');
  const previous = path.join(staging, 'previous-dist');
  if (fs.existsSync(destination)) {
    if (fs.lstatSync(destination).isSymbolicLink()) throw new Error('dist 是符号链接，未替换；请检查本地构建目录。');
    fs.renameSync(destination, previous);
  }
  try { fs.renameSync(dist, destination); }
  catch (error) { if (fs.existsSync(previous)) fs.renameSync(previous, destination); throw error; }
  return { reused: false, ...info };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const command = process.argv[2] || 'ensure';
  const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  try {
    if (command === 'status') console.log(JSON.stringify(inspectBuild(web)));
    else if (['ensure', 'build'].includes(command)) {
      const result = prepareBuild(web, { force: command === 'build' || process.argv.includes('--rebuild') });
      console.log(`${result.reused ? '复用已验证页面' : '页面已重新构建'} · ${result.build_id}`);
    } else throw new Error('不支持的构建操作。');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
