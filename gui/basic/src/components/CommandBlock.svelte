<script lang="ts">
  import { createEventDispatcher } from "svelte";

  // Props
  export let command: any;                        // {name, doc, args:[{name,type,doc,required,default,choices}]}
  export let index = 0;
  export let defaultOpen = false;
  export let executor: (name: string, args: Record<string, any>) => Promise<any>;

  const dispatch = createEventDispatcher();

  // UI state
  let open = defaultOpen;
  let running = false;
  let error: string | null = null;
  let result: any = null;

  // Arg defs & values
  $: argDefs = Array.isArray(command?.args) ? command.args : [];

  // Probe for release event
  $: hasRelease = !!command?.events?.release;
  $: releaseName = command?.events?.release;

  // keep user edits on spec refresh; fill sensible defaults
  function initValues(args: any[], prev: Record<string, any>) {
    const out: Record<string, any> = {};
    for (const a of args) {
      const prevVal = prev?.[a.name];
      if (prevVal !== undefined) {
        out[a.name] = prevVal;
        continue;
      }
      if (Array.isArray(a.choices) && a.choices.length) {
        out[a.name] = a.default ?? (a.required ? a.choices[0] : "");
      } else if (a.default !== null && a.default !== undefined) {
        out[a.name] = a.default;
      } else if (a.type === "bool") {
        out[a.name] = false;
      } else {
        out[a.name] = "";
      }
    }
    return out;
  }

  let values: Record<string, any> = {};
  $: values = initValues(argDefs, values);

  function coerceForSubmit(def: any, raw: any) {
    // Treat empty string as null for non-required fields
    if (raw === "" && !def.required) return null;

    switch (def.type) {
      case "int": {
        const n = parseInt(raw, 10);
        return Number.isFinite(n) ? n : null;
      }
      case "float": {
        const n = parseFloat(raw);
        return Number.isFinite(n) ? n : null;
      }
      case "bool":
        return !!raw;
      case "str":
      default:
        return raw;
    }
  }

  function buildArgs() {
    const out: Record<string, any> = {};
    for (const def of argDefs) {
      out[def.name] = coerceForSubmit(def, values[def.name]);
    }
    return out;
  }

  function fmtType(t: string | null | undefined) {
    return t ? String(t) : "Any";
  }

  function pretty(x: any) {
    try { return JSON.stringify(x, null, 2); } catch { return String(x); }
  }


  let pressed = false;

  async function onPress(){
    if (pressed) return;
    pressed = true;
    const args = buildArgs();

    try {
      const r = executor ? await executor(command?.name, args): null;
      result = r;
      dispatch("ran", {args, result: r})
    } catch (e: any) {
      error = e?.message ?? String(e);
      dispatch("error", { args, error });
    } finally {
      running = false;
    }
  }

  async function onRelease(){
    if (!pressed) return;
    pressed = false;
    if (!hasRelease) return;

    const args = buildArgs();

    try{
      const r = executor ? await executor(releaseName, args): null;
      result = r;
      dispatch("released", {args, result:r})
    }catch (e: any) {
      error = e?.message ?? String(e);
      dispatch("error", { args, error });
    } finally {
      running = false;
    }
  }

  // Event glue
  function handlePointerDown(e: PointerEvent) {
    e.preventDefault();
    onPress();
  }
  function handlePointerUp(e: PointerEvent) {
    e.preventDefault();
    onRelease();
  }

  function handleBlur() {
    // If the button loses focus while pressed (e.g., alt-tab), release safely
    if (pressed) onRelease();
  }

  async function onRun() {
    running = true; error = null; result = null;
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
  <div class="cmd-head {index % 2 ? 'alt2' : 'alt1'}">
    <button
      class="cmd-toggle"
      aria-expanded={open}
      on:click={() => (open = !open)}
      title={open ? 'Hide' : 'Show'}
    >
      {#if open}⮝{:else}⮟{/if}
    </button>

    <div class="cmd-title">
      <span>
      <strong>{command?.name}</strong>(
        {#each argDefs as a, i}
         {#if i}, {/if} 
         <span class="title-arg-type">{fmtType(a.type)}</span>
         <span class="title-arg-name">{a.name}</span>
         <!-- {#if a.default}
         = {a.default}
         {/if} -->
        {/each}
        )
        </span>
      {#if command?.doc}
        <div class="cmd-doc">{command.doc}</div>
      {/if}
    </div>

    <div class="cmd-actions">
      <!-- <button class="cmd-btn" on:click={onRun} disabled={running}>
        {#if running}Running…{:else}Run{/if}
      </button> -->
      <button
        class="btn"
        aria-pressed={pressed}
        on:pointerdown={hasRelease ? handlePointerDown : undefined}
        on:pointerup={hasRelease ? handlePointerUp : undefined}
        on:pointerleave={hasRelease ? handlePointerUp : undefined}
        on:pointercancel={hasRelease ? handlePointerUp : undefined}
        on:blur={hasRelease ? handleBlur : undefined}
        on:click={!hasRelease ? onRun : undefined}
      >
        {#if running || pressed}In progress{:else}Run{/if}
      </button>
    </div>
  </div>

  {#if open}
    <div class="cmd-body">
      {#if argDefs.length === 0}
        <div class="muted">No arguments.</div>
      {:else}
        <form class="args" on:submit|preventDefault={onRun}>
          <div class="arg-row arg-header">
            <div>Argument</div>
            <div>Type</div>
            <div>Value</div>
          </div>

          {#each argDefs as a}
            <div class="arg-row">
              <div class="arg-name">
                <div class="label">
                  {a.name}{#if a.required}<span class="req" title="Required">*</span>{/if}
                </div>
                {#if a.doc}<div class="doc">{a.doc}</div>{/if}
              </div>

              <div class="arg-type">{fmtType(a.type)}</div>

              <div class="arg-input">
                {#if Array.isArray(a.choices) && a.choices.length}
                  <select bind:value={values[a.name]} disabled={running}>
                    {#if !a.required}<option value="">—</option>{/if}
                    {#each a.choices as opt}
                      <option value={opt}>{opt}</option>
                    {/each}
                  </select>

                {:else if a.type === 'bool'}
                  <label class="check">
                    <input type="checkbox" bind:checked={values[a.name]} disabled={running} />
                    <span>Enable</span>
                  </label>

                {:else if a.type === 'int' || a.type === 'float'}
                  <input
                    type="number"
                    bind:value={values[a.name]}
                    step={a.type === 'float' ? 'any' : '1'}
                    inputmode="decimal"
                    disabled={running}
                  />

                {:else}
                  <input type="text" bind:value={values[a.name]} disabled={running} />
                {/if}
              </div>
            </div>
          {/each}

          <!-- <div class="arg-actions">
            <button type="submit" class="cmd-btn" disabled={running}>
              {#if running}Running…{:else}Run{/if}
            </button>
          </div> -->
        </form>
      {/if}

      {#if error}<div class="cmd-error">Error: {error}</div>{/if}
      {#if result !== null}
        <pre class="cmd-result">{pretty(result)}</pre>
      {/if}
    </div>
  {/if}
</div>

<style>
  .cmd-block{ border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:#fff; margin:12px 0 16px; }
  .cmd-head{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid var(--border); }
  .cmd-head.alt1{ background:var(--cmd-head-1); }
  .cmd-head.alt2{ background:var(--cmd-head-2); }

  .cmd-toggle{
    width: 34px; height: 34px; border:1px solid #d0d0d0; border-radius:20px; background:#fff;
    line-height:16px; text-align:center; cursor:pointer; user-select:none; font-size:14px; margin-right:10px;
  }
  .cmd-title{ display:flex; flex-direction:column; gap:4px; }
  .title-arg-type{color:#444; font-weight: 200;font-style: italic;}
  .title-arg-name{font-weight:400; font-style: italic;}
  .cmd-doc{ color:var(--muted); font-size:12px; }

  .cmd-actions .cmd-btn{ height:32px; padding:0 12px; border:1px solid #d0d0d0; border-radius:6px; background:#fff; cursor:pointer; }
  .cmd-actions .cmd-btn:hover{ background:#fafafa; }
  .cmd-actions .cmd-btn:disabled{ opacity:.6; cursor:not-allowed; }

  .cmd-body{ padding:10px; }

  .args{ display:block; }
  .arg-header{ font-weight:600; background:var(--alt); }
  .arg-row{
    display:grid;
    grid-template-columns: minmax(160px, 2fr) 110px minmax(220px, 3fr);
    gap:10px; align-items:center;
    padding:8px 6px; border-bottom:1px solid #eee;
  }

  .arg-name .label{ font-weight:600; }
  .arg-name .doc{ color:var(--muted); font-size:12px; margin-top:2px; }
  .arg-type{ color:#444; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size:12px; }
  .req{ color:#d33; margin-left:4px; }

  .arg-input input[type="text"],
  .arg-input input[type="number"],
  .arg-input select{
    height:32px; line-height:32px; padding:0 8px; border:1px solid var(--border); border-radius:6px; width:100%;
  }
  .check{ display:flex; align-items:center; gap:8px; }

  .arg-actions{ display:flex; justify-content:flex-end; padding:10px 6px 0; }
  .arg-actions .cmd-btn{ height:32px; padding:0 12px; border:1px solid #d0d0d0; border-radius:6px; background:#fff; cursor:pointer; }
  .arg-actions .cmd-btn:hover{ background:#fafafa; }

  .cmd-error{ color:#a00; margin-top:8px; }
  .cmd-result{ background:#fafafa; border:1px solid #eee; border-radius:6px; padding:8px; margin-top:8px; max-height:240px; overflow:auto; }
</style>
