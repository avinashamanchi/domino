/* Where a page's events come from.
 *  LIVE:   served by this Mac's bridge → long-poll /events (events come from this Mac's own Flower process).
 *  REPLAY: opened as a file, or no bridge → play a recorded real Flower run embedded at build time.
 * The badge always says which one.
 */
const Source = (() => {
  const live = location.protocol.startsWith('http') && !new URLSearchParams(location.search).has('replay');
  let seq = 0;
  let handler = () => {};
  let playing = null;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function poll() {
    for (;;) {
      try {
        const res = await fetch(`/events?since=${seq}&wait=20`, { cache: 'no-store' });
        const j = await res.json();
        const catchUp = seq === 0;
        seq = j.seq;
        if (catchUp) handler(null, { catchUp: true, events: j.events });
        else j.events.forEach(e => handler(e, {}));
      } catch {
        await sleep(1500);
      }
    }
  }

  async function replay(events, { speed = 1, maxGap = 2200 } = {}) {
    const token = {};
    playing = token;
    for (let i = 0; i < events.length; i++) {
      if (playing !== token) return;
      const gap = i ? Math.min(maxGap, Math.max(0, (events[i].t - events[i - 1].t) * 1000)) / speed : 0;
      if (gap) await sleep(gap);
      if (playing !== token) return;
      handler(events[i], { replay: true });
    }
    playing = null;
  }

  return {
    live,
    on(f) { handler = f; if (live) poll(); },
    replay,
    stop() { playing = null; },
    async post(path, body = {}) {
      if (!live) return { ok: false, offline: true };
      try {
        const r = await fetch(path, { method: 'POST', body: JSON.stringify(body) });
        return await r.json();
      } catch { return { ok: false }; }
    },
  };
})();
