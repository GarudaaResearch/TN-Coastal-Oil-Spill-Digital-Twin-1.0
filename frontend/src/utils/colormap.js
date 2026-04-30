/**
 * Colormap utilities for oil concentration heatmap rendering.
 * Uses a perceptually uniform INFERNO-style palette (dark → red → orange → yellow)
 * appropriate for scientific visualization of concentration data.
 */

/** Inferno-inspired stops: [r, g, b] at 0%, 25%, 50%, 75%, 100% */
const INFERNO_STOPS = [
  [0,   0,   0  ],   // 0.00 — black (no oil)
  [80,  18,  124],   // 0.25 — deep violet
  [188, 55,  84 ],   // 0.50 — crimson
  [251, 136, 31 ],   // 0.75 — amber
  [252, 255, 164],   // 1.00 — pale yellow (max conc)
]

/**
 * Map a normalized value [0,1] to an RGBA color string.
 * @param {number} v   - normalized concentration [0, 1]
 * @param {number} alpha - base alpha; actual alpha scales with v
 */
export function infernoColor(v, alpha = 1.0) {
  const t = Math.max(0, Math.min(1, v))
  const n = INFERNO_STOPS.length - 1
  const idx = t * n
  const i0 = Math.floor(idx)
  const i1 = Math.min(i0 + 1, n)
  const f = idx - i0

  const [r0, g0, b0] = INFERNO_STOPS[i0]
  const [r1, g1, b1] = INFERNO_STOPS[i1]
  const r = Math.round(r0 + f * (r1 - r0))
  const g = Math.round(g0 + f * (g1 - g0))
  const b = Math.round(b0 + f * (b1 - b0))
  const a = t < 0.01 ? 0 : alpha * (0.3 + 0.7 * t)  // transparent for near-zero

  return `rgba(${r},${g},${b},${a.toFixed(3)})`
}

/**
 * Build a full ImageData from a 2D concentration grid for canvas rendering.
 * @param {number[][]} grid  - GRID_H × GRID_W normalized values [0,1]
 * @param {number[][]} landMask - same shape, 1=ocean, 0=land
 * @param {number} W  - canvas pixel width
 * @param {number} H  - canvas pixel height
 * @param {number} gW - grid columns
 * @param {number} gH - grid rows
 */
export function buildHeatmapImageData(grid, landMask, W, H, gW, gH) {
  const data = new Uint8ClampedArray(W * H * 4)
  const scaleX = gW / W
  const scaleY = gH / H

  for (let py = 0; py < H; py++) {
    for (let px = 0; px < W; px++) {
      const gx = Math.min(Math.floor(px * scaleX), gW - 1)
      const gy = Math.min(Math.floor(py * scaleY), gH - 1)
      const idx = (py * W + px) * 4
      const v   = grid[gy][gx]
      const land = landMask ? landMask[gy][gx] : 1

      if (land < 0.5) {
        // Land — dark gray-green
        data[idx]     = 34
        data[idx + 1] = 49
        data[idx + 2] = 34
        data[idx + 3] = 220
      } else if (v < 0.005) {
        // Ocean — deep blue-teal
        const depth = 0.15 + 0.1 * Math.sin(py * 0.08) * Math.cos(px * 0.05)
        data[idx]     = Math.round(10  + depth * 20)
        data[idx + 1] = Math.round(40  + depth * 60)
        data[idx + 2] = Math.round(80  + depth * 80)
        data[idx + 3] = 255
      } else {
        // Oil concentration — inferno colormap
        const t = Math.max(0, Math.min(1, v))
        const n = INFERNO_STOPS.length - 1
        const fi = t * n
        const i0 = Math.floor(fi), i1 = Math.min(i0 + 1, n)
        const f = fi - i0
        const [r0, g0, b0] = INFERNO_STOPS[i0]
        const [r1, g1, b1] = INFERNO_STOPS[i1]
        data[idx]     = Math.round(r0 + f * (r1 - r0))
        data[idx + 1] = Math.round(g0 + f * (g1 - g0))
        data[idx + 2] = Math.round(b0 + f * (b1 - b0))
        data[idx + 3] = Math.round(120 + 135 * t)
      }
    }
  }
  return new ImageData(data, W, H)
}

/** Node energy → color mapping */
export function energyColor(energyPct) {
  if (energyPct > 60) return '#00e676'
  if (energyPct > 30) return '#ffeb3b'
  if (energyPct > 10) return '#ff9800'
  return '#f44336'
}

/** Sensitivity → subtle zone tint rgba */
export function sensitivityTint(s) {
  const r = Math.round(255 * s)
  const g = Math.round(80  * (1 - s))
  return `rgba(${r}, ${g}, 0, ${(0.08 + s * 0.18).toFixed(2)})`
}
