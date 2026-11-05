"""Build the self-contained interactive demo page.

Runs every scenario through the real library and embeds the actual
run records into demo/index.html. No build step, no dependencies:
the output is one static file.

The embedded JSON includes the poison ids (a fully self-contained
page cannot avoid shipping its own answers), but nothing rendered
before the reveal identifies the poisoned write.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mpolab import run_all  # noqa: E402

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memory Poisoning Lab - can you spot the write that turns the agent?</title>
<style>
  :root { --ink:#251f21; --ink2:#585254; --line:#eae9ea; --bg:#f4efec; --card:#ffffff;
          --teal:#73a89a; --red:#ed313e; --amber:#b97900; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:20px 16px 48px; }
  h1 { font-size:24px; margin:12px 0 4px; }
  .sub { color:var(--ink2); margin:0 0 4px; }
  .caveat { background:#fff; border:1px solid var(--line); border-radius:10px; padding:10px 12px;
            color:var(--ink2); font-size:13px; margin:14px 0; }
  .tabs { display:flex; gap:8px; margin:18px 0 12px; flex-wrap:wrap; }
  .tabs button { flex:1; min-width:120px; border:1px solid var(--line); background:#fff; color:var(--ink);
                 padding:9px 10px; border-radius:8px; cursor:pointer; font-size:14px; }
  .tabs button.active { border-color:var(--teal); box-shadow:0 0 0 2px var(--teal) inset; font-weight:600; }
  .story { background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
  .story .klass { color:var(--ink2); font-size:13px; margin-top:4px; }
  .controls { display:flex; gap:8px; align-items:center; margin:14px 0; flex-wrap:wrap; }
  .controls button { border:1px solid var(--ink); background:var(--ink); color:#fff; padding:9px 16px;
                     border-radius:8px; cursor:pointer; font-size:14px; }
  .controls button.secondary { background:#fff; color:var(--ink); }
  .controls button:disabled { opacity:.35; cursor:default; }
  .hint { color:var(--ink2); font-size:13px; }
  #timeline { display:flex; flex-direction:column; gap:8px; margin:10px 0 16px; }
  .write { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px;
           cursor:pointer; transition:border-color .15s; }
  .write .meta { display:flex; justify-content:space-between; font-size:12px; color:var(--ink2); }
  .write .text { margin-top:4px; }
  .write.guess { border-color:var(--amber); box-shadow:0 0 0 2px var(--amber) inset; }
  .write.poison { border-color:var(--red); box-shadow:0 0 0 2px var(--red) inset; }
  .write.quarantined { opacity:.75; border-style:dashed; }
  .compacted-banner { background:#fdf3dd; border:1px solid #e8cf9a; border-radius:10px;
    color:#8a5a00; font-size:12.5px; text-align:center; padding:10px 12px; }
  .tag { display:inline-block; font-size:11px; border-radius:6px; padding:1px 7px; margin-left:6px; }
  .tag.owner { background:#e3efeb; color:#2f6b5c; }
  .tag.tool_untrusted { background:#f6e3e4; color:#a1222c; }
  .tag.summary { background:#fdf3dd; color:#8a5a00; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin:10px 0; }
  .panel h2 { font-size:16px; margin:0 0 6px; }
  .verdict { font-size:15px; margin:4px 0; }
  .bad { color:var(--red); font-weight:600; }
  .good { color:#2f6b5c; font-weight:600; }
  .aggregate { display:flex; gap:10px; margin:16px 0; flex-wrap:wrap; }
  .aggregate div { flex:1; min-width:140px; background:#fff; border:1px solid var(--line); border-radius:10px;
                   padding:10px 12px; text-align:center; }
  .aggregate b { display:block; font-size:20px; }
  footer { color:var(--ink2); font-size:12.5px; margin-top:22px; }
  .hidden { display:none; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Memory Poisoning Lab</h1>
  <p class="sub">Can you spot the write that turns the agent?</p>
  <div class="caveat">A teaching replay on synthetic data with a scripted agent. It demonstrates the
  mechanics of memory poisoning and repair from published research; it is not evidence about the
  safety of any real LLM or production memory system. Every number on this page is regenerated from
  the repo's test suite.</div>
  <div class="tabs" id="tabs"></div>
  <div class="story">
    <div id="storyline"></div>
    <div class="klass" id="attackclass"></div>
  </div>
  <div class="controls">
    <button id="play">Play the writes</button>
    <button id="reveal" class="secondary" disabled>Reveal the poison</button>
    <button id="defend" class="secondary hidden">Run defenses + repair</button>
    <button id="reset" class="secondary">Reset</button>
    <span class="hint" id="hint"></span>
  </div>
  <div id="timeline"></div>
  <div id="decision" class="panel hidden"></div>
  <div id="defense" class="panel hidden"></div>
  <div class="aggregate" id="aggregate"></div>
  <footer>
    Attack classes from published memory-poisoning research (MemSecBench; AgentPoison; see README).
    Scripted agent, synthetic targets, deterministic seeds. The page ships its own run data, so the
    answer exists in the source - nothing visible before the reveal identifies the poisoned write.
  </footer>
</div>
<script>
const DATA = __DATA__;
const tabs = document.getElementById('tabs');
const timeline = document.getElementById('timeline');
const hint = document.getElementById('hint');
const playBtn = document.getElementById('play');
const revealBtn = document.getElementById('reveal');
const defendBtn = document.getElementById('defend');
const resetBtn = document.getElementById('reset');
const decisionPanel = document.getElementById('decision');
const defensePanel = document.getElementById('defense');

let scenarioId = 'A1';
let shown = 0, timer = null, guess = null, revealed = false;

function scenario() { return DATA.scenarios[scenarioId]; }

function buildTabs() {
  tabs.innerHTML = '';
  for (const id of Object.keys(DATA.scenarios)) {
    const b = document.createElement('button');
    b.textContent = id + ' - ' + DATA.scenarios[id].name;
    b.className = id === scenarioId ? 'active' : '';
    b.onclick = () => { scenarioId = id; reset(); };
    tabs.appendChild(b);
  }
}

function cardFor(w) {
  const div = document.createElement('div');
  div.className = 'write';
  div.dataset.id = w.id;
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.innerHTML = '<span>write #' + w.id + ' - step ' + w.step + '</span><span class="prov"></span>';
  const text = document.createElement('div');
  text.className = 'text';
  text.textContent = w.text;
  div.appendChild(meta); div.appendChild(text);
  div.onclick = () => {
    if (revealed) return;
    document.querySelectorAll('.write').forEach(c => c.classList.remove('guess'));
    div.classList.add('guess');
    guess = w.id;
    revealBtn.disabled = false;
    hint.textContent = 'Guess locked on write #' + w.id + '.';
  };
  return div;
}

function play() {
  playBtn.disabled = true;
  const writes = scenario().pre_writes || scenario().writes;
  timer = setInterval(() => {
    if (shown >= writes.length) {
      clearInterval(timer);
      if (scenario().compacted) { compact(); return; }
      hint.textContent = 'One of these writes is the poison. Click a card to lock your guess.';
      return;
    }
    timeline.appendChild(cardFor(writes[shown]));
    shown++;
  }, 450);
}

function compact() {
  // The teaching moment: episodic writes are dropped, preference-shaped
  // sentences survive as trust='summary' entries. Cards swap in place.
  const banner = document.createElement('div');
  banner.className = 'compacted-banner';
  banner.textContent = 'memory.compact() runs: episodic writes are summarized, owner policy is kept verbatim';
  timeline.innerHTML = '';
  timeline.appendChild(banner);
  const finalWrites = scenario().writes;
  finalWrites.forEach(w => timeline.appendChild(cardFor(w)));
  hint.textContent = 'One of these writes is the poison. Click a card to lock your guess.';
}

function reveal() {
  revealed = true;
  const s = scenario();
  const poison = new Set(s.poison_ids);
  let correct = poison.has(guess);
  document.querySelectorAll('.write').forEach(c => {
    const id = Number(c.dataset.id);
    const w = s.writes.find(x => x.id === id);
    const prov = c.querySelector('.prov');
    prov.innerHTML = '<span class="tag ' + w.origin + '">' + w.origin + '</span>' +
      (w.trust !== w.origin ? '<span class="tag ' + w.trust + '">labeled ' + w.trust + '</span>' : '') +
      (w.quarantined ? '<span class="tag tool_untrusted">quarantined</span>' : '');
    if (poison.has(id)) c.classList.add('poison');
  });
  decisionPanel.classList.remove('hidden');
  const ownerLine = s.subject === 'courier'
    ? 'The owner never set a courier policy - the fallback is <b>' + s.baseline + '</b>.'
    : 'Owner policy says <b>' + s.baseline + '</b>.';
  const action = s.subject === 'courier' ? 'booked delivery with' : 'ordered from';
  decisionPanel.innerHTML = '<h2>What the naive agent did</h2>' +
    '<p class="verdict">' + (correct ? '<span class="good">You found it.</span> ' : '<span class="bad">Not that one.</span> ') +
    'The poison was write ' + s.poison_ids.map(i => '#' + i).join(', ') + ' (' + s.attack_class.toLowerCase() + ').</p>' +
    '<p class="verdict">' + ownerLine + ' With no defenses, the agent ' + action + ' ' +
    '<span class="bad">' + s.naive[s.subject] + '</span> - steered by write #' + s.naive.influenced_by + '.</p>';
  revealBtn.disabled = true;
  defendBtn.classList.remove('hidden');
  hint.textContent = '';
}

function defend() {
  const s = scenario();
  defendBtn.disabled = true;
  defensePanel.classList.remove('hidden');
  const action = s.subject === 'courier' ? 'books delivery with' : 'orders from';
  let repairLine;
  if (s.repair.restored) {
    const removed = s.repair.removed_ids.map(i => '#' + i).join(', ');
    repairLine = '<p class="verdict">Repair pass removed write ' + removed + ' - policy: <i>' + s.repair.policy +
      '</i>. The decision returns to <span class="good">' + s.repair.decision_after + '</span>.</p>';
  } else {
    const a = s.repair.anchored;
    const removedA = a.removed_ids.map(i => '#' + i).join(', ');
    repairLine = '<p class="verdict"><span class="bad">Repair pass removed nothing.</span> The graft contradicts no owner claim - ' +
      'the documented limit of conflict-scoped repair (<i>' + s.repair.policy + '</i>).</p>' +
      '<p class="verdict">Once the owner states a policy ("' + a.owner_write + '"), the same pass removes write ' +
      removedA + ' and the decision returns to <span class="good">' + a.decision_after + '</span>.</p>';
  }
  defensePanel.innerHTML = '<h2>With trust partitioning, write screening and repair</h2>' +
    '<p class="verdict">Origin-aware recall and write-time quarantine: the agent ' + action + ' ' +
    '<span class="good">' + s.defended[s.subject] + '</span>. The attack is blocked.</p>' +
    repairLine;
}

function reset() {
  clearInterval(timer);
  shown = 0; guess = null; revealed = false;
  timeline.innerHTML = '';
  decisionPanel.classList.add('hidden');
  defensePanel.classList.add('hidden');
  defendBtn.classList.add('hidden');
  defendBtn.disabled = false;
  revealBtn.disabled = true;
  playBtn.disabled = false;
  const s = scenario();
  document.getElementById('storyline').innerHTML = s.subject === 'courier'
    ? 'The agent reorders printer paper and books the delivery. Owner policy sets the vendor (<b>OfficeDepot</b>) but says nothing about couriers. ' +
      'Watch the memory writes arrive, then call the poison before the reveal.'
    : 'The agent reorders printer paper for the office. Owner policy: <b>' + s.baseline + '</b>. ' +
      'Watch the memory writes arrive, then call the poison before the reveal.';
  document.getElementById('attackclass').textContent = 'Attack class: ' + s.attack_class + '.';
  hint.textContent = '';
  buildTabs();
}

function aggregate() {
  const a = DATA.aggregate;
  document.getElementById('aggregate').innerHTML =
    '<div><b>' + a.naive_flips + '/' + a.total + '</b>attacks flipped the undefended agent</div>' +
    '<div><b>' + a.defended_blocks + '/' + a.total + '</b>blocked with defenses on</div>' +
    '<div><b>' + a.repairs_restored + '/' + a.total + '</b>restored by the repair pass</div>' +
    (a.repair_limitations.length
      ? '<div><b>' + a.repair_limitations.join(', ') + '</b>graft needs an owner-stated policy before repair can remove it</div>'
      : '');
}

// Deep links for testing and sharing a state: #reveal=A1, #defense=A2
function autodrive() {
  const h = location.hash || '';
  const m = h.match(/#(play|reveal|defense)=(A1|A2|A3|A4|A5|A6)/);
  if (!m) return;
  scenarioId = m[2]; reset();
  if (scenario().compacted) {
    const banner = document.createElement('div');
    banner.className = 'compacted-banner';
    banner.textContent = 'memory.compact() runs: episodic writes are summarized, owner policy is kept verbatim';
    timeline.appendChild(banner);
  }
  const writes = scenario().writes;
  while (shown < writes.length) { timeline.appendChild(cardFor(writes[shown])); shown++; }
  playBtn.disabled = true;
  if (m[1] === 'play') return;
  guess = scenario().poison_ids[0];
  revealBtn.disabled = false;
  reveal();
  if (m[1] === 'defense') defend();
}

aggregate();
reset();
autodrive();
</script>
</body>
</html>
"""


def main() -> str:
    data = run_all()
    html = TEMPLATE.replace("__DATA__", json.dumps(data))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo", "index.html")
    with open(out, "w") as fh:
        fh.write(html)
    return out


if __name__ == "__main__":
    print(main())
