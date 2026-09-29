#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

function usage() {
  console.error("Usage: node accept-review.mjs --latest <latest-review.json> [--state <state.json>] [--audit <audit.json>] [--model <model.inx>]");
  process.exit(2);
}

function arg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const latest = arg("--latest");
if (!latest) usage();
const statePath = arg("--state") || path.join(path.dirname(latest), ".monitor-state.json");
const review = JSON.parse(fs.readFileSync(latest, "utf8"));
if (review.reviewResult?.decision !== "ok") {
  throw new Error(`Cannot accept non-ok review: ${review.reviewResult?.decision}`);
}

const prev = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, "utf8")) : {};
const next = {
  ...prev,
  ...(prev.audit ? { audit: path.basename(prev.audit) } : {}),
  ...(prev.modelOut ? { modelOut: path.basename(prev.modelOut) } : {}),
  processedCreatedAt: review.createdAt,
  decision: "ok",
  acceptedReview: true,
  acceptedAt: new Date().toISOString(),
};
if (arg("--audit")) next.audit = path.basename(arg("--audit"));
if (arg("--model")) next.modelOut = path.basename(arg("--model"));
fs.writeFileSync(statePath, JSON.stringify(next, null, 2));
console.log(JSON.stringify(next, null, 2));
