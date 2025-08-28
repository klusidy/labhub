<script>
  import { onMount } from 'svelte';
  import { listDevices, openEvents } from './api';
  import DevicePage from './components/DevicePage.svelte';
  import faviconUrl from './assets/favicon.ico';

  let devices = [];
  let activeId = null;
  $: active = devices.find(d => d.id === activeId) || devices[0];

  function setActive(id){ activeId = id; }

  onMount(async () => {
    devices = await listDevices();
    if (!activeId && devices.length) activeId = devices[0].id;

    const ws = openEvents([]);
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === 'snapshot') {
        const ids = new Set(ev.devices.map(d=>d.id));
        // merge by id
        for (const snap of ev.devices) {
          const i = devices.findIndex(d=>d.id===snap.id);
          if (i === -1) devices = [...devices, snap];
          else devices[i] = { ...devices[i], ...snap };
        }
        devices = devices.filter(d=>ids.has(d.id));
        if (!activeId && devices.length) activeId = devices[0].id;
      } else if (ev.type === 'device.state') {
        const i = devices.findIndex(d=>d.id===ev.id);
        if (i !== -1) devices[i] = { ...devices[i], state: ev.state, status: 'connected' };
      }
    };
  });
</script>
<!--
<div class="bar">
  <strong>LabHub UI</strong>
  <span class="muted">/ui</span>
</div>-->

<svelte:head>
  <link rel="icon" href={faviconUrl} type="image/svg+xml" />
</svelte:head>

<div class="grid">
  <div class="sidebar">
    <div class="bar">
      <strong>LabHub UI</strong>
      <span class="muted">/ui</span>
    </div>
    <div class="muted">Devices</div>
    {#each devices as d}
      <div class="row">
        <button on:click={() => setActive(d.id)} class:selected={d.id===activeId}>{d.id}</button>
        <!--<span class="muted">{d.kind}</span>-->
        {#if d?.doc}
        <span class="prop-doc">{d.doc}</span>
        {/if}
      </div>
    {/each}
  </div>

<div class="content">
  {#if active}
    {#key active.id}
      <DevicePage d={active}/>
    {/key}
  {:else}
    <p>No devices.</p>
  {/if}
</div>
</div>

<style>
  .selected { outline: 2px solid #6aa7ff; }
</style>
