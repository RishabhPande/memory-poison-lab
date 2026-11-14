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
  .evidence { margin:20px 0; border:1px solid var(--ink); border-radius:12px; overflow:hidden; background:#fff; }
  .evidence-head { padding:18px; background:var(--ink); color:#fff; }
  .evidence-head .eyebrow { color:#b2d4ca; font-size:11px; text-transform:uppercase; letter-spacing:.12em; font-weight:600; }
  .evidence h2 { font-size:22px; margin:3px 0 6px; letter-spacing:-.025em; }
  .evidence-head p { margin:0; font-size:13px; color:#e4dcdf; }
  .trace-controls { display:flex; flex-wrap:wrap; gap:6px; padding:14px 16px 6px; }
  .trace-controls button, #download { min-height:44px; border:1px solid var(--line); border-radius:6px;
    background:#fff; color:var(--ink); padding:8px 12px; font:inherit; font-size:13px; cursor:pointer; }
  .trace-controls button[aria-pressed=true] { background:#e3efeb; border-color:var(--teal); font-weight:600; }
  .trace-summary { padding:10px 16px 14px; border-bottom:1px solid var(--line); overflow-wrap:anywhere; }
  .trace-summary strong { display:block; font-size:21px; line-height:1.3; margin:4px 0; }
  .trace-summary small { color:var(--ink2); display:block; }
  .trace-stats { display:flex; gap:20px; flex-wrap:wrap; margin-top:10px; font-size:12px; color:var(--ink2); }
  .trace-stats b { color:var(--ink); font-size:17px; margin-right:4px; }
  .recall-strip { display:flex; flex-wrap:wrap; gap:5px; margin-top:14px; }
  .recall-slot { min-width:48px; border:1px solid var(--line); background:#f4efec; border-radius:4px; padding:5px 7px; font-size:11px; text-align:center; }
  .recall-slot b { display:block; font-size:13px; }
  .recall-slot.winner { background:#e3efeb; border-color:#73a89a; font-weight:600; }
  .recall-note { font-size:12px; color:var(--ink2); margin-top:8px; }
  .trace-row { margin:10px 14px; border:1px solid var(--line); border-left:3px solid #c0bebf; border-radius:5px; overflow-wrap:anywhere; }
  .trace-row.selected { border-left-color:#2f6b5c; background:#f1f7f4; }
  .trace-row.quarantined, .trace-row.untrusted_origin { border-left-color:var(--red); }
  .trace-row summary { cursor:pointer; padding:12px; font-size:13px; min-height:44px; }
  .trace-row .reason { display:block; color:var(--ink2); margin:4px 0 0 18px; font-size:12px; }
  .trace-row .entry-body { padding:0 12px 12px; font-size:13px; }
  .trace-row dl { display:grid; grid-template-columns:90px minmax(0,1fr); gap:3px 8px; margin:10px 0 0; font-size:12px; }
  .trace-row dt { color:var(--ink2); } .trace-row dd { margin:0; }
  .trace-foot { margin:12px 16px; font-size:12px; color:var(--ink2); }
  #download { margin-top:10px; font-weight:600; }
  button:focus-visible, summary:focus-visible { outline:3px solid #2f6b5c; outline-offset:3px; }
  @media(max-width:420px) { .evidence h2 { font-size:20px; } .trace-controls button { flex:1 1 40%; } }
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
  <section class="evidence hidden" id="evidence" aria-label="Decision evidence">
    <header class="evidence-head">
      <div class="eyebrow">Inside the recall window</div>
      <h2>What reached the decision?</h2>
      <p>Follow the stored write, its recorded origin, and the policy that chose or rejected it.</p>
    </header>
    <div class="trace-controls" id="trace-controls" aria-label="Replay phase"></div>
    <div id="trace-summary" class="trace-summary" aria-live="polite"></div>
    <div id="trace-rows"></div>
    <div class="trace-foot">Ranks show actual recall order, not relevance scores. A write outside recall may be irrelevant or displaced.
      Recorded origin is not proof of pre-import provenance. Scripted replay, not an LLM evaluation.<br>
      <button id="download" type="button">Download this replay (.json)</button>
    </div>
  </section>
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
let defensesShown = false, tracePhase = 'naive';

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
  renderTrace('naive');
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
  defensesShown = true;
  renderTrace('defended');
}

function reset() {
  clearInterval(timer);
  shown = 0; guess = null; revealed = false; defensesShown = false; tracePhase = 'naive';
  document.getElementById('evidence').classList.add('hidden');
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

const traceLabels = {naive:'No defenses', defended:'Defenses on', repaired:'Repair alone', anchored:'Owner + repair'};
const reasonLabels = {
  selected:'Selected by the decision policy', lower_priority:'Eligible, but lower confidence or older than the winner',
  quarantined:'Write screening quarantined it before recall', not_recalled:'Stored, but outside this recall window',
  not_preference:'Recalled fact, not a preference', untrusted_origin:'Recalled, but recorded origin is not owner',
  no_subject_claim:'Recalled, but no parseable claim for this subject'
};
function element(tag, text, klass) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (klass) node.className = klass;
  return node;
}
function renderTrace(phase) {
  tracePhase = phase;
  const s = scenario();
  const trace = phase === 'anchored' ? s.repair.anchored.trace : s.traces[phase];
  document.getElementById('evidence').classList.remove('hidden');
  const controls = document.getElementById('trace-controls'); controls.replaceChildren();
  const phases = defensesShown ? ['naive','defended','repaired'] : ['naive'];
  if (defensesShown && s.repair.anchored) phases.push('anchored');
  for (const key of phases) {
    const button = element('button', traceLabels[key]);
    button.type = 'button'; button.setAttribute('aria-pressed', String(phase === key));
    button.onclick = () => renderTrace(key); controls.appendChild(button);
  }
  const summary = document.getElementById('trace-summary'); summary.replaceChildren();
  summary.appendChild(element('small', traceLabels[phase] + ' / ' + trace.subject));
  summary.appendChild(element('strong', trace.decision[trace.subject]));
  summary.appendChild(element('small', trace.decision.influenced_by === null
    ? 'Fallback: no eligible recalled claim.' : 'Chosen from write #' + trace.decision.influenced_by + '. Policy: highest confidence, then newest write.'));
  summary.appendChild(element('small', 'Recall query: "' + trace.query + '"'));
  const stats = element('div', undefined, 'trace-stats');
  for (const [n, label] of [[trace.entries.length,'stored'],[trace.decision.recalled_ids.length,'recalled / limit ' + trace.recall_limit],
    [trace.entries.filter(e => e.reason === 'quarantined').length,'quarantined']]) {
    const stat = element('span'); stat.append(element('b',String(n)), document.createTextNode(label)); stats.appendChild(stat);
  }
  summary.appendChild(stats);
  const strip = element('div',undefined,'recall-strip'); strip.setAttribute('aria-label','Recall window in rank order');
  trace.decision.recalled_ids.forEach((id,index) => {
    const slot = element('div',undefined,'recall-slot' + (id === trace.decision.influenced_by ? ' winner' : ''));
    slot.append(element('span','Rank ' + (index+1)),element('b','#' + id)); strip.appendChild(slot);
  });
  summary.appendChild(strip);
  const missingOwners = trace.entries.filter(e => e.origin === 'owner' && e.reason === 'not_recalled').map(e => '#' + e.id);
  if (missingOwners.length) summary.appendChild(element('div','Owner writes outside recall: ' + missingOwners.join(', '), 'recall-note'));
  const rows = document.getElementById('trace-rows'); rows.replaceChildren();
  const ordered = [...trace.entries].sort((a,b) => (a.recall_rank ?? Infinity) - (b.recall_rank ?? Infinity) || a.id-b.id);
  for (const entry of ordered) {
    const row = element('details', undefined, 'trace-row ' + entry.reason);
    row.dataset.entry = entry.id; row.dataset.reason = entry.reason;
    row.open = entry.reason === 'selected';
    const heading = element('summary', (entry.recall_rank === null ? 'Outside recall' : 'Rank ' + entry.recall_rank)
      + ' / write #' + entry.id + ' / ' + entry.origin);
    heading.appendChild(element('span', reasonLabels[entry.reason], 'reason'));
    const body = element('div', undefined, 'entry-body'); body.appendChild(element('div', entry.text));
    const metadata = element('dl');
    for (const [label,value] of [['Stored label',entry.trust],['Origin',entry.origin],['Source',entry.source || 'Not recorded'],
      ['Confidence',String(entry.confidence)],['Step',String(entry.step)]]) metadata.append(element('dt',label),element('dd',value));
    body.appendChild(metadata); row.append(heading,body); rows.appendChild(row);
  }
  if (!ordered.length) rows.appendChild(element('p','No stored writes.', 'trace-foot'));
}
function downloadReplay() {
  if (!revealed) return;
  const report = {schema_version:1, scope:'Scripted deterministic replay on synthetic targets, not an LLM evaluation.', scenario:scenario()};
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'memory-poison-lab-' + scenarioId + '.json';
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
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

playBtn.onclick = play;
revealBtn.onclick = reveal;
defendBtn.onclick = defend;
resetBtn.onclick = reset;
document.getElementById('download').onclick = downloadReplay;
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
