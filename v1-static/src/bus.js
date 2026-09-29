/* Domino message bus.
 * - Same browser: BroadcastChannel.
 * - Across Macs: relay.py (long-poll). Used when the page is served by the relay,
 *   or opened as a file with ?relay=<ip>:8765 (remembered in localStorage).
 * Every message is plain JSON; byte counts on screen are real.
 */
const Bus = (() => {
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const params = new URLSearchParams(location.search);
  let base = null;
  if (location.protocol.startsWith('http')) base = location.origin;
  const relayParam = params.get('relay');
  if (relayParam) store.set('domino.relay', relayParam);
  const relay = relayParam || (base ? null : store.get('domino.relay'));
  if (relay) base = relay.startsWith('http') ? relay.replace(/\/$/, '') : 'http://' + relay;

  const listeners = new Set();
  const linkListeners = new Set();
  const seen = new Set();
  let linked = false;
  let seq = null;

  const rid = () => Math.random().toString(36).slice(2, 10);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const bytes = obj => new Blob([JSON.stringify(obj)]).size;

  function setLinked(v) {
    if (v === linked) return;
    linked = v;
    linkListeners.forEach(f => f(linked, base));
  }
  function deliver(m) {
    if (!m || !m.mid || seen.has(m.mid)) return;
    seen.add(m.mid);
    listeners.forEach(f => { try { f(m); } catch (e) { console.error(e); } });
  }

  let bc = null;
  try { bc = new BroadcastChannel('domino'); bc.onmessage = e => deliver(e.data); } catch { bc = null; }

  function send(m) {
    m.mid = m.mid || rid();
    m.ts = Date.now();
    seen.add(m.mid);
    if (bc) bc.postMessage(m);
    if (base) {
      fetch(base + '/bus', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(m) })
        .then(() => setLinked(true)).catch(() => setLinked(false));
    }
    return m;
  }

  async function poll() {
    while (base) {
      try {
        const since = seq == null ? -1 : seq;
        const res = await fetch(`${base}/bus?since=${since}&wait=20`, { cache: 'no-store' });
        const j = await res.json();
        setLinked(true);
        const first = seq == null;
        seq = j.seq;
        if (!first) j.messages.forEach(deliver);
      } catch {
        setLinked(false);
        await sleep(2000);
      }
    }
  }
  if (base) poll();

  return {
    send, bytes, rid,
    on(f) { listeners.add(f); },
    onLink(f) { linkListeners.add(f); f(linked, base); },
    get base() { return base; },
    get linked() { return linked; },
  };
})();
