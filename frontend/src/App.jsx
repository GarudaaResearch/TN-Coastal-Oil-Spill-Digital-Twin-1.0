import { useState, useCallback } from 'react'
import { useWebSocket, api } from './hooks/useWebSocket'
import MapCanvas          from './components/MapCanvas'
import ControlPanel      from './components/ControlPanel'
import Dashboard         from './components/Dashboard'
import AnalyticsCharts   from './components/AnalyticsCharts'
import AlertSystem       from './components/AlertSystem'
import Footer            from './components/Footer'

/**
 * App — root component.
 *
 * Layout:
 *  ┌─────────────────────────────────────────┐
 *  │               Header / Nav              │
 *  ├──────────┬──────────────────┬───────────┤
 *  │ Control  │  SimCanvas       │ Dashboard │
 *  │ Panel    │  (canvas 2D)     │ (metrics) │
 *  │          ├──────────────────┤           │
 *  │          │  AnalyticsCharts │           │
 *  ├──────────┴──────────────────┴───────────┤
 *  │                  Footer                 │
 *  └─────────────────────────────────────────┘
 *
 * Click modes:
 *  null    — no action on canvas click
 *  'spill' — inject oil spill at clicked cell
 *  'hydro' — deploy hydrochar at clicked cell
 */
export default function App() {
  const { state, connected, error } = useWebSocket()
  const [clickMode, setClickMode]   = useState(null)
  const [spillMass, setSpillMass]   = useState(5000)
  const [spillRate, setSpillRate]   = useState(0.5)
  const [hydroMass, setHydroMass]   = useState(50)

  // Expose spill/hydro params via context (simplified: read from ControlPanel defaults)
  const handleCellClick = useCallback(async ({ row, col }) => {
    if (!clickMode || !state?.running) return

    if (clickMode === 'spill') {
      await api.post('/spill/inject', {
        row, col,
        total_mass_kg: spillMass,
        release_rate_kg_s: spillRate,
      })
    } else if (clickMode === 'hydro') {
      await api.post('/hydrochar/deploy', { row, col, mass_kg: hydroMass })
    }
  }, [clickMode, state, spillMass, spillRate, hydroMass])

  return (
    <div className="app-root">

      {/* ── Header ─────────────────────────────────── */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-logo">🌊</div>
          <div>
            <div className="header-title">
              TN Coastal Oil Spill Digital Twin
            </div>
            <div className="header-subtitle">
              AI-Driven Bio-Adaptive Routing · Buoyant WSN · Magnetic Hydrochar · Tamil Nadu 2026
            </div>
          </div>
        </div>

        <div className="header-status">
          {/* Click-mode indicator */}
          {clickMode && (
            <div style={{
              padding: '4px 12px',
              borderRadius: 20,
              fontSize: '0.70rem',
              fontWeight: 600,
              background: clickMode === 'spill'
                ? 'rgba(248,113,113,0.12)' : 'rgba(52,211,153,0.12)',
              border: `1px solid ${clickMode === 'spill'
                ? 'rgba(248,113,113,0.35)' : 'rgba(52,211,153,0.35)'}`,
              color: clickMode === 'spill'
                ? 'var(--clr-danger)' : 'var(--clr-success)',
              cursor: 'pointer',
            }}
              onClick={() => setClickMode(null)}
              title="Click to cancel mode"
            >
              {clickMode === 'spill' ? '💧 PLACE SPILL — click canvas' : '🧲 PLACE HYDRO — click canvas'}
              &nbsp;✕
            </div>
          )}

          {/* Simulation time */}
          <div className="tick-counter">
            ⏱ {state ? `T=${state.t_hours.toFixed(2)}h · Tick #${state.tick}` : 'Waiting…'}
          </div>

          {/* Connection status */}
          <div className={`status-pill ${connected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot" />
            {connected ? 'Live' : 'Offline'}
          </div>

          {/* Error badge */}
          {error && (
            <div style={{
              fontSize: '0.68rem', color: 'var(--clr-danger)',
              maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }} title={error}>
              ⚠ {error}
            </div>
          )}
        </div>
      </header>

      {/* ── Main 3-column layout ───────────────────── */}
      <main className="app-main">

        {/* Left: Controls */}
        <ControlPanel
          state={state}
          clickMode={clickMode}
          onClickModeChange={setClickMode}
        />

        {/* Center: Canvas + Charts stacked vertically */}
        <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <MapCanvas
            state={state}
            onCellClick={handleCellClick}
          />
          <AnalyticsCharts state={state} />
        </div>

        {/* Right: Dashboard */}
        <Dashboard state={state} />

      </main>

      {/* ── Floating Alerts ────────────────────────── */}
      <AlertSystem state={state} />

      {/* ── Footer ─────────────────────────────────── */}
      <Footer />

      {/* ── No-connection overlay ──────────────────── */}
      {!connected && (
        <div style={{
          position: 'fixed', inset: 0,
          background: 'rgba(3,8,18,0.75)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 999,
          flexDirection: 'column',
          gap: 16,
        }}>
          <div style={{
            background: 'var(--clr-bg-2)',
            border: '1px solid var(--clr-border)',
            borderRadius: 16,
            padding: '32px 40px',
            textAlign: 'center',
            maxWidth: 440,
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 16 }}>🌊</div>
            <div style={{
              fontFamily: 'var(--ff-head)',
              fontSize: '1.2rem',
              fontWeight: 700,
              color: 'var(--clr-text-1)',
              marginBottom: 8,
            }}>
              Connecting to Simulation Backend…
            </div>
            <div style={{
              fontSize: '0.80rem',
              color: 'var(--clr-text-3)',
              lineHeight: 1.6,
              marginBottom: 20,
            }}>
              Ensure the FastAPI backend is running:<br />
              <code style={{
                fontFamily: 'var(--ff-mono)',
                color: 'var(--clr-accent-1)',
                fontSize: '0.75rem',
                background: 'var(--clr-bg-3)',
                padding: '4px 8px',
                borderRadius: 4,
                display: 'inline-block',
                marginTop: 8,
              }}>
                cd backend &amp;&amp; uvicorn main:app --reload
              </code>
            </div>
            <div style={{
              display: 'flex', gap: 8, justifyContent: 'center',
            }}>
              {[1,2,3].map(i => (
                <div key={i} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: 'var(--clr-accent-1)',
                  animation: `pulse-dot 1.2s ${i*0.2}s infinite`,
                }} />
              ))}
            </div>
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--clr-text-3)' }}>
            Auto-reconnecting every 2 seconds…
          </div>
        </div>
      )}
    </div>
  )
}
