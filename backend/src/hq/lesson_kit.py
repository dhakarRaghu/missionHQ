"""The page kit: one design for every lesson page he reads in Mission HQ.

Tutor used to write each page's whole document — doctype, head, a style
block, the script — and every page looked a little different, spent a large
part of its output on CSS, and was the reason a course phase answer ran past
the time limit. Now tutor writes only the body, using the components below,
and `wrap_page` puts it in one document with one stylesheet and one small
script. Pages look like one product, and each writing call carries teaching,
not boilerplate.

The page renders in a sandboxed frame with no same-origin (see the Courses
and Learn frames): no network, no storage. The script therefore never touches
localStorage, cookies or the network, and everything is inline.

Components tutor may use (the `teaching` skill documents them):

    <p class="why">                      lead: why this section matters
    <div class="keypoints">              the three closing lines of a concept
      <p class="remember">…  <p class="trap">…  <p class="try">…
    <div class="callout note|tip|warn">  a short aside
    <p data-added="update|correction|incident|deeper|practice">
                                         a paragraph Mission HQ added, written
                                         as part of the section, with its
                                         source linked inline
    <figure class="diagram"> <svg>…</svg> <figcaption>…
    <pre class="ascii">                 a box-drawing diagram, kept exact
    <pre><code data-lang="python">       code; a copy button is added
    <div class="compare"> <div class="wrong">… <div class="right">…
    <ol class="steps">                   a walkthrough, one step at a time
    <div class="tabs"> <div data-tab="Label">…   alternatives side by side
    <div class="stats"> <div class="stat"><b>730 ms</b><span>p99</span>
    <div class="bars"> <div class="bar" style="--v:73" data-label="p99" data-value="730 ms">
    <ol class="timeline"> <li><time>t=0s</time> …
    <ul class="exercises"> <li><label><input type="checkbox"> <b>E1</b> …
    <details class="answer"><summary>Answer sketch</summary> …
    <div class="cards" data-cols="2"> <div class="card"><h4>…</h4><p>…</p>
    <div class="lab">                    a block he runs, with its command
    <span class="badge">offline</span>   <kbd>Ctrl</kbd>
    <div class="calc" id="kv">           a number he can move:
      <label>Layers <input type="range" name="layers" min="8" max="96" value="32">
        <span class="val" data-val="layers"></span></label>
      <div class="result">KV per token <b data-out="bytes"></b></div>
      <script>kit.calc('#kv', v => ({bytes: kit.fmt(2*v.layers*128*2) + ' B'}))</script>
    <div class="toggle-fig">             one view at a time:
      <button data-show="before">Before</button><button data-show="after">After</button>
      <div class="views"><div data-view="before">…</div><div data-view="after">…</div></div>
    <div class="legend"><span><i style="background:var(--accent)"></i>prefill</span>
    <pre class="cheatsheet">
    <ul class="sources">
"""

from __future__ import annotations

import html as html_lib
import re

KIT_CSS = """
:root{
  --bg:#fbfaf7;--fg:#1c1b19;--muted:#6b675f;--line:#e6e2d9;--card:#ffffff;
  --soft:#f3f0e9;--accent:#2f5bd3;--accent-soft:#e8eefc;
  --ok:#2f7d4f;--ok-soft:#e5f3ea;--bad:#b3261e;--bad-soft:#fbe9e7;
  --warn:#9a6a00;--warn-soft:#fdf3dc;--violet:#6b4bc7;--violet-soft:#efeafb;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#161614;--fg:#ecebe6;--muted:#a19d94;--line:#2e2c28;--card:#1d1c1a;
  --soft:#23221f;--accent:#8fb0ff;--accent-soft:#1e2740;
  --ok:#7fcf9c;--ok-soft:#17291e;--bad:#ff968c;--bad-soft:#35191a;
  --warn:#e8c170;--warn-soft:#30280f;--violet:#bba7ff;--violet-soft:#241d3a;
}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
  font:16.5px/1.7 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
#progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:9}
.layout{max-width:1180px;margin:0 auto;padding:2.2rem 1.2rem 5rem;display:grid;gap:2.5rem}
@media (min-width:1100px){.layout{grid-template-columns:230px minmax(0,1fr)}}
main{min-width:0;max-width:74ch}
nav.toc{font-size:.84rem}
@media (min-width:1100px){nav.toc{position:sticky;top:1.5rem;align-self:start;
  max-height:calc(100vh - 3rem);overflow:auto}}
nav.toc b{display:block;color:var(--muted);font-size:.72rem;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:.5rem}
nav.toc a{display:block;padding:.28rem .6rem;border-left:2px solid var(--line);
  color:var(--muted);text-decoration:none;line-height:1.35}
nav.toc a:hover{color:var(--fg)}
nav.toc a.on{border-color:var(--accent);color:var(--fg);font-weight:600}
header.hero{margin-bottom:2rem;padding-bottom:1.4rem;border-bottom:1px solid var(--line)}
.eyebrow{color:var(--accent);font-weight:600;font-size:.8rem;letter-spacing:.06em;text-transform:uppercase}
h1{font-size:2.05rem;line-height:1.2;margin:.35rem 0 .6rem;letter-spacing:-.015em}
.subtitle{font-size:1.12rem;color:var(--muted);margin:0}
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.9rem}
.chip{font-size:.75rem;border:1px solid var(--line);border-radius:99px;padding:.15rem .6rem;color:var(--muted)}
h2{display:flex;gap:.4rem;align-items:baseline;font-size:1.45rem;line-height:1.3;margin:3.2rem 0 .8rem;letter-spacing:-.01em;scroll-margin-top:1rem}
h2 .num{display:inline-block;min-width:2.6em;margin-right:.45rem;padding:.05rem .45rem;
  border-radius:6px;background:var(--accent-soft);color:var(--accent);font-size:.8em;text-align:center}
h3{font-size:1.1rem;margin:2rem 0 .5rem}
p,li{max-width:74ch}
a{color:var(--accent)}
strong{font-weight:650}
code{font-family:var(--mono);font-size:.88em;background:var(--soft);padding:.08em .35em;border-radius:4px}
pre{position:relative;font-family:var(--mono);font-size:.82rem;line-height:1.45;
  background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:1rem 1.1rem;overflow-x:auto;white-space:pre}
pre code{background:none;padding:0;font-size:inherit}
pre[data-lang]{padding-top:2rem}
pre[data-lang]::before{content:attr(data-lang);position:absolute;top:.45rem;left:1.1rem;
  font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
pre.ascii{line-height:1.25;background:var(--soft)}
.copy{position:absolute;top:.3rem;right:.4rem;font:inherit;font-size:.7rem;
  border:1px solid var(--line);background:var(--bg);color:var(--muted);
  border-radius:6px;padding:.1rem .5rem;cursor:pointer}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:1.2rem 0;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:.45rem .6rem;text-align:left;vertical-align:top}
th{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.why{font-size:1.06rem;border-left:3px solid var(--accent);padding:.1rem 0 .1rem 1rem;margin:1rem 0 1.4rem}
.keypoints{display:grid;gap:.5rem;margin:1.8rem 0;padding:1rem 1.1rem;
  border:1px solid var(--line);border-radius:12px;background:var(--card)}
.keypoints p{margin:0;padding-left:1.9rem;position:relative}
.keypoints p::before{position:absolute;left:0;top:0;font-weight:700}
.remember::before{content:"★";color:var(--accent)}
.trap::before{content:"⚠";color:var(--bad)}
.try::before{content:"▶";color:var(--ok)}
.callout{margin:1.4rem 0;padding:.8rem 1rem;border-radius:10px;border:1px solid var(--line);background:var(--soft)}
.callout.tip{background:var(--ok-soft);border-color:transparent}
.callout.warn{background:var(--warn-soft);border-color:transparent}
/* What Mission HQ found reads as part of the lesson, not as a box bolted on
   it: "why it is explicit, let it be part". The kind is kept in the markup so
   the claims run can still find every added paragraph and check it, and it is
   invisible to him. A correction keeps one quiet mark, because knowing the
   original said something else is part of the teaching. */
.addition{margin:1.2rem 0}
.addition[data-kind=correction]{border-left:2px solid var(--line);padding-left:1rem}
.addition>:first-child{margin-top:0}.addition>:last-child{margin-bottom:0}
p[data-added]{margin:1rem 0}
figure.diagram{margin:2rem 0;padding:1rem;border:1px solid var(--line);border-radius:12px;background:var(--card)}
figure.diagram svg{width:100%;height:auto;display:block}
figure.diagram svg text{fill:var(--fg);font-family:inherit}
figcaption{font-size:.85rem;color:var(--muted);margin-top:.6rem}
figure.diagram button,.steps-nav button,.tabs-nav button,.toggle-fig button{font:inherit;font-size:.82rem;
  padding:.3rem .8rem;border-radius:8px;border:1px solid var(--line);background:var(--bg);
  color:var(--fg);cursor:pointer;margin:.5rem .3rem 0 0}
button.on{background:var(--fg)!important;color:var(--bg)!important;border-color:var(--fg)!important}
.compare{display:grid;gap:.8rem;margin:1.4rem 0}
@media (min-width:760px){.compare{grid-template-columns:1fr 1fr}}
.compare>div{border-radius:10px;padding:.8rem 1rem;border:1px solid var(--line);min-width:0}
.compare>div::before{display:block;font-size:.72rem;font-weight:700;letter-spacing:.08em;margin-bottom:.3rem}
.wrong{background:var(--bad-soft)}.wrong::before{content:"✗ WRONG";color:var(--bad)}
.right{background:var(--ok-soft)}.right::before{content:"✓ RIGHT";color:var(--ok)}
.steps{counter-reset:s;list-style:none;padding:0}
.steps>li{counter-increment:s;position:relative;padding:.6rem 0 .6rem 2.6rem;border-left:2px solid var(--line);margin-left:.9rem}
.steps>li::before{content:counter(s);position:absolute;left:-.95rem;top:.55rem;width:1.8rem;height:1.8rem;
  border-radius:50%;background:var(--accent);color:#fff;font-size:.8rem;display:grid;place-items:center}
.steps.stepping>li{display:none}.steps.stepping>li.show{display:block}
.tabs-nav{border-bottom:1px solid var(--line);margin-top:1.2rem}
.tabs>[data-tab]{padding:.6rem 0}.tabs.ready>[data-tab]:not(.show){display:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.6rem;margin:1.4rem 0}
.stat{border:1px solid var(--line);border-radius:10px;padding:.7rem .9rem;background:var(--card)}
.stat b{display:block;font-size:1.35rem;line-height:1.2}
.stat span{font-size:.8rem;color:var(--muted)}
.bars{margin:1.4rem 0;display:grid;gap:.45rem}
.bar{display:grid;grid-template-columns:8rem 1fr 6rem;gap:.6rem;align-items:center;font-size:.85rem}
.bar::before{content:attr(data-label);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar::after{content:attr(data-value);text-align:right;font-family:var(--mono)}
.bar i{display:block;height:.7rem;border-radius:4px;background:var(--accent);width:calc(var(--v,0)*1%)}
.timeline{list-style:none;padding:0;border-left:2px solid var(--line);margin:1.4rem 0 1.4rem .4rem}
.timeline li{position:relative;padding:.25rem 0 .25rem 1.3rem}
.timeline li::before{content:"";position:absolute;left:-.4rem;top:.75rem;width:.7rem;height:.7rem;border-radius:50%;background:var(--accent)}
.timeline time{font-family:var(--mono);font-size:.8rem;color:var(--muted);margin-right:.5rem}
.exercises{list-style:none;padding:0}
.exercises>li{border:1px solid var(--line);border-radius:10px;padding:.8rem 1rem;margin:.7rem 0;background:var(--card)}
.exercises>li:has(input:checked){opacity:.6}
.exercises label{cursor:pointer}
.tag{display:inline-block;font-size:.7rem;border-radius:99px;padding:0 .5rem;margin-left:.3rem;
  background:var(--soft);color:var(--muted);vertical-align:middle}
.tag.break{background:var(--bad-soft);color:var(--bad)}
details.answer{margin:.8rem 0;border:1px solid var(--line);border-radius:10px;padding:.2rem 1rem;background:var(--card)}
details.answer summary{cursor:pointer;font-weight:600;padding:.5rem 0;color:var(--accent)}
pre.cheatsheet{background:var(--accent-soft);border-color:transparent}
.sources li{margin:.4rem 0}
hr{border:0;border-top:1px solid var(--line);margin:3rem 0}
/* --- richer pieces, so a lesson can show a mechanism instead of describing
   it: a number he can move, a figure he can step through, a card that carries
   one idea. All of it works inside the sandboxed frame: no network, no
   storage, inline script only. --- */
.cards{display:grid;gap:.8rem;margin:1.4rem 0}
@media (min-width:720px){.cards[data-cols="2"]{grid-template-columns:1fr 1fr}
  .cards[data-cols="3"]{grid-template-columns:repeat(3,1fr)}}
.card{border:1px solid var(--line);border-radius:12px;padding:.9rem 1rem;background:var(--card)}
.card h4{margin:0 0 .3rem;font-size:.95rem}
.card p{margin:0;font-size:.92rem;color:var(--muted)}
.lab{border:1px solid var(--line);border-left:3px solid var(--ok);border-radius:10px;
  padding:.8rem 1rem;margin:1.4rem 0;background:var(--card)}
.badge{display:inline-block;font-size:.7rem;font-weight:600;letter-spacing:.04em;
  text-transform:uppercase;border-radius:99px;padding:.1rem .55rem;background:var(--soft);color:var(--muted)}
kbd{font-family:var(--mono);font-size:.8em;border:1px solid var(--line);border-bottom-width:2px;
  border-radius:5px;padding:.05em .35em;background:var(--card)}
/* A number he can move. Inputs drive the outputs through kit.calc. */
.calc{border:1px solid var(--line);border-radius:12px;padding:1rem 1.1rem;margin:1.6rem 0;background:var(--card)}
.calc h4{margin:0 0 .6rem;font-size:.95rem}
.calc label{display:grid;grid-template-columns:11rem 1fr 5rem;gap:.6rem;align-items:center;
  font-size:.85rem;margin:.45rem 0}
.calc input[type=range]{width:100%;accent-color:var(--accent)}
.calc output,.calc .val{font-family:var(--mono);font-size:.85rem;text-align:right}
.calc .result{margin-top:.8rem;padding-top:.7rem;border-top:1px solid var(--line);
  font-size:1.05rem;display:flex;flex-wrap:wrap;gap:.4rem 1.2rem}
.calc .result b{font-family:var(--mono)}
.calc .note{font-size:.8rem;color:var(--muted);margin-top:.5rem}
/* Something he can flip between: before and after, wrong and right. */
.toggle-fig{border:1px solid var(--line);border-radius:12px;padding:1rem;margin:1.6rem 0;background:var(--card)}
.toggle-fig .views>[data-view]{display:none}
.toggle-fig .views>[data-view].show{display:block}
.legend{display:flex;flex-wrap:wrap;gap:.8rem;font-size:.8rem;color:var(--muted);margin-top:.6rem}
.legend i{display:inline-block;width:.8rem;height:.8rem;border-radius:3px;margin-right:.3rem;vertical-align:-1px}
h2 a.anchor,h3 a.anchor{opacity:0;text-decoration:none;color:var(--muted);font-weight:400;margin-left:.3rem}
h2:hover a.anchor,h3:hover a.anchor{opacity:1}
@media print{nav.toc,#progress,.copy{display:none}}
"""

KIT_API = """
// kit: the few helpers a figure needs, so a lesson's own script stays short.
// It is defined in the head, before any body script runs, so a figure can
// call kit.calc right where it is written.
(function(){
  var ready=[], fired=false;
  function whenReady(fn){ if(fired) fn(); else ready.push(fn); }
  document.addEventListener('DOMContentLoaded',function(){
    fired=true; ready.forEach(function(fn){ fn(); }); ready=[];
  });
  window.kit={
    $:function(sel,root){return (root||document).querySelector(sel);},
    $$:function(sel,root){return [].slice.call((root||document).querySelectorAll(sel));},
    fmt:function(n,digits){
      if(n===null||n===undefined||isNaN(n)) return '-';
      return Number(n).toLocaleString('en-US',{maximumFractionDigits:digits===undefined?2:digits});
    },
    // calc('#id', function(v){ return {label: value, ...} }): every input in
    // the box is read by name, and every [data-out] is filled from the result.
    calc:function(sel,compute){
      whenReady(function(){ window.kit._calc(sel,compute); });
    },
    _calc:function(sel,compute){
      var box=typeof sel==='string'?document.querySelector(sel):sel; if(!box) return;
      var inputs=[].slice.call(box.querySelectorAll('input,select'));
      function run(){
        var v={};
        inputs.forEach(function(i){ v[i.name||i.id]=i.type==='checkbox'?i.checked:(isNaN(+i.value)?i.value:+i.value); });
        inputs.forEach(function(i){
          var shown=box.querySelector('[data-val="'+(i.name||i.id)+'"]');
          if(shown) shown.textContent=i.type==='range'?window.kit.fmt(+i.value,0):i.value;
        });
        var out=compute(v)||{};
        Object.keys(out).forEach(function(k){
          var el=box.querySelector('[data-out="'+k+'"]');
          if(el) el.textContent=out[k];
        });
      }
      inputs.forEach(function(i){ i.addEventListener('input',run); });
      run();
    }
  };
})();
"""

KIT_JS = """
(function(){
  var main=document.querySelector('main'); if(!main) return;
  // Contents: built from the page's own h2s, so it can never disagree with them.
  var nav=document.querySelector('nav.toc'), heads=[].slice.call(main.querySelectorAll('h2'));
  heads.forEach(function(h,i){
    if(!h.id) h.id='s'+(i+1)+'-'+h.textContent.toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,40);
    if(nav){var a=document.createElement('a');a.href='#'+h.id;a.textContent=h.textContent;nav.appendChild(a);}
  });
  var links=nav?[].slice.call(nav.querySelectorAll('a')):[];
  var bar=document.getElementById('progress');
  function onScroll(){
    var doc=document.documentElement, max=doc.scrollHeight-doc.clientHeight;
    if(bar) bar.style.width=(max>0?doc.scrollTop/max*100:0)+'%';
    var cur=0; heads.forEach(function(h,i){ if(h.getBoundingClientRect().top<120) cur=i; });
    links.forEach(function(a,i){ a.classList.toggle('on',i===cur); });
  }
  window.addEventListener('scroll',onScroll,{passive:true}); onScroll();

  // Views: one visible at a time, driven by buttons carrying data-show.
  [].forEach.call(main.querySelectorAll('.toggle-fig'),function(box){
    var views=[].slice.call(box.querySelectorAll('[data-view]'));
    var buttons=[].slice.call(box.querySelectorAll('[data-show]'));
    function pick(name){
      views.forEach(function(v){ v.classList.toggle('show', v.getAttribute('data-view')===name); });
      buttons.forEach(function(b){ b.classList.toggle('on', b.getAttribute('data-show')===name); });
    }
    buttons.forEach(function(b){ b.onclick=function(){ pick(b.getAttribute('data-show')); }; });
    if(views.length) pick(views[0].getAttribute('data-view'));
  });
  // A link on every heading, so he can send himself back to one section.
  heads.concat([].slice.call(main.querySelectorAll('h3'))).forEach(function(h){
    if(!h.id||h.querySelector('a.anchor')) return;
    var a=document.createElement('a');a.className='anchor';a.href='#'+h.id;a.textContent='#';
    a.setAttribute('aria-label','link to this section');h.appendChild(a);
  });
  // Copy buttons. The clipboard can be refused inside the sandbox; say so.
  [].forEach.call(main.querySelectorAll('pre'),function(pre){
    var code=pre.querySelector('code'); var lang=code&&code.getAttribute('data-lang');
    if(lang&&!pre.hasAttribute('data-lang')) pre.setAttribute('data-lang',lang);
    var b=document.createElement('button');b.type='button';b.className='copy';b.textContent='Copy';
    b.onclick=function(){
      var t=pre.innerText.replace(/Copy$/,'');
      try{navigator.clipboard.writeText(t).then(function(){b.textContent='Copied';},function(){b.textContent='Select + copy';});}
      catch(e){b.textContent='Select + copy';}
      setTimeout(function(){b.textContent='Copy';},1600);
    };
    pre.appendChild(b);
  });
  // Bars: the value lives in --v; the <i> is the drawn part.
  [].forEach.call(main.querySelectorAll('.bar'),function(el){
    if(!el.querySelector('i')) el.appendChild(document.createElement('i'));
  });
  // Steps: one at a time, with a way to see them all.
  [].forEach.call(main.querySelectorAll('ol.steps'),function(ol){
    var items=[].slice.call(ol.children); if(items.length<2) return;
    var i=0, navEl=document.createElement('div'); navEl.className='steps-nav';
    function btn(label,fn){var b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=fn;navEl.appendChild(b);return b;}
    function show(){items.forEach(function(li,k){li.classList.toggle('show',k<=i);});
      count.textContent='Step '+(i+1)+' of '+items.length;}
    ol.classList.add('stepping');
    btn('Previous',function(){if(i>0){i--;show();}});
    btn('Next',function(){if(i<items.length-1){i++;show();}});
    btn('Show all',function(){ol.classList.remove('stepping');navEl.remove();});
    var count=document.createElement('span');count.style.cssText='font-size:.8rem;color:var(--muted);margin-left:.4rem';
    navEl.appendChild(count); ol.parentNode.insertBefore(navEl,ol.nextSibling); show();
  });
  // Tabs: labels come from data-tab.
  [].forEach.call(main.querySelectorAll('.tabs'),function(box){
    var panes=[].slice.call(box.children).filter(function(c){return c.hasAttribute('data-tab');});
    if(!panes.length) return;
    var navEl=document.createElement('div');navEl.className='tabs-nav';
    var buttons=panes.map(function(p,k){var b=document.createElement('button');b.type='button';
      b.textContent=p.getAttribute('data-tab');b.onclick=function(){pick(k);};navEl.appendChild(b);return b;});
    function pick(k){panes.forEach(function(p,j){p.classList.toggle('show',j===k);});
      buttons.forEach(function(b,j){b.classList.toggle('on',j===k);});}
    box.insertBefore(navEl,box.firstChild); box.classList.add('ready'); pick(0);
  });
})();
"""

_DOCTYPE_RE = re.compile(r"^\s*<!doctype", re.IGNORECASE)


def is_full_document(html: str) -> bool:
    return bool(_DOCTYPE_RE.match(html))


def wrap_page(
    body: str,
    *,
    title: str,
    eyebrow: str = "",
    subtitle: str = "",
    chips: list[str] | None = None,
) -> str:
    """One lesson page: the kit's head, a contents rail, the hero, the body.

    A body that is already a whole document is returned unchanged, so older
    pages and hand-written ones keep working.
    """
    if is_full_document(body):
        return body
    esc = html_lib.escape
    chip_html = "".join(f'<span class="chip">{esc(c)}</span>' for c in (chips or []) if c)
    hero = (
        '<header class="hero">'
        + (f'<div class="eyebrow">{esc(eyebrow)}</div>' if eyebrow else "")
        + f"<h1>{esc(title)}</h1>"
        + (f'<p class="subtitle">{esc(subtitle)}</p>' if subtitle else "")
        + (f'<div class="chips">{chip_html}</div>' if chip_html else "")
        + "</header>"
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>{KIT_CSS}</style>\n"
        f"<script>{KIT_API}</script>\n</head>\n<body>\n"
        '<div id="progress"></div>\n<div class="layout">\n'
        '<nav class="toc" aria-label="Contents"><b>In this lesson</b></nav>\n'
        f"<main>\n{hero}\n{body}\n</main>\n</div>\n<script>{KIT_JS}</script>\n"
        "</body>\n</html>\n"
    )
