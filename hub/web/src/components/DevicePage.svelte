<script lang="ts">
  import { patchProperties, runCommand, openDataStream, getSpec, getPlotSpec, getFrame} from '../api';
  import PropertyField from './PropertyField.svelte';
  import CommandBlock from './CommandBlock.svelte';
  //import PlotBlock from './uPlot_PlotBlock.svelte';
  //import PlotBlock from './failed_from_scratch_PlotBlock.svelte';
  import PlotBlock from './PlotBlock.svelte';

  import { loadWidget } from '../device_widgets';
  //import StreamPlot from './StreamPlot.svelte';

  export let d:any;

    // spec state: undefined = loading, null = no spec/404, object = ok
  let spec:any = undefined;
  let lastId:any = null;

  let streamWS = null;
  let streamFmt = 'json';
  let cmdValues = {};


  async function fetchSpec(id:any) {
    try {
      const s = await getSpec(id);   // returns spec or null on 404
      if (lastId === id) spec = (s ?? null);
    } catch (e) {
      if (lastId === id) spec = null;
      console.error('spec load failed', e);
    }
  }

  $: if (d?.id && d.id !== lastId) {
    lastId = d.id;
    spec = undefined;
    fetchSpec(d.id);
  }

async function onPropertySet(name: string, value: any) {
  try {
    await patchProperties(d.id, { [name]: value }); // don't touch d here
    // events WS will push the fresh state — no bounce, no extra logic
  } catch (e) {
    console.error('PATCH failed:', e);
  }
}

//  async function onParamSet(name:any, value:any) {
//     const info = await patchParams(d.id, { [name]: value }).catch(console.error);
//     d.state = info;
//   }

// let saving = false;

// async function onParamSet(name: string, value: any) {
//   if (saving) return;
//   saving = true;
//   try {
//     const info = await patchParams(d.id, { [name]: value });
//     d.state = info;  // overwrite with authoritative state
//   } finally {
//     saving = false;
//   }
// }

  // let pending = new Set<string>();
  // async function onParamSet(name: string, value: any) {
  //   // 1) optimistic snapshot update
  //   pending.add(name);
  //   const prev = d;
  //   //d.state = { ...d.state, state: { ...d.state.state, [name]: value } };
  //   d = {...d, state: {...d.state, [name]: value}    };

  //   try {
  //     // 2) send PATCH; overwrite with server’s DeviceInfo
  //     const info = await patchParams(d.id, { [name]: value });
  //     d = info;
  //   } catch (err) {
  //     // 3) rollback if it failed
  //     d = prev;
  //     console.error("PATCH failed:", err);
  //   } finally {
  //     pending.delete(name);
  //   }
  // }


  function hasCmd(name:any) { return !!spec?.commands?.some((c: { name: any; }) => c.name === name); }

   async function onRunCommand(name: string, args: Record<string, any>) {
    try {
      const res = await runCommand(d.id, name, args);
      // optional: refresh state after commands that mutate state
      // await refreshState();
      return res;
    } catch (err) {
      console.error("Command failed:", err);
    }
  }


  const properties = () => (spec?.properties || []);//.filter((p: { read_only: any; }) => !p.read_only);
  //const commands = () => (spec?.commands || []);
  const plotSources = () => (spec?.data_sources || []).filter((s:any) => s?.has_plot); // TODO - is this filter relevant?

  // widget handling
  let Widget:any = null;
  let lastKind:any = null;
  $: if (d?.kind && d.kind !== lastKind) {
    lastKind = d.kind;
    Widget = null;
    loadWidget(d.kind).then(w => { if (lastKind === d.kind) Widget = w; });
  }
 // DEBUG ONLY
  $: if (d.state == null) {
    console.warn('DevicePage: state became', d.state);
    console.trace();
  }
</script>

<h2 class="device">{d.id}
  <!-- <span class="muted">[{d.kind}]</span>-->
</h2>

{#if Widget}
  <!--<h3>Live widget</h3>-->
  <svelte:component this={Widget} {d} {spec} />
{/if}


{#if spec === undefined}
  <p class="muted">Loading spec…</p>
{:else if spec === null}
  <p class="muted">No spec found for this device.</p>
{:else}


{#if plotSources().length}
<h3>Plots</h3>
<div class="plots-list">
  
    {#each plotSources() as s, i}
      <PlotBlock
        deviceId={d.id}
        source={s.name}
        index={i}
        defaultOpen={i === 0}
        {getPlotSpec}
        {getFrame}
        {openDataStream}
      />
    {/each}
</div>
{/if}





  <h3>Properties</h3>
  <div class="props-table">
    <div class="prop-row prop-header" style="font-weight:bold;">
      <span>Name</span>
      <span>Type</span>
      <span>Current</span>
      <span>Edit</span>
      <span></span>
    </div>
  {#each properties() as p}
  <PropertyField property={p}
                 value={d.state?.[p.name]}
                 on:propertySet={(e)=>onPropertySet(e.detail.name, e.detail.value)} />
  {/each}
  </div>

  
    <h3>Commands</h3>
    <div class="cmds-list">
      {#if Array.isArray(spec?.commands) && spec.commands.length}
        {#each spec.commands as c, i}
          <CommandBlock command={c} index={i} executor={onRunCommand} defaultOpen={false} />
        {/each}
      {:else}
        <div class="muted">No commands.</div>
      {/if}
    </div>

{/if}



<!-- //{#if hasCmd('start')}
//  <h3>Live plot</h3>
  <StreamPlot chunks={d.state?.__chunks || []} />
{/if} -->
