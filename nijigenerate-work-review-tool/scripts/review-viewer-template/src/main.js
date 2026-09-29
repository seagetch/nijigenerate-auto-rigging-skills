import './styles.css';
import { safeColor, localUrl } from './security.mjs';
import * as THREE from 'three';
import { createIcons, icons as lucideIcons } from 'lucide';

const DEFAULT_MANIFEST = '/manifest.json';

let manifest;
let manifestUrl;
let manifestBaseUrl;
let ASSETS = Object.create(null);
let TARGETS = Object.create(null);
let targetOrder = [];
let gridCalibration = Object.create(null);
let reviewSchema = 'depth-review-v1';
let viewerMode = 'depth';

const resizeHandleNames = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const minRangeSize = 0.015;

const state = {
  target: null,
  view: '2d',
  imageMode: 'overlay',
  tool: 'select',
  moveMode: 'free',
  snap: true,
  axisLock: false,
  zoom: 0.76,
  pan: { x: 70, y: 20 },
  tags: [],
  selectedId: null,
  globalComment: '',
  reviewDecision: 'retake',
  reviewOutput: '',
  status: 'Ready',
  images: Object.create(null),
  depth: Object.create(null),
  depthSources: Object.create(null),
  meshSources: Object.create(null),
  deformations: Object.create(null),
  undoStack: [],
  verticesExpanded: false,
  drag: null
};

const app = document.querySelector('#app');
app.innerHTML = `
  <div class="app">
    <aside class="panel"><div class="panel-inner">
      <div class="section">
        <div class="section-title">Target</div>
        <div class="segmented targets" id="targetButtons"></div>
      </div>
      <div class="section">
        <div class="section-title">View</div>
        <div class="segmented two" id="viewButtons">
          <button data-view="2d"><i data-lucide="image"></i>2D</button>
          <button data-view="3d"><i data-lucide="box"></i>3D</button>
        </div>
        <div class="segmented">
          <button data-image-mode="original"><i data-lucide="eye"></i>Original</button>
          <button data-image-mode="overlay"><i data-lucide="grid-2x2"></i>Mesh</button>
          <button data-image-mode="both"><i data-lucide="square"></i>Both</button>
        </div>
      </div>
      <div class="section">
        <div class="section-title">Tools</div>
        <div class="segmented" id="toolButtons"></div>
        <div class="segmented" id="moveButtons"></div>
        <div class="segmented two hidden" id="actionButtons"></div>
        <p class="small" id="toolHelp"></p>
      </div>
      <div class="section">
        <div class="section-title"><span>Tags</span><button id="addTag"><i data-lucide="plus"></i></button></div>
        <div id="tagList" class="tag-list"></div>
      </div>
      <div class="section hidden" id="meshSection">
        <div class="section-title">Meshes</div>
        <div id="meshList" class="mesh-list"></div>
      </div>
    </div></aside>

    <main class="workspace">
      <div class="topbar">
        <div class="toolbar-group">
          <strong id="targetTitle"></strong>
          <span id="coordReadout" class="small"></span>
        </div>
        <div class="toolbar-group">
          <button id="zoomOut">-</button>
          <button id="zoomReset">100%</button>
          <button id="zoomIn">+</button>
        </div>
      </div>
      <div class="canvas-shell">
        <canvas id="reviewCanvas" class="review-canvas"></canvas>
        <div id="threeHost" class="three-host hidden"></div>
      </div>
    </main>

    <aside class="panel right"><div class="panel-inner">
      <div class="section">
        <div class="section-title">Selected Tag</div>
        <div id="editor" class="stack"></div>
      </div>
      <div class="section">
        <div class="section-title">Global Comment</div>
        <textarea id="globalComment" placeholder="Overall review notes"></textarea>
      </div>
      <div class="section">
        <div class="section-title">Review</div>
        <div class="segmented two decision-group">
          <button data-decision="ok"><i data-lucide="check-circle"></i>OK</button>
          <button data-decision="retake"><i data-lucide="rotate-ccw"></i>Retake</button>
        </div>
        <button id="copyReview"><i data-lucide="copy"></i>Copy</button>
        <textarea id="reviewOutput" class="json-output" readonly></textarea>
        <div id="status" class="status"></div>
      </div>
    </div></aside>
  </div>
`;
createIcons({ icons: lucideIcons });

const canvas = document.querySelector('#reviewCanvas');
const ctx = canvas.getContext('2d');
const threeHost = document.querySelector('#threeHost');
let renderer;
let scene;
let camera;
let mesh;
let wire;
let originalTexture;
let isThreeReady = false;
let threeRotation = { x: -0.35, y: 0.45 };
let threeDrag = null;

function manifestFromUri() {
  const url = new URL(window.location.href);
  const direct = url.searchParams.get('manifest');
  if (direct) return direct;
  const project = url.searchParams.get('project');
  if (project) return `/projects/${project}/manifest.json`;
  const hashParams = new URLSearchParams(url.hash.startsWith('#') ? url.hash.slice(1) : url.hash);
  const hashManifest = hashParams.get('manifest');
  if (hashManifest) return hashManifest;
  if (url.pathname.endsWith('/manifest.json')) return url.pathname;
  return DEFAULT_MANIFEST;
}

function resolveManifestUrl(uri) {
  return localUrl(uri, window.location.href, window.location.origin);
}

function resolveAssetUrl(uri) {
  return localUrl(uri, manifestBaseUrl, window.location.origin, true);
}

function getByJsonPath(value, jsonPath = '') {
  if (!jsonPath) return value;
  return jsonPath.split('.').filter(Boolean).reduce((current, key) => current?.[key], value);
}

function resolvePointer(value, pointer) {
  if (!pointer) return value;
  return pointer.split('/').filter(Boolean).reduce((current, key) => current?.[decodeURIComponent(key)], value);
}

function splitRef(ref) {
  const [file, pointer = ''] = ref.split('#');
  return { file, pointer };
}

async function fetchJson(url) {
  const response = await fetch(url, { redirect: 'error' });
  if (!response.ok) throw new Error(`Failed to load ${url}: ${response.status}`);
  return response.json();
}

function withIds(tags) {
  return tags.map((tag) => ({
    ...tag,
    color: safeColor(tag.color),
    kind: ['point', 'range', 'meshSet'].includes(tag.kind) ? tag.kind : 'point',
    point: tag.point || { x: 0.5, y: 0.5 },
    rect: tag.rect || { x: 0.44, y: 0.46, w: 0.12, h: 0.08 },
    comment: tag.comment || '',
    id: tag.id || crypto.randomUUID()
  }));
}

function normalizeMeshTag(tag) {
  return {
    kind: 'meshSet',
    meshIds: [],
    vertexRefs: [],
    ...tag,
    kind: 'meshSet',
    meshIds: Array.isArray(tag.meshIds) ? tag.meshIds : [],
    vertexRefs: normalizeVertexRefs(tag.vertexRefs || tag.vertices || [])
  };
}

function normalizeVertexRefs(refs) {
  return (Array.isArray(refs) ? refs : []).map((ref) => {
    if (Array.isArray(ref)) return { meshId: String(ref[0]), vertexIndex: Number(ref[1]) || 0 };
    return { meshId: String(ref.meshId), vertexIndex: Number(ref.vertexIndex ?? ref.index) || 0 };
  }).filter((ref) => ref.meshId && Number.isFinite(ref.vertexIndex));
}

function normalizePoint(point) {
  if (Array.isArray(point)) return { x: Number(point[0]) || 0, y: Number(point[1]) || 0 };
  return { x: Number(point?.x) || 0, y: Number(point?.y) || 0 };
}

function pointFromSourceImage(value) {
  if (!value) return null;
  if (Array.isArray(value)) return value.length >= 2 ? normalizePoint(value) : null;
  const x = value.x ?? value[0];
  const y = value.y ?? value[1];
  if (x === undefined || y === undefined) return null;
  return { x: Number(x) || 0, y: Number(y) || 0 };
}

function normalizeCoordinatePair(pair) {
  if (!pair) return null;
  const source = pointFromSourceImage(pair.source);
  const image = pointFromSourceImage(pair.image);
  return source && image ? { source, image } : null;
}

function coordinatePairsFrom(value) {
  if (!value || typeof value !== 'object') return [];
  return Array.isArray(value.sourceToImage)
    ? value.sourceToImage.map(normalizeCoordinatePair).filter(Boolean)
    : [];
}

function solveLinear3(matrix, vector) {
  const a = matrix.map((row, index) => [...row, vector[index]]);
  for (let col = 0; col < 3; col++) {
    let pivot = col;
    for (let row = col + 1; row < 3; row++) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    }
    if (Math.abs(a[pivot][col]) < 1e-9) return null;
    [a[col], a[pivot]] = [a[pivot], a[col]];
    const div = a[col][col];
    for (let c = col; c < 4; c++) a[col][c] /= div;
    for (let row = 0; row < 3; row++) {
      if (row === col) continue;
      const factor = a[row][col];
      for (let c = col; c < 4; c++) a[row][c] -= factor * a[col][c];
    }
  }
  return [a[0][3], a[1][3], a[2][3]];
}

function affineFromCoordinatePairs(pairs) {
  if (!pairs.length) return null;
  if (pairs.length === 1) {
    const [{ source, image }] = pairs;
    return { a: 1, b: 0, c: image.x - source.x, d: 0, e: 1, f: image.y - source.y, quality: 'translation' };
  }
  if (pairs.length === 2) {
    const [p, q] = pairs;
    const sx = q.source.x - p.source.x;
    const sy = q.source.y - p.source.y;
    const ix = q.image.x - p.image.x;
    const iy = q.image.y - p.image.y;
    const scaleX = Math.abs(sx) > 1e-9 ? ix / sx : 1;
    const scaleY = Math.abs(sy) > 1e-9 ? iy / sy : scaleX;
    return {
      a: scaleX,
      b: 0,
      c: p.image.x - scaleX * p.source.x,
      d: 0,
      e: scaleY,
      f: p.image.y - scaleY * p.source.y,
      quality: 'two-point-axis-aligned'
    };
  }
  const normal = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const bx = [0, 0, 0];
  const by = [0, 0, 0];
  for (const { source, image } of pairs) {
    const row = [source.x, source.y, 1];
    for (let r = 0; r < 3; r++) {
      bx[r] += row[r] * image.x;
      by[r] += row[r] * image.y;
      for (let c = 0; c < 3; c++) normal[r][c] += row[r] * row[c];
    }
  }
  const x = solveLinear3(normal, bx);
  const y = solveLinear3(normal, by);
  return x && y ? { a: x[0], b: x[1], c: x[2], d: y[0], e: y[1], f: y[2], quality: 'affine-least-squares' } : null;
}

function transformPoint(point, transform) {
  return {
    x: transform.a * point.x + transform.b * point.y + transform.c,
    y: transform.d * point.x + transform.e * point.y + transform.f
  };
}

function transformBounds(bounds, transform) {
  if (!bounds || !transform) return bounds;
  const points = [
    { x: bounds.x, y: bounds.y },
    { x: bounds.x + bounds.w, y: bounds.y },
    { x: bounds.x + bounds.w, y: bounds.y + bounds.h },
    { x: bounds.x, y: bounds.y + bounds.h }
  ].map((point) => transformPoint(point, transform));
  return boundsForPoints(points);
}

function transformFromMeshItem(meshItem) {
  const pairs = coordinatePairsFrom(meshItem.sourceToImage ? meshItem : meshItem.reviewTransform);
  const transform = affineFromCoordinatePairs(pairs);
  return transform ? { ...transform, pairCount: pairs.length } : null;
}

function normalizeMeshes(meshes) {
  const list = Array.isArray(meshes) ? meshes : [];
  return list.map((meshItem, index) => {
    const transform = transformFromMeshItem(meshItem);
    const sourceVertices = (meshItem.vertices || meshItem.points || []).map(normalizePoint);
    const vertices = transform ? sourceVertices.map((point) => transformPoint(point, transform)) : sourceVertices;
    const triangles = (meshItem.triangles || meshItem.faces || []).map((face) => Array.isArray(face) ? face.map(Number) : []);
    const sourcePolygon = (meshItem.polygon || meshItem.outline || []).map(normalizePoint);
    const polygon = transform ? sourcePolygon.map((point) => transformPoint(point, transform)) : sourcePolygon;
    return {
      id: String(meshItem.id || meshItem.key || meshItem.name || `mesh-${index + 1}`),
      label: meshItem.label || meshItem.name || meshItem.id || `Mesh ${index + 1}`,
      color: safeColor(meshItem.color),
      vertices,
      triangles,
      polygon,
      bounds: (transform && meshItem.bounds) ? transformBounds(meshItem.bounds, transform) : (meshItem.bounds || boundsForPoints(polygon.length ? polygon : vertices)),
      coordinateTransform: transform,
      raw: meshItem
    };
  });
}

function normalizeDeformations(value) {
  const result = Object.create(null);
  if (!value || typeof value !== 'object') return result;
  if (Array.isArray(value)) {
    for (const item of value) {
      const meshId = String(item.meshId || '');
      const vertexIndex = Number(item.vertexIndex ?? item.index);
      if (!meshId || !Number.isFinite(vertexIndex)) continue;
      result[meshId] ??= Object.create(null);
      result[meshId][vertexIndex] = normalizePoint(item.deformation || item);
    }
    return result;
  }
  for (const [meshId, vertices] of Object.entries(value)) {
    result[meshId] = Object.create(null);
    if (Array.isArray(vertices)) {
      vertices.forEach((point, index) => { result[meshId][index] = normalizePoint(point); });
    } else if (vertices && typeof vertices === 'object') {
      for (const [index, point] of Object.entries(vertices)) result[meshId][index] = normalizePoint(point);
    }
  }
  return result;
}

function boundsForPoints(points) {
  if (!points.length) return { x: 0, y: 0, w: 0, h: 0 };
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  return {
    x: left,
    y: top,
    w: Math.max(...xs) - left,
    h: Math.max(...ys) - top
  };
}

function isMeshSelectionMode() {
  return viewerMode === 'mesh-selection';
}

async function loadManifest() {
  manifestUrl = resolveManifestUrl(manifestFromUri());
  manifestBaseUrl = new URL('.', manifestUrl).href;
  manifest = await fetchJson(manifestUrl);
  if (!['depth-review-manifest-v1', 'review-viewer-manifest-v1'].includes(manifest.schema)) {
    throw new Error(`Unsupported manifest schema: ${manifest.schema}`);
  }
  viewerMode = manifest.mode || manifest.review?.mode || 'depth';
  state.tool = isMeshSelectionMode() ? 'mesh' : 'select';
  reviewSchema = manifest.review?.schema || 'depth-review-v1';
  ASSETS = {
    original: resolveAssetUrl(manifest.assets.original)
  };
  const targets = Object.create(null);
  gridCalibration = Object.create(null);
  for (const target of manifest.targets || []) {
    const entry = {
      key: target.key,
      label: target.label,
      image: target.image ? resolveAssetUrl(target.image) : null,
      color: safeColor(target.color)
    };
    if (target.grid?.calibration) {
      const { file, pointer } = splitRef(target.grid.calibration);
      const calibrationUrl = resolveAssetUrl(file);
      const calibration = await fetchJson(calibrationUrl);
      entry.grid = resolvePointer(calibration, pointer);
      gridCalibration[target.key] = entry.grid;
    }
    if (target.depth?.file) {
      entry.depthUrl = resolveAssetUrl(target.depth.file);
      entry.depthPath = target.depth.path;
    }
    if (typeof target.meshes === 'string') {
      const { file, pointer } = splitRef(target.meshes);
      entry.meshesUrl = resolveAssetUrl(file);
      entry.meshesPointer = pointer;
    } else if (target.meshes?.file) {
      const { file, pointer } = splitRef(target.meshes.file);
      entry.meshesUrl = resolveAssetUrl(file);
      entry.meshesPath = target.meshes.path;
      entry.meshesPointer = target.meshes.pointer || pointer;
    } else if (Array.isArray(target.meshes?.items)) {
      entry.meshes = normalizeMeshes(target.meshes.items);
    }
    if (typeof target.deformations === 'string') {
      const { file, pointer } = splitRef(target.deformations);
      entry.deformationsUrl = resolveAssetUrl(file);
      entry.deformationsPointer = pointer;
    } else if (target.deformations?.file) {
      const { file, pointer } = splitRef(target.deformations.file);
      entry.deformationsUrl = resolveAssetUrl(file);
      entry.deformationsPath = target.deformations.path;
      entry.deformationsPointer = target.deformations.pointer || pointer;
    } else if (target.deformations) {
      state.deformations[target.key] = normalizeDeformations(target.deformations);
    }
    targets[target.key] = entry;
  }
  TARGETS = targets;
  targetOrder = Object.keys(TARGETS);
  state.target = targetOrder[0] || null;
  const initialTags = manifest.initialTags ? await fetchJson(resolveAssetUrl(manifest.initialTags)) : [];
  state.tags = withIds(initialTags);
  if (isMeshSelectionMode()) state.tags = state.tags.map(normalizeMeshTag);
  state.selectedId = state.tags.find((tag) => tag.target === state.target)?.id ?? state.tags[0]?.id ?? null;
  renderTargetButtons();
  renderToolButtons();
}

function renderTargetButtons() {
  const container = document.querySelector('#targetButtons');
  container.innerHTML = '';
  for (const key of targetOrder) {
    const button = document.createElement('button');
    button.dataset.target = key;
    button.textContent = TARGETS[key].label || key;
    container.append(button);
  }
}

function renderToolButtons() {
  const toolButtons = document.querySelector('#toolButtons');
  const moveButtons = document.querySelector('#moveButtons');
  const actionButtons = document.querySelector('#actionButtons');
  const help = document.querySelector('#toolHelp');
  const tools = isMeshSelectionMode()
    ? [
        ['select', 'mouse-pointer-2', 'Select'],
        ['mesh', 'grid-2x2', 'Mesh'],
        ['vertex', 'circle-dot', 'Vertex'],
        ['deform', 'move', 'Arrow']
      ]
    : [
        ['select', 'mouse-pointer-2', 'Select'],
        ['point', 'plus', 'Point'],
        ['range', 'square', 'Range']
      ];
  toolButtons.classList.toggle('four', isMeshSelectionMode());
  toolButtons.innerHTML = tools.map(([value, icon, label]) => `<button data-tool="${value}"><i data-lucide="${icon}"></i>${label}</button>`).join('');
  if (isMeshSelectionMode()) {
    moveButtons.classList.add('hidden');
    moveButtons.innerHTML = '';
    actionButtons.classList.remove('hidden');
    actionButtons.innerHTML = '<button id="undoButton"><i data-lucide="undo-2"></i>Undo</button>';
    help.textContent = 'Mesh selects layer meshes. Vertex toggles vertices for the selected tag. Arrow drags deformation endpoints. Undo reverts the last arrow drag.';
  } else {
    moveButtons.classList.remove('hidden');
    actionButtons.classList.add('hidden');
    actionButtons.innerHTML = '';
    moveButtons.innerHTML = `
      <button data-move="free"><i data-lucide="move"></i>Free</button>
      <button data-move="snap"><i data-lucide="magnet"></i>Snap</button>
      <button id="axisToggle"><i data-lucide="lock"></i>Axis</button>
    `;
    help.textContent = 'Drag selected tags to move them. Drag range handles to resize. Hold Shift to lock movement to the dominant axis. Snap mode uses the current target mesh grid.';
  }
  bindToolButtons();
  updateUndoButton();
  createIcons({ icons: lucideIcons });
}

async function loadImage(src) {
  const img = new window.Image();
  img.decoding = 'async';
  img.src = src;
  await img.decode();
  return img;
}

async function boot() {
  await loadManifest();
  state.images.original = await loadImage(ASSETS.original);
  for (const [key, target] of Object.entries(TARGETS)) {
    if (target.image) state.images[key] = await loadImage(target.image);
  }
  for (const target of Object.values(TARGETS).filter((item) => item.depthUrl)) {
    if (!state.depthSources[target.depthUrl]) state.depthSources[target.depthUrl] = await fetchJson(target.depthUrl);
    state.depth[target.key] = getByJsonPath(state.depthSources[target.depthUrl], target.depthPath);
  }
  for (const target of Object.values(TARGETS).filter((item) => item.meshesUrl)) {
    if (!state.meshSources[target.meshesUrl]) state.meshSources[target.meshesUrl] = await fetchJson(target.meshesUrl);
    const source = target.meshesPointer ? resolvePointer(state.meshSources[target.meshesUrl], target.meshesPointer) : getByJsonPath(state.meshSources[target.meshesUrl], target.meshesPath);
    target.meshes = normalizeMeshes(source);
  }
  for (const target of Object.values(TARGETS).filter((item) => item.deformationsUrl)) {
    if (!state.meshSources[target.deformationsUrl]) state.meshSources[target.deformationsUrl] = await fetchJson(target.deformationsUrl);
    const source = target.deformationsPointer ? resolvePointer(state.meshSources[target.deformationsUrl], target.deformationsPointer) : getByJsonPath(state.meshSources[target.deformationsUrl], target.deformationsPath);
    state.deformations[target.key] = normalizeDeformations(source);
  }
  await loadLatestReview();
  bindUi();
  resize();
  render();
}

async function loadLatestReview() {
  try {
    const response = await fetch(`/api/review/latest?manifest=${encodeURIComponent(manifestUrl)}`);
    if (!response.ok) return;
    const review = await response.json();
    if (review.schema !== reviewSchema) return;
    if (Array.isArray(review.tags)) {
      state.tags = migrateReviewTags(review.tags);
      if (isMeshSelectionMode()) state.tags = state.tags.map(normalizeMeshTag);
    }
    if (review.deformations && isMeshSelectionMode()) {
      state.deformations = normalizeReviewDeformations(review.deformations);
    }
    if (typeof review.globalComment === 'string') state.globalComment = review.globalComment;
    if (review.reviewResult?.decision === 'ok' || review.reviewResult?.decision === 'retake') state.reviewDecision = review.reviewResult.decision;
    const target = migrateTargetKey(review.target, state.tags.find((tag) => tag.target === review.target)?.label);
    if (TARGETS[target]) state.target = target;
    const first = state.tags.find((tag) => tag.target === state.target) ?? state.tags[0];
    state.selectedId = first?.id ?? null;
  } catch {
    // The viewer is still usable when no previous review exists.
  }
}

function normalizeReviewDeformations(value) {
  const result = Object.create(null);
  if (!value || typeof value !== 'object') return result;
  for (const [targetKey, targetValue] of Object.entries(value)) {
    result[targetKey] = normalizeDeformations(targetValue);
  }
  return result;
}

function migrateTargetKey(target, label = '') {
  if (TARGETS[target]) return target;
  if (target === 'hair') {
    const hairTargets = targetOrder.filter((key) => /hair/i.test(key) || /hair/i.test(TARGETS[key].label));
    const back = hairTargets.find((key) => /back/i.test(key) || /back/i.test(TARGETS[key].label));
    const front = hairTargets.find((key) => /front/i.test(key) || /front/i.test(TARGETS[key].label));
    return /back/i.test(label) ? (back ?? hairTargets[0] ?? state.target) : (front ?? hairTargets[0] ?? state.target);
  }
  return state.target || targetOrder[0];
}

function migrateReviewTags(tags) {
  return tags.map((tag) => ({
    ...tag,
    target: migrateTargetKey(tag.target, tag.label)
  }));
}

function bindUi() {
  window.addEventListener('resize', resize);
  window.addEventListener('keydown', keyDown);
  document.querySelectorAll('[data-target]').forEach((button) => button.addEventListener('click', () => {
    state.target = button.dataset.target;
    const first = state.tags.find((tag) => tag.target === state.target);
    state.selectedId = first?.id ?? null;
    render();
  }));
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => {
    if (isMeshSelectionMode() && button.dataset.view === '3d') return;
    state.view = button.dataset.view;
    render();
  }));
  document.querySelectorAll('[data-image-mode]').forEach((button) => button.addEventListener('click', () => {
    state.imageMode = button.dataset.imageMode;
    render();
  }));
  document.querySelectorAll('[data-decision]').forEach((button) => button.addEventListener('click', async () => {
    state.reviewDecision = button.dataset.decision;
    render();
    await submitReview({ keepEditor: true });
  }));
  document.querySelector('#addTag').addEventListener('click', addTag);
  document.querySelector('#zoomOut').addEventListener('click', () => { state.zoom *= 0.85; render(); });
  document.querySelector('#zoomIn').addEventListener('click', () => { state.zoom *= 1.15; render(); });
  document.querySelector('#zoomReset').addEventListener('click', () => { state.zoom = 0.76; state.pan = { x: 70, y: 20 }; render(); });
  document.querySelector('#globalComment').addEventListener('input', (event) => { state.globalComment = event.target.value; });
  document.querySelector('#copyReview').addEventListener('click', copyReview);
  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointerleave', pointerUp);
  canvas.addEventListener('wheel', wheel, { passive: false });
  threeHost.addEventListener('pointerdown', threePointerDown);
  threeHost.addEventListener('pointermove', threePointerMove);
  threeHost.addEventListener('pointerup', () => { threeDrag = null; });
  threeHost.addEventListener('pointerleave', () => { threeDrag = null; });
}

function bindToolButtons() {
  document.querySelectorAll('[data-tool]').forEach((button) => button.addEventListener('click', () => {
    state.tool = button.dataset.tool;
    render();
  }));
  document.querySelectorAll('[data-move]').forEach((button) => button.addEventListener('click', () => {
    state.moveMode = button.dataset.move;
    state.snap = state.moveMode === 'snap';
    render();
  }));
  const axisToggle = document.querySelector('#axisToggle');
  if (axisToggle) {
    axisToggle.addEventListener('click', () => {
      state.axisLock = !state.axisLock;
      render();
    });
  }
  const undoButton = document.querySelector('#undoButton');
  if (undoButton) undoButton.addEventListener('click', undoLast);
}

function resize() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (renderer) {
    renderer.setSize(rect.width, rect.height);
    camera.aspect = rect.width / rect.height;
    camera.updateProjectionMatrix();
  }
  render();
}

function rasterMeshImage() {
  return state.images[state.target];
}

function imageToScreen(x, y) {
  return { x: state.pan.x + x * state.zoom, y: state.pan.y + y * state.zoom };
}

function screenToImage(x, y) {
  return { x: (x - state.pan.x) / state.zoom, y: (y - state.pan.y) / state.zoom };
}

function gridBounds(grid) {
  if (!grid) return { x: 0, y: 0, w: state.images.original?.width || 1, h: state.images.original?.height || 1 };
  return {
    x: grid.xs[0],
    y: grid.ys[0],
    w: grid.xs.at(-1) - grid.xs[0],
    h: grid.ys.at(-1) - grid.ys[0]
  };
}

function axisValue(values, n) {
  const scaled = clamp01(n) * (values.length - 1);
  const index = Math.min(values.length - 2, Math.max(0, Math.floor(scaled)));
  const t = scaled - index;
  return values[index] + (values[index + 1] - values[index]) * t;
}

function inverseAxisValue(values, value) {
  if (value <= values[0]) return 0;
  if (value >= values.at(-1)) return 1;
  for (let i = 0; i < values.length - 1; i++) {
    const a = values[i];
    const b = values[i + 1];
    if (value >= a && value <= b) return (i + (value - a) / (b - a)) / (values.length - 1);
  }
  return 0;
}

function gridToImage(targetKey, x, y) {
  const grid = TARGETS[targetKey].grid;
  if (!grid) return { x: x * (state.images.original?.width || 1), y: y * (state.images.original?.height || 1) };
  return { x: axisValue(grid.xs, x), y: axisValue(grid.ys, y) };
}

function imageToGrid(targetKey, point) {
  const grid = TARGETS[targetKey].grid;
  if (!grid) {
    return {
      x: clamp01(point.x / (state.images.original?.width || 1)),
      y: clamp01(point.y / (state.images.original?.height || 1))
    };
  }
  return {
    x: clamp01(inverseAxisValue(grid.xs, point.x)),
    y: clamp01(inverseAxisValue(grid.ys, point.y))
  };
}

function tagBounds(tag) {
  if (tag.kind === 'meshSet') return meshSetBounds(tag);
  if (tag.kind === 'point') {
    const p = gridToImage(tag.target, tag.point.x, tag.point.y);
    return {
      x: p.x,
      y: p.y,
      w: 0,
      h: 0
    };
  }
  const p = gridToImage(tag.target, tag.rect.x, tag.rect.y);
  const q = gridToImage(tag.target, tag.rect.x + tag.rect.w, tag.rect.y + tag.rect.h);
  return {
    x: p.x,
    y: p.y,
    w: q.x - p.x,
    h: q.y - p.y
  };
}

function meshSetBounds(tag) {
  const meshes = meshesForTag(tag);
  if (!meshes.length) return { x: 0, y: 0, w: 0, h: 0 };
  const bounds = meshes.map((item) => boundsForPoints(item.vertices.map((_, index) => deformedVertex(item.id, index, tag.target)).filter(Boolean))).filter(Boolean);
  const left = Math.min(...bounds.map((item) => item.x));
  const top = Math.min(...bounds.map((item) => item.y));
  const right = Math.max(...bounds.map((item) => item.x + item.w));
  const bottom = Math.max(...bounds.map((item) => item.y + item.h));
  return { x: left, y: top, w: right - left, h: bottom - top };
}

function meshesForTag(tag) {
  const ids = new Set(tag.meshIds || []);
  return (TARGETS[tag.target]?.meshes || []).filter((item) => ids.has(item.id));
}

function gridSnapImage(point, targetKey = state.target) {
  const grid = TARGETS[targetKey].grid;
  const normalized = imageToGrid(targetKey, point);
  const x = Math.round(normalized.x * (grid.cols - 1)) / (grid.cols - 1);
  const y = Math.round(normalized.y * (grid.rows - 1)) / (grid.rows - 1);
  return gridToImage(targetKey, x, y);
}

function render() {
  document.querySelectorAll('[data-target]').forEach((b) => b.classList.toggle('active', b.dataset.target === state.target));
  document.querySelectorAll('[data-view]').forEach((b) => b.classList.toggle('active', b.dataset.view === state.view));
  document.querySelectorAll('[data-image-mode]').forEach((b) => b.classList.toggle('active', b.dataset.imageMode === state.imageMode));
  document.querySelectorAll('[data-tool]').forEach((b) => b.classList.toggle('active', b.dataset.tool === state.tool));
  document.querySelectorAll('[data-move]').forEach((b) => b.classList.toggle('active', b.dataset.move === state.moveMode));
  document.querySelectorAll('[data-decision]').forEach((b) => b.classList.toggle('active', b.dataset.decision === state.reviewDecision));
  document.querySelector('#axisToggle')?.classList.toggle('active', state.axisLock);
  updateUndoButton();
  document.querySelector('#viewButtons').classList.toggle('hidden', isMeshSelectionMode());
  document.querySelector('#meshSection').classList.toggle('hidden', !isMeshSelectionMode());
  if (isMeshSelectionMode() && state.view === '3d') state.view = '2d';
  document.querySelector('#targetTitle').textContent = `${TARGETS[state.target].label} Review`;
  document.querySelector('#status').textContent = state.status;
  document.querySelector('#globalComment').value = state.globalComment;
  renderTagList();
  renderMeshList();
  renderEditor();
  if (state.view === '3d') {
    canvas.classList.add('hidden');
    threeHost.classList.remove('hidden');
    ensureThree();
    renderThree();
  } else {
    threeHost.classList.add('hidden');
    canvas.classList.remove('hidden');
    renderCanvas();
  }
}

function renderCanvas() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  const original = state.images.original;
  if (!original) return;
  ctx.imageSmoothingEnabled = true;
  const overlay = rasterMeshImage();
  if (state.imageMode === 'original') {
    ctx.drawImage(original, state.pan.x, state.pan.y, original.width * state.zoom, original.height * state.zoom);
  } else if (state.imageMode === 'overlay') {
    if (overlay) {
      ctx.drawImage(overlay, state.pan.x, state.pan.y, overlay.width * state.zoom, overlay.height * state.zoom);
    } else {
      ctx.drawImage(original, state.pan.x, state.pan.y, original.width * state.zoom, original.height * state.zoom);
    }
    if (isMeshSelectionMode()) drawLayerMeshes();
    else drawMeshGrid();
  } else if (state.imageMode === 'both') {
    ctx.globalAlpha = 1;
    ctx.drawImage(original, state.pan.x, state.pan.y, original.width * state.zoom, original.height * state.zoom);
    if (overlay) {
      ctx.globalAlpha = 0.58;
      ctx.drawImage(overlay, state.pan.x, state.pan.y, overlay.width * state.zoom, overlay.height * state.zoom);
    }
    ctx.globalAlpha = 1;
  }
  if (isMeshSelectionMode()) drawLayerMeshes();
  else drawMeshGrid();
  drawTags();
}

function drawMeshGrid() {
  if (!TARGETS[state.target]?.grid) return;
  drawImageSpaceGrid(ctx, state.target, {
    alpha: 0.9,
    lineWidth: 1,
    pointToCanvas: imageToScreen
  });
}

function drawLayerMeshes() {
  const target = TARGETS[state.target];
  if (!target?.meshes?.length) return;
  const selected = selectedTag();
  for (const layerMesh of target.meshes) {
    const included = selected?.meshIds?.includes(layerMesh.id);
    drawLayerMesh(layerMesh, {
      color: included ? (selected.color || target.color) : (layerMesh.color || target.color),
      alpha: included ? 0.95 : 0.38,
      fillAlpha: included ? 0.18 : 0.04,
      lineWidth: included ? 3 : 1
    });
  }
}

function drawLayerMesh(layerMesh, options = {}) {
  const color = options.color || TARGETS[state.target].color;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = options.lineWidth ?? 1;
  ctx.globalAlpha = options.alpha ?? 0.6;
  for (const triangle of layerMesh.triangles) {
    drawMeshPath(triangle.map((index) => deformedVertex(layerMesh.id, index)).filter(Boolean), options.fillAlpha ?? 0);
  }
  if (layerMesh.polygon.length) {
    drawMeshPath(layerMesh.polygon, options.fillAlpha ?? 0.08);
  } else if (!layerMesh.triangles.length && layerMesh.vertices.length) {
    drawMeshPath(layerMesh.vertices.map((_, index) => deformedVertex(layerMesh.id, index)), options.fillAlpha ?? 0.05);
  }
  const b = layerMesh.bounds;
  if (!layerMesh.vertices.length && b?.w && b?.h) {
    const p = imageToScreen(b.x, b.y);
    ctx.globalAlpha = options.fillAlpha ?? 0.08;
    ctx.fillRect(p.x, p.y, b.w * state.zoom, b.h * state.zoom);
    ctx.globalAlpha = options.alpha ?? 0.6;
    ctx.strokeRect(p.x, p.y, b.w * state.zoom, b.h * state.zoom);
  }
  ctx.restore();
}

function deformedVertex(meshId, vertexIndex, targetKey = state.target) {
  const layerMesh = meshById(targetKey, meshId);
  const point = layerMesh?.vertices?.[vertexIndex];
  if (!point) return null;
  const d = deformationFor(targetKey, meshId, vertexIndex);
  return { x: point.x + d.x, y: point.y + d.y };
}

function deformationFor(targetKey, meshId, vertexIndex) {
  return state.deformations[targetKey]?.[meshId]?.[vertexIndex] || { x: 0, y: 0 };
}

function setDeformation(targetKey, meshId, vertexIndex, next) {
  state.deformations[targetKey] ??= Object.create(null);
  state.deformations[targetKey][meshId] ??= Object.create(null);
  state.deformations[targetKey][meshId][vertexIndex] = {
    x: Number(next.x) || 0,
    y: Number(next.y) || 0
  };
}

function samePoint(a, b) {
  return Math.abs((a?.x || 0) - (b?.x || 0)) < 1e-6 && Math.abs((a?.y || 0) - (b?.y || 0)) < 1e-6;
}

function pushUndo(entry) {
  state.undoStack.push(entry);
  if (state.undoStack.length > 100) state.undoStack.shift();
  updateUndoButton();
}

function undoLast() {
  const entry = state.undoStack.pop();
  if (!entry) return;
  if (entry.type === 'deformation') {
    setDeformation(entry.targetKey, entry.meshId, entry.vertexIndex, entry.before);
    state.target = entry.targetKey;
    state.status = `Undid ${entry.meshId} #${entry.vertexIndex}`;
    render();
  }
}

function updateUndoButton() {
  const button = document.querySelector('#undoButton');
  if (!button) return;
  button.disabled = state.undoStack.length === 0;
  button.title = state.undoStack.length ? 'Undo last arrow drag' : 'No arrow edits to undo';
}

function meshById(targetKey, meshId) {
  return (TARGETS[targetKey]?.meshes || []).find((item) => item.id === meshId);
}

function drawMeshPath(points, fillAlpha) {
  if (!points.length) return;
  ctx.beginPath();
  for (const [index, point] of points.entries()) {
    const p = imageToScreen(point.x, point.y);
    if (index === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();
  if (fillAlpha > 0) {
    const alpha = ctx.globalAlpha;
    ctx.globalAlpha = fillAlpha;
    ctx.fill();
    ctx.globalAlpha = alpha;
  }
  ctx.stroke();
}

function drawImageSpaceGrid(targetCtx, targetKey, options = {}) {
  const grid = TARGETS[targetKey].grid;
  const pointToCanvas = options.pointToCanvas || ((x, y) => ({ x, y }));
  targetCtx.save();
  targetCtx.strokeStyle = TARGETS[targetKey].color;
  targetCtx.lineWidth = options.lineWidth ?? 1;
  targetCtx.globalAlpha = options.alpha ?? 0.9;
  for (let c = 0; c < grid.xs.length; c++) {
    targetCtx.beginPath();
    for (let r = 0; r < grid.ys.length; r++) {
      const s = pointToCanvas(grid.xs[c], grid.ys[r]);
      if (r === 0) targetCtx.moveTo(s.x, s.y);
      else targetCtx.lineTo(s.x, s.y);
    }
    targetCtx.stroke();
  }
  for (let r = 0; r < grid.ys.length; r++) {
    targetCtx.beginPath();
    for (let c = 0; c < grid.xs.length; c++) {
      const s = pointToCanvas(grid.xs[c], grid.ys[r]);
      if (c === 0) targetCtx.moveTo(s.x, s.y);
      else targetCtx.lineTo(s.x, s.y);
    }
    targetCtx.stroke();
  }
  targetCtx.restore();
}

function drawTags() {
  for (const tag of state.tags.filter((item) => item.target === state.target)) {
    const bounds = tagBounds(tag);
    const selected = tag.id === state.selectedId;
    ctx.save();
    ctx.strokeStyle = tag.color;
    ctx.fillStyle = tag.color;
    ctx.lineWidth = selected ? 3 : 2;
    if (tag.kind === 'meshSet') {
      for (const layerMesh of meshesForTag(tag)) {
        drawLayerMesh(layerMesh, {
          color: tag.color,
          alpha: selected ? 1 : 0.72,
          fillAlpha: selected ? 0.22 : 0.12,
          lineWidth: selected ? 3 : 2
        });
      }
      if (selected) drawMeshVertices(tag);
      const p = imageToScreen(bounds.x, bounds.y);
      ctx.fillStyle = '#fff';
      ctx.fillText(`${tag.label} (${tag.meshIds?.length || 0}/${tag.vertexRefs?.length || 0})`, p.x + 6, p.y - 8);
    } else if (tag.kind === 'point') {
      const p = imageToScreen(bounds.x, bounds.y);
      ctx.beginPath();
      ctx.arc(p.x, p.y, selected ? 8 : 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#111';
      ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.fillText(tag.label, p.x + 10, p.y - 10);
    } else {
      const p = imageToScreen(bounds.x, bounds.y);
      const q = imageToScreen(bounds.x + bounds.w, bounds.y + bounds.h);
      ctx.globalAlpha = selected ? 0.22 : 0.14;
      ctx.fillRect(p.x, p.y, q.x - p.x, q.y - p.y);
      ctx.globalAlpha = 1;
      ctx.strokeRect(p.x, p.y, q.x - p.x, q.y - p.y);
      ctx.fillStyle = '#fff';
      ctx.fillText(tag.label, p.x + 6, p.y - 8);
      if (selected) drawResizeHandles(tag);
    }
    ctx.restore();
  }
}

function drawMeshVertices(tag) {
  const selectedKeys = new Set((tag.vertexRefs || []).map(vertexRefKey));
  ctx.save();
  for (const layerMesh of meshesForTag(tag)) {
    for (const [index, point] of layerMesh.vertices.entries()) {
      const d = deformationFor(tag.target, layerMesh.id, index);
      const p = imageToScreen(point.x, point.y);
      const q = imageToScreen(point.x + d.x, point.y + d.y);
      const selected = selectedKeys.has(vertexRefKey({ meshId: layerMesh.id, vertexIndex: index }));
      if (d.x || d.y) {
        drawDeformArrow(p, q, selected);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = selected ? '#ffef6a' : '#101010';
      ctx.strokeStyle = selected ? '#111111' : '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(q.x, q.y, selected ? 6 : 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawDeformArrow(from, to, selected) {
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  const head = Math.min(14, Math.max(7, length * 0.32));
  ctx.save();
  ctx.strokeStyle = selected ? '#ffef6a' : '#ffffff';
  ctx.fillStyle = selected ? '#ffef6a' : '#ffffff';
  ctx.globalAlpha = selected ? 0.98 : 0.72;
  ctx.lineWidth = selected ? 2.5 : 1.5;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  if (length > 2) {
    ctx.beginPath();
    ctx.moveTo(to.x, to.y);
    ctx.lineTo(to.x - head * Math.cos(angle - Math.PI / 6), to.y - head * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(to.x - head * Math.cos(angle + Math.PI / 6), to.y - head * Math.sin(angle + Math.PI / 6));
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();
}

function vertexRefKey(ref) {
  return `${ref.meshId}:${ref.vertexIndex}`;
}

function encodeRef(meshId, vertexIndex) {
  return `${encodeURIComponent(meshId)}:${vertexIndex}`;
}

function decodeRef(value) {
  const separator = value.lastIndexOf(':');
  return {
    meshId: decodeURIComponent(value.slice(0, separator)),
    vertexIndex: Number(value.slice(separator + 1)) || 0
  };
}

function drawResizeHandles(tag) {
  ctx.save();
  for (const handle of resizeHandles(tag)) {
    const p = imageToScreen(handle.x, handle.y);
    ctx.fillStyle = '#111';
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.rect(p.x - 5, p.y - 5, 10, 10);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

function renderTagList() {
  const list = document.querySelector('#tagList');
  list.innerHTML = '';
  for (const tag of state.tags.filter((item) => item.target === state.target)) {
    const row = document.createElement('button');
    row.className = `tag-item ${tag.id === state.selectedId ? 'selected' : ''}`;
    const meshCount = tag.kind === 'meshSet' ? ` · ${tag.meshIds?.length || 0} meshes` : '';
    row.innerHTML = `<span class="swatch" style="background:${safeColor(tag.color)}"></span><span><span class="tag-name">${escapeHtml(tag.label)}</span><br><span class="tag-kind">${escapeHtml(tag.kind)}${meshCount}</span></span><span>›</span>`;
    row.addEventListener('click', () => { state.selectedId = tag.id; render(); });
    list.append(row);
  }
}

function renderMeshList() {
  const list = document.querySelector('#meshList');
  list.innerHTML = '';
  if (!isMeshSelectionMode()) return;
  const tag = selectedTag();
  for (const layerMesh of TARGETS[state.target]?.meshes || []) {
    const row = document.createElement('button');
    const included = tag?.meshIds?.includes(layerMesh.id);
    row.className = `mesh-item ${included ? 'selected' : ''}`;
    row.innerHTML = `<span class="swatch" style="background:${safeColor(layerMesh.color || TARGETS[state.target].color)}"></span><span>${escapeHtml(layerMesh.label)}</span><span>${included ? 'on' : ''}</span>`;
    row.addEventListener('click', () => toggleMeshOnSelectedTag(layerMesh.id));
    list.append(row);
  }
}

function setMeshOnTag(tag, meshId, enabled) {
  const ids = new Set(tag.meshIds || []);
  if (enabled) ids.add(meshId);
  else ids.delete(meshId);
  tag.meshIds = [...ids];
}

function toggleMeshOnSelectedTag(meshId) {
  const tag = selectedTag();
  if (!tag || tag.target !== state.target || tag.kind !== 'meshSet') return;
  const enabled = !tag.meshIds.includes(meshId);
  setMeshOnTag(tag, meshId, enabled);
  refreshAnnotations();
  renderEditor();
}

function toggleVertexOnSelectedTag(meshId, vertexIndex) {
  const tag = selectedTag();
  if (!tag || tag.target !== state.target || tag.kind !== 'meshSet') return;
  if (!tag.meshIds.includes(meshId)) setMeshOnTag(tag, meshId, true);
  const key = vertexRefKey({ meshId, vertexIndex });
  const refs = tag.vertexRefs || [];
  if (refs.some((ref) => vertexRefKey(ref) === key)) {
    tag.vertexRefs = refs.filter((ref) => vertexRefKey(ref) !== key);
  } else {
    tag.vertexRefs = [...refs, { meshId, vertexIndex }];
  }
  refreshAnnotations();
  renderEditor();
}

function removeVertexFromSelectedTag(meshId, vertexIndex) {
  const tag = selectedTag();
  if (!tag || tag.kind !== 'meshSet') return;
  const key = vertexRefKey({ meshId, vertexIndex });
  tag.vertexRefs = (tag.vertexRefs || []).filter((ref) => vertexRefKey(ref) !== key);
  refreshAnnotations();
  renderEditor();
}

function hitMeshVertex(pos, options = {}) {
  const tag = selectedTag();
  const meshIds = new Set(tag?.meshIds || []);
  const selectedKeys = new Set((tag?.vertexRefs || []).map(vertexRefKey));
  const meshes = [...(TARGETS[state.target]?.meshes || [])].filter((item) => meshIds.has(item.id)).reverse();
  const radius = 10 / state.zoom;
  let nearest = null;
  for (const layerMesh of meshes) {
    for (const [index] of layerMesh.vertices.entries()) {
      if (options.selectedOnly && !selectedKeys.has(vertexRefKey({ meshId: layerMesh.id, vertexIndex: index }))) continue;
      const point = deformedVertex(layerMesh.id, index);
      if (!point) continue;
      const distance = Math.hypot(pos.x - point.x, pos.y - point.y);
      if (distance <= radius && (!nearest || distance < nearest.distance)) nearest = { meshId: layerMesh.id, vertexIndex: index, distance };
    }
  }
  return nearest;
}

function hitLayerMesh(pos) {
  const meshes = [...(TARGETS[state.target]?.meshes || [])].reverse();
  for (const layerMesh of meshes) {
    if (pointInLayerMesh(pos, layerMesh)) return layerMesh;
  }
  return null;
}

function pointInLayerMesh(pos, layerMesh) {
  if (layerMesh.polygon.length && pointInPolygon(pos, layerMesh.polygon)) return true;
  for (const triangle of layerMesh.triangles) {
    const points = triangle.map((index) => layerMesh.vertices[index]).filter(Boolean);
    if (points.length >= 3 && pointInPolygon(pos, points)) return true;
  }
  const b = layerMesh.bounds;
  return Boolean(b && pos.x >= b.x && pos.x <= b.x + b.w && pos.y >= b.y && pos.y <= b.y + b.h);
}

function pointInPolygon(pos, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const a = points[i];
    const b = points[j];
    const intersects = ((a.y > pos.y) !== (b.y > pos.y)) && (pos.x < ((b.x - a.x) * (pos.y - a.y)) / ((b.y - a.y) || 1e-9) + a.x);
    if (intersects) inside = !inside;
  }
  return inside;
}

function renderEditor() {
  const editor = document.querySelector('#editor');
  const tag = selectedTag();
  if (!tag) {
    editor.innerHTML = '<p class="small">No tag selected.</p>';
    return;
  }
  if (tag.kind === 'meshSet') {
    renderMeshTagEditor(editor, tag);
    return;
  }
  const rect = tag.kind === 'range' ? tag.rect : null;
  const point = tag.kind === 'point' ? tag.point : null;
  editor.innerHTML = `
    <div class="field"><label>Label<input id="tagLabel" value="${escapeAttr(tag.label)}"></label></div>
    <div class="row">
      <label>Kind<select id="tagKind"><option value="point">point</option><option value="range">range</option></select></label>
      <label>Color<input id="tagColor" type="color" value="${safeColor(tag.color)}"></label>
    </div>
    <div class="range-grid">
      <label>X<input id="tagX" type="number" min="0" max="1" step="0.001" value="${(point?.x ?? rect.x).toFixed(3)}"></label>
      <label>Y<input id="tagY" type="number" min="0" max="1" step="0.001" value="${(point?.y ?? rect.y).toFixed(3)}"></label>
      <label class="${tag.kind === 'point' ? 'hidden' : ''}">W<input id="tagW" type="number" min="0" max="1" step="0.001" value="${(rect?.w ?? 0).toFixed(3)}"></label>
      <label class="${tag.kind === 'point' ? 'hidden' : ''}">H<input id="tagH" type="number" min="0" max="1" step="0.001" value="${(rect?.h ?? 0).toFixed(3)}"></label>
    </div>
    <label>Comment<textarea id="tagComment">${escapeHtml(tag.comment || '')}</textarea></label>
    <button id="deleteTag" class="danger"><i data-lucide="trash-2"></i>Delete</button>
  `;
  editor.querySelector('#tagKind').value = tag.kind;
  editor.querySelector('#tagLabel').addEventListener('input', (e) => {
    tag.label = e.target.value;
    refreshAnnotations();
  });
  editor.querySelector('#tagKind').addEventListener('change', (e) => {
    if (e.target.value === tag.kind) return;
    if (e.target.value === 'point') {
      const b = tag.kind === 'range' ? { x: tag.rect.x + tag.rect.w / 2, y: tag.rect.y + tag.rect.h / 2 } : tag.point;
      tag.kind = 'point';
      tag.point = b;
      delete tag.rect;
    } else {
      const p = tag.point ?? { x: 0.5, y: 0.5 };
      tag.kind = 'range';
      tag.rect = { x: clamp01(p.x - 0.06), y: clamp01(p.y - 0.04), w: 0.12, h: 0.08 };
      delete tag.point;
    }
    render();
  });
  editor.querySelector('#tagColor').addEventListener('input', (e) => {
    tag.color = e.target.value;
    refreshAnnotations();
  });
  ['X', 'Y', 'W', 'H'].forEach((key) => {
    const input = editor.querySelector(`#tag${key}`);
    if (!input) return;
    input.addEventListener('input', () => {
      const value = clamp01(Number(input.value));
      if (tag.kind === 'point') {
        if (key === 'X') tag.point.x = value;
        if (key === 'Y') tag.point.y = value;
      } else {
        const prop = key.toLowerCase();
        tag.rect[prop] = value;
      }
      refreshAnnotations();
    });
  });
  editor.querySelector('#tagComment').addEventListener('input', (e) => { tag.comment = e.target.value; });
  editor.querySelector('#deleteTag').addEventListener('click', () => {
    state.tags = state.tags.filter((item) => item.id !== tag.id);
    state.selectedId = state.tags.find((item) => item.target === state.target)?.id ?? null;
    render();
  });
  createIcons({ icons: lucideIcons });
}

function renderMeshTagEditor(editor, tag) {
  const meshes = TARGETS[tag.target]?.meshes || [];
  const vertexRows = meshes.filter((layerMesh) => tag.meshIds.includes(layerMesh.id)).flatMap((layerMesh) => layerMesh.vertices.map((point, vertexIndex) => {
    const selected = (tag.vertexRefs || []).some((ref) => ref.meshId === layerMesh.id && ref.vertexIndex === vertexIndex);
    const d = deformationFor(tag.target, layerMesh.id, vertexIndex);
    return { layerMesh, point, vertexIndex, selected, d };
  }));
  editor.innerHTML = `
    <div class="field"><label>Label<input id="tagLabel" value="${escapeAttr(tag.label)}"></label></div>
    <div class="row">
      <label>Kind<input value="meshSet" disabled></label>
      <label>Color<input id="tagColor" type="color" value="${safeColor(tag.color)}"></label>
    </div>
    <div class="mesh-checks">
      ${meshes.map((layerMesh) => `
        <label class="mesh-check">
          <input type="checkbox" data-mesh-id="${escapeAttr(layerMesh.id)}" ${tag.meshIds.includes(layerMesh.id) ? 'checked' : ''}>
          <span>${escapeHtml(layerMesh.label)}</span>
        </label>
      `).join('')}
    </div>
    <div class="section-title collapsible-title">
      <button id="toggleVertices" class="icon-button"><i data-lucide="${state.verticesExpanded ? 'chevron-down' : 'chevron-right'}"></i></button>
      <span>Vertices (${vertexRows.filter((row) => row.selected).length}/${vertexRows.length})</span>
    </div>
    <div class="vertex-list ${state.verticesExpanded ? '' : 'hidden'}">
      ${vertexRows.map(renderVertexRow).join('') || '<p class="small">Select one or more meshes, then choose vertices.</p>'}
    </div>
    <label>Comment<textarea id="tagComment">${escapeHtml(tag.comment || '')}</textarea></label>
    <button id="deleteTag" class="danger"><i data-lucide="trash-2"></i>Delete</button>
  `;
  editor.querySelector('#tagLabel').addEventListener('input', (e) => {
    tag.label = e.target.value;
    refreshAnnotations();
  });
  editor.querySelector('#tagColor').addEventListener('input', (e) => {
    tag.color = e.target.value;
    refreshAnnotations();
  });
  editor.querySelectorAll('[data-mesh-id]').forEach((input) => {
    input.addEventListener('change', () => {
      setMeshOnTag(tag, input.dataset.meshId, input.checked);
      refreshAnnotations();
      renderEditor();
    });
  });
  editor.querySelector('#toggleVertices').addEventListener('click', () => {
    state.verticesExpanded = !state.verticesExpanded;
    renderEditor();
  });
  editor.querySelectorAll('[data-vertex-pick]').forEach((input) => {
    input.addEventListener('change', () => {
      const { meshId, vertexIndex } = decodeRef(input.dataset.vertexPick);
      toggleVertexOnSelectedTag(meshId, vertexIndex);
    });
  });
  editor.querySelectorAll('[data-deform-x], [data-deform-y]').forEach((input) => {
    input.addEventListener('input', () => {
      const ref = input.dataset.deformX || input.dataset.deformY;
      const { meshId, vertexIndex } = decodeRef(ref);
      const current = deformationFor(tag.target, meshId, vertexIndex);
      setDeformation(tag.target, meshId, vertexIndex, {
        x: input.dataset.deformX ? Number(input.value) : current.x,
        y: input.dataset.deformY ? Number(input.value) : current.y
      });
      refreshAnnotations();
    });
  });
  editor.querySelectorAll('[data-remove-vertex]').forEach((button) => {
    button.addEventListener('click', () => {
      const { meshId, vertexIndex } = decodeRef(button.dataset.removeVertex);
      removeVertexFromSelectedTag(meshId, vertexIndex);
    });
  });
  editor.querySelector('#tagComment').addEventListener('input', (e) => { tag.comment = e.target.value; });
  editor.querySelector('#deleteTag').addEventListener('click', () => {
    state.tags = state.tags.filter((item) => item.id !== tag.id);
    state.selectedId = state.tags.find((item) => item.target === state.target)?.id ?? null;
    render();
  });
  createIcons({ icons: lucideIcons });
}

function renderVertexRow({ layerMesh, point, vertexIndex, selected, d }) {
  return `
    <div class="vertex-row ${selected ? 'selected' : ''}">
      <label class="vertex-pick">
        <input type="checkbox" data-vertex-pick="${escapeAttr(encodeRef(layerMesh.id, vertexIndex))}" ${selected ? 'checked' : ''}>
        <span>${escapeHtml(layerMesh.label)} #${vertexIndex}</span>
      </label>
      <span class="vertex-pos">${Math.round(point.x)}, ${Math.round(point.y)}</span>
      <label>dx<input type="number" step="1" data-deform-x="${escapeAttr(encodeRef(layerMesh.id, vertexIndex))}" value="${Number(d.x).toFixed(0)}"></label>
      <label>dy<input type="number" step="1" data-deform-y="${escapeAttr(encodeRef(layerMesh.id, vertexIndex))}" value="${Number(d.y).toFixed(0)}"></label>
      <button data-remove-vertex="${escapeAttr(encodeRef(layerMesh.id, vertexIndex))}" class="${selected ? '' : 'hidden'}"><i data-lucide="x"></i></button>
    </div>
  `;
}

function refreshAnnotations() {
  renderTagList();
  renderMeshList();
  if (state.view === '3d') renderThree();
  else renderCanvas();
}

function selectedTag() {
  return state.tags.find((tag) => tag.id === state.selectedId);
}

function ensureMeshTag() {
  let tag = selectedTag();
  if (tag?.target === state.target && tag.kind === 'meshSet') return tag;
  tag = state.tags.find((item) => item.target === state.target && item.kind === 'meshSet');
  if (tag) {
    state.selectedId = tag.id;
    return tag;
  }
  tag = {
    id: crypto.randomUUID(),
    target: state.target,
    kind: 'meshSet',
    label: 'new mesh tag',
    color: TARGETS[state.target]?.color || '#d4e157',
    comment: '',
    meshIds: [],
    vertexRefs: []
  };
  state.tags.push(tag);
  state.selectedId = tag.id;
  return tag;
}

function addTag() {
  if (isMeshSelectionMode()) {
    const tag = {
      id: crypto.randomUUID(),
      target: state.target,
      kind: 'meshSet',
      label: 'new mesh tag',
      color: TARGETS[state.target]?.color || '#d4e157',
      comment: '',
      meshIds: [],
      vertexRefs: []
    };
    state.tags.push(tag);
    state.selectedId = tag.id;
    render();
    return;
  }
  const tag = {
    id: crypto.randomUUID(),
    target: state.target,
    kind: state.tool === 'point' ? 'point' : 'range',
    label: `new ${state.tool === 'point' ? 'point' : 'range'}`,
    color: '#d4e157',
    comment: ''
  };
  if (tag.kind === 'point') tag.point = { x: 0.5, y: 0.5 };
  else tag.rect = { x: 0.42, y: 0.42, w: 0.16, h: 0.14 };
  state.tags.push(tag);
  state.selectedId = tag.id;
  render();
}

function pointerDown(event) {
  const pos = screenToImage(event.offsetX, event.offsetY);
  if (isMeshSelectionMode()) {
    meshPointerDown(event, pos);
    return;
  }
  if (state.tool === 'point' || state.tool === 'range') {
    const local = imageToGrid(state.target, pos);
    const tag = {
      id: crypto.randomUUID(),
      target: state.target,
      kind: state.tool,
      label: state.tool === 'point' ? 'new point' : 'new range',
      color: state.tool === 'point' ? '#ff8c6b' : '#d4e157',
      comment: ''
    };
    if (state.tool === 'point') tag.point = local;
    else tag.rect = { x: local.x, y: local.y, w: 0.14, h: 0.1 };
    state.tags.push(tag);
    state.selectedId = tag.id;
    state.tool = 'select';
    render();
    return;
  }

  const resizeHandle = hitResizeHandle(pos);
  if (resizeHandle) {
    state.selectedId = resizeHandle.tag.id;
    state.drag = {
      tagId: resizeHandle.tag.id,
      start: pos,
      original: structuredClone(resizeHandle.tag),
      resizeHandle: resizeHandle.name,
      axis: null
    };
    canvas.classList.add('dragging');
    render();
    return;
  }

  const hit = hitTag(pos);
  if (hit) {
    state.selectedId = hit.id;
    const b = tagBounds(hit);
    state.drag = { tagId: hit.id, start: pos, original: structuredClone(hit), bounds: b, axis: null };
    canvas.classList.add('dragging');
    render();
  } else {
    state.drag = { pan: true, startScreen: { x: event.offsetX, y: event.offsetY }, originalPan: { ...state.pan } };
    canvas.classList.add('dragging');
  }
}

function meshPointerDown(event, pos) {
  ensureMeshTag();
  if (state.tool === 'mesh') {
    const hitMesh = hitLayerMesh(pos);
    if (hitMesh) {
      toggleMeshOnSelectedTag(hitMesh.id);
      return;
    }
  } else if (state.tool === 'vertex') {
    const hitVertex = hitMeshVertex(pos, { selectedOnly: false });
    if (hitVertex) {
      toggleVertexOnSelectedTag(hitVertex.meshId, hitVertex.vertexIndex);
      return;
    }
  } else if (state.tool === 'deform') {
    const hitVertex = hitMeshVertex(pos, { selectedOnly: true });
    if (hitVertex) {
      state.drag = {
        deform: true,
        start: pos,
        targetKey: state.target,
        meshId: hitVertex.meshId,
        vertexIndex: hitVertex.vertexIndex,
        original: { ...deformationFor(state.target, hitVertex.meshId, hitVertex.vertexIndex) }
      };
      canvas.classList.add('dragging');
      return;
    }
  } else {
    const hitMesh = hitLayerMesh(pos);
    if (hitMesh) refreshAnnotations();
  }
  state.drag = { pan: true, startScreen: { x: event.offsetX, y: event.offsetY }, originalPan: { ...state.pan } };
  canvas.classList.add('dragging');
}

function pointerMove(event) {
  const imagePos = screenToImage(event.offsetX, event.offsetY);
  document.querySelector('#coordReadout').textContent = `x ${Math.round(imagePos.x)} y ${Math.round(imagePos.y)}`;
  if (!state.drag) {
    if (isMeshSelectionMode()) {
      const canEditArrow = state.tool === 'deform' && hitMeshVertex(imagePos, { selectedOnly: true });
      const canPickVertex = state.tool === 'vertex' && hitMeshVertex(imagePos, { selectedOnly: false });
      const canPickMesh = state.tool === 'mesh' && hitLayerMesh(imagePos);
      canvas.style.cursor = canEditArrow ? 'crosshair' : (canPickVertex || canPickMesh ? 'pointer' : 'grab');
      return;
    }
    const handle = hitResizeHandle(imagePos);
    canvas.style.cursor = handle ? cursorForHandle(handle.name) : 'grab';
    return;
  }
  if (!state.drag) return;
  if (state.drag.pan) {
    state.pan.x = state.drag.originalPan.x + event.offsetX - state.drag.startScreen.x;
    state.pan.y = state.drag.originalPan.y + event.offsetY - state.drag.startScreen.y;
    renderCanvas();
    return;
  }
  if (state.drag.deform) {
    setDeformation(state.drag.targetKey, state.drag.meshId, state.drag.vertexIndex, {
      x: state.drag.original.x + imagePos.x - state.drag.start.x,
      y: state.drag.original.y + imagePos.y - state.drag.start.y
    });
    renderCanvas();
    return;
  }
  const tag = state.tags.find((item) => item.id === state.drag.tagId);
  if (!tag) return;
  let dx = imagePos.x - state.drag.start.x;
  let dy = imagePos.y - state.drag.start.y;
  if (event.shiftKey || state.axisLock) {
    if (!state.drag.axis) state.drag.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
    if (state.drag.axis === 'x') dy = 0;
    else dx = 0;
  }
  if (state.drag.resizeHandle) resizeRangeTag(tag, state.drag.original, dx, dy, state.drag.resizeHandle);
  else moveTag(tag, state.drag.original, dx, dy);
  renderCanvas();
  renderEditor();
}

function pointerUp() {
  const deformDrag = state.drag?.deform ? { ...state.drag } : null;
  if (deformDrag) {
    const after = { ...deformationFor(deformDrag.targetKey, deformDrag.meshId, deformDrag.vertexIndex) };
    if (!samePoint(deformDrag.original, after)) {
      pushUndo({
        type: 'deformation',
        targetKey: deformDrag.targetKey,
        meshId: deformDrag.meshId,
        vertexIndex: deformDrag.vertexIndex,
        before: deformDrag.original,
        after
      });
    }
  }
  const updateEditor = Boolean(deformDrag);
  state.drag = null;
  canvas.classList.remove('dragging');
  canvas.style.cursor = 'grab';
  if (updateEditor) renderEditor();
}

function keyDown(event) {
  const target = event.target;
  const isEditingText = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
  if (isEditingText) return;
  if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    undoLast();
  }
}

function wheel(event) {
  event.preventDefault();
  const before = screenToImage(event.offsetX, event.offsetY);
  const factor = event.deltaY < 0 ? 1.08 : 0.92;
  state.zoom = Math.max(0.18, Math.min(4, state.zoom * factor));
  const after = screenToImage(event.offsetX, event.offsetY);
  state.pan.x += (after.x - before.x) * state.zoom;
  state.pan.y += (after.y - before.y) * state.zoom;
  renderCanvas();
}

function moveTag(tag, original, dx, dy) {
  if (tag.kind === 'point') {
    const p = gridToImage(tag.target, original.point.x, original.point.y);
    let x = p.x + dx;
    let y = p.y + dy;
    if (state.snap || state.moveMode === 'snap') ({ x, y } = gridSnapImage({ x, y }, tag.target));
    tag.point = imageToGrid(tag.target, { x, y });
  } else {
    const p = gridToImage(tag.target, original.rect.x, original.rect.y);
    let x = p.x + dx;
    let y = p.y + dy;
    if (state.snap || state.moveMode === 'snap') ({ x, y } = gridSnapImage({ x, y }, tag.target));
    const next = imageToGrid(tag.target, { x, y });
    tag.rect.x = Math.min(next.x, 1 - tag.rect.w);
    tag.rect.y = Math.min(next.y, 1 - tag.rect.h);
  }
}

function resizeHandles(tag) {
  if (!tag || tag.kind !== 'range') return [];
  const b = tagBounds(tag);
  const left = b.x;
  const top = b.y;
  const right = b.x + b.w;
  const bottom = b.y + b.h;
  const cx = (left + right) / 2;
  const cy = (top + bottom) / 2;
  return [
    { name: 'nw', x: left, y: top },
    { name: 'n', x: cx, y: top },
    { name: 'ne', x: right, y: top },
    { name: 'e', x: right, y: cy },
    { name: 'se', x: right, y: bottom },
    { name: 's', x: cx, y: bottom },
    { name: 'sw', x: left, y: bottom },
    { name: 'w', x: left, y: cy }
  ];
}

function hitResizeHandle(pos) {
  const tag = selectedTag();
  if (!tag || tag.target !== state.target || tag.kind !== 'range') return null;
  const radius = 9 / state.zoom;
  let nearest = null;
  for (const handle of resizeHandles(tag)) {
    const dx = pos.x - handle.x;
    const dy = pos.y - handle.y;
    const distance = Math.hypot(dx, dy);
    if (Math.abs(dx) <= radius && Math.abs(dy) <= radius && distance <= radius * 1.35) {
      if (!nearest || distance < nearest.distance) nearest = { tag, name: handle.name, distance };
    }
  }
  return nearest;
}

function resizeRangeTag(tag, original, dx, dy, handle) {
  let left = original.rect.x;
  let top = original.rect.y;
  let right = original.rect.x + original.rect.w;
  let bottom = original.rect.y + original.rect.h;

  if (handle.includes('w') || handle.includes('n')) {
    const p = gridToImage(tag.target, left, top);
    const next = imageToGrid(tag.target, { x: p.x + (handle.includes('w') ? dx : 0), y: p.y + (handle.includes('n') ? dy : 0) });
    if (handle.includes('w')) left = next.x;
    if (handle.includes('n')) top = next.y;
  }
  if (handle.includes('e') || handle.includes('s')) {
    const p = gridToImage(tag.target, right, bottom);
    const next = imageToGrid(tag.target, { x: p.x + (handle.includes('e') ? dx : 0), y: p.y + (handle.includes('s') ? dy : 0) });
    if (handle.includes('e')) right = next.x;
    if (handle.includes('s')) bottom = next.y;
  }

  if (state.snap || state.moveMode === 'snap') {
    const grid = TARGETS[tag.target].grid;
    if (handle.includes('w')) left = Math.round(left * (grid.cols - 1)) / (grid.cols - 1);
    if (handle.includes('e')) right = Math.round(right * (grid.cols - 1)) / (grid.cols - 1);
    if (handle.includes('n')) top = Math.round(top * (grid.rows - 1)) / (grid.rows - 1);
    if (handle.includes('s')) bottom = Math.round(bottom * (grid.rows - 1)) / (grid.rows - 1);
  }

  left = Math.max(0, Math.min(left, 1 - minRangeSize));
  right = Math.max(minRangeSize, Math.min(right, 1));
  top = Math.max(0, Math.min(top, 1 - minRangeSize));
  bottom = Math.max(minRangeSize, Math.min(bottom, 1));

  if (right - left < minRangeSize) {
    if (handle.includes('w')) left = right - minRangeSize;
    else right = left + minRangeSize;
  }
  if (bottom - top < minRangeSize) {
    if (handle.includes('n')) top = bottom - minRangeSize;
    else bottom = top + minRangeSize;
  }

  tag.rect.x = clamp01(left);
  tag.rect.y = clamp01(top);
  tag.rect.w = clamp01(right - left);
  tag.rect.h = clamp01(bottom - top);
}

function cursorForHandle(handle) {
  if (handle === 'n' || handle === 's') return 'ns-resize';
  if (handle === 'e' || handle === 'w') return 'ew-resize';
  if (handle === 'nw' || handle === 'se') return 'nwse-resize';
  if (handle === 'ne' || handle === 'sw') return 'nesw-resize';
  return 'grab';
}

function hitTag(pos) {
  const tags = state.tags.filter((tag) => tag.target === state.target).toReversed();
  for (const tag of tags) {
    const b = tagBounds(tag);
    if (tag.kind === 'point') {
      if (Math.hypot(pos.x - b.x, pos.y - b.y) < 18 / state.zoom) return tag;
    } else if (pos.x >= b.x && pos.x <= b.x + b.w && pos.y >= b.y && pos.y <= b.y + b.h) {
      return tag;
    }
  }
  return null;
}

function ensureThree() {
  if (isThreeReady) return;
  const rect = threeHost.getBoundingClientRect();
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(rect.width, rect.height);
  threeHost.append(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, rect.width / rect.height, 0.1, 100);
  camera.position.set(0, 0, 4.2);
  scene.add(new THREE.AmbientLight(0xffffff, 1));
  const light = new THREE.DirectionalLight(0xffffff, 1.4);
  light.position.set(1, 1, 2);
  scene.add(light);
  originalTexture = new THREE.Texture(state.images.original);
  originalTexture.colorSpace = THREE.SRGBColorSpace;
  originalTexture.minFilter = THREE.LinearFilter;
  originalTexture.magFilter = THREE.LinearFilter;
  originalTexture.needsUpdate = true;
  isThreeReady = true;
}

function makeDepthGrid() {
  return state.depth[state.target];
}

function renderThree() {
  ensureThree();
  if (mesh) {
    scene.remove(mesh);
    scene.remove(wire);
  }
  const zGrid = makeDepthGrid();
  const rows = zGrid.length;
  const cols = zGrid[0].length;
  const targetBounds = gridBounds(TARGETS[state.target].grid);
  const aspect = targetBounds.h / Math.max(1, targetBounds.w);
  const planeH = aspect >= 1 ? 2.75 : 2.75 * aspect;
  const planeW = aspect >= 1 ? 2.75 / aspect : 2.75;
  const geo = new THREE.PlaneGeometry(planeW, planeH, cols - 1, rows - 1);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  let k = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const z = zGrid[r][c] * 0.26;
      const artPoint = gridToImage(state.target, c / (cols - 1), r / (rows - 1));
      uv.setXY(k, artPoint.x / state.images.original.width, 1 - artPoint.y / state.images.original.height);
      pos.setZ(k++, z);
    }
  }
  pos.needsUpdate = true;
  uv.needsUpdate = true;
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({
    map: originalTexture,
    color: 0xffffff,
    roughness: 0.62,
    metalness: 0.02,
    side: THREE.DoubleSide
  });
  mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = threeRotation.x;
  mesh.rotation.y = threeRotation.y;
  wire = new THREE.LineSegments(new THREE.WireframeGeometry(geo), new THREE.LineBasicMaterial({ color: 0x101010, transparent: true, opacity: 0.55 }));
  wire.rotation.copy(mesh.rotation);
  scene.add(mesh);
  scene.add(wire);
  renderer.render(scene, camera);
}

function threePointerDown(event) {
  threeDrag = { x: event.clientX, y: event.clientY, rx: threeRotation.x, ry: threeRotation.y };
}

function threePointerMove(event) {
  if (!threeDrag) return;
  threeRotation.y = threeDrag.ry + (event.clientX - threeDrag.x) * 0.01;
  threeRotation.x = threeDrag.rx + (event.clientY - threeDrag.y) * 0.01;
  renderThree();
}

function reviewPayload() {
  const payload = {
    schema: reviewSchema,
    createdAt: new Date().toISOString(),
    mode: viewerMode,
    manifest: {
      url: manifestUrl,
      schema: manifest.schema,
      model: manifest.model
    },
    target: state.target,
    reviewResult: {
      decision: state.reviewDecision,
      nextAction: state.reviewDecision === 'ok' ? 'proceed' : 'retake',
      source: 'review-viewer'
    },
    globalComment: state.globalComment,
    tags: state.tags.map((tag) => ({ ...tag })),
    assets: {
      original: ASSETS.original,
      overlays: Object.fromEntries(Object.entries(TARGETS).filter(([, target]) => target.image).map(([key, target]) => [key, target.image]))
    }
  };
  if (isMeshSelectionMode()) {
    payload.meshes = Object.fromEntries(Object.entries(TARGETS).map(([key, target]) => [key, {
      source: target.meshesUrl || null,
      items: target.meshes || []
    }]));
    payload.deformations = state.deformations;
  } else {
    payload.gridCalibration = gridCalibration;
    payload.depthMaps = Object.fromEntries(Object.entries(state.depthSources).map(([url, data]) => [url, data]));
  }
  return payload;
}

async function submitReview(options = {}) {
  const payload = reviewPayload();
  const text = JSON.stringify(payload, null, 2);
  state.reviewOutput = text;
  document.querySelector('#reviewOutput').value = text;
  try {
    const response = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: text
    });
    const result = await response.json();
    state.status = result.ok ? `Saved ${result.latest}` : `Save failed: ${result.error}`;
  } catch (error) {
    state.status = `Review JSON ready. Server save unavailable: ${error}`;
  }
  if (options.keepEditor) refreshAnnotations();
  else render();
}

async function copyReview() {
  const text = state.reviewOutput || JSON.stringify(reviewPayload(), null, 2);
  state.reviewOutput = text;
  document.querySelector('#reviewOutput').value = text;
  try {
    await navigator.clipboard.writeText(text);
    state.status = 'Review JSON copied to clipboard.';
  } catch {
    state.status = 'Review JSON displayed.';
  }
  render();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[ch]);
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, '&quot;');
}

function clamp01(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

boot().catch((error) => {
  app.textContent = `Failed to start viewer: ${error.stack || error}`;
});
