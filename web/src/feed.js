/* A hospital agent's own events -> staged cards (spinner -> check), reasoning, and a decision card for its person.
 * Used by each hospital console, and by the projector's Alder column (Alder's own machine). */
function AgentFeed(host, me, { post, scroll = () => {} }) {
  const q = [];
  let busy = false, round = null;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const esc = Think.esc;
  const nice = d => d ? new Date(d + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '';
  const cards = {};
  function enqueue(fn) { q.push(fn); if (!busy) drain(); }
  async function drain() { busy = true; while (q.length) { try { await q.shift()(); } catch (e) { console.error(e); } } busy = false; }
  async function card(spec, res, ms = 850) {
    const b = Think.work(spec); host.appendChild(b.el); scroll();
    await wait(ms); b.resolve(res); scroll(); await wait(450); return b;
  }
  function header(text) {
    const h = document.createElement('div');
    h.className = 'round rise';
    h.innerHTML = `<span>${esc(text)}</span>`;
    host.appendChild(h); scroll();
  }
  function decisionCard(e) {
    const a = e.advice, el = document.createElement('div');
    el.className = 'decide rise';
    const kind = e.kind, hold = a.decision === 'hold', decline = a.decision === 'decline';
    const primary = kind === 'approve'
      ? (hold ? { d: 'hold', t: `Ask everyone to wait until ${nice(a.hold_until)}`, s: 'The surgeon decides · agent advice: not this week' } : { d: 'approve', t: `Approve for ${nice(e.day)}`, s: 'Agent advice: ready' })
      : (decline ? { d: 'decline', t: "Reply: we can't wait", s: 'Agent advice · the reason stays here' } : { d: 'accept', t: 'Reply: we can wait', s: 'Agent advice' });
    const secondary = kind === 'approve' ? (hold ? { d: 'approve', t: 'Approve anyway' } : { d: 'hold', t: 'Not this week' }) : (decline ? { d: 'accept', t: 'We can wait' } : { d: 'decline', t: "We can't wait" });
    el.innerHTML = `<div class="dh">${hold ? 'Surgeon decision' : 'Your decision'}<span class="cd"></span></div>`;
    const b1 = Think.hero({ title: primary.t, sub: primary.s, onClick: () => choose(primary.d) });
    const b2 = document.createElement('button');
    b2.className = 'btn secondary'; b2.textContent = secondary.t; b2.onclick = () => choose(secondary.d);
    el.appendChild(b1); el.appendChild(b2);
    const t0 = Date.now(), cd = el.querySelector('.cd');
    const tick = setInterval(() => { const left = Math.max(0, Math.round(e.timeout - (Date.now() - t0) / 1000)); cd.textContent = hold ? '' : `sends in ${left}s`; }, 250);
    function choose(d) { post('/decision', { id: e.id, decision: d, hold_until: d === 'hold' ? a.hold_until : '' }); lock(d, 'you'); }
    function lock(d, by) {
      clearInterval(tick); el.classList.add('done');
      el.querySelectorAll('button').forEach(b => { b.disabled = true; });
      cd.textContent = by === 'countdown' ? 'sent automatically' : 'sent';
      b1.querySelector('.ht').textContent = { hold: `Asked everyone to wait until ${nice(a.hold_until)}`, approve: 'Approved', accept: 'Replied: we can wait', decline: "Replied: we can't wait" }[d] || d;
      if (d === primary.d) b1.classList.add('done');
    }
    cards[e.id] = { lock };
    host.appendChild(el); scroll();
  }
  function reasonLines(e) {
    if (e.kind === 'hold') return [`Asked to wait until ${nice(e.hold_until)}.`, e.why, e.decision === 'accept' ? '→ We can wait.' : "→ We can't wait."];
    if (e.decision === 'hold') return [`${e.patient}: ${e.why.split('.')[0]}.`, `Rule ${e.rule}: 7 days fever-free, off IV antibiotics.`, `→ Not this week. Wait until ${nice(e.hold_until)}.`];
    return [`${e.patient}'s chart is clear.`, `${e.why}.`, `→ Ready for ${nice(e.day || '2026-10-02')}.`];
  }
  function push(e) {
    if (!e || (e.who && e.who !== me)) return;
    switch (e.type) {
      case 'flower.message':
        if (e.direction === 'in') {
          const r = e.request || {};
          const t = { profiles: 'Alder asks: share donor profiles', compat: (r.donors || []).some(d => d.pair === 'ALT') ? "A stranger's kidney: who can it help?" : 'Alder asks: which donors fit your patients?',
            approve: `Alder asks: approve the ${r.plan} for ${nice(r.surgery_date)}`, hold: `${(r.from || 'A hospital').replace(/^./, c => c.toUpperCase())} asks everyone to wait until ${nice(r.hold_until)}` }[e.kind] || e.kind;
          round = e.kind; enqueue(async () => header(t));
        } else {
          const r = e.response || {};
          const res = e.kind === 'approve' ? r.answers.map(a => `${a.pair}: ${a.decision}${a.hold_until ? ' until ' + a.hold_until : ''} · ${a.reason}`).join(' · ')
            : e.kind === 'hold' ? `${r.decision} · ${r.reason.replace('_', ' ')}` : e.kind === 'compat' ? `${r.edges.length} match${r.edges.length === 1 ? '' : 'es'} · pair ids only` : `${(r.pairs || []).length} donor profiles`;
          enqueue(() => card({ accent: 'blue', working: 'Replying over Flower…', done: 'Replied over Flower' }, { result: `${res} · ${e.bytes} B` }, 600));
        }
        break;
      case 'profiles':
        enqueue(() => card({ working: 'Opening our pod…', done: 'Shared our donor profiles' }, { result: `${e.count} donors · blood type + HLA · no names`, lock: true }));
        break;
      case 'screen': {
        const m = e.matches;
        const txt = m.length ? m.map(x => `${x.patient_name} ← ${x.donor === 'ALT' ? 'the stranger' : x.donor + "'s donor"}`).join(' · ') : 'No match for our patients';
        enqueue(() => card({ working: `Checking ${e.donors} donors against our patients…`, done: `Checked ${e.checked} combinations` }, { result: txt }));
        break;
      }
      case 'scan.arrived':
        enqueue(() => card({ accent: 'red', working: 'A new scan is arriving…', done: `New scan: ${e.patient}` }, { result: e.file.split('/').pop(), ok: true }));
        break;
      case 'retrieve':
        if (round === 'approve') enqueue(() => card({ working: 'Checking our rulebook…', done: 'Checked our rulebook' }, { result: e.hits.map(h => h.title).join(' · ') }));
        break;
      case 'availability':
        enqueue(() => card({ working: `Checking ${e.donor}'s file…`, done: `${e.donor}: free until ${nice(e.available_to)}` }, { result: e.quote, ok: e.ok }));
        break;
      case 'advice':
        enqueue(async () => {
          if (e.kind !== 'hold') await card({ accent: e.decision === 'hold' ? 'red' : 'teal', working: `Reading ${e.patient}'s chart…`, done: e.decision === 'hold' ? 'Not this week' : 'Ready' }, { result: e.why, ok: e.decision !== 'hold' });
          await Think.reason(new Think.Run(), host, reasonLines(e), { scroll, lineMs: 550 });
        });
        break;
      case 'decision.request': enqueue(async () => decisionCard(e)); break;
      case 'decision.made': enqueue(async () => cards[e.id]?.lock(e.decision, e.by)); break;
    }
  }
  return { push, reset() { host.innerHTML = ''; q.length = 0; } };
}
