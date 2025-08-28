<script lang="ts">
  import { createEventDispatcher } from "svelte";

  /** One command spec from /spec */
  export let command: any;
  export let index: number = 0;
  export let executor: (name: string, args: Record<string, any>) => Promise<any>;  
  export let defaultOpen: boolean = false;

  const dispatch = createEventDispatcher();

  let open = defaultOpen; 
  let edit: Record<string, any> = {};
  let running = false;
  let result: any = null;
  let error: string | null = null;

  const bodyId = `cmdbody-${(command?.name || 'cmd')}-${index}`;

  function argEntries(args: any): [string, any][] {
    if (!args) return [];
    if (Array.isArray(args)) return args.map((n: string) => [n, {} as any]);
    if (typeof args === "object") return Object.entries(args);
    return [];
  }

  function coerce(value: any, spec: any) {
    const t = spec?.type ?? "any";
    if (value === "" || value === undefined || value === null) return undefined;
    if (spec?.choices?.length) return value;
    if (t === "bool") return !!value;
    if (t === "int")  { const v = parseInt(value, 10);   return Number.isFinite(v) ? v : undefined; }
    if (t === "float" || t === "number") { const v = parseFloat(value); return Number.isFinite(v) ? v : undefined; }
    return value; // string/any
  }
  function stepFor(spec: any) {
    if (spec?.step != null) return spec.step;
    return spec?.type === "int" ? 1 : "any";
  }

  function buildArgs(): Record<string, any> {
    const out: Record<string, any> = {};
    for (const [name, spec] of argEntries(command?.args)) {
      const raw = edit[name] !== undefined ? edit[name] : spec?.default;
      const v = coerce(raw, spec);
      if (v !== undefined) out[name] = v;
    }
    return out;
  }
  function missingRequired(): string[] {
    const miss: string[] = [];
    for (const [name, spec] of argEntries(command?.args)) {
      if (!spec?.required) continue;
      const raw = edit[name] !== undefined ? edit[name] : spec?.default;
      const v = coerce(raw, spec);
      if (v === undefined) miss.push(name);
    }
    return miss;
  }

  function pretty(v: any) {
    try { return JSON.stringify(v, null, 2); }
    catch { return String(v); }
  }

  async function onRun() {
    running = true; open=true; error = null; result = null;
    const args = buildArgs();
    try {
      const r = executor ? await executor(command?.name, args) : null;
      result = r;
      dispatch("ran", { args, result: r });
    } catch (e: any) {
      error = e?.message ?? String(e);
      dispatch("error", { args, error });
    } finally {
      running = false;
    }
  }
</script>

<div class="cmd-block">
  <!-- HEADER (accent, alternating) -->
  <div class="cmd-head {index % 2 ? 'alt2' : 'alt1'}">
    
    <div class="cmd-title">
      <button
        class="cmd-toggle"
        aria-expanded={open}
        aria-controls={bodyId}
        on:click={() => (open = !open)}
        title={open ? 'Hide details' : 'Show details'}>
        {#if open}⮝{:else}⮟{/if}
      </button>
      <strong>{command?.name}()</strong>
      {#if command?.returns}
        <span class="cmd-returns">→ {command.returns}</span>
      {/if}
    </div>
    <div class="cmd-actions">
      <button
        class="cmd-run"
        disabled={running || !!missingRequired().length}
        title={missingRequired().length ? "Missing: " + missingRequired().join(", ") : ""}
        on:click={onRun}>
        {#if running}<span class="cmd-spinner" aria-hidden="true"></span> Running…{:else}⏵ Run{/if}
      </button>
    </div>
  </div>
 {#if open}
    <!-- DOC (neutral) -->
    {#if command?.doc}
        <div class="cmd-doc">{command.doc}</div>
    {/if}

    <!-- ARGS (neutral area) -->
    {#if argEntries(command?.args).length}
        <div class="cmd-args">
        {#each argEntries(command.args) as [aname, aspec]}
            <div class="cmd-arg-row">
            <div class="cmd-arg-name">{aname}</div>
            <div class="cmd-arg-type">{aspec?.type ?? 'Any'}</div>

            <div class="cmd-arg-input">
                {#if aspec?.choices}
                <select bind:value={edit[aname]}>
                    {#each aspec.choices as c}<option value={c}>{c}</option>{/each}
                </select>

                {:else if aspec?.type === 'bool'}
                <input type="checkbox" bind:checked={edit[aname]}>

                {:else if aspec?.type === 'int' || aspec?.type === 'float' || aspec?.min != null || aspec?.maximum != null}
                <input
                    class="cmd-num"
                    type="number"
                    bind:value={edit[aname]}
                    placeholder={aspec?.default ?? ''}
                    step={stepFor(aspec)}
                    min={aspec?.min}
                    max={aspec?.max}
                >

                {:else}
                <input
                    class="cmd-text"
                    type="text"
                    bind:value={edit[aname]}
                    placeholder={aspec?.default ?? ''}
                >
                {/if}
            </div>
            </div>
        {/each}
        </div>
    {/if}

    <!-- RESULT (neutral area) -->
    <div class="cmd-result">
        {#if running}
        <div class="muted">Executing…</div>
        {/if}
        {#if error}
        <div class="cmd-error">Error: {error}</div>
        {/if}
        {#if !running && result !== null}
        <div class="cmd-result-title">Result</div>
        <pre class="cmd-result-pre">{pretty(result)}</pre>
        {/if}
    </div>
  {/if}
</div>

<style>
  .cmd-block {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;           /* header corners */
    background: var(--alt);
    margin: 12px 0 16px;
  }

  /* Header (accent only here) */
  .cmd-head {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
  }
  .cmd-head.alt1 { background: var(--cmd-head-1); }
  .cmd-head.alt2 { background: var(--cmd-head-2); }

  .cmd-toggle {
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
  .cmd-toggle:hover { background: #f7f7f7; }

  .cmd-title { font-size: 16px; }
  .cmd-returns {
    color: var(--muted);
    font-size: 12px;
    margin-left: 6px;
    font-family: var(--mono);
  }
  .cmd-actions { display: flex; gap: 8px; }
  .cmd-run {
    height: 32px; padding: 0 14px;
    border: 1px solid #d0d0d0; 
    background: #fafafa;
    border-radius: 6px; cursor: pointer;
    width: 80px;
  }
  .cmd-run:hover { background: #ededea; }
  .cmd-run:disabled { opacity: .5; cursor: not-allowed; }
  .cmd-spinner {
    width: 12px; height: 12px; display: inline-block; margin-right: 6px;
    border: 2px solid #999; border-top-color: transparent; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Neutral body */
  .cmd-doc {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.35;
    padding: 8px 10px 4px;
  }

  .cmd-args {
    padding: 6px 10px 10px;
    display: grid; row-gap: 6px;
  }
  .cmd-arg-row {
    display: grid;
    grid-template-columns: 220px 120px auto; /* name | type | input */
    align-items: center; column-gap: 8px;
    min-height: var(--row-h);
  }
  .cmd-arg-name { font-weight: 600; }
  .cmd-arg-type { font-family: var(--mono); font-size: 12px; color: var(--muted); }

  .cmd-arg-input input[type="number"],
  .cmd-arg-input input[type="text"],
  .cmd-arg-input select {
    height: 32px; line-height: 32px;
    padding: 0 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .cmd-arg-input .cmd-num  { width: var(--cmd-num-width, 120px); }  /* ⬅️ narrower */
  .cmd-arg-input .cmd-text { width: var(--cmd-text-width, 240px); }

  .cmd-result {
    padding: 6px 10px 10px;
    border-top: 1px solid var(--border);
  }
  .cmd-result-title { font-weight: 600; margin-bottom: 4px; }
  .cmd-result-pre {
    margin: 0; padding: 8px; border: 1px solid var(--border);
    border-radius: 6px; background: var(--result-bg);
    font-family: var(--mono); font-size: 12px; overflow: auto;
  }
  .cmd-error { color: #a00; }

  @media (max-width: 720px) {
    .cmd-arg-row { grid-template-columns: 1fr; row-gap: 4px; }
    .cmd-arg-type { display: none; }
  }
</style>
