// Auto-load widgets named after device kind, e.g. example_device.svelte
const loaders = import.meta.glob('./*.svelte');  // lazy chunks

export async function loadWidget(kind: string): Promise<any|null> {
  const path = `./${kind}.svelte`;
  const loader = loaders[path];
  if (!loader) return null;
  const mod = await loader();
  return mod?.default ?? null;
}
