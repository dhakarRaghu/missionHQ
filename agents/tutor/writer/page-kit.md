# The page kit

The page is wrapped in one design for you: light and dark, a contents rail
built from the section headings, a reading progress bar, copy buttons on
code, working steppers, tabs and calc boxes. Build the body only from these.

```
<details class="predict"><summary>Predict: …</summary>  the question first; answer inside
<details class="evidence"><summary>Evidence</summary>   who measured it, where; closed
<p class="why">                        why this section matters (the lead)
<div class="keypoints">                <p class="remember">  <p class="trap">  <p class="try">
<div class="callout note|tip|warn">    a short aside
<figure class="diagram"><svg viewBox="…">…</svg><figcaption>…
<pre class="ascii">                    an exact box-drawing diagram
<pre><code data-lang="python">          code
<div class="compare"><div class="wrong">…</div><div class="right">…</div></div>
<ol class="steps"><li>…                a walkthrough, shown one step at a time
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
```

`kit` is ready before your script runs: `kit.$`, `kit.$$`, `kit.fmt(n, digits)`
and `kit.calc(selector, compute)`. `kit.calc` reads every input in the box by
its `name`, writes each `[data-val="name"]` with the current value, calls your
function with them, and fills each `[data-out="key"]` from what it returns. A
slider figure is four lines of script. Write no other script.

Pick the piece that matches the idea:

| The idea | The piece |
|---|---|
| where a request goes, what holds what | `<figure class="diagram">` with SVG, or `<pre class="ascii">` |
| how one number drives another | `<div class="calc">` with a slider |
| before and after a change | `<div class="toggle-fig">` |
| the wrong way next to the right way | `<div class="compare">` |
| an order of operations | `<ol class="steps">` |
| a measurement | `<div class="stats">` or `<div class="bars">` |
| the same job in two systems | `<div class="tabs">` |
| something he runs himself | `<div class="lab">` |

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
