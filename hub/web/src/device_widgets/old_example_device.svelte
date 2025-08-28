<!-- <script>
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { onMount } from 'svelte';
  import { openStream, runCommand } from '../api';

  export let d;    // { id, kind, state, ... }
  export let spec; // not required here, but available

  let el, u = null, ws = null;

  // static X (timestamps), frame-replaced Y
  let X = [];
  let Y = [];

  // user-throttle: server push rate (Hz)
  let rateHz = 20;   // change in UI; stream restarts
  let lastAppliedRate = rateHz;

  // remember last params to refetch X on change
  let _lastTimeStep = undefined;
  let _lastNSteps   = undefined;

  async function fetchTimestamps() {
    try {
      // server may return the array directly, or wrap it (defensive)
      const r = await runCommand(d.id, 'get_timestamps', {});
      X = Array.isArray(r) ? r : (Array.isArray(r?.timestamps) ? r.timestamps : []);
      // reset plot data width to match X
      if (u) u.setData([X, Y.length === X.length ? Y : new Array(X.length).fill(null)]);
    } catch (e) {
      console.error('get_timestamps failed', e);
      X = [];
    }
  }

  function resetPlot() {
    u?.destroy();
    u = new uPlot({
      width: el?.clientWidth || 720,
      height: 320,
      series: [{}, { label: 'y' }],
      axes: [{}, {}],
    }, [X, Y], el);
  }

  function startStream() {
    stopStream(); // ensure clean
    ws = openStream(d.id, rateHz, 'json'); // server sends frames at 'rateHz'
    ws.onmessage = (m) => {
      try {
        const chunk = JSON.parse(m.data);
        // Accept either {y:[...]} or {t:[...], y:[...]} or bare array
        const incoming = Array.isArray(chunk) ? chunk : (chunk?.y ?? []);
        if (incoming && incoming.length) {
          // REPLACE: set Y to this frame (trim/pad to X length)
          if (X.length && incoming.length !== X.length) {
            // pad/trim to match X (defensive)
            if (incoming.length > X.length) Y = incoming.slice(0, X.length);
            else {
              Y = incoming.slice();
              while (Y.length < X.length) Y.push(null);
            }
          } else {
            Y = incoming;
          }
          if (u) u.setData([X, Y]);
        }
      } catch (e) {
        // ignore parse errors
      }
    };
    ws.onclose = () => { ws = null; };
  }

  function stopStream() {
    try { ws?.close(); } catch {}
    ws = null;
    lastAppliedRate = rateHz; // cancel pending reopen logic
}

  async function startDevice() {
    try { await runCommand(d.id, 'start', { duration_in_seconds: 0 }); } catch {}
    startStream();
  }
  async function stopDevice() {
    try { await runCommand(d.id, 'stop', {}); } catch {}
    stopStream();
  }

  // mount / resize / boot
  onMount(() => {
    const ro = new ResizeObserver(() => resetPlot());
    ro.observe(el);
    (async () => {
      await fetchTimestamps();
      resetPlot();
      //startDevice();
    })();
    return () => {
      ro.disconnect();
      //stopDevice();
      u?.destroy(); u = null;
    };
  });

  // restart stream when rate changes
//   $: if (ws && rateHz) {
//     // debounce a little to avoid rapid restarts while typing
//     clearTimeout(startStream._t); startStream._t = setTimeout(() => startStream(), 250);
//   }
    function applyRate() {
    if (rateHz === lastAppliedRate) return;
    lastAppliedRate = rateHz;
    startStream();       // closes and reopens once
    }

  // refetch X when time_step or number_of_time_steps change
  $: if (d?.state) {
    const ts = d.state.time_step;
    const n  = d.state.number_of_time_steps;
    if (ts !== _lastTimeStep || n !== _lastNSteps) {
      _lastTimeStep = ts;
      _lastNSteps   = n;
      (async () => {
        await fetchTimestamps();
        if (u) u.setData([X, (Y.length === X.length) ? Y : new Array(X.length).fill(null)]);
      })();
    }
  }
</script>

<div bind:this={el}></div>

<div class="row" style="margin-top:8px; gap:12px; align-items:center;">
  <label class="muted">WS rate (Hz)</label>
  <input type="number" min="1" max="60" step="1" bind:value={rateHz} style="width:80px;" />
  <button on:click={applyRate}>Apply rate</button> <change rate only when start is pressed again
  <button on:click={startDevice}>Start</button>
  <button on:click={stopDevice}>Stop</button>
</div> -->
