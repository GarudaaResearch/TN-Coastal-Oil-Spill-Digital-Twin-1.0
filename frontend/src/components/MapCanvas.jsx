import { useRef, useEffect, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { energyColor } from '../utils/colormap'

// ── Grid / Geo constants (must match ocean_model.py) ─────────────────────────
const GRID_W  = 120
const GRID_H  = 90
const LON_MIN = 78.0
const LON_MAX = 80.0
const LAT_MIN = 8.0
const LAT_MAX = 13.5

/** Convert grid (row, col) → [lat, lng] */
function cellToLatLng(row, col) {
  const lat = LAT_MAX - (row / GRID_H) * (LAT_MAX - LAT_MIN)
  const lng = LON_MIN + (col / GRID_W) * (LON_MAX - LON_MIN)
  return [lat, lng]
}

// ── Canvas overlay draw ───────────────────────────────────────────────────────
function drawOverlay(map, canvas, state) {
  if (!state || !canvas || canvas.width === 0) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height
  ctx.clearRect(0, 0, w, h)

  /** Leaflet container-point for a grid cell */
  function cellToPoint(row, col) {
    return map.latLngToContainerPoint(cellToLatLng(row, col))
  }

  // ── 1. Oil concentration heatmap ─────────────────────────────────────────
  const grid = state.concentration_grid
  if (grid) {
    // Compute single cell pixel size once
    const p00 = cellToPoint(0, 0)
    const p01 = cellToPoint(0, 1)
    const p10 = cellToPoint(1, 0)
    const cellW = Math.max(1, Math.abs(p01.x - p00.x) + 1)
    const cellH = Math.max(1, Math.abs(p10.y - p00.y) + 1)

    for (let gy = 0; gy < GRID_H; gy++) {
      for (let gx = 0; gx < GRID_W; gx++) {
        const conc = grid[gy]?.[gx] ?? 0
        if (conc < 0.001) continue
        const pt = cellToPoint(gy, gx)
        const alpha = Math.min(conc * 5, 0.88)
        // Inferno-style: navy→purple→orange→yellow
        const r = Math.min(255, Math.floor(conc * 900))
        const g = Math.min(255, Math.floor(conc * 220))
        const b = Math.max(0, Math.floor(140 - conc * 500))
        ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`
        ctx.fillRect(pt.x, pt.y, Math.ceil(cellW), Math.ceil(cellH))
      }
    }
  }

  // ── 2. Sensitivity zone overlay (subtle gold tint on high-sens cells) ─────
  const sens = state.sensitivity_grid
  if (sens) {
    const p00 = cellToPoint(0, 0)
    const p01 = cellToPoint(0, 3)
    const p10 = cellToPoint(3, 0)
    const cW3 = Math.max(1, Math.abs(p01.x - p00.x))
    const cH3 = Math.max(1, Math.abs(p10.y - p00.y))
    for (let gy = 0; gy < GRID_H; gy += 3) {
      for (let gx = 0; gx < GRID_W; gx += 3) {
        const s = sens[gy]?.[gx] ?? 0
        if (s < 0.7) continue
        const pt = cellToPoint(gy, gx)
        ctx.fillStyle = `rgba(255, 193, 7, ${(s - 0.7) * 0.12})`
        ctx.fillRect(pt.x, pt.y, Math.ceil(cW3), Math.ceil(cH3))
      }
    }
  }

  // ── 3. WSN communication links ────────────────────────────────────────────
  const nodes  = state.sensor_nodes || []
  const nodeMap = {}
  nodes.forEach(n => { nodeMap[n.id] = n })

  ctx.save()
  ctx.lineWidth = 1
  const drawn = new Set()
  nodes.forEach(n => {
    if (!n.alive) return
    ;(n.neighbors || []).forEach(nbId => {
      const key = [Math.min(n.id, nbId), Math.max(n.id, nbId)].join('-')
      if (drawn.has(key)) return
      drawn.add(key)
      const nb = nodeMap[nbId]
      if (!nb || !nb.alive) return
      const p1 = cellToPoint(n.row, n.col)
      const p2 = cellToPoint(nb.row, nb.col)
      const energyAvg = ((n.energy / 50000) + (nb.energy / 50000)) / 2
      ctx.strokeStyle = `rgba(41,128,255,${0.10 + energyAvg * 0.22})`
      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.lineTo(p2.x, p2.y)
      ctx.stroke()
    })
  })
  ctx.restore()

  // ── 4. Routing next-hop arrows ─────────────────────────────────────────────
  ctx.save()
  nodes.forEach(n => {
    if (!n.alive || n.next_hop == null) return
    const nb = nodeMap[n.next_hop]
    if (!nb || !nb.alive) return
    const p1 = cellToPoint(n.row, n.col)
    const p2 = cellToPoint(nb.row, nb.col)
    const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x)
    const len = Math.hypot(p2.x - p1.x, p2.y - p1.y)
    if (len < 3) return

    ctx.strokeStyle = 'rgba(255,193,7,0.50)'
    ctx.lineWidth = 1.0
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(p1.x, p1.y)
    ctx.lineTo(p2.x, p2.y)
    ctx.stroke()
    ctx.setLineDash([])

    // Arrowhead
    const ax = p2.x - 6 * Math.cos(angle)
    const ay = p2.y - 6 * Math.sin(angle)
    ctx.fillStyle = 'rgba(255,193,7,0.70)'
    ctx.beginPath()
    ctx.moveTo(p2.x, p2.y)
    ctx.lineTo(ax + 3 * Math.cos(angle + Math.PI / 2), ay + 3 * Math.sin(angle + Math.PI / 2))
    ctx.lineTo(ax - 3 * Math.cos(angle + Math.PI / 2), ay - 3 * Math.sin(angle + Math.PI / 2))
    ctx.closePath()
    ctx.fill()
  })
  ctx.restore()

  // ── 5. Hydrochar deployment zones ─────────────────────────────────────────
  ctx.save()
  ;(state.hydrochar_units || []).forEach(u => {
    if (!u.active) return
    const pt  = cellToPoint(u.row, u.col)
    const pt2 = cellToPoint(u.row, u.col + (u.radius || 5))
    const r   = Math.max(12, Math.abs(pt2.x - pt.x))

    const grad = ctx.createRadialGradient(pt.x, pt.y, r * 0.3, pt.x, pt.y, r)
    grad.addColorStop(0, 'rgba(0,214,143,0.28)')
    grad.addColorStop(1, 'rgba(0,214,143,0.00)')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
    ctx.fill()

    ctx.strokeStyle = 'rgba(0,214,143,0.65)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
    ctx.stroke()
    ctx.setLineDash([])

    ctx.fillStyle = '#00d68f'
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2)
    ctx.fill()
  })
  ctx.restore()

  // ── 6. Sensor nodes ───────────────────────────────────────────────────────
  ctx.save()
  nodes.forEach(n => {
    const pt = cellToPoint(n.row, n.col)
    const energyPct = n.is_sink ? 100 : (n.energy / 50000) * 100
    const color = energyColor(energyPct)
    const r = n.is_sink ? 8 : 5

    if (!n.alive) {
      ctx.strokeStyle = 'rgba(120,120,120,0.55)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(pt.x - 3, pt.y - 3); ctx.lineTo(pt.x + 3, pt.y + 3)
      ctx.moveTo(pt.x + 3, pt.y - 3); ctx.lineTo(pt.x - 3, pt.y + 3)
      ctx.stroke()
      return
    }

    // Glow halo
    const glow = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, r * 2.5)
    const baseColor = color.replace(')', ',0.35)').replace('rgb', 'rgba')
    glow.addColorStop(0, baseColor)
    glow.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = glow
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, r * 2.5, 0, Math.PI * 2)
    ctx.fill()

    // Node dot
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
    ctx.fill()

    // Oil reading orange ring
    if (n.oil > 0.02) {
      ctx.strokeStyle = `rgba(255,123,44,${Math.min(n.oil * 8, 0.9)})`
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(pt.x, pt.y, r + 3, 0, Math.PI * 2)
      ctx.stroke()
    }

    // Sink label
    if (n.is_sink) {
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 9px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('SINK', pt.x, pt.y - 12)
    }
  })
  ctx.restore()

  // ── 7. Response agent vessels ──────────────────────────────────────────────
  ctx.save()
  ;(state.response_agents || []).forEach(ag => {
    const pt = cellToPoint(ag.row, ag.col)
    const isMaritime = ag.type === 'maritime'

    if (!ag.active) {
      ctx.strokeStyle = isMaritime
        ? 'rgba(41,128,255,0.28)' : 'rgba(255,193,7,0.28)'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.arc(pt.x, pt.y, 6, 0, Math.PI * 2)
      ctx.stroke()
      ctx.setLineDash([])
      return
    }

    ctx.fillStyle = isMaritime ? '#2980ff' : '#ffc107'
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(pt.x,     pt.y - 8)
    ctx.lineTo(pt.x + 6, pt.y)
    ctx.lineTo(pt.x,     pt.y + 8)
    ctx.lineTo(pt.x - 6, pt.y)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
  })
  ctx.restore()
}

// ── Custom Leaflet overlay layer ──────────────────────────────────────────────
function makeOverlayLayer(overlayCanvasRef, stateRef) {
  return L.Layer.extend({
    onAdd(map) {
      this._map = map
      const pane = map.getPane('overlayPane')
      const canvas = L.DomUtil.create('canvas', 'sim-leaflet-overlay', pane)
      overlayCanvasRef.current = canvas
      canvas.style.position    = 'absolute'
      canvas.style.top         = '0'
      canvas.style.left        = '0'
      canvas.style.pointerEvents = 'none'
      this._update()
      map.on('zoom move viewreset resize zoomend moveend', this._update, this)
    },

    onRemove(map) {
      map.off('zoom move viewreset resize zoomend moveend', this._update, this)
      if (overlayCanvasRef.current) {
        L.DomUtil.remove(overlayCanvasRef.current)
        overlayCanvasRef.current = null
      }
    },

    _update() {
      const map    = this._map
      const size   = map.getSize()
      const canvas = overlayCanvasRef.current
      if (!canvas) return
      canvas.width  = size.x
      canvas.height = size.y
      canvas.style.width  = size.x + 'px'
      canvas.style.height = size.y + 'px'
      // Reset transform so canvas aligns with container
      L.DomUtil.setPosition(canvas, { x: 0, y: 0 })
      drawOverlay(map, canvas, stateRef.current)
    },

    redraw() {
      if (!this._map) return
      drawOverlay(this._map, overlayCanvasRef.current, stateRef.current)
    },
  })
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function MapCanvas({ state, onCellClick }) {
  const mapDivRef      = useRef(null)
  const leafletMap     = useRef(null)
  const overlayCanvas  = useRef(null)
  const overlayInst    = useRef(null)
  const stateRef       = useRef(state)

  // Keep stateRef fresh on every render
  useEffect(() => { stateRef.current = state }, [state])

  // ── Initialise Leaflet once ───────────────────────────────────────────────
  useEffect(() => {
    if (!mapDivRef.current || leafletMap.current) return

    const map = L.map(mapDivRef.current, {
      center:           [10.75, 79.0],
      zoom:             8,
      zoomControl:      true,
      attributionControl: true,
      preferCanvas:     true,
    })
    leafletMap.current = map

    // Base layer — ESRI World Satellite (free, no API key)
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, USGS, AEX, GeoEye',
        maxZoom: 18,
      }
    ).addTo(map)

    // Label overlay — CartoDB dark labels (white text on satellite)
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png',
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains:  'abcd',
        maxZoom:     18,
        opacity:     0.85,
        pane:        'shadowPane',   // renders above tiles but below markers
      }
    ).addTo(map)

    // Simulation overlay canvas layer
    const OverlayClass = makeOverlayLayer(overlayCanvas, stateRef)
    const overlay = new OverlayClass()
    overlay.addTo(map)
    overlayInst.current = overlay

    // Map click → grid cell conversion
    map.on('click', (e) => {
      if (!onCellClick) return
      const { lat, lng } = e.latlng
      const col = Math.floor((lng - LON_MIN) / (LON_MAX - LON_MIN) * GRID_W)
      const row = Math.floor((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * GRID_H)
      if (col >= 0 && col < GRID_W && row >= 0 && row < GRID_H) {
        onCellClick({ row, col })
      }
    })

    return () => {
      map.remove()
      leafletMap.current  = null
      overlayInst.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Redraw overlay whenever simulation state updates ──────────────────────
  useEffect(() => {
    if (!leafletMap.current || !overlayCanvas.current || !state) return
    drawOverlay(leafletMap.current, overlayCanvas.current, state)
  }, [state])

  const alertActive = state?.response_metrics?.alert_active ?? false

  return (
    <div className={`canvas-container ${alertActive ? 'alert-glow' : ''}`}>

      {/* Leaflet map fills the container */}
      <div
        ref={mapDivRef}
        style={{ width: '100%', height: '100%', zIndex: 0 }}
      />

      {/* Overlay badges */}
      <div className="canvas-overlay" style={{ zIndex: 500, pointerEvents: 'none' }}>
        <div className="canvas-badge">
          🌊 T = {state ? state.t_hours.toFixed(2) : '0.00'} h
        </div>
        <div className="canvas-badge">
          💨 Wind {state?.wind_speed ?? 0} m/s @ {state?.wind_dir ?? 0}°
        </div>
        {alertActive && (
          <div className="canvas-badge" style={{
            color: '#ff3b5c',
            borderColor: 'rgba(255,59,92,0.45)',
            animation: 'pulse-dot 1s infinite',
          }}>
            🚨 SPILL DETECTED
          </div>
        )}
      </div>

      {/* Colormap legend */}
      <div className="canvas-legend" style={{ zIndex: 500 }}>
        <div style={{ fontSize: '0.62rem', color: 'var(--clr-text-3)', marginBottom: 3 }}>
          Oil Concentration
        </div>
        <div className="legend-bar" />
        <div className="legend-labels">
          <span>0</span><span>25</span><span>50 kg/m²</span>
        </div>
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {[
            { color: '#4ade80', label: 'Sensor Node (alive)'   },
            { color: '#ff3b5c', label: 'Node (critical energy)'},
            { color: '#00d68f', label: 'Hydrochar zone'         },
            { color: '#2980ff', label: 'Maritime vessel'        },
            { color: '#ffc107', label: 'Routing path'           },
          ].map(({ color, label }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{
                width: 8, height: 8,
                borderRadius: '50%',
                background: color,
                flexShrink: 0,
              }} />
              <span style={{ fontSize: '0.60rem', color: 'var(--clr-text-3)' }}>
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
