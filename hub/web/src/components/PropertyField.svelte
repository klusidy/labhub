<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { formatCurrent } from "../utils/formatter";

  export let property: any;   // spec for a single property
  export let value: any;   // current value from state
  export let index = 0;    // for alternating background
  //export let pending = false;

  const dispatch = createEventDispatcher();

  // local edit buffer; must exist before we bind into its fields
  let edit: any = null;

  // initialize edit buffer once per mount or when property/value changes meaningfully
  $: initEdit();
  function initEdit() {
    if (property?.fields) {
      // composite: ensure object; clone so we don't mutate parent state
      const base = (value && typeof value === "object") ? value : {};
      edit = structuredClone(base);
      // create missing field keys with defaults if present
      if (property.fields && typeof property.fields === "object") {
        for (const [fname, fspec] of Object.entries<any>(property.fields)) {
          if (!(fname in edit)) {
            edit[fname] = fspec?.default ?? null;
          }
        }
      }
    } else {
      // scalar: copy value (primitive or simple)
      edit = value ?? property?.default ?? null;
    }
  }

  const isRO = !!property?.read_only;
  const hasChoices = Array.isArray(property?.choices) && property.choices.length > 0;

  function numStep(meta: any) {
    if (meta?.step != null) return meta.step;
    const t = meta?.type;
    return t === "int" ? 1 : "any";
  }

  function propertySet() {
    dispatch("propertySet", { name: property.name, value: edit });
  }

   // helpers kept at bottom for clarity
  function objectEntries(obj: any): [string, any][] {
    if (!obj) return [];
    return Object.entries(obj);
  }
  function hasMinMax(meta: any) {
    return meta?.min != null || meta?.max != null;
  }
  function inferType(p: any): string {
    if (!p) return "Any";
    if (p?.choices) {
      // crude inference for display purposes
      const t = typeof p.choices[0];
      return t === "string" ? "Literal" : t;
    }
    if (hasMinMax(p)) return "float";
    return p?.type ?? "Any";
  }
  // function formatCurrent(v: any): string {
  //   if (v == null) return "—";
  //   if (typeof v === "object") return JSON.stringify(v);
  //   return String(v);
  // }

  $: valid = !!property && typeof property.name === "string";

  function fieldEntries(fields: any): [string, any][] {
    if (!fields) return [];
    if (Array.isArray(fields)) return fields.map((n: string) => [n, {} as any]); // list → pairs
    if (typeof fields === "object") return Object.entries(fields);               // map → entries
    return [];
  }
</script>

<!-- full-width alt background row -->
{#if index % 2 === 1}
  <div class="prop-bg"></div>
{/if}

<!-- aligned cells -->
<div class="prop-row">
  <div class="prop-cell prop-name">
    <span class="prop-label">{property.name}</span>
    {#if property?.doc}
    <br/><span class="prop-doc">{property.doc}</span>
    {/if}  
  </div>
  <div class="prop-cell prop-type">{property.type ?? inferType(property)}</div>
  <div class="prop-cell prop-current">
  <!--{#if pending}
    <span class="spinner" aria-hidden="true"></span> saving…
  {:else}
    {formatCurrent(value)}
  {/if}-->
  {formatCurrent(value, property?.unit)} 
  </div>

  <div class="prop-cell prop-edit">
    {#if !isRO}
      {#if property.fields}
        <!-- composite -->
        <div class="composite">
          <details>
            <summary>{property.name} fields</summary>
            <div class="composite-body">
              {#each fieldEntries(property.fields) as [fname, fmeta]}
                <div class="composite-item">
                  <label for={property.name + "-" + fname}>{fname}</label>
                </div>
                <div class="composite-item">
                  {#if fmeta?.choices}
                    <select id={property.name + "-" + fname} bind:value={edit[fname]}>
                      {#each fmeta.choices as c}
                        <option value={c}>{c}</option>
                      {/each}
                    </select>
                  {:else if fmeta?.type === 'bool'}
                    <input id={property.name + "-" + fname} type="checkbox" bind:checked={edit[fname]} />
                  {:else if fmeta?.type === 'int' || fmeta?.type === 'float' || hasMinMax(fmeta)}
                    <input
                      id={property.name + "-" + fname}
                      type="number"
                      bind:value={edit[fname]}
                      step={numStep(fmeta)}
                      min={fmeta?.min}
                      max={fmeta?.max}
                    />
                  {:else}
                    <input
                      id={property.name + "-" + fname}
                      type="text"
                      bind:value={edit[fname]}
                    />
                  {/if}
                </div>
              {/each}
            </div>
          </details>
        </div>
      {:else if hasChoices}
        <select bind:value={edit} disabled={isRO}>
          {#each property.choices as c}
            <option value={c}>{c}</option>
          {/each}
        </select>
      {:else if property?.type === 'bool'}
        <input type="checkbox" bind:checked={edit} disabled={isRO} />
      {:else if property?.type === 'int' || property?.type === 'float' || hasMinMax(property)}
        <input
          type="number"
          bind:value={edit}
          step={numStep(property)}
          min={property?.min}
          max={property?.max}
          disabled={isRO}
        />
      {:else}
        <input type="text" bind:value={edit} disabled={isRO} />
      {/if}
    {/if}
  </div>

  <div class="prop-cell param-set-button">
    {#if !isRO}
      <button on:click={propertySet} disabled={isRO}>Set</button>
    {/if}
  </div>
</div>



