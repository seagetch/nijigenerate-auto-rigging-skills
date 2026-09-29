import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const MAX_BYTES = 10_000_000;
const loopback = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const hosts = new Set(['127.0.0.1', 'localhost', '[::1]']);

function fail(status = 400, message = 'Invalid review request') {
  throw Object.assign(new Error(message), { status });
}

function inside(root, candidate) {
  const rel = path.relative(root, candidate);
  return rel === '' || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${path.sep}`));
}

function relativeName(value) {
  if (typeof value !== 'string' || !value || /[\\\x00-\x1f\x7f:%?#]/.test(value)
      || path.posix.isAbsolute(value) || path.win32.isAbsolute(value)
      || value.split('/').some(part => !part || part === '.' || part === '..')) fail();
  return value;
}

// Inspect every existing component, including dangling links. No symlinks are
// permitted, even links whose present target happens to be inside the root.
export async function checkedPath(root, candidate, { missing = false } = {}) {
  if (!inside(root, candidate)) fail(403, 'Path is outside the review project');
  const rel = path.relative(root, candidate);
  let current = root;
  for (const part of ['', ...rel.split(path.sep).filter(Boolean)]) {
    current = part ? path.join(current, part) : current;
    try {
      const stat = await fs.lstat(current);
      if (stat.isSymbolicLink()) fail(403, 'Symbolic links are not allowed');
      const real = await fs.realpath(current);
      if (!inside(root, real)) fail(403, 'Path is outside the review project');
    } catch (error) {
      if (missing && error.code === 'ENOENT') return candidate;
      throw error;
    }
  }
  return candidate;
}

async function readJsonFile(root, file) {
  await checkedPath(root, file);
  const handle = await fs.open(file, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.size > MAX_BYTES) fail(413, 'Review file is too large or not a regular file');
    return JSON.parse(await handle.readFile('utf8'));
  } finally {
    await handle.close();
  }
}

export function manifestName(uri = '/manifest.json', origin) {
  if (typeof uri !== 'string' || /[\\\x00-\x20\x7f]/.test(uri) || uri.startsWith('//')) fail();
  let value = uri;
  if (/^[a-z][a-z\d+.-]*:/i.test(value)) {
    let url;
    try { url = new URL(value); } catch { fail(); }
    if (!origin || url.origin !== origin || url.username || url.password || url.search || url.hash) fail(403, 'Manifest must use the viewer origin');
    // Check the original path too: URL parsing alone silently removes ../.
    value = value.slice(value.indexOf('://') + 3);
    value = value.includes('/') ? value.slice(value.indexOf('/')) : '/';
  }
  try { value = decodeURIComponent(value); } catch { fail(); }
  value = relativeName(value.replace(/^\//, ''));
  if (!value.endsWith('.json')) fail();
  return value;
}

export async function reviewPathsForManifest(publicRoot, uri, origin) {
  const root = path.resolve(publicRoot);
  const name = manifestName(uri, origin);
  const manifestPath = await checkedPath(root, path.join(root, name));
  const manifest = await readJsonFile(root, manifestPath);
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) fail();
  const manifestDir = path.dirname(manifestPath);
  const resultName = relativeName(manifest.review?.resultsDir ?? 'reviews');
  // Output belongs to a dedicated reviews directory, never arbitrary project files.
  if (path.posix.basename(resultName) !== 'reviews') fail(403, 'resultsDir must end with reviews');
  const resultsDir = await checkedPath(root, path.resolve(manifestDir, resultName), { missing: true });
  const latestName = relativeName(manifest.review?.latestReview ?? `${resultName}/latest-review.json`);
  const latest = path.resolve(manifestDir, latestName);
  if (!inside(resultsDir, latest) || path.dirname(latest) !== resultsDir || !latest.endsWith('.json')) fail(403, 'latestReview must be a JSON file directly inside resultsDir');
  await checkedPath(root, latest, { missing: true });
  return { root, manifestPath, manifest, manifestDir, resultsDir, latest };
}

function requestOrigin(req) {
  if (!loopback.has(req.socket.remoteAddress)) fail(403, 'Only loopback clients are allowed');
  const host = req.headers.host;
  if (typeof host !== 'string') fail(403, 'Invalid Host');
  let url;
  try { url = new URL(`http://${host}`); } catch { fail(403, 'Invalid Host'); }
  if (!hosts.has(url.hostname) || url.host !== host || url.username || url.password
      || Number(url.port || 80) !== req.socket.localPort) fail(403, 'Invalid Host');
  const origin = `${req.socket.encrypted ? 'https:' : 'http:'}//${host}`;
  if (req.headers.origin !== undefined && req.headers.origin !== origin) fail(403, 'Cross-origin requests are not allowed');
  if (req.headers['sec-fetch-site'] && req.headers['sec-fetch-site'] !== 'same-origin' && req.headers['sec-fetch-site'] !== 'none') fail(403, 'Cross-site requests are not allowed');
  if (req.method === 'POST') {
    if (req.headers.origin !== origin) fail(403, 'Same-origin POST required');
    if (!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type'] || '')) fail(415, 'JSON content type required');
  }
  return origin;
}

function send(res, status, value) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(JSON.stringify(value));
}

async function readBody(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BYTES) fail(413, 'Review request is too large');
    chunks.push(chunk);
  }
  const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!body || typeof body !== 'object' || Array.isArray(body)) fail();
  return body;
}

async function saveReview(paths, review, prefix) {
  const { root, manifestDir, resultsDir, latest } = paths;
  await checkedPath(root, resultsDir, { missing: true });
  await fs.mkdir(resultsDir, { recursive: true, mode: 0o700 });
  await checkedPath(root, resultsDir);
  await checkedPath(root, latest, { missing: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const archived = path.join(resultsDir, `${prefix}-${stamp}-${randomUUID()}.json`);
  const text = JSON.stringify(review, null, 2) + '\n';
  // Exclusive creation plus rename avoids following a final symlink or modifying
  // an existing hard-linked file. Parent directory races by local OS users are
  // outside the threat model: the workspace must be owned by the running user.
  await fs.writeFile(archived, text, { flag: 'wx', mode: 0o600 });
  const temp = path.join(resultsDir, `.review-${randomUUID()}.tmp`);
  try {
    await fs.writeFile(temp, text, { flag: 'wx', mode: 0o600 });
    await checkedPath(root, latest, { missing: true });
    await fs.rename(temp, latest);
  } finally {
    await fs.unlink(temp).catch(error => { if (error.code !== 'ENOENT') throw error; });
  }
  return { ok: true, latest: path.relative(manifestDir, latest).split(path.sep).join('/'), archived: path.relative(manifestDir, archived).split(path.sep).join('/') };
}

export function createReviewHandler({ publicRoot, prefix = 'review' }) {
  return async (req, res) => {
    try {
      const origin = requestOrigin(req);
      const url = new URL(req.url || '/', origin);
      if (req.method === 'GET' && url.pathname === '/latest') {
        const paths = await reviewPathsForManifest(publicRoot, url.searchParams.get('manifest') || '/manifest.json', origin);
        send(res, 200, await readJsonFile(paths.root, paths.latest));
        return;
      }
      if (req.method !== 'POST') { send(res, 405, { ok: false, error: 'Method Not Allowed' }); return; }
      if (url.pathname !== '/') { send(res, 404, { ok: false, error: 'Not Found' }); return; }
      const review = await readBody(req);
      const uri = review.manifest?.url || url.searchParams.get('manifest') || '/manifest.json';
      const paths = await reviewPathsForManifest(publicRoot, uri, origin);
      if (review.manifest) review.manifest.url = '/' + manifestName(uri, origin);
      send(res, 200, await saveReview(paths, review, prefix));
    } catch (error) {
      // Never echo fs errors or input data: they may contain local private paths.
      const status = error.status || (error.code === 'ENOENT' ? 404 : 400);
      send(res, status, { ok: false, error: error.status ? error.message : (status === 404 ? 'Review file not found' : 'Invalid review data or unavailable review storage') });
    }
  };
}

export function reviewReceiver({ endpoint, prefix }) {
  return {
    name: `${prefix}-receiver`,
    configureServer(server) {
      if (!server.config.publicDir) throw new Error('A public directory is required');
      // Vite's public-file middleware bypasses the review API. Guard that path
      // too so a public symlink cannot disclose an external local file.
      const publicRoot = path.resolve(server.config.publicDir);
      server.middlewares.use(async (req, res, next) => {
        try {
          requestOrigin(req);
          const rawPath = (req.url || '/').split('?')[0];
          let name;
          try { name = decodeURIComponent(rawPath); } catch { fail(); }
          if (/[\\\x00-\x1f\x7f]/.test(name) || name.startsWith('//')
              || name.split('/').some(part => part === '..')
              || name === '/@fs' || name.startsWith('/@fs/')) fail(403, 'Invalid public path');
          await checkedPath(publicRoot, path.resolve(publicRoot, name.replace(/^\//, '')), { missing: true });
          next();
        } catch (error) {
          send(res, error.status || 403, { ok: false, error: 'Public file access denied' });
        }
      });
      server.middlewares.use(endpoint, createReviewHandler({ publicRoot: server.config.publicDir, prefix }));
    }
  };
}
