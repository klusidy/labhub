/**
 * Plot settings interface for persistent storage
 */
export interface PlotSettings {
  // Scale settings
  xScale: 'linear' | 'log'
  yScale: 'linear' | 'log'

  // Zoom state
  zoom: {
    active: boolean // true if user has zoomed, false if autoscale
    xRange?: [number, number] // Only present if zoomed
    yRange?: [number, number] // Only present if zoomed
    xType?: 'linear' | 'log' // Scale type when zoom was saved (for validation)
    yType?: 'linear' | 'log' // Scale type when zoom was saved (for validation)
  }

  // Metadata for validation and cleanup
  version: number // For future schema migrations
  timestamp: number // Last update time (milliseconds since epoch)
}
