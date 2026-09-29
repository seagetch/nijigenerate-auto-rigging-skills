export function safeColor(value, fallback = '#d4e157') {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
}

// Resolve only same-origin public URLs. Do not let manifests fetch remote data,
// internal Vite modules, file URLs, or assets outside their project directory.
export function localUrl(value, base, origin, asset = false) {
  if (typeof value !== 'string' || !value || /[\\\x00-\x20\x7f]/.test(value) || value.startsWith('//')) throw new Error('Invalid project URL');
  let decoded;
  try { decoded = decodeURIComponent(value); } catch { throw new Error('Invalid project URL'); }
  if (decoded.includes('%') || /[\\\x00-\x20\x7f]/.test(decoded) || decoded.split(/[/?#]/).some(part => part === '..' || part === '.')) throw new Error('Invalid project URL');
  const url = new URL(value, base);
  if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Only local project URLs are allowed');
  const pathname = decodeURIComponent(url.pathname);
  if (pathname.split('/').some(part => part.startsWith('.') || part.startsWith('@')) || /^\/(?:src|node_modules|api)(?:\/|$)/.test(pathname)) throw new Error('Invalid project asset URL');
  if (asset && !pathname.startsWith(decodeURIComponent(new URL('.', base).pathname))) throw new Error('Asset is outside the project directory');
  return url.href;
}
