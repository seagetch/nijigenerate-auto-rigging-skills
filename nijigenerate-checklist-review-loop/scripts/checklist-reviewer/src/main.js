import "./styles.css";
import yaml from "js-yaml";
import { localUrl } from "./security.mjs";
import { CheckCircle2, RotateCcw, Send } from "lucide";

const app = document.querySelector("#app");
let manifestUrl;

function resolveRef(ref, baseUrl) {
  if (!ref) return null;
  return localUrl(ref, baseUrl, location.origin, true);
}

async function fetchText(url) {
  const response = await fetch(url, { cache: "no-store", redirect: "error" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  const text = await response.text();
  if (text.length > 2_000_000) throw new Error("Checklist input is too large");
  return text;
}

async function fetchJson(url) {
  return JSON.parse(await fetchText(url));
}

function normalizeResult(value) {
  const v = String(value || "").trim().toLowerCase();
  return v === "retake" ? "retake" : "ok";
}

function selfReviewMap(selfReview) {
  const list = selfReview?.results || selfReview?.items || selfReview?.reviews || [];
  const map = new Map();
  for (const item of Array.isArray(list) ? list : []) {
    if (!item?.id) continue;
    map.set(String(item.id), {
      id: String(item.id),
      result: normalizeResult(item.result || item.decision || item.status),
      reason: String(item.reason || item.comment || ""),
    });
  }
  return map;
}

function checklistItems(checklist) {
  const sections = Array.isArray(checklist?.sections) ? checklist.sections : [];
  return sections.map((section) => ({
    name: String(section.name || "Section"),
    checklist: (section.checklist || []).map((item) => ({
      id: String(item.id || ""),
      target: String(item.target || ""),
      check: String(item.check || ""),
      translationOnly: Boolean(item.translationOnly),
    })),
  }));
}

function translatedChecklistRef(manifest) {
  return manifest.translatedChecklist
    || manifest.checklistTranslation
    || manifest.translation?.checklist
    || null;
}

function mergeTranslatedChecklist(originalChecklist, translatedChecklist) {
  if (!translatedChecklist) return originalChecklist;

  const originalSections = checklistItems(originalChecklist);
  const translatedSections = checklistItems(translatedChecklist);
  const translatedById = new Map();
  const translatedSectionById = new Map();

  for (const section of translatedSections) {
    for (const item of section.checklist) {
      if (!item.id) continue;
      translatedById.set(item.id, item);
      translatedSectionById.set(item.id, section.name);
    }
  }

  const originalIds = new Set();
  const sections = originalSections.map((section) => {
    const translatedSectionName = section.checklist
      .map((item) => translatedSectionById.get(item.id))
      .find(Boolean);
    return {
      name: translatedSectionName || section.name,
      checklist: section.checklist.map((item) => {
        originalIds.add(item.id);
        const translated = translatedById.get(item.id);
        if (!translated) return item;
        return {
          ...item,
          target: translated.target || item.target,
          check: translated.check || item.check,
        };
      }),
    };
  });

  const sectionByName = new Map(sections.map((section) => [section.name, section]));
  for (const translatedSection of translatedSections) {
    const extras = translatedSection.checklist
      .filter((item) => item.id && !originalIds.has(item.id))
      .map((item) => ({
        ...item,
        translationOnly: true,
      }));
    if (!extras.length) continue;
    let section = sectionByName.get(translatedSection.name);
    if (!section) {
      section = { name: translatedSection.name || "Translation Only", checklist: [] };
      sections.push(section);
      sectionByName.set(section.name, section);
    }
    section.checklist.push(...extras);
  }

  return {
    ...originalChecklist,
    title: translatedChecklist.title || originalChecklist.title,
    sections,
  };
}

function sectionStats(section, reviews) {
  let ok = 0;
  let retake = 0;
  for (const item of section.checklist) {
    if (item.translationOnly) continue;
    if (reviews[item.id]?.result === "retake") retake += 1;
    else ok += 1;
  }
  return { ok, retake };
}

function resultSummary(sections, reviews) {
  let ok = 0;
  let retake = 0;
  for (const section of sections) {
    const stats = sectionStats(section, reviews);
    ok += stats.ok;
    retake += stats.retake;
  }
  return { ok, retake, total: ok + retake };
}

function iconSvg(icon) {
  const children = icon.map(([tag, attrs]) => {
    const attrText = Object.entries(attrs || {})
      .map(([key, value]) => `${key}="${escapeHtml(value)}"`)
      .join(" ");
    return `<${tag} ${attrText}></${tag}>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${children}</svg>`;
}

function render({ manifest, checklist, selfReview, reviews, status = "" }) {
  const sections = checklistItems(checklist);
  const summary = resultSummary(sections, reviews);
  const title = checklist?.title || manifest.model?.name || "Checklist Review";
  const retakeClass = summary.retake ? " retake" : "";

  app.innerHTML = `
    <div class="app">
      <header class="topbar">
        <div class="title">
          <h1>${escapeHtml(title)}</h1>
          <p>${escapeHtml(manifest.model?.id || "")}</p>
        </div>
        <div class="summary">
          <span class="pill">Total ${summary.total}</span>
          <span class="pill">OK ${summary.ok}</span>
          <span class="pill${retakeClass}">Retake ${summary.retake}</span>
          <span class="save-state">${escapeHtml(status)}</span>
        </div>
        <button class="submit" id="submitReview">${iconSvg(Send)} Submit</button>
      </header>
      <main class="content">
        ${sections.map((section) => renderSection(section, reviews)).join("")}
      </main>
    </div>
  `;

  app.querySelectorAll("[data-result]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.getAttribute("data-id");
      const result = button.getAttribute("data-result");
      reviews[id] = reviews[id] || { id, result: "ok", reason: "" };
      reviews[id].result = result;
      render({ manifest, checklist, selfReview, reviews });
    });
  });

  app.querySelectorAll(".reason[data-id]").forEach((reason) => {
    reason.addEventListener("click", () => {
      reason.setAttribute("contenteditable", "true");
      reason.classList.add("editing");
      reason.focus();
    });
    reason.addEventListener("blur", () => {
      reason.setAttribute("contenteditable", "false");
      reason.classList.remove("editing");
    });
    reason.addEventListener("input", () => {
      const id = reason.getAttribute("data-id");
      reviews[id] = reviews[id] || { id, result: "ok", reason: "" };
      reviews[id].reason = reason.textContent;
    });
  });

  app.querySelector("#submitReview")?.addEventListener("click", async () => {
    const button = app.querySelector("#submitReview");
    button.disabled = true;
    try {
      const payload = buildPayload({ manifest, checklist, selfReview, reviews, manifestUrl });
      const response = await fetch(`/api/checklist-review?manifest=${encodeURIComponent(manifestUrl)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || "submit failed");
      render({ manifest, checklist, selfReview, reviews, status: `Saved ${result.latest}` });
    } catch (error) {
      render({ manifest, checklist, selfReview, reviews, status: `Error: ${String(error.message || error)}` });
    }
  });
}

function renderSection(section, reviews) {
  const stats = sectionStats(section, reviews);
  return `
    <section class="section">
      <div class="section-header">
        <h2>${escapeHtml(section.name)}</h2>
        <span class="pill">OK ${stats.ok}</span>
        <span class="pill${stats.retake ? " retake" : ""}">Retake ${stats.retake}</span>
      </div>
      <div class="table">
        <div class="thead">
          <div>ID</div>
          <div>Target</div>
          <div>Check</div>
          <div>Result</div>
          <div>Reason</div>
        </div>
        ${section.checklist.map((item) => renderRow(item, reviews[item.id] || { result: "ok", reason: "" })).join("")}
      </div>
    </section>
  `;
}

function renderRow(item, review) {
  if (item.translationOnly) {
    return `
      <div class="row translation-only">
        <div class="cell id">${escapeHtml(item.id)}<span class="note">翻訳のみ存在</span></div>
        <div class="cell target">${escapeHtml(item.target)}</div>
        <div class="cell check">${escapeHtml(item.check)}</div>
        <div class="cell muted">対象外</div>
        <div class="cell muted">この ID はオリジナル checklist に存在しないため、レビュー結果には含めません。</div>
      </div>
    `;
  }
  const result = normalizeResult(review.result);
  return `
    <div class="row">
      <div class="cell id">${escapeHtml(item.id)}</div>
      <div class="cell target">${escapeHtml(item.target)}</div>
      <div class="cell check">${escapeHtml(item.check)}</div>
      <div class="cell">
        <div class="toggle" role="group" aria-label="result for ${escapeHtml(item.id)}">
          <button class="ok ${result === "ok" ? "active" : ""}" data-id="${escapeHtml(item.id)}" data-result="ok">${iconSvg(CheckCircle2)} OK</button>
          <button class="retake ${result === "retake" ? "active" : ""}" data-id="${escapeHtml(item.id)}" data-result="retake">${iconSvg(RotateCcw)} Retake</button>
        </div>
      </div>
      <div class="cell">
        <div class="reason" data-id="${escapeHtml(item.id)}" contenteditable="false" tabindex="0">${escapeHtml(review.reason || "")}</div>
      </div>
    </div>
  `;
}

function buildPayload({ manifest, checklist, selfReview, reviews, manifestUrl }) {
  const sections = checklistItems(checklist);
  const results = [];
  for (const section of sections) {
    for (const item of section.checklist) {
      if (item.translationOnly) continue;
      const review = reviews[item.id] || { id: item.id, result: "ok", reason: "" };
      results.push({
        id: item.id,
        section: section.name,
        target: item.target,
        check: item.check,
        result: normalizeResult(review.result),
        reason: String(review.reason || ""),
      });
    }
  }
  const hasRetake = results.some((item) => item.result === "retake");
  return {
    schema: manifest.review?.schema || "checklist-review-result-v1",
    createdAt: new Date().toISOString(),
    manifest: {
      url: manifestUrl,
      model: manifest.model || null,
      checklist: manifest.checklist || null,
      translatedChecklist: translatedChecklistRef(manifest),
      selfReview: manifest.selfReview || null,
      selfReviewCreatedAt: selfReview?.createdAt || null,
    },
    reviewResult: {
      decision: hasRetake ? "retake" : "ok",
    },
    results,
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function main() {
  app.innerHTML = `<div class="notice">Loading checklist review...</div>`;
  try {
    manifestUrl = localUrl(new URLSearchParams(location.search).get("manifest") || "/manifest.json", location.href, location.origin);
    const manifest = await fetchJson(manifestUrl);
    const manifestBase = new URL(manifestUrl, location.origin);
    const checklistUrl = resolveRef(manifest.checklist, manifestBase);
    const selfReviewUrl = resolveRef(manifest.selfReview, manifestBase);
    const translatedChecklistUrl = resolveRef(translatedChecklistRef(manifest), manifestBase);
    if (!checklistUrl || !selfReviewUrl) throw new Error("manifest requires checklist and selfReview");
    const [checklistYaml, selfReviewYaml, translatedChecklistYaml] = await Promise.all([
      fetchText(checklistUrl),
      fetchText(selfReviewUrl),
      translatedChecklistUrl ? fetchText(translatedChecklistUrl) : Promise.resolve(null),
    ]);
    const originalChecklist = yaml.load(checklistYaml, { schema: yaml.JSON_SCHEMA });
    const translatedChecklist = translatedChecklistYaml ? yaml.load(translatedChecklistYaml, { schema: yaml.JSON_SCHEMA }) : null;
    const checklist = mergeTranslatedChecklist(originalChecklist, translatedChecklist);
    const selfReview = yaml.load(selfReviewYaml, { schema: yaml.JSON_SCHEMA });
    const selfMap = selfReviewMap(selfReview);
    const reviews = Object.create(null);
    for (const section of checklistItems(checklist)) {
      for (const item of section.checklist) {
        const existing = selfMap.get(item.id);
        reviews[item.id] = {
          id: item.id,
          result: normalizeResult(existing?.result || "ok"),
          reason: existing?.reason || "",
        };
      }
    }
    render({ manifest, checklist, selfReview, reviews });
  } catch (error) {
    app.innerHTML = `<div class="error">${escapeHtml(error.stack || error.message || error)}</div>`;
  }
}

main();
