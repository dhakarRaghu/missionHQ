// Builds the phone reader (`public/reader/`) from the lesson files in git.
//
// The reader used to be exported from Postgres on the Mac that runs the
// backend (`backend/src/hq/reader_export.py`), so it went stale whenever that
// Mac was off. Every lesson page is already a complete HTML file in
// `learning/lessons/`, so this script needs nothing but the repo: it runs
// before every `next build`, locally and on Vercel.
//
// Rules:
// - `<date>-<course>-phase-<NN>-<slug>.html` is a course phase. When a phase
//   was rewritten under a newer date, only the newest file is kept.
// - `<date>-lab-…` files and every other page are articles.
// - `…-page.html` files are drafts and are left out.
// - Every shipped page gets the safety tags (see `harden`).
// - Details the HTML does not carry (reading time, kind, topic, the read
//   flag from the old Postgres export) are kept from the previous
//   `index.json` for files that still exist.
//
// If `learning/lessons` is not there (a build that only sees `frontend/`),
// the committed bundle is left as it is and the build continues.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LEARNING = path.resolve(FRONTEND, "..", "learning");
const LESSONS = path.join(LEARNING, "lessons");
const STUDY = path.join(LEARNING, "study-material");
const OUT = path.join(FRONTEND, "public", "reader");

const PHASE_RE = /^(\d{4}-\d{2}-\d{2})-(.+?)-phase-(\d+[a-z]?)-(.+)\.html$/u;
const DATE_RE = /^(\d{4}-\d{2}-\d{2})-/u;
const ONE_LINER_MAX = 400;

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

// The same walls `harden_page` in `backend/src/hq/api/learning.py` puts on a
// lesson: the content policy (inline style and script only, nothing loads)
// and `<base target="_blank">` (a source link must open a new tab, never
// navigate the lesson frame). Vercel serves these files with no backend in
// front, so the build is the only place to add them.
const CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';" +
  " img-src data:; font-src data:; form-action 'none'; base-uri 'none'";

// Lets the reader page hide the lesson's own contents column. The parent
// posts `{ type: "hq-reader", contents: false }`; only messages from the
// parent frame count. Lessons without `nav.toc` ignore it.
const READER_KIT =
  "<style>html.hq-no-toc nav.toc{display:none!important}" +
  "@media (min-width:1100px){html.hq-no-toc .layout{grid-template-columns:minmax(0,1fr)!important}" +
  "html.hq-no-toc main{margin-inline:auto}}</style>" +
  '<script data-hq="reader-kit">addEventListener("message",function(e){' +
  'if(e.source!==parent||!e.data||e.data.type!=="hq-reader")return;' +
  'document.documentElement.classList.toggle("hq-no-toc",e.data.contents===false)});</script>';

function harden(html) {
  const page = html.replace(/^---\n[\s\S]*?\n---\n/u, "");
  const head = `<meta http-equiv="Content-Security-Policy" content="${CSP}"><base target="_blank">${READER_KIT}`;
  const at = page.match(/<head[^>]*>/iu);
  return at ? page.slice(0, at.index + at[0].length) + head + page.slice(at.index + at[0].length) : head + page;
}

function decode(text) {
  return text
    .replace(/&#x([0-9a-f]+);/giu, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/gu, (_, dec) => String.fromCodePoint(Number(dec)))
    .replace(/&([a-z]+);/giu, (whole, name) => ENTITIES[name.toLowerCase()] ?? whole);
}

function plain(html) {
  return decode(html.replace(/<[^>]+>/gu, "")).replace(/\s+/gu, " ").trim();
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/** Title and first paragraph of a lesson page. */
function pageText(file) {
  const html = fs.readFileSync(path.join(LESSONS, file), "utf8");
  const title = plain(html.match(/<title>([\s\S]*?)<\/title>/iu)?.[1] ?? "");
  const main = html.match(/<main[^>]*>([\s\S]*)/iu)?.[1] ?? html;
  const first = main.match(/<p[^>]*>([\s\S]*?)<\/p>/iu)?.[1] ?? "";
  return { title, oneLiner: plain(first).slice(0, ONE_LINER_MAX) };
}

function courseTitle(slug, previous) {
  const meta = readJson(path.join(STUDY, slug, "course.json"));
  if (meta?.title) return String(meta.title);
  if (previous) return previous;
  return slug.replace(/-/gu, " ").replace(/^\w/u, (c) => c.toUpperCase());
}

function main() {
  if (!fs.existsSync(LESSONS)) {
    console.log(`reader: ${LESSONS} not found; keeping the committed bundle`);
    return;
  }

  // What the previous index knew, keyed by file name.
  const previous = readJson(path.join(OUT, "index.json"));
  const known = new Map();
  const knownCourseTitles = new Map();
  for (const course of previous?.courses ?? []) {
    knownCourseTitles.set(course.slug, course.title);
    for (const phase of course.phases) known.set(phase.file, phase);
  }
  for (const article of previous?.articles ?? []) known.set(article.file, article);

  const files = fs
    .readdirSync(LESSONS)
    .filter((f) => f.endsWith(".html") && !f.endsWith("-page.html"))
    .sort();

  // Newest file per (course, phase); file names sort by date first.
  const phases = new Map();
  const articleFiles = [];
  for (const file of files) {
    const m = file.match(PHASE_RE);
    if (!m || m[2].startsWith("lab-")) {
      articleFiles.push(file);
      continue;
    }
    const [, date, course, phase, rest] = m;
    phases.set(`${course}\u0000${phase}`, { file, date, course, phase, rest });
  }

  const courses = new Map();
  for (const p of phases.values()) {
    const old = known.get(p.file);
    const text = pageText(p.file);
    if (!courses.has(p.course)) {
      courses.set(p.course, {
        slug: p.course,
        title: courseTitle(p.course, knownCourseTitles.get(p.course)),
        phases: [],
      });
    }
    courses.get(p.course).phases.push({
      slug: `${p.course}-phase-${p.phase}-${p.rest}`,
      title: text.title || old?.title || p.rest,
      one_liner: old?.one_liner || text.oneLiner,
      minutes: old?.minutes ?? null,
      date: p.date,
      read: Boolean(old?.read),
      file: p.file,
      phase: p.phase,
    });
  }

  const courseList = [...courses.values()];
  for (const course of courseList) {
    course.phases.sort((a, b) => a.phase.localeCompare(b.phase, "en", { numeric: true }));
    for (const phase of course.phases) delete phase.phase;
  }
  // The course with the newest phase comes first: that is the one he is on.
  const newest = (c) => c.phases.reduce((max, p) => (p.date > max ? p.date : max), "");
  courseList.sort((a, b) => newest(b).localeCompare(newest(a)));

  const articles = articleFiles
    .map((file) => {
      const old = known.get(file);
      const text = pageText(file);
      const lab = file.match(PHASE_RE)?.[2]?.replace(/^lab-/u, "");
      return {
        title: text.title || old?.title || file,
        one_liner: old?.one_liner || text.oneLiner,
        topic: old?.topic ?? (file.includes("-week-review-") ? "week review" : lab ?? ""),
        kind: old?.kind ?? "",
        date: file.match(DATE_RE)?.[1] ?? null,
        read: Boolean(old?.read),
        file,
      };
    })
    .sort((a, b) => b.file.localeCompare(a.file));

  // Replace the lesson folder so a file that left the index does not linger.
  const lessonsOut = path.join(OUT, "lessons");
  fs.rmSync(lessonsOut, { recursive: true, force: true });
  fs.mkdirSync(lessonsOut, { recursive: true });
  const shipped = [...courseList.flatMap((c) => c.phases), ...articles].map((l) => l.file);
  for (const file of shipped) {
    const html = fs.readFileSync(path.join(LESSONS, file), "utf8");
    fs.writeFileSync(path.join(lessonsOut, file), harden(html));
  }

  const index = { built_at: new Date().toISOString(), courses: courseList, articles };
  fs.writeFileSync(path.join(OUT, "index.json"), `${JSON.stringify(index, null, 1)}\n`);

  const counts = courseList.map((c) => `${c.slug} ${c.phases.length}`).join(", ");
  console.log(`reader: ${shipped.length} pages (${counts}; articles ${articles.length})`);
}

main();
