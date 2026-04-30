import { useState } from 'react'
import { api } from '../hooks/useWebSocket'

/**
 * ControlPanel — left sidebar.
 * Simulation lifecycle, spill injection, hydrochar deployment,
 * routing algorithm selection, and click-mode switching.
 */
export default function ControlPanel({ state, onClickModeChange, clickMode }) {
  const [algo,     setAlgo]     = useState('aco')
  const [nodes,    setNodes]    = useState(40)
  const [spillMass, setSpillMass] = useState(5000)
  const [spillRate, setSpillRate] = useState(0.5)
  const [hydroMass, setHydroMass] = useState(50)
  const [loading,  setLoading]  = useState(false)
  const [msg,      setMsg]      = useState(null)

  const toast = (text, color = 'var(--clr-accent-1)') => {
    setMsg({ text, color })
    setTimeout(() => setMsg(null), 3000)
  }

  const doStart = async () => {
    setLoading(true)
    try {
      await api.post('/simulation/start', { seed: 42, n_nodes: nodes, algorithm: algo })
      toast('✅ Simulation started', 'var(--clr-success)')
    } catch { toast('❌ Failed to start. Is backend running?', 'var(--clr-danger)') }
    setLoading(false)
  }

  const doStop = async () => {
    await api.post('/simulation/stop')
    toast('⏸ Simulation paused', 'var(--clr-warn)')
  }

  const doResume = async () => {
    await api.post('/simulation/resume')
    toast('▶ Simulation resumed', 'var(--clr-success)')
  }

  const doSetAlgo = async (a) => {
    setAlgo(a)
    await api.post('/routing/algorithm', { algorithm: a })
    toast(`🔀 Routing: ${a.toUpperCase()}`, 'var(--clr-accent-3)')
  }

  const running = state?.running ?? false

  return (
    <div className="panel panel-left">
      {/* Notification toast */}
      {msg && (
        <div style={{
          padding: '10px 16px',
          background: 'rgba(8,15,30,0.95)',
          borderBottom: `2px solid ${msg.color}`,
          fontSize: '0.75rem',
          color: msg.color,
          fontWeight: 600,
          transition: 'all 0.3s',
        }}>
          {msg.text}
        </div>
      )}

      {/* ── Simulation Control ─────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">⚙ Simulation Control</div>

        <div className="form-group">
          <label className="form-label">Sensor Nodes</label>
          <div className="range-group">
            <input type="range" min={10} max={80} step={5}
              value={nodes} onChange={e => setNodes(+e.target.value)} />
            <span className="range-val">{nodes}</span>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">AI Routing Algorithm</label>
          <div className="tabs">
            {[['greedy','GEA-R'],['aco','ACO'],['qlearn','Q-Learn']].map(([k,v]) => (
              <button key={k} className={`tab ${algo===k?'active':''}`}
                onClick={() => doSetAlgo(k)}>{v}</button>
            ))}
          </div>
        </div>

        <div className="btn-row">
          <button className="btn btn-primary" onClick={doStart} disabled={loading}>
            {loading ? '⏳ Starting…' : '▶ Start / Reset'}
          </button>
          <div className="btn-row-h">
            <button className="btn btn-ghost" onClick={doStop}  disabled={!running}>⏸ Pause</button>
            <button className="btn btn-ghost" onClick={doResume} disabled={running}>▶ Resume</button>
          </div>
        </div>
      </div>

      {/* ── Spill Injection ────────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">💧 Spill Injection</div>
        <p style={{ fontSize:'0.68rem', color:'var(--clr-text-3)', marginBottom:10, lineHeight:1.5 }}>
          Click canvas to inject spill at chosen location, or use Quick Inject below.
        </p>

        <div className="form-group">
          <label className="form-label">Total Mass (kg)</label>
          <div className="range-group">
            <input type="range" min={500} max={20000} step={500}
              value={spillMass} onChange={e => setSpillMass(+e.target.value)} />
            <span className="range-val">{(spillMass/1000).toFixed(1)}t</span>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Release Rate (kg/s)</label>
          <div className="range-group">
            <input type="range" min={0.1} max={5.0} step={0.1}
              value={spillRate} onChange={e => setSpillRate(+e.target.value)} />
            <span className="range-val">{spillRate.toFixed(1)}</span>
          </div>
        </div>

        <div className="btn-row-h">
          <button
            className={`btn ${clickMode==='spill'?'btn-danger':'btn-ghost'}`}
            onClick={() => onClickModeChange(clickMode==='spill' ? null : 'spill')}
          >
            {clickMode==='spill' ? '✓ Click Map' : '🖱 Place Spill'}
          </button>
          <button className="btn btn-danger"
            onClick={() => api.post('/spill/inject',
              { row: 25, col: 40, total_mass_kg: spillMass, release_rate_kg_s: spillRate })
              .then(() => toast('💧 Spill injected!', 'var(--clr-accent-2)'))
            }
            disabled={!running}
          >
            Quick Inject
          </button>
        </div>
      </div>

      {/* ── Hydrochar Deployment ───────────────────────── */}
      <div className="panel-section">
        <div className="section-title">🧲 Hydrochar Deployment</div>
        <p style={{ fontSize:'0.68rem', color:'var(--clr-text-3)', marginBottom:10, lineHeight:1.5 }}>
          Magnetic hydrochar (q_max = 1200 mg/g). Click map to deploy at location.
        </p>

        <div className="form-group">
          <label className="form-label">Deploy Mass (kg)</label>
          <div className="range-group">
            <input type="range" min={10} max={200} step={10}
              value={hydroMass} onChange={e => setHydroMass(+e.target.value)} />
            <span className="range-val">{hydroMass}kg</span>
          </div>
        </div>

        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Stockpile Remaining</label>
          <div className="progress-bar-container">
            <div className="progress-bar">
              <div className="progress-fill cleanup" style={{
                width: `${Math.min(100, (state?.hydrochar_metrics?.total_available_kg ?? 1000) / 10)}%`
              }} />
            </div>
            <div className="progress-label">
              <span style={{ marginTop:3 }}>
                {state?.hydrochar_metrics?.total_available_kg ?? 1000} kg available
              </span>
            </div>
          </div>
        </div>

        <div className="btn-row-h" style={{ marginTop: 10 }}>
          <button
            className={`btn ${clickMode==='hydro'?'btn-success':'btn-ghost'}`}
            onClick={() => onClickModeChange(clickMode==='hydro' ? null : 'hydro')}
          >
            {clickMode==='hydro' ? '✓ Click Map' : '🖱 Place Hydro'}
          </button>
          <button className="btn btn-success"
            onClick={() => api.post('/hydrochar/deploy',
              { row: 25, col: 40, mass_kg: hydroMass })
              .then(() => toast('🧲 Hydrochar deployed!', 'var(--clr-accent-4)'))
            }
            disabled={!running}
          >
            Quick Deploy
          </button>
        </div>
      </div>

      {/* ── Coastal Zone Legend ────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">🌍 Coastal Zones</div>
        <div className="zone-tags">
          {[
            { name: 'Coromandel Coast',    color: '#1a6fa8', sens: '55%' },
            { name: 'Palk Bay',            color: '#2e9e6b', sens: '70%' },
            { name: 'Gulf of Mannar',      color: '#e8a020', sens: '95%' },
            { name: 'Mangroves/Estuaries', color: '#6d4c41', sens: '100%' },
          ].map(z => (
            <div key={z.name} className="zone-tag">
              <div className="zone-color" style={{ background: z.color }} />
              <span>{z.name}</span>
              <span className="zone-sens">{z.sens} sens.</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
