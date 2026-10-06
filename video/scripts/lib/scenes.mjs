// scenes.mjs: the scene windows of a rendered spec video, computed the same way the templates do
// (src/spec/templates/concept.tsx and beats.tsx). A scene is one screen: a step, or one panel of a
// step with `panels`. render.mjs uses it for --stills=steps, verify.mjs for the frame checks.

const firstOf = (tb, letter) => {
  const l = tb.steps.filter((s) => new RegExp(`^${letter}[0-9]`).test(s.key));
  return l.length ? l[0].at : null;
};
const panelsOf = (s) => (s.panels ? s.panels : s.panel ? [s.panel] : []);
const panelKeys = (p) => {
  switch (p.kind) {
    case "chips": case "stats": case "bars": return p.items.map((x) => x.at);
    case "flow": return p.nodes.map((x) => x.at);
    case "table": return p.rows.map((x) => x.at);
    case "equation": case "prompt": return p.lines.map((x) => x.at);
    case "compare": return [p.at_left, p.at_right];
    default: return [];
  }
};

/**
 * Returns [{ beat, name, from, to, still }] in absolute frames. `still` sits `before` frames before the
 * scene ends (0.5 s by default), or in the middle of a short scene.
 */
export function scenes(spec, timing, before = 15) {
  const out = [];
  const order = spec.beats.map((b) => b.id);
  spec.beats.forEach((beat, i) => {
    const tb = timing.beats[beat.id];
    const nextId = order[i + 1];
    const until = (nextId ? timing.beats[nextId].start : timing.totalFrames) - tb.start;
    const k = (key) => tb.steps.find((s) => s.key === key)?.at ?? 0;
    const pstart = (p) => Math.min(...panelKeys(p).map(k));
    const local = [];
    const addPanels = (name, panels, from, to) => {
      panels.forEach((p, j) => {
        const a = j === 0 ? from : pstart(p);
        const b = j + 1 < panels.length ? pstart(panels[j + 1]) : to;
        local.push({ name: panels.length > 1 ? `${name}.${j + 1}` : name, from: a, to: b });
      });
    };
    if (beat.kind === "concept") {
      const end = until;
      const s0 = firstOf(tb, "s") ?? end;
      const p0 = firstOf(tb, "p") ?? s0;
      const q0 = firstOf(tb, "q") ?? firstOf(tb, "t") ?? p0;
      const m0 = firstOf(tb, "m") ?? q0;
      const n0 = firstOf(tb, "n") ?? m0;
      const r0 = firstOf(tb, "r") ?? n0;
      const steps = beat.steps ?? [];
      const get = (n) => steps.find((s) => s.step === n);
      const bridge = get("bridge");
      const h0 = bridge ? firstOf(tb, "h") ?? end : end;
      local.push({ name: "claim", from: 0, to: s0 });
      if (get("situation")) addPanels("situation", panelsOf(get("situation")), s0, p0);
      if (get("picture")) addPanels("picture", panelsOf(get("picture")), p0, q0);
      local.push({ name: "think", from: q0, to: m0 });
      local.push({ name: "mechanism", from: m0, to: n0 });
      if (get("number")) addPanels("number", panelsOf(get("number")), n0, r0);
      local.push({ name: "keypoints", from: r0, to: h0 });
      if (bridge) addPanels("bridge", panelsOf(bridge), h0, end);
    } else if (beat.kind === "cold" || beat.kind === "payoff") {
      const all = (beat.steps ?? []).flatMap(panelsOf);
      addPanels("panel", all, 0, until);
    } else {
      local.push({ name: beat.kind, from: 0, to: until });
    }
    for (const s of local) {
      const len = s.to - s.from;
      const still = len > 2 * before + 10 ? s.to - before : s.from + Math.floor(len / 2);
      out.push({ beat: beat.id, kind: beat.kind, name: s.name, from: tb.start + s.from, to: tb.start + s.to, still: tb.start + still });
    }
  });
  return out;
}
