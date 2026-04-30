import { useRef, useEffect, useState, useCallback } from 'react'
import { buildHeatmapImageData, energyColor } from '../utils/colormap'

const GRID_W = 120
const GRID_H = 90

/**
 * SimulationCanvas — primary 2D renderer for the digital twin.
 *
 * Renders (in order, back-to-front):
 *  1. Ocean + land heatmap (via ImageData pixel buffer)
 *  2. Ecological sensitivity zone tints
 *  3. Oil concentration heatmap (INFERNO colormap)
 *  4. WSN communication links
 *  5. Sensor nodes (colored by energy)
 *  6. Hydrochar deployment zones (teal circles)
 *  7. Response agent vessels
 *  8. Routing path arrows (next-hop links)
 *  9. Coordinate tooltip on hover
 */
export default function SimulationCanvas({ state, onCellClick }) {
  const canvasRef   = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [canvasSize, setCanvasSize] = useState({ w: 720, h: 540 })
  const containerRef = useRef(null)

  // Fit canvas to container
  useEffect(() => {
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width, height } = e.contentRect
        const aspect = GRID_W / GRID_H
        const h = Math.min(height, width / aspect)
        const w = h * aspect
        setCanvasSize({ w: Math.floor(w), h: Math.floor(h) })
      }
    })
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Helpers
  const cellX = useCallback((col) => (col / GRID_W) * canvasSize.w, [canvasSize.w])
  const cellY = useCallback((row) => (row / GRID_H) * canvasSize.h, [canvasSize.h])
  const cellW = canvasSize.w / GRID_W
  const cellH = canvasSize.h / GRID_H

  // Main render
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !state) return
    const ctx = canvas.getContext('2d')
    const { w, h } = canvasSize

    // ── 1. Base heatmap (ocean + land + oil) ──────────────────
    const imgData = buildHeatmapImageData(
      state.concentration_grid,
      state.land_mask,
      w, h, GRID_W, GRID_H
    )
    ctx.putImageData(imgData, 0, 0)

    // ── 2. Sensitivity zone tints ─────────────────────────────
    const sens = state.sensitivity_grid
    if (sens) {
      for (let gy = 0; gy < GRID_H; gy += 3) {
        for (let gx = 0; gx < GRID_W; gx += 3) {
          const s = sens[gy][gx]
          if (s > 0.7) {
            ctx.fillStyle = `rgba(255, 180, 0, ${(s - 0.7) * 0.18})`
            ctx.fillRect(
              Math.floor(gx * cellW), Math.floor(gy * cellH),
              Math.ceil(3 * cellW),   Math.ceil(3 * cellH)
            )
          }
        }
      }
    }

    // ── 3. WSN Communication links ────────────────────────────
    const nodes = state.sensor_nodes || []
    const nodeMap = {}
    nodes.forEach(n => { nodeMap[n.id] = n })

    ctx.save()
    ctx.lineWidth = 0.8
    const drawn = new Set()
    nodes.forEach(n => {
      if (!n.alive) return
      ;(n.neighbors || []).forEach(nbId => {
        const key = [Math.min(n.id, nbId), Math.max(n.id, nbId)].join('-')
        if (drawn.has(key)) return
        drawn.add(key)
        const nb = nodeMap[nbId]
        if (!nb || !nb.alive) return
        const energyAvg = ((n.energy / 50000) + (nb.energy / 50000)) / 2
        ctx.strokeStyle = `rgba(56, 189, 248, ${0.08 + energyAvg * 0.18})`
        ctx.beginPath()
        ctx.moveTo(cellX(n.col), cellY(n.row))
        ctx.lineTo(cellX(nb.col), cellY(nb.row))
        ctx.stroke()
      })
    })
    ctx.restore()

    // ── 4. Routing next-hop arrows ────────────────────────────
    ctx.save()
    nodes.forEach(n => {
      if (!n.alive || n.next_hop == null) return
      const nb = nodeMap[n.next_hop]
      if (!nb || !nb.alive) return
      const x1 = cellX(n.col), y1 = cellY(n.row)
      const x2 = cellX(nb.col), y2 = cellY(nb.row)
      const angle = Math.atan2(y2 - y1, x2 - x1)
      const len = Math.sqrt((x2-x1)**2 + (y2-y1)**2)
      if (len < 2) return

      ctx.strokeStyle = 'rgba(167, 139, 250, 0.55)'
      ctx.lineWidth = 1.2
      ctx.setLineDash([4, 4])
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()

      // Arrowhead
      ctx.setLineDash([])
      const ax = x2 - 6 * Math.cos(angle)
      const ay = y2 - 6 * Math.sin(angle)
      ctx.fillStyle = 'rgba(167, 139, 250, 0.75)'
      ctx.beginPath()
      ctx.moveTo(x2, y2)
      ctx.lineTo(ax + 3 * Math.cos(angle + Math.PI/2),
                 ay + 3 * Math.sin(angle + Math.PI/2))
      ctx.lineTo(ax - 3 * Math.cos(angle + Math.PI/2),
                 ay - 3 * Math.sin(angle + Math.PI/2))
      ctx.closePath()
      ctx.fill()
    })
    ctx.restore()

    // ── 5. Hydrochar deployment zones ─────────────────────────
    ctx.save()
    ;(state.hydrochar_units || []).forEach(u => {
      if (!u.active) return
      const cx = cellX(u.col), cy = cellY(u.row)
      const rx = u.radius * cellW, ry = u.radius * cellH
      const r = Math.max(rx, ry)

      // Outer glow ring
      const grad = ctx.createRadialGradient(cx, cy, r * 0.3, cx, cy, r)
      grad.addColorStop(0, 'rgba(52, 211, 153, 0.20)')
      grad.addColorStop(1, 'rgba(52, 211, 153, 0.00)')
      ctx.fillStyle = grad
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      // Border
      ctx.strokeStyle = 'rgba(52, 211, 153, 0.55)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.stroke()
      ctx.setLineDash([])

      // Center marker
      ctx.fillStyle = '#34d399'
      ctx.beginPath()
      ctx.arc(cx, cy, 4, 0, Math.PI * 2)
      ctx.fill()
    })
    ctx.restore()

    // ── 6. Sensor nodes ───────────────────────────────────────
    ctx.save()
    nodes.forEach(n => {
      const cx = cellX(n.col), cy = cellY(n.row)
      const energyPct = n.is_sink ? 100 : (n.energy / 50000) * 100
      const color = energyColor(energyPct)
      const r = n.is_sink ? 8 : 5

      if (!n.alive) {
        // Dead node — small grey X
        ctx.strokeStyle = 'rgba(100,100,100,0.5)'
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(cx - 3, cy - 3); ctx.lineTo(cx + 3, cy + 3)
        ctx.moveTo(cx + 3, cy - 3); ctx.lineTo(cx - 3, cy + 3)
        ctx.stroke()
        return
      }

      // Glow
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 2.5)
      glow.addColorStop(0, color.replace(')', ',0.35)').replace('rgb', 'rgba'))
      glow.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = glow
      ctx.beginPath()
      ctx.arc(cx, cy, r * 2.5, 0, Math.PI * 2)
      ctx.fill()

      // Node dot
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      // Oil reading indicator (orange ring)
      if (n.oil > 0.02) {
        ctx.strokeStyle = `rgba(251,136,31,${Math.min(n.oil * 8, 0.9)})`
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.arc(cx, cy, r + 3, 0, Math.PI * 2)
        ctx.stroke()
      }

      // Sink node label
      if (n.is_sink) {
        ctx.fillStyle = '#fff'
        ctx.font = 'bold 9px JetBrains Mono'
        ctx.textAlign = 'center'
        ctx.fillText('SINK', cx, cy - 12)
      }
    })
    ctx.restore()

    // ── 7. Response agents ────────────────────────────────────
    ctx.save()
    ;(state.response_agents || []).forEach(ag => {
      const cx = cellX(ag.col), cy = cellY(ag.row)
      const isMaritime = ag.type === 'maritime'

      if (!ag.active) {
        // Waiting — faded outline only
        ctx.strokeStyle = isMaritime
          ? 'rgba(56,189,248,0.25)' : 'rgba(251,191,36,0.25)'
        ctx.lineWidth = 1
        ctx.setLineDash([3, 3])
        ctx.beginPath()
        ctx.arc(cx, cy, 6, 0, Math.PI * 2)
        ctx.stroke()
        ctx.setLineDash([])
        return
      }

      ctx.fillStyle = isMaritime ? '#38bdf8' : '#fbbf24'
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5

      // Diamond shape for vessel
      ctx.beginPath()
      ctx.moveTo(cx,     cy - 8)
      ctx.lineTo(cx + 6, cy)
      ctx.lineTo(cx,     cy + 8)
      ctx.lineTo(cx - 6, cy)
      ctx.closePath()
      ctx.fill()
      ctx.stroke()

      // Label
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 8px Inter'
      ctx.textAlign = 'center'
      ctx.fillText(isMaritime ? '⛴' : '🚒', cx, cy + 18)
    })
    ctx.restore()

    // ── 8. Coast zone labels ──────────────────────────────────
    ctx.save()
    const labels = [
      { text: 'Coromandel',  row: 75, col: 95 },
      { text: 'Palk Bay',    row: 42, col: 95 },
      { text: 'Gulf of Mannar', row: 15, col: 55 },
      { text: 'Mangroves',   row: 55, col: 103 },
    ]
    ctx.font = '500 8.5px Inter'
    ctx.textAlign = 'center'
    labels.forEach(l => {
      const x = cellX(l.col), y = cellY(l.row)
      ctx.fillStyle = 'rgba(148,163,184,0.70)'
      ctx.fillText(l.text, x, y)
    })
    ctx.restore()

  }, [state, canvasSize, cellX, cellY, cellW, cellH])

  // ── Mouse interaction ─────────────────────────────────────
  const handleMouseMove = useCallback((e) => {
    if (!state) return
    const rect = canvasRef.current.getBoundingClientRect()
    const px = e.clientX - rect.left
    const py = e.clientY - rect.top
    const gx = Math.floor((px / canvasSize.w) * GRID_W)
    const gy = Math.floor((py / canvasSize.h) * GRID_H)

    if (gx < 0 || gx >= GRID_W || gy < 0 || gy >= GRID_H) return

    const conc = state.concentration_grid?.[gy]?.[gx] ?? 0
    const sens = state.sensitivity_grid?.[gy]?.[gx] ?? 0
    const land = state.land_mask?.[gy]?.[gx] ?? 1

    setTooltip({
      x: e.clientX - rect.left + 12,
      y: e.clientY - rect.top - 8,
      gx, gy,
      conc: (conc * 50).toFixed(3),
      sens: (sens * 100).toFixed(0),
      land: land > 0.5 ? 'Ocean' : 'Land',
    })
  }, [state, canvasSize])

  const handleMouseLeave = useCallback(() => setTooltip(null), [])

  const handleClick = useCallback((e) => {
    if (!onCellClick) return
    const rect = canvasRef.current.getBoundingClientRect()
    const gx = Math.floor(((e.clientX - rect.left) / canvasSize.w) * GRID_W)
    const gy = Math.floor(((e.clientY - rect.top)  / canvasSize.h) * GRID_H)
    onCellClick({ row: gy, col: gx })
  }, [onCellClick, canvasSize])

  const alertActive = state?.response_metrics?.alert_active ?? false

  return (
    <div
      ref={containerRef}
      className={`canvas-container ${alertActive ? 'alert-glow' : ''}`}
    >
      <canvas
        ref={canvasRef}
        className="sim-canvas"
        width={canvasSize.w}
        height={canvasSize.h}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
      />

      {/* Overlay badges */}
      <div className="canvas-overlay">
        <div className="canvas-badge">
          🌊 T = {state ? (state.t_hours).toFixed(2) : '0.00'} h
        </div>
        <div className="canvas-badge">
          💨 Wind {state?.wind_speed ?? 0} m/s @ {state?.wind_dir ?? 0}°
        </div>
        {alertActive && (
          <div className="canvas-badge" style={{
            color: '#f87171', borderColor: 'rgba(248,113,113,0.4)',
            animation: 'pulse-dot 1s infinite'
          }}>
            🚨 SPILL DETECTED
          </div>
        )}
      </div>

      {/* Colormap legend */}
      <div className="canvas-legend">
        <div style={{ fontSize: '0.62rem', color: 'var(--clr-text-3)', marginBottom: 3 }}>
          Oil Concentration
        </div>
        <div className="legend-bar" />
        <div className="legend-labels">
          <span>0</span><span>25</span><span>50 kg/m²</span>
        </div>
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {[
            { color: '#4ade80', label: 'Sensor Node (alive)' },
            { color: '#f87171', label: 'Node (critical energy)' },
            { color: '#34d399', label: 'Hydrochar zone' },
            { color: '#38bdf8', label: 'Maritime vessel' },
          ].map(({ color, label }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontSize: '0.60rem', color: 'var(--clr-text-3)' }}>{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Cursor tooltip */}
      {tooltip && (
        <div className="canvas-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          Grid ({tooltip.gx}, {tooltip.gy}) — {tooltip.land}<br />
          Oil: {tooltip.conc} kg/m² | Sens: {tooltip.sens}%
        </div>
      )}
    </div>
  )
}
