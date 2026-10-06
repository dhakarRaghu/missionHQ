#!/usr/bin/env node
/**
 * check-spec.mjs: checks a narration file and a spec file against video/SPEC.md before anything renders.
 *
 *   node scripts/check-spec.mjs <narration.json> <spec.json>
 *
 * Prints every problem as "<file>:<JSON path>: <message>", then "OK" or the count. Exit code 0 when
 * there is no problem, 1 when there is at least one, 2 for a usage error.
 *
 * Checks (SPEC.md "What code checks"):
 *   1. both files parse and match the contract (JSON Schema, unknown fields are errors)
 *   2. beat ids and order match between narration and spec, and follow cold, title, c1…, payoff, recap, end
 *   3. every `at` key exists in its beat, and `at` keys never go backwards inside a step or across a beat's visuals
 *   4. every text field is within its limit (maxLength / maxItems in the schema, reported with the field path)
 *   5. concept beats have the steps in order (claim … keypoints, then bridge exactly when the beat has `h` lines),
 *      every step's letter exists in the narration, and each step's `at` keys use that step's letter
 * TODO(check 6): the narration rules (sentence length, banned words, no part names, terms defined at first use,
 *   numbers in `text` spelled out in `say`) are checked by the Python backend, agents/tutor/video/rules.md.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const [, , narrPath, specPath] = process.argv;
if (!narrPath || !specPath) {
  console.error("usage: check-spec.mjs <narration.json> <spec.json>");
  process.exit(2);
}

const problems = [];
const bad = (file, path, msg) => problems.push(`${file}:${path || "$"}: ${msg}`);
const N = "narration";
const S = "spec";

const load = (file, label) => {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (e) {
    bad(label, "$", `cannot parse: ${e.message}`);
    return null;
  }
};
const narr = load(narrPath, N);
const spec = load(specPath, S);

// ---------------------------------------------------------------- 1 and 4: schema, limits

const ajv = new Ajv({ allErrors: true, discriminator: true, strict: false, verbose: true });
const ptr = (p) => "$" + p.replace(/\/(\d+)/g, "[$1]").replace(/\/([^/]+)/g, ".$1");
const schemaCheck = (data, schemaFile, label) => {
  const validate = ajv.compile(JSON.parse(readFileSync(join(root, "spec", schemaFile), "utf8")));
  if (validate(data)) return true;
  for (const e of validate.errors) {
    if (e.keyword === "if") continue; // the failing `then` is reported on its own
    let msg = e.message;
    if (e.keyword === "maxLength") msg = `is ${String(e.data).length} characters; the limit is ${e.params.limit}: ${JSON.stringify(e.data)}`;
    if (e.keyword === "maxItems") msg = `has ${e.data.length} items; the limit is ${e.params.limit}`;
    if (e.keyword === "additionalProperties") msg = `unknown field "${e.params.additionalProperty}"`;
    if (e.keyword === "const" || e.keyword === "enum") msg = `${e.message}: ${JSON.stringify(e.params.allowedValue ?? e.params.allowedValues)}`;
    bad(label, ptr(e.instancePath), msg);
  }
  return false;
};
const narrOk = narr && schemaCheck(narr, "narration.schema.json", N);
const specOk = spec && schemaCheck(spec, "video-spec.schema.json", S);

// The structural checks below need the basic shape; without it they would only repeat schema errors.
const shapeOk = narr && spec && typeof narr.beats === "object" && Array.isArray(spec.beats);

function structural() {
  // ---------------------------------------------------------------- 2: beat ids and order
  const nIds = Object.keys(narr.beats);
  const sIds = spec.beats.map((b) => b?.id);
  if (nIds.join(",") !== sIds.join(",")) {
    bad(S, "$.beats", `beat ids ${JSON.stringify(sIds)} do not match the narration's ${JSON.stringify(nIds)} (same ids, same order)`);
  }
  const rank = (id) => {
    if (id === "cold") return 0;
    if (id === "title") return 1;
    const m = /^c(\d+)$/.exec(id ?? "");
    if (m) return 10 + Number(m[1]);
    return { payoff: 100, recap: 101, end: 102 }[id] ?? -1;
  };
  for (let i = 1; i < sIds.length; i++) {
    if (rank(sIds[i]) <= rank(sIds[i - 1])) bad(S, `$.beats[${i}].id`, `"${sIds[i]}" is out of order after "${sIds[i - 1]}" (cold, title, c1…, payoff, recap, end)`);
  }
  for (const req of ["cold", "title", "recap", "end"]) if (!sIds.includes(req)) bad(S, "$.beats", `the "${req}" beat is missing`);
  const concepts = sIds.filter((id) => /^c\d+$/.test(id ?? ""));
  concepts.forEach((id, i) => { if (id !== `c${i + 1}`) bad(S, "$.beats", `concept beats must be numbered c1, c2, … without gaps; found "${id}" at position ${i + 1}`); });
  const kindOf = (id) => (/^c\d+$/.test(id) ? "concept" : id);
  spec.beats.forEach((b, i) => {
    if (b?.id && b.kind && kindOf(b.id) !== b.kind) bad(S, `$.beats[${i}].kind`, `beat "${b.id}" must have kind "${kindOf(b.id)}", not "${b.kind}"`);
  });

  // ---------------------------------------------------------------- 3 and 5: at keys, steps
  spec.beats.forEach((beat, bi) => {
    const nb = narr.beats[beat?.id];
    const base = `$.beats[${bi}]`;
    if (!nb || !Array.isArray(nb.lines)) return;
    const keys = nb.lines.map((l) => l.key);
    const pos = new Map(keys.map((k, i) => [k, i]));
    const dup = keys.filter((k, i) => keys.indexOf(k) !== i);
    for (const d of new Set(dup)) bad(N, `$.beats.${beat.id}.lines`, `line key "${d}" is used more than once`);
    const letter = (k) => /^[a-z]+?(?=\d)/.exec(k)?.[0] ?? "";
    const letters = new Set(keys.map(letter));

    // the "mark" words must be in the claim or the title
    if (beat.mark) {
      const host = beat.kind === "title" ? spec.title : beat.kind === "concept" ? nb.lines.filter((l) => letter(l.key) === "k").map((l) => l.text).join(" ") : null;
      if (host == null) bad(S, `${base}.mark`, `"mark" is only for concept and title beats`);
      else if (!host.includes(beat.mark)) bad(S, `${base}.mark`, `"${beat.mark}" is not part of ${beat.kind === "title" ? "the title" : "the claim (k lines)"}`);
    }

    let lastAt = -1; // across the whole beat's visuals, in screen order
    let lastPath = "";
    const steps = Array.isArray(beat.steps) ? beat.steps : [];
    steps.forEach((st, si) => {
      const sp = `${base}.steps[${si}]`;
      sideAts.length = 0;
      const ats = collectAts(st, sp);
      const groups = [ats, [...sideAts]];
      for (const group of groups) {
      let prev = -1;
      let prevPath = "";
      for (const { key, path } of group) {
        if (!pos.has(key)) { bad(S, path, `"${key}" is not a line key of beat "${beat.id}" in the narration`); continue; }
        const p = pos.get(key);
        if (p < prev) bad(S, path, `"${key}" goes backwards: its line comes before the line of ${prevPath}`);
        prev = p;
        prevPath = path;
        if (beat.kind === "concept") {
          const want = STEP_LETTER[st.step];
          if (want && !want.includes(letter(key))) bad(S, path, `"${key}" belongs to another step; ${st.step} elements must use ${want.map((x) => `"${x}"`).join(" or ")} lines, or they never show`);
        }
      }
      }
      // the first element of each panel must not come before the previous panel's first element
      // and, inside one `panels` list, each panel must start on a LATER line than
      // the one before: two panels on the same line give the first one no time
      // on screen (a zero-length scene crashed a render on 2026-10-06).
      let prevPanel = -1, prevPanelPath = "";
      for (const pp of firstOfPanels(st, sp)) {
        if (!pos.has(pp.key)) continue;
        const p = pos.get(pp.key);
        if (p < lastAt) bad(S, pp.path, `this panel starts at "${pp.key}", before the panel at ${lastPath}; panels show one after another`);
        else if (Array.isArray(st.panels) && p === prevPanel) bad(S, pp.path, `this panel starts on the same line "${pp.key}" as ${prevPanelPath}; each panel needs its own, later line, or the one before it never shows`);
        if (p >= lastAt) { lastAt = p; lastPath = pp.path; }
        prevPanel = p; prevPanelPath = pp.path;
      }
    });

    if (beat.kind === "concept") conceptSteps(beat, base, steps, nb, letters, keys, letter);
  });
}

const sideAts = [];
const STEP_LETTER = { situation: ["s"], picture: ["p"], mechanism: ["m"], number: ["n"], bridge: ["h"] };
const ORDER = ["claim", "situation", "picture", "think", "mechanism", "number", "keypoints"];
const NEEDS = { claim: ["k"], situation: ["s"], picture: ["p"], think: ["q", "t"], mechanism: ["m"], number: ["n"], keypoints: ["r"] };

function conceptSteps(beat, base, steps, nb, letters, keys, letter) {
  const names = steps.map((s) => s?.step);
  const want = letters.has("h") ? [...ORDER, "bridge"] : ORDER;
  if (names.join(",") !== want.join(",")) {
    bad(S, `${base}.steps`, `concept steps must be ${JSON.stringify(want)}${letters.has("h") ? " (the narration has h lines, so a bridge step closes it)" : ""}; found ${JSON.stringify(names)}`);
  }
  for (const [step, ls] of Object.entries(NEEDS)) {
    for (const l of ls) if (!letters.has(l)) bad(N, `$.beats.${beat.id}.lines`, `the ${step} step needs "${l}" lines (${l}0, ${l}1, …)`);
  }
  if (letters.has("t") && keys.filter((k) => letter(k) === "t").length < 3) bad(N, `$.beats.${beat.id}.lines`, `think it through needs three "t" lines: first thought, what it misses, the real question`);
  if (keys.filter((k) => letter(k) === "r").length !== 3) bad(N, `$.beats.${beat.id}.lines`, `key points need exactly three "r" lines: remember, the trap, try this`);
  // narration letters must come in step order, so every step's window is one block of lines
  const seq = ["k", "s", "p", "q", "t", "m", "n", "r", "h"];
  let maxRank = -1;
  nb.lines.forEach((l, i) => {
    const r = seq.indexOf(letter(l.key));
    if (r < 0) bad(N, `$.beats.${beat.id}.lines[${i}].key`, `"${l.key}": concept line keys start with one of ${seq.join(", ")}`);
    else if (r < maxRank) bad(N, `$.beats.${beat.id}.lines[${i}].key`, `"${l.key}" comes after a later step's line; keep the lines in step order k s p q t m n r h`);
    else maxRank = r;
  });
  const mech = steps.find((s) => s?.step === "mechanism");
  if (mech && Array.isArray(mech.items)) {
    const m = keys.filter((k) => letter(k) === "m");
    if (mech.items.length !== m.length) bad(S, `${base}.steps[${steps.indexOf(mech)}].items`, `has ${mech.items.length} items; the narration has ${m.length} "m" lines and needs one item per line`);
    mech.items.forEach((it, i) => {
      if (m[i] && it.at !== m[i]) bad(S, `${base}.steps[${steps.indexOf(mech)}].items[${i}].at`, `item ${i + 1} must be at "${m[i]}", its own m line`);
    });
  }
}

/** Every `at` key in a step, in screen order, with its JSON path. */
function collectAts(st, sp) {
  const out = [];
  if (!st || typeof st !== "object") return out;
  if (st.step === "mechanism") {
    (st.items ?? []).forEach((it, i) => out.push({ key: it.at, path: `${sp}.items[${i}].at` }));
    // the side panel is a second column; its keys are checked on their own, so the columns may interleave
    if (st.side) sideAts.push(...panelAts(st.side, `${sp}.side`));
    return out;
  }
  panelsOf(st).forEach(({ p, path }) => out.push(...panelAts(p, `${sp}${path}`)));
  return out;
}

function panelsOf(st) {
  if (Array.isArray(st.panels)) return st.panels.map((p, i) => ({ p, path: `.panels[${i}]` }));
  if (st.panel) return [{ p: st.panel, path: ".panel" }];
  return [];
}

function panelAts(p, path) {
  if (!p || typeof p !== "object") return [];
  const list = (arr, name) => (Array.isArray(arr) ? arr.map((x, i) => ({ key: x?.at, path: `${path}.${name}[${i}].at` })) : []);
  switch (p.kind) {
    case "chips": case "stats": case "bars": return list(p.items, "items");
    case "flow": return list(p.nodes, "nodes");
    case "table": return list(p.rows, "rows");
    case "equation": case "prompt": return list(p.lines, "lines");
    case "compare": return [{ key: p.at_left, path: `${path}.at_left` }, { key: p.at_right, path: `${path}.at_right` }];
    default: return [];
  }
}

function firstOfPanels(st, sp) {
  return panelsOf(st).map(({ p, path }) => {
    const ats = panelAts(p, `${sp}${path}`);
    return ats[0] ? { key: ats[0].key, path: ats[0].path } : null;
  }).filter(Boolean);
}

if (shapeOk) structural();

if (problems.length === 0) {
  console.log(`OK: ${narrPath} and ${specPath} match the contract (${spec.beats.length} beats).`);
  process.exit(0);
}
for (const p of problems) console.log(p);
console.log(`${problems.length} problem${problems.length === 1 ? "" : "s"}.`);
process.exit(1);
