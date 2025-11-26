<script>
  import { onMount } from 'svelte';
  import { listDevices, openEvents } from './api';
  import DevicePage from './components/DevicePage.svelte';
  import faviconUrl from './assets/favicon.ico';

  let devices = [];
  let activeId = null;
  $: active = devices.find(d => d.id === activeId) || devices[0];

  function setActive(id){ activeId = id; }

  // snapshot form state
  let snapshotName   = 'snapshot_{now:%y%m%d_%H%M%S}';
  let snapshotBusy   = false;

  function formatNowInTemplate(template, now) {
    // support: snapshot_{now:%y%m%d_%H%M%S}
    const pad2 = (n) => String(n).padStart(2, '0');
    const yy = pad2(now.getFullYear() % 100);
    const MM = pad2(now.getMonth() + 1);
    const dd = pad2(now.getDate());
    const HH = pad2(now.getHours());
    const mm = pad2(now.getMinutes());
    const ss = pad2(now.getSeconds());

    const formatted = `${yy}${MM}${dd}_${HH}${mm}${ss}`;
    return template.replace(/{now:%y%m%d_%H%M%S}/g, formatted);
  }


  async function onSnapshot() {
    if (snapshotBusy) return;
    snapshotBusy = true;
    try {
      const devices = await listDevices();
      const now = new Date();
      const baseName = formatNowInTemplate(snapshotName, now) || 'snapshot';
      const filename = `${baseName}.json`;

      const blob = new Blob([JSON.stringify(devices, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      // browsers ignore directories here; user picks actual folder
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Snapshot failed', err);
    } finally {
      snapshotBusy = false;
    }
  }


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

    <div class="snapshot">
      <div class="muted snapshot-title">Snapshot</div>

      

      <div class="row">
        <input
          class="snapshot-name"
          type="text"
          bind:value={snapshotName}
        />
        <!-- <select bind:value={snapshotType}>
          <option value="json">json</option>
          <option value="yaml">yaml</option>
        </select> -->
     
       
        <button on:click={onSnapshot} disabled={snapshotBusy}>
          📸 save 
        </button>
        
      </div>
      
    </div>


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
