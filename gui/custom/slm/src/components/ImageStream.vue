<template>
  <q-card flat bordered class="image-stream-card" :class="{ 'full-size': fullSize }">
   
    <q-card-section class="q-py-xs q-px-sm text-caption text-grey-7 shrink">
      {{ label }}
    </q-card-section>
    <q-separator />
    <div class="image-wrapper">
      <img v-if="imgSrc" :src="imgSrc" class="stream-img" />
      <div v-else class="text-grey-5 text-caption flex flex-center">
        waiting for stream...
      </div>
    </div>
  </q-card>
</template>



<script setup lang="ts">
  import { ref, onMounted, onUnmounted, watch } from 'vue'
  import { openImageStream, getImageFrame } from 'src/api/slm'

  const props = withDefaults(
    defineProps<{
      devicePath: string
      source: string
      label: string
      rate?: number
      fullSize?: boolean
    }>(),
    { rate: 5, fullSize: false }
  )

  const imgSrc = ref<string | null>(null)
  let ws: WebSocket | null = null

  function applyB64(b64: string) {
    imgSrc.value = `data:image/png;base64,${b64}`
  }

  async function connect() {
    if (ws) {
      ws.close()
      ws = null
    }

    // Show current frame immediately so we don't wait for the next push
    const current = await getImageFrame(props.devicePath, props.source)
    if (current) applyB64(current)

    // Subscribe to live updates
    const socket = openImageStream(props.devicePath, props.source, props.rate)
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as { image_b64?: string }
        if (msg.image_b64) applyB64(msg.image_b64)
      } catch {
        // ignore malformed frames
      }
    }
    socket.onerror = () => console.warn(`image stream ${props.devicePath}/${props.source} error`)
    socket.onclose = () => console.log(`image stream ${props.devicePath}/${props.source} closed`)
    ws = socket
  }

  onMounted(connect)
  onUnmounted(() => ws?.close())

  watch(() => [props.devicePath, props.source, props.rate], connect)
</script>

<style scoped>
.image-stream-card {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.image-wrapper {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stream-img {
  display: block;
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  image-rendering: pixelated;
}

  .image-stream-card.full-size {
    flex: 1;
    min-height: 0;
  }

</style>
