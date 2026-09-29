/* Staged "agent at work" components + a small cancellable timeline and event log. */
const Think = (() => {
  const ACC = {
    indigo: { s: '#4F46E5', m: '#C7C3FF', w: '#EEEDFF' },
    amber: { s: '#B45309', m: '#F3C98B', w: '#FDF3E7' },
    teal: { s: '#0E7C61', m: '#A7D8C9', w: '#E6F4EF' },
    purple: { s: '#6D28D9', m: '#D2BEF3', w: '#F2ECFC' },
    blue: { s: '#0C7AC9', m: '#B9DAF2', w: '#EAF4FB' },
    red: { s: '#B3261E', m: '#F1B8B4', w: '#FDECEA' },
  };
  const CYCLE = ['indigo', 'amber', 'teal', 'purple', 'blue'];
  const LOCK = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="7" width="10" height="8" rx="1.5" fill="currentColor"/><path d="M5 7V5a3 3 0 0 1 6 0v2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
  const SPARK = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.7 5.1a4 4 0 0 0 2.5 2.5L21.5 11l-5.3 1.4a4 4 0 0 0-2.5 2.5L12 20l-1.7-5.1a4 4 0 0 0-2.5-2.5L2.5 11l5.3-1.4a4 4 0 0 0 2.5-2.5z"/></svg>';
  const FLOWER = '<svg viewBox="0 0 32 32" aria-hidden="true"><g fill="#4FA3A5"><ellipse cx="16" cy="8" rx="5" ry="7"/><ellipse cx="16" cy="24" rx="5" ry="7"/><ellipse cx="8" cy="16" rx="7" ry="5"/><ellipse cx="24" cy="16" rx="7" ry="5"/></g><circle cx="16" cy="16" r="5" fill="#EC8017"/></svg>';
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const make = html => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const CANCEL = Symbol('cancel');

  /* A timeline that can be cancelled (new run, reset) or fast-forwarded (catch-up). */
  class Run {
    constructor(fast = false) { this.alive = true; this.fast = fast || REDUCED; }
    cancel() { this.alive = false; }
    check() { if (!this.alive) throw CANCEL; }
    async wait(ms) { if (!this.fast) await sleep(ms); this.check(); }
  }
  /* Events seen so far, and promises waiting for one that matches. */
  class Log {
    constructor() { this.events = []; this.waiters = []; }
    push(e) { this.events.push(e); this.waiters = this.waiters.filter(w => !w(e)); }
    find(pred) { return this.events.find(pred); }
    count(pred) { return this.events.filter(pred).length; }
    waitFor(pred, run) {
      const hit = this.events.find(pred);
      if (hit) return Promise.resolve(hit);
      return new Promise((res, rej) => {
        const w = e => { if (!run.alive) { rej(CANCEL); return true; } if (pred(e)) { res(e); return true; } return false; };
        this.waiters.push(w);
        const poll = setInterval(() => { if (!run.alive) { clearInterval(poll); rej(CANCEL); } }, 250);
      });
    }
  }

  function connect({ mark = FLOWER, name, working, done, chips }) {
    const el = make(`<div class="connect rise"><div class="ch"><span class="mk">${mark}</span><span><span class="nm">${esc(name)}</span><span class="sb">${esc(working)}</span></span></div><div class="chips2"></div></div>`);
    const wrap = el.querySelector('.chips2');
    const els = chips.map(c => {
      const ch = make(`<span class="chip2 pending" style="--c:${c.color || '#0E7C61'}"><span class="d"></span><span class="nmx">${esc(c.name)}</span><span class="st">${esc(c.pending || 'connecting…')}</span></span>`);
      wrap.appendChild(ch);
      return ch;
    });
    return {
      el,
      set(i, state, label) { const c = els[i]; if (!c) return; c.className = 'chip2 ' + state; c.querySelector('.st').textContent = label; },
      finish() { el.querySelector('.sb').textContent = done; },
    };
  }

  let n = 0;
  function work({ accent, working, done, more }) {
    const a = ACC[accent || CYCLE[n++ % CYCLE.length]];
    const el = make(`<div class="work rise" style="--as:${a.s};--am:${a.m};--aw:${a.w}"><span class="ic"><span class="spin"></span></span><span class="bd"><span class="tt">${esc(working)}</span><span class="rs" style="display:none"></span></span></div>`);
    return {
      el,
      resolve({ title = done, result = '', lock = false, ok = true, html = false, details = more } = {}) {
        if (!ok) { const r = ACC.red; el.style.setProperty('--as', r.s); el.style.setProperty('--am', r.m); el.style.setProperty('--aw', r.w); }
        el.querySelector('.ic').innerHTML = `<span class="okc">${ok ? '✓' : '✗'}</span>`;
        el.querySelector('.tt').textContent = title;
        const rs = el.querySelector('.rs');
        rs.className = 'rs rise' + (lock ? ' lock' : '');
        rs.innerHTML = (lock ? LOCK : '') + (html ? result : esc(result));
        rs.style.display = result ? '' : 'none';
        if (details) el.querySelector('.bd').insertAdjacentHTML('beforeend', `<details class="more"><summary>details</summary>${details}</details>`);
      },
    };
  }

  function think(lines, title = 'Reasoning') {
    const el = make(`<div class="think rise"><div class="th">${SPARK}<span>${esc(title)}</span><span class="dots"><span></span><span></span><span></span></span></div><div class="ls">${lines.map(l => `<div class="l">${esc(l)}</div>`).join('')}</div></div>`);
    const ls = [...el.querySelectorAll('.l')];
    return { el, show(i) { ls[i]?.classList.add('show'); }, all() { ls.forEach(l => l.classList.add('show')); }, done() { el.classList.add('done'); } };
  }

  function conclusion({ label = 'Conclusion', text, tone = '', extra = '' }) {
    return make(`<div class="concl rise ${tone}"><span class="cl">${esc(label)}</span><span class="ct">${esc(text)}</span>${extra ? `<div class="cx">${extra}</div>` : ''}</div>`);
  }

  function hero({ title, sub = '', onClick, disabled = false }) {
    const el = make(`<button type="button" class="hero rise"><span><span class="ht">${esc(title)}</span>${sub ? `<span class="hs">${esc(sub)}</span>` : ''}</span><span class="ha">→</span></button>`);
    el.disabled = disabled;
    if (onClick) el.addEventListener('click', onClick);
    return el;
  }

  /* One step: show a spinner box, wait for its event (and a minimum beat), then resolve it. */
  async function step(run, host, spec, waitPromise, resolveWith, { minMs = 1300, gapMs = 900, scroll } = {}) {
    const box = work(spec);
    host.appendChild(box.el);
    scroll?.();
    const t0 = performance.now();
    const ev = await waitPromise;
    run.check();
    await run.wait(Math.max(0, minMs - (performance.now() - t0)));
    box.resolve(resolveWith(ev));
    scroll?.();
    await run.wait(gapMs);
    return ev;
  }

  async function reason(run, host, lines, { title, lineMs = 650, scroll } = {}) {
    const t = think(lines, title);
    host.appendChild(t.el);
    scroll?.();
    await run.wait(500);
    for (let i = 0; i < lines.length; i++) { t.show(i); scroll?.(); await run.wait(lineMs); }
    await run.wait(400);
    t.done();
    return t;
  }

  return { ACC, LOCK, SPARK, FLOWER, CANCEL, Run, Log, connect, work, think, conclusion, hero, step, reason, esc, sleep };
})();
