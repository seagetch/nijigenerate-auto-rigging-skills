import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { createReviewHandler, reviewPathsForManifest, manifestName, reviewReceiver } from '../review-security.mjs';
import { safeColor, localUrl } from '../src/security.mjs';

async function fixture(t, review) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'review-security-'));
  const publicRoot = path.join(root, 'public');
  await fs.mkdir(publicRoot);
  await fs.writeFile(path.join(publicRoot, 'manifest.json'), JSON.stringify({ review }));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  return { root, publicRoot };
}

async function serve(t, publicRoot) {
  const server = http.createServer(createReviewHandler({ publicRoot }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
  return `http://127.0.0.1:${server.address().port}`;
}

function post(origin, value, headers = {}) {
  return fetch(origin, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) });
}

test('valid public manifest names and exact same-origin URLs work', () => {
  assert.equal(manifestName('/projects/a/manifest.json'), 'projects/a/manifest.json');
  assert.equal(manifestName('http://localhost:5173/manifest.json', 'http://localhost:5173'), 'manifest.json');
  for (const value of ['file:///etc/test.json', '/../../test.json', '/%2e%2e/test.json', '/%252e%252e/test.json', 'C:\\test.json', '//example.com/test.json', 'https://example.com/test.json', '/manifest.json?x=1', '/foo\\test.json', '/manifest.json%00', '/manifest.txt', 'http://localhost:5173/a/../manifest.json']) {
    assert.throws(() => manifestName(value, 'http://localhost:5173'), undefined, value);
  }
});

test('output paths reject traversal, absolute paths, and non-review destinations', async t => {
  const { publicRoot } = await fixture(t);
  for (const review of [
    { resultsDir: '../reviews' }, { resultsDir: '/tmp/reviews' }, { resultsDir: '.' },
    { resultsDir: 'assets' }, { resultsDir: 'nested/../reviews' },
    { latestReview: '../private.json' }, { latestReview: '/tmp/private.json' },
    { latestReview: 'reviews/nested/file.json' }, { latestReview: 'reviews/startup.sh' },
    { resultsDir: 'reviews', latestReview: 'reviews/../manifest.json' },
  ]) {
    await fs.writeFile(path.join(publicRoot, 'manifest.json'), JSON.stringify({ review }));
    await assert.rejects(reviewPathsForManifest(publicRoot, '/manifest.json'));
  }
});

test('all bundled manifests have valid storage paths', async () => {
  const root = path.resolve(new URL('../public/', import.meta.url).pathname);
  const files = await fs.readdir(root, { recursive: true });
  for (const file of files.filter(file => file.endsWith('manifest.json'))) {
    await reviewPathsForManifest(root, '/' + file.split(path.sep).join('/'));
  }
});

test('symlinks in manifests, result directories, ancestors and latest files are rejected', async t => {
  const { root, publicRoot } = await fixture(t);
  const outside = path.join(root, 'outside');
  await fs.mkdir(outside);
  await fs.writeFile(path.join(outside, 'secret.json'), '{"secret":true}');
  await fs.symlink(outside, path.join(publicRoot, 'linked'));
  await assert.rejects(reviewPathsForManifest(publicRoot, '/linked/secret.json'));
  await fs.symlink(path.join(outside, 'secret.json'), path.join(publicRoot, 'linked.json'));
  await assert.rejects(reviewPathsForManifest(publicRoot, '/linked.json'));
  await fs.symlink(outside, path.join(publicRoot, 'reviews'));
  await assert.rejects(reviewPathsForManifest(publicRoot, '/manifest.json'));
  await fs.unlink(path.join(publicRoot, 'reviews'));
  await fs.mkdir(path.join(publicRoot, 'reviews'));
  await fs.symlink(path.join(outside, 'missing.json'), path.join(publicRoot, 'reviews/latest-review.json'));
  await assert.rejects(reviewPathsForManifest(publicRoot, '/manifest.json'));
});

test('normal POST/GET works, archives are unique, output paths are relative', async t => {
  const { publicRoot } = await fixture(t);
  const origin = await serve(t, publicRoot);
  const replies = await Promise.all([1, 2, 3].map(id => post(origin, { id, manifest: { url: origin + '/manifest.json' } })));
  const data = await Promise.all(replies.map(async r => { assert.equal(r.status, 200); return r.json(); }));
  assert.equal(new Set(data.map(d => d.archived)).size, 3);
  for (const item of data) { assert.equal(item.latest, 'reviews/latest-review.json'); assert.ok(!path.isAbsolute(item.archived)); }
  const latest = await (await fetch(origin + '/latest')).json();
  assert.equal(latest.manifest.url, '/manifest.json');
  assert.ok([1, 2, 3].includes(latest.id));
});

test('existing hard links are replaced without modifying their other names', async t => {
  const { root, publicRoot } = await fixture(t);
  const privateFile = path.join(root, 'private.json');
  await fs.writeFile(privateFile, '{"private":true}');
  await fs.mkdir(path.join(publicRoot, 'reviews'));
  await fs.link(privateFile, path.join(publicRoot, 'reviews/latest-review.json'));
  const origin = await serve(t, publicRoot);
  assert.equal((await post(origin, { ok: true })).status, 200);
  assert.equal(await fs.readFile(privateFile, 'utf8'), '{"private":true}');
});

test('cross-origin, null origin, no origin, wrong content type and unknown routes fail closed', async t => {
  const { publicRoot } = await fixture(t);
  const origin = await serve(t, publicRoot);
  for (const headers of [{ Origin: 'https://attacker.invalid' }, { Origin: 'null' }, { 'Content-Type': 'text/plain' }, { 'Sec-Fetch-Site': 'cross-site' }]) {
    const response = await post(origin, {}, headers);
    assert.ok([403, 415].includes(response.status), JSON.stringify({ headers, status: response.status }));
  }
  const badHostStatus = await new Promise((resolve, reject) => {
    const req = http.request(origin, { method: 'POST', headers: { Host: 'attacker.invalid', Origin: origin, 'Content-Type': 'application/json' } }, res => { res.resume(); resolve(res.statusCode); });
    req.on('error', reject); req.end('{}');
  });
  assert.equal(badHostStatus, 403);
  assert.equal((await fetch(origin, { method: 'POST', body: '{}' })).status, 403);
  assert.equal((await fetch(origin + '/latest', { headers: { Origin: 'https://attacker.invalid' } })).status, 403);
  assert.equal((await fetch(origin, { method: 'DELETE' })).status, 405);
  assert.equal((await post(origin, { manifest: { url: 'file:///etc/test.json' } })).status, 403);
  await assert.rejects(fs.stat(path.join(publicRoot, 'reviews')));
});

test('malformed JSON and missing files never expose local paths', async t => {
  const { root, publicRoot } = await fixture(t);
  const origin = await serve(t, publicRoot);
  for (const response of [await fetch(origin + '/latest'), await fetch(origin, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: '{' })]) {
    assert.ok(response.status >= 400);
    assert.ok(!(await response.text()).includes(root));
  }
  const response = await post(origin, []);
  assert.equal(response.status, 400);
});

test('non-loopback clients are refused before any I/O', async () => {
  const headers = {};
  let output;
  const res = { setHeader(k, v) { headers[k] = v; }, end(v) { output = JSON.parse(v); } };
  await createReviewHandler({ publicRoot: '/does-not-exist' })({ method: 'GET', socket: { remoteAddress: '192.0.2.1' }, headers: {} }, res);
  assert.equal(res.statusCode, 403);
  assert.equal(output.ok, false);
});

test('DOM colors and asset URLs reject injection and external fetches', () => {
  assert.equal(safeColor('#aAbB00'), '#aAbB00');
  for (const value of ['red', '#fff', '" onmouseover="alert(1)', 'url(https://attacker.invalid)', '</span><script>x</script>', null]) assert.equal(safeColor(value), '#d4e157');
  const base = 'http://localhost:5173/projects/a/manifest.json';
  const origin = 'http://localhost:5173';
  assert.equal(localUrl('images/a.png', base, origin, true), origin + '/projects/a/images/a.png');
  for (const value of ['https://attacker.invalid/data.json', '//attacker.invalid/a', 'file:///tmp/a', '../b/data.json', '/projects/b/a.png', '/@fs/etc/passwd', '/src/main.js', '/%2e%2e/data.json', 'data:text/html,hello', 'javascript:alert(1)']) assert.throws(() => localUrl(value, base, origin, true), undefined, value);
});


test('Vite public middleware rejects symlink reads and @fs requests', async t => {
  const { root, publicRoot } = await fixture(t);
  const privateFile = path.join(root, 'private.json');
  await fs.writeFile(privateFile, '{"private":true}');
  await fs.symlink(privateFile, path.join(publicRoot, 'linked.json'));
  let guard;
  reviewReceiver({ endpoint: '/api/review', prefix: 'review' }).configureServer({
    config: { publicDir: publicRoot }, middlewares: { use(...args) { if (args.length === 1) guard = args[0]; } }
  });
  for (const name of ['/linked.json', '/@fs' + privateFile, '/%2e%2e/private.json']) {
    let next = false;
    const res = { setHeader() {}, end() {} };
    await guard({ method: 'GET', url: name, headers: { host: '127.0.0.1:5173' }, socket: { localPort: 5173, remoteAddress: '127.0.0.1' } }, res, () => { next = true; });
    assert.equal(next, false);
    assert.equal(res.statusCode, 403);
  }
  let next = false;
  await guard({ method: 'GET', url: '/manifest.json', headers: { host: '127.0.0.1:5173' }, socket: { localPort: 5173, remoteAddress: '127.0.0.1' } }, { setHeader() {}, end() {} }, () => { next = true; });
  assert.equal(next, true);
});
