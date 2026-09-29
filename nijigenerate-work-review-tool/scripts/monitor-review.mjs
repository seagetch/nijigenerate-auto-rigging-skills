#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

function usage() {
  console.error("Usage: node monitor-review.mjs --latest <latest-review.json> [--state <state.json>]");
  process.exit(2);
}

function arg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const latest = arg("--latest");
if (!latest) usage();
const statePath = arg("--state") || path.join(path.dirname(latest), ".monitor-state.json");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const exists = fs.existsSync(latest);
const state = fs.existsSync(statePath) ? readJson(statePath) : {};
if (!exists) {
  console.log(JSON.stringify({ exists: false, latest: path.basename(latest), statePath: path.basename(statePath), isNew: false }, null, 2));
  process.exit(0);
}

const review = readJson(latest);
const createdAt = review.createdAt || null;
const processedCreatedAt = state.processedCreatedAt || null;
const isNew = Boolean(createdAt && (!processedCreatedAt || new Date(createdAt) > new Date(processedCreatedAt)));
const decision = review.reviewResult?.decision || null;

console.log(JSON.stringify({
  exists: true,
  latest: path.basename(latest),
  statePath: path.basename(statePath),
  createdAt,
  processedCreatedAt,
  isNew,
  decision,
  nextAction: review.reviewResult?.nextAction || null,
  globalComment: review.globalComment || "",
  tagCount: Array.isArray(review.tags) ? review.tags.length : 0,
}, null, 2));
