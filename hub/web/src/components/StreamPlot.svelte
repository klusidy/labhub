<script>
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { onMount, onDestroy } from 'svelte';

  export let chunks = [];

  let el;
  let u = null;
  let X = []; let Y = [];

  function init() {
    if (!el) return;
    u?.destroy();
    u = new uPlot({
      width: el.clientWidth || 600, height: 300,
      series: [{}, {label:'y'}],
      axes: [{}, {}]
    }, [X, Y], el);
  }

  function append() {
    if (!u) return;
    const last = chunks[chunks.length-1];
    if (!last) return;
    X = X.concat(last.t || []); Y = Y.concat(last.y || []);
    u.setData([X, Y]);
  }

  onMount(() => {
    init();
    const r = new ResizeObserver(()=>init()); r.observe(el);
    const iv = setInterval(append, 200);
    onDestroy(()=>{clearInterval(iv); r.disconnect(); u?.destroy();});
  });
</script>

<div bind:this={el}></div>
