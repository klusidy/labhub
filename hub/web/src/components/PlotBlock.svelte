<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";
  export let deviceId: string;
  export let source: string;
  export let index = 0;
  export let defaultOpen = false;

  export let getPlotSpec!: (dev: string, src: string) => Promise<any>;
  export let getFrame!: (dev: string, src: string) => Promise<any>;
  export let openDataStream!: (dev: string, src: string, rate?: number) => WebSocket;

  // UI state
  let open = defaultOpen;
  let running = false;
  let lastError: string | null = null;
  let loadingSpec = true;

  // meta/spec
  let spec: any = null;
  let xLabel = "";
  let yLabel = "";
  let title = "";

  // WS + draw cadence
  let rateHz = 10;
  let ws: WebSocket | null = null;
  let wsRateApplied = 0;

  // uPlot handles
  let u: uPlot | null = null;
  let plotEl: HTMLDivElement | null = null;
  let xLabEl: HTMLDivElement | null = null;
  let yLabEl: HTMLDivElement | null = null;

  // current unified data
  // uPlot expects [x, s1, s2, ...] all same length
  let xData: number[] = [];
  let seriesNames: string[] = [];
  let seriesData: number[][] = [];

  const bodyId = `plotbody-${(deviceId || 'plot')}-${index}`;
  const palette = ["#2d6cdf","#d9534f","#5cb85c","#f0ad4e","#5bc0de","#6f42c1","#20c997","#fd7e14","#6610f2","#17a2b8"];

  // ----- lifecycle -----
  onMount(async () => {
    await loadSpec();
    if (open) mountChart();      // build chart on first open
    return () => cleanup();
  });
  onDestroy(cleanup);

  async function loadSpec() {
    try {
      loadingSpec = true;
      lastError = null;
      const ps = await getPlotSpec(deviceId, source);
      spec = ps || {};
      title = spec?.title || source;
      xLabel = spec?.["x-label"] || "";
      yLabel = spec?.["y-label"] || "";
      // If spec ships fixed x-values, keep them; otherwise we’ll build index-based
      const xv = spec?.["x-values"];
      xData = Array.isArray(xv) ? xv.slice() : [];
    } catch (e: any) {
      lastError = e?.message ?? String(e);
    } finally {
      loadingSpec = false;
    }
  }

  function cleanup() {
    closeWS();
    destroyChart();
  }


  // rebuild when container re-appears
  $: if (open && plotEl && !u) {
    mountChart();
    const data: uPlot.AlignedData = [xData, ...(seriesData.length ? seriesData : [[]])];
    u!.setData(data);          // compute initial scales
    restoreScales(savedScales);
    bootstrapped = true;
  }
  // pause everything when collapsing
  $: if (!open) {
    closeWS();
    savedScales = captureScales();
    destroyChart();
  }

  // ----- controls -----
  async function doOnce() {
    try {
      open = true;
      //destroyChart();
      //mountChart();
      //if (!u) mountChart();
      await refreshSpec(true);
      const fr = await getFrame(deviceId, source);
      applyIncoming(fr);
      redraw();
    } catch (e:any) { lastError = String(e); }
  }
  function onStartStop() {
    running ? stop() : start();
  }
  async function start() {
    lastError = null;
    open = true;
    await refreshSpec(true); 
    openWS(rateHz); 

    //if (!u) mountChart();
    //await refreshSpec(true);
    running = true;
    //openWS(rateHz);
  }
  function stop() {
    running = false;
    closeWS();
  }
  // reopen WS if rate changes while running/open
  $: if (open && running && rateHz !== wsRateApplied) {
    closeWS();
    openWS(rateHz);
  }

  // ----- WS -----
  function openWS(rate: number) {
    try {
      ws = openDataStream(deviceId, source, rate);
      wsRateApplied = rate;
      ws.onmessage = (ev) => {
        try {
          const fr = typeof ev.data === "string" ? JSON.parse(ev.data) : JSON.parse(new TextDecoder().decode(ev.data));
          applyIncoming(fr);
          // Throttle redraw to ~rateHz by just letting uPlot render each frame quickly.
          // uPlot render is very fast; if you want extra throttle, gate with a timestamp.
          redraw();
        } catch {}
      };
      ws.onerror = () => { lastError = "stream error"; };
      ws.onclose = () => { /* freeze on last frame */ };
    } catch (e:any) { lastError = String(e); }
  }
  function closeWS() {
    wsRateApplied = 0;
    if (ws) { try { ws.close(); } catch {} ws = null; }
  }

  // ----- frame normalization -> xData + seriesNames + seriesData -----
  function applyIncoming(fr: any) {
    // Update x-values if provided
    const xv = fr?.["x-values"] ?? fr?.x ?? null;
    if (Array.isArray(xv)) xData = xv.slice();

    // 1) standard: { series: [{name, data}, ...] }
    if (Array.isArray(fr?.series) && fr.series.length) {
      const list = fr.series.filter((s: any) => Array.isArray(s?.data));
      seriesNames = list.map((s: any) => String(s.name ?? "series"));
      seriesData  = list.map((s: any) => s.data as number[]);
      unifyLengths();
      return;
    }
    // 2) single: { data: [...] , name? }
    if (Array.isArray(fr?.data)) {
      seriesNames = [String(fr?.name ?? "data")];
      seriesData  = [fr.data as number[]];
      unifyLengths();
      return;
    }
    // 3) object-of-arrays: { "PSD":[...], "Ch1":[...], meta?, x? }
    if (fr && typeof fr === "object") {
      const names: string[] = [];
      const arrays: number[][] = [];
      for (const [k,v] of Object.entries(fr)) {
        if (k === "meta" || k === "x" || k === "x-values" || k === "name" || k === "series") continue;
        if (Array.isArray(v) && (v as any[]).every(n => typeof n === "number")) {
          names.push(k);
          arrays.push(v as number[]);
        }
      }
      if (names.length) {
        seriesNames = names;
        seriesData = arrays;
        unifyLengths();
      }
    }
  }

function unifyLengths() {
  // If we have xData from spec/frame, it is authoritative.
  let N = xData.length;

  if (N === 0) {
    // No xData? derive index-based x from the first series length (or 0)
    N = seriesData[0]?.length || 0;
    if (N) xData = Array.from({ length: N }, (_, i) => i);
  }

  function padOrTrim(arr: number[]) {
    if (arr.length === N) return arr;
    if (arr.length > N) return arr.slice(0, N);
    const out = arr.slice();
    while (out.length < N) out.push(NaN); // pad with NaN (gaps)
    return out;
  }

  xData = padOrTrim(xData);
  seriesData = seriesData.map(padOrTrim);
}


  // ----- uPlot -----
  function buildOpts(): uPlot.Options {
    const width = Math.max(200, plotEl?.clientWidth || 600);
    const height = Math.max(220, Math.floor(width * 0.1345));

    const axes: uPlot.Axis[] = [
      {
        // X axis
        values: (u, vals) => vals.map(fmtTick),
        grid: { show: true },
      },
      {
        // Y axis
        values: (u, vals) => vals.map(fmtTick),
        grid: { show: true },
      },
    ];

    return {
      width, height,
      title,
      legend: { show: true },
      scales: { x: { time: false }, y: { auto: true } },
      axes,
      series: [
        {}, // x
        ...seriesNames.map((name, i) => ({
          label: name,
          stroke: palette[i % palette.length],
          width: 2,
        })),
      ],
      // selection -> zoom
      hooks: {
        ready: [
          (uu) => {
            // dblclick to reset
            uu.root.addEventListener("dblclick", () => {
              uu.setScale("x", { min: null, max: null });
              uu.setScale("y", { min: null, max: null });
            });

            // wheel zoom centered at cursor
            uu.root.addEventListener("wheel", (e: WheelEvent) => {
              e.preventDefault();
              const rect = uu.over.getBoundingClientRect();
              const left = e.clientX - rect.left;
              const xVal = uu.posToVal(left, "x");
              const factor = e.deltaY < 0 ? 0.9 : 1.1;
              const sc = uu.scales.x;
              const min = sc.min ?? uu.data[0][0];
              const max = sc.max ?? uu.data[0][uu.data[0].length - 1];
              const newMin = xVal - (xVal - min) * factor;
              const newMax = xVal + (max - xVal) * factor;
              uu.setScale("x", { min: newMin, max: newMax });
            }, { passive: false });
          },
        ],
        setSelect: [
          (uu) => {
            const s = uu.select;
            if (s.width > 0) {
              const xMin = uu.posToVal(s.left, "x");
              const xMax = uu.posToVal(s.left + s.width, "x");
              uu.setScale("x", { min: xMin, max: xMax });
              uu.setSelect({ left: 0, width: 0, top: 0, height: 0 }, false);
            }
          },
        ],
      },
    };
  }

  function mountChart() {
    destroyChart();
    seriesNames = seriesNames || [];
    // ensure series structure at least 1 series
    const data: uPlot.AlignedData = [xData || [], ...(seriesData.length ? seriesData : [[]])];
    u = new uPlot(buildOpts(), data, plotEl!);
    // axis labels overlay
    updateAxisLabels();
    // responsive: observe container
    const ro = new ResizeObserver(() => {
      if (!u || !plotEl) return;
      const width = Math.max(200, plotEl.clientWidth);
      const height = Math.max(220, Math.floor(width * 0.30));
      u.setSize({ width, height });
      updateAxisLabels();
    });
    ro.observe(plotEl!);
    // keep the observer on the uPlot root
    (u as any)._ro = ro;
  }

  function destroyChart() {
    if (u) {
      const ro = (u as any)?._ro as ResizeObserver | undefined;
      if (ro) ro.disconnect();
      u.destroy();
      u = null;
    }
  }

function isZoomed(axis: "x" | "y") {
  if (!u) return false;
  const s = u.scales[axis];
  return s.min != null || s.max != null;   // numeric bounds = user-zoomed
}

function captureScales() {
  if (!u) return null;
  return {
    x: { min: u.scales.x.min, max: u.scales.x.max },
    y: { min: u.scales.y.min, max: u.scales.y.max },
  };
}
function restoreScales(saved: any) {
  if (!u || !saved) return;
  const { x, y } = saved;
  if (x && x.min != null && x.max != null) u.setScale("x", { min: x.min, max: x.max });
  if (y && y.min != null && y.max != null) u.setScale("y", { min: y.min, max: y.max });
}

let lastXLen = 0; // top-level

async function refreshSpec(keepZoom = true) {
  const keep = keepZoom ? captureScales() : null;

  let xLenChanged = false;
  try {
    const ps = await getPlotSpec(deviceId, source);
    spec   = ps || {};
    title  = spec?.title || source;
    xLabel = spec?.["x-label"] || "";
    yLabel = spec?.["y-label"] || "";

    const xv = spec?.["x-values"];
    xData = Array.isArray(xv) ? xv.slice() : [];

    xLenChanged = (xData.length !== lastXLen);
    lastXLen = xData.length;

    unifyLengths();            // with the new authoritative version
  } catch (e: any) {
    lastError = e?.message ?? String(e);
  }

  destroyChart();
  if (open && plotEl) mountChart();

  if (u) {
    const aligned: uPlot.AlignedData = [xData, ...(seriesData.length ? seriesData : [[]])];
    u.setData(aligned); // autoscale once

    if (keepZoom) {
      // if x length changed, do not restore old X (it would clamp to the old domain)
      if (!xLenChanged && keep?.x) u.setScale("x", { min: keep.x.min, max: keep.x.max });
      if (keep?.y)                  u.setScale("y", { min: keep.y.min, max: keep.y.max });
    }

    updateAxisLabels();
    bootstrapped = true;
  }
}




let bootstrapped = false;
let savedScales: any = null;


function redraw() {
  if (!u) { if (open && plotEl) mountChart(); return; }

  const aligned: uPlot.AlignedData = [xData, ...seriesData];

  // series count changed? -> rebuild (legend/colors), keep zoom
  const needsRebuild = u.series.length - 1 !== seriesNames.length;
  if (needsRebuild) {
    const keep = captureScales();
    mountChart();
    u!.setData(aligned);          // recompute internals
    restoreScales(keep);
    bootstrapped = true;
    return;
  }

  const zoomX = isZoomed("x");
  const zoomY = isZoomed("y");

  if (!bootstrapped) {
    u.setData(aligned);           // first real data: autoscale once
    bootstrapped = true;
    return;
  }

  if (zoomX || zoomY) {
    const keep = captureScales();
    u.setData(aligned);           // update data (let non-zoomed axis auto)
    restoreScales(keep);          // restore user zoom
  } else {
    u.setData(aligned);           // fully autoscale when not zoomed
  }
}

  function fmtTick(v: number) {
    const av = Math.abs(v);
    if (av >= 1e6 || (av && av < 1e-3)) return v.toExponential(2);
    const s = v.toFixed(6).replace(/\.?0+$/,'');
    return s;
  }

  // axis labels overlay (centered)
  function updateAxisLabels() {
    if (!u) return;
    if (xLabel) { if (xLabEl) xLabEl.textContent = xLabel; }
    if (yLabel) { if (yLabEl) yLabEl.textContent = yLabel; }
  }
</script>

<div class="plot-block">
  <div class="plot-head {index % 2 ? 'alt2' : 'alt1'}">
    <!--<button class="plot-toggle" aria-expanded={open} on:click={() => open = !open}>
      {#if open}⟰{:else}⟱{/if}
    </button>-->
    <button
        class="plot-toggle"
        aria-expanded={open}
        
        on:click={() => (open = !open)}
        title={open ? 'Hide details' : 'Show details'}>
        {#if open}⮝{:else}⮟{/if}
      </button>

    <div class="plot-title"><strong>{source}</strong>{#if spec?.title}<span class="plot-sub"> — {spec.title}</span>{/if}</div>

    <div class="plot-actions">
      <button class="plot-btn" on:click={doOnce} disabled={running || loadingSpec}>Once</button>
      <button class="plot-btn" on:click={onStartStop} disabled={loadingSpec}>{#if running}Stop{:else}Start{/if}</button>
      <label class="plot-rate">
        <span>rate</span>
        <input type="number" min="0.2" step="0.2" bind:value={rateHz} />
        <span>Hz</span>
      </label>
    </div>
  </div>

  {#if open}
    <div class="plot-body">
      {#if lastError}<div class="cmd-error">Error: {lastError}</div>{/if}
      {#if loadingSpec}<div class="muted">Loading plot spec…</div>{/if}
      <div class="uplot-wrap">
        <div class="uplot-host" bind:this={plotEl}></div>
        <!-- axis labels (overlays) -->
        {#if xLabel}<div class="axis-label x" bind:this={xLabEl}></div>{/if}
        {#if yLabel}<div class="axis-label y" bind:this={yLabEl}></div>{/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .plot-block{ border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:#fff; margin:12px 0 16px; }
  .plot-head{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid var(--border); }
  .plot-head.alt1{ background:var(--cmd-head-1); }
  .plot-head.alt2{ background:var(--cmd-head-2); }
  .plot-toggle{ 
    width: 34px; height: 34px;
    border: 1px solid #d0d0d0;
    border-radius: 20px;
    background: #fff;
    line-height: 16px;
    text-align: center;
    cursor: pointer;
    user-select: none;
    font-size: 14px;
    margin-right:10px;
  }
  .plot-toggle:hover { background: #f7f7f7; }
  .plot-title{ font-size:16px; }
  .plot-sub{ color:var(--muted); font-size:12px; margin-left:4px; }
  .plot-actions{ display:flex; align-items:center; gap:8px; }
  .plot-btn{ height:32px; padding:0 12px; border:1px solid #d0d0d0; border-radius:6px; background:#fff; cursor:pointer; }
  .plot-btn:hover{ background:#fafafa; } .plot-btn:disabled{ opacity:.5; cursor:not-allowed; }
  .plot-rate{ display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); }
  .plot-rate input{ width:68px; height:28px; line-height:28px; padding:0 8px; border:1px solid var(--border); border-radius:6px; }

  .plot-body{ padding:8px 10px 10px; }
  .uplot-wrap{ position:relative; width:100%; }
  .uplot-host :global(.uplot){ width:100%; }
  .axis-label.x{
    position:absolute; left:50%; transform:translateX(-50%);
    bottom:-6px; font-size:12px; color:#666; pointer-events:none;
  }
  .axis-label.y{
    position:absolute; left:-8px; top:50%; transform:translate(-100%,-50%) rotate(-90deg);
    transform-origin: top right; font-size:12px; color:#666; pointer-events:none;
  }
  .cmd-error{ color:#a00; }
</style>
