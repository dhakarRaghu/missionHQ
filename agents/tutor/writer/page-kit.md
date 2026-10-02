# The page kit

The page is wrapped in one design for you: light and dark, a contents rail
built from the section headings, a reading progress bar, copy buttons on
code, working steppers, tabs and calc boxes. Build the body only from these.

```
<details class="predict"><summary>Predict: …</summary>  the question first; answer inside
<details class="evidence"><summary>Evidence</summary>   who measured it, where; closed
<dfn>KV cache</dfn>                    a term, at the one place the lesson defines it
<p class="why">                        why this section matters (the lead)
<div class="keypoints">                <p class="remember">  <p class="trap">  <p class="try">
<div class="callout note|tip|warn">    a short aside
<figure class="diagram"><svg viewBox="…">…</svg><figcaption>…
<pre class="ascii">                    an exact box-drawing diagram
<pre><code data-lang="python">          code
<div class="compare"><div class="wrong">…</div><div class="right">…</div></div>
<ol class="steps"><li>…                a walkthrough, shown one step at a time
<ol><li>…  <ul><li>…                   a plain numbered or bullet list: ordered steps, or three or more parallel points
<div class="tabs"><div data-tab="vLLM">…</div><div data-tab="SGLang">…</div></div>
<div class="stats"><div class="stat"><b>730 ms</b><span>p99 TTFT</span></div></div>
<div class="bars"><div class="bar" style="--v:73" data-label="p99" data-value="730 ms"></div></div>
<ol class="timeline"><li><time>t=3s</time> …
<ul class="exercises"><li><label><input type="checkbox"> <b>E1</b> <span class="tag">offline</span></label> …
<details class="answer"><summary>Answer sketch</summary> …
<div class="cards" data-cols="2"><div class="card"><h4>…</h4><p>…</p></div></div>
<div class="lab">                      a block he runs: the command, what he should see
<span class="badge">offline</span>     <kbd>Ctrl</kbd>
<div class="calc" id="s3-kv">          a number he can move, and the result moves
  <h4>KV cache per sequence</h4>
  <label>Layers <input type="range" name="layers" min="8" max="96" value="32">
    <span class="val" data-val="layers"></span></label>
  <div class="result">Per token <b data-out="bytes"></b></div>
  <script>kit.calc('#s3-kv', function(v){ return {bytes: kit.fmt(4*v.layers*128,0)+' B'}; });</script>
</div>
<div class="toggle-fig">               one view at a time: before and after
  <button data-show="before">Without paging</button><button data-show="after">With paging</button>
  <div class="views"><div data-view="before">…</div><div data-view="after">…</div></div>
</div>
<div class="legend"><span><i style="background:var(--accent)"></i>prefill</span>…</div>

<ol class="flow">                      an order of operations; arrows are drawn for you
  <li><b>model scores</b><span>one score for every token</span></li>
  <li class="hot"><b>mask</b><span>tokens the schema forbids are removed</span></li>
  <li class="ok"><b>pick</b><span>the best legal token</span></li>
</ol>                                  data-dir="down" stacks it; li class: hot | ok | bad

<div class="lanes" id="s2-freeze" data-play>   who does what in each step, to scale
  <h4>One long prompt, no chunking</h4>
  <div class="lane" data-label="new prompt">
    <i class="idle" style="--w:18"></i><i class="idle" style="--w:18"></i>
    <i class="prefill" style="--w:720" data-t="24,000 tokens · 720 ms"></i>
    <i class="idle" style="--w:18"></i></div>
  <div class="lane" data-label="stream A">
    <i class="decode" style="--w:18" data-t="18"></i><i class="decode" style="--w:18" data-t="18"></i>
    <i class="frozen" style="--w:720" data-t="no token"></i>
    <i class="decode" style="--w:18" data-t="18"></i></div>
  <p class="at" data-step="3">Step 3: the whole prefill runs, and stream A gets no token for 720 ms.</p>
  <p class="at" data-step="all">Illustration from the lesson's cost model, not measured.</p>
</div>                                 every lane has the same number of <i>, one per step;
                                       --w is the step's size; class: decode | prefill |
                                       frozen | wait | idle; data-play adds Next and Previous

<div class="stack">                    one whole and its parts, to scale; the list is built for you
  <h4>A 32,000-token window</h4>
  <div class="whole">
    <i style="--w:1000;--c:var(--violet)" data-label="system" data-value="1,000" data-note="first in the prompt"></i>
    <i style="--w:7000;--c:var(--warn)" data-label="headroom" data-value="7,000" data-note="for the reply"></i>
  </div>
</div>                                 --c: var(--accent|--ok|--bad|--warn|--violet|--muted)

<ul class="tree">                      a decision: a question, and what each answer leads to
  <li><b>Did the call return 400 for length?</b>
    <ul><li class="ok"><em>yes</em><span>compact, then send once</span></li>
        <li class="bad"><em>no</em><span>a retry may help</span></li></ul></li>
</ul>

<td class="ok">  <td class="bad">  <tr class="pick">   a table cell or row that carries a verdict
```

`kit` is ready before your script runs: `kit.$`, `kit.$$`, `kit.fmt(n, digits)`
and `kit.calc(selector, compute)`. `kit.calc` reads every input in the box by
its `name`, writes each `[data-val="name"]` with the current value, calls your
function with them, and fills each `[data-out="key"]` from what it returns. A
slider figure is four lines of script. Write no other script.

Pick the piece that matches the idea:

| The idea | The piece |
|---|---|
| what happens in each step, and how long each step takes | `<div class="lanes" data-play>` |
| an order of operations, a request's path | `<ol class="flow">`, or `<ol class="steps">` when each step needs a paragraph |
| steps told in words, or three or more parallel points | a plain `<ol>` or `<ul>`, one full sentence per item |
| one whole divided into parts (a window, a bill, a memory budget) | `<div class="stack">` |
| a choice and where each answer leads | `<ul class="tree">` |
| how one number drives another | `<div class="calc">` with a slider |
| before and after a change | `<div class="toggle-fig">` holding two drawn views |
| the wrong way next to the right way | `<div class="compare">` |
| a grid of values, what each option promises | a `<table>`, with `td class="ok"` and `class="bad"` |
| a measurement | `<div class="stats">` or `<div class="bars">` |
| the same job in two systems | `<div class="tabs">` |
| where things sit in space | `<figure class="diagram">` with SVG |
| something he runs himself | `<div class="lab">` |

Draw, do not type. A figure built from characters in `<pre class="ascii">`
is hard to read on a phone and cannot move. Use it only for a layout he
would read in a terminal, at most one to a section, and never as the
section's only figure.

Let him move it. When the section has a formula with an input he could
change (a prompt length, a token budget, a number of streams), give it a
`calc` box with a slider, using the constants from the lesson. When the
mechanism happens in steps, give the `lanes` figure `data-play` and write
one `<p class="at" data-step="N">` for each step that matters, saying what
happens in it. One figure that moves teaches more than three that do not.

Rules the page checks:

- Nothing loads from the internet: no CDN, no web font, no remote image.
- SVG text uses `fill="currentColor"`, so it reads in dark mode.
- Every id starts with this section's prefix, and every id or class a
  script looks up exists in the markup, spelled the same.
- Example data is labelled: real values say where they came from; values
  made up to show a shape say "illustration, not measured".
- A figure shows a mechanism (where a request goes, where the time is spent,
  what a number does to the outcome), labelled with the real names. A box
  per heading is decoration.
