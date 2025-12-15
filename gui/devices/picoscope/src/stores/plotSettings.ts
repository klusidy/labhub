import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PlotSettings } from 'src/types/plotSettings'

const STORAGE_PREFIX = 'plotSettings'
const CURRENT_VERSION = 1

export const usePlotSettingsStore = defineStore('plotSettings', () => {
  // In-memory cache of all settings
  const settings = ref<Record<string, PlotSettings>>({})

  /**
   * Create storage key for a specific plot
   */
  function makeKey(plotArea: string, dataSource: string): string {
    return `${STORAGE_PREFIX}:${plotArea}:${dataSource}`
  }

  /**
   * Create default settings
   */
  function createDefaultSettings(): PlotSettings {
    return {
      xScale: 'linear',
      yScale: 'linear',
      zoom: { active: false },
      version: CURRENT_VERSION,
      timestamp: Date.now(),
    }
  }

  /**
   * Load settings from localStorage
   */
  function loadSettings(plotArea: string, dataSource: string): PlotSettings {
    const key = makeKey(plotArea, dataSource)
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return createDefaultSettings()

      const parsed = JSON.parse(raw) as PlotSettings

      // Validate version (for future migrations)
      if (parsed.version !== CURRENT_VERSION) {
        console.warn(`Settings version mismatch for ${key}, using defaults`)
        return createDefaultSettings()
      }

      return parsed
    } catch (e) {
      console.error(`Failed to load settings for ${key}:`, e)
      return createDefaultSettings()
    }
  }

  /**
   * Save settings to localStorage
   */
  function saveSettings(
    plotArea: string,
    dataSource: string,
    newSettings: PlotSettings
  ) {
    const key = makeKey(plotArea, dataSource)
    try {
      newSettings.timestamp = Date.now()
      localStorage.setItem(key, JSON.stringify(newSettings))
      settings.value[key] = newSettings
    } catch (e) {
      console.error(`Failed to save settings for ${key}:`, e)
    }
  }

  /**
   * Get settings for a specific plot (loads from localStorage if not cached)
   */
  function getSettings(plotArea: string, dataSource: string): PlotSettings {
    const key = makeKey(plotArea, dataSource)
    if (!settings.value[key]) {
      settings.value[key] = loadSettings(plotArea, dataSource)
    }
    return settings.value[key]
  }

  /**
   * Update scale setting for a specific axis
   */
  function updateScale(
    plotArea: string,
    dataSource: string,
    axis: 'x' | 'y',
    scale: 'linear' | 'log'
  ) {
    const current = getSettings(plotArea, dataSource)
    const updated: PlotSettings = {
      ...current,
      [`${axis}Scale`]: scale,
    }
    saveSettings(plotArea, dataSource, updated)
  }

  /**
   * Update zoom state
   */
  function updateZoom(
    plotArea: string,
    dataSource: string,
    zoomState: PlotSettings['zoom']
  ) {
    const current = getSettings(plotArea, dataSource)
    const updated: PlotSettings = {
      ...current,
      zoom: zoomState,
    }
    saveSettings(plotArea, dataSource, updated)
  }

  /**
   * Clear settings for a specific plot
   */
  function clearSettings(plotArea: string, dataSource: string) {
    const key = makeKey(plotArea, dataSource)
    localStorage.removeItem(key)
    delete settings.value[key]
  }

  /**
   * Clear all plot settings (useful for debugging/reset)
   */
  function clearAllSettings() {
    Object.keys(localStorage)
      .filter((k) => k.startsWith(STORAGE_PREFIX))
      .forEach((k) => localStorage.removeItem(k))
    settings.value = {}
  }

  /**
   * Clean up stale settings (optional utility for maintenance)
   */
  function cleanupStaleSettings(
    validSources: string[],
    maxAgeMs: number = 30 * 24 * 60 * 60 * 1000 // 30 days default
  ) {
    const now = Date.now()
    Object.keys(localStorage)
      .filter((k) => k.startsWith(STORAGE_PREFIX))
      .forEach((k) => {
        try {
          const raw = localStorage.getItem(k)
          if (!raw) return

          const parsed = JSON.parse(raw) as PlotSettings
          const age = now - parsed.timestamp

          // Extract dataSource from key (format: plotSettings:plotArea:dataSource)
          const parts = k.split(':')
          const dataSource = parts[2]

          if (!dataSource || age > maxAgeMs || !validSources.includes(dataSource)) {
            localStorage.removeItem(k)
            console.info(`Cleaned up stale setting: ${k}`)
          }
        } catch (e) {
          // Invalid format, delete
          localStorage.removeItem(k)
          console.info(`Cleaned up invalid setting: ${k}`)
        }
      })
  }

  return {
    getSettings,
    updateScale,
    updateZoom,
    clearSettings,
    clearAllSettings,
    cleanupStaleSettings,
  }
})
