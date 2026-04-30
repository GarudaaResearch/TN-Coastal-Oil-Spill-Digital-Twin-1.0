import { energyColor } from '../utils/colormap'

/**
 * Dashboard — right sidebar.
 * Real-time KPI metrics for all simulation modules,
 * sensor node list, hydrochar units, and event log.
 */
export default function Dashboard({ state }) {
  const oil   = state?.oil_metrics        ?? {}
  const wsn   = state?.wsn_metrics        ?? {}
  const route = state?.routing_metrics    ?? {}
  const hydro = state?.hydrochar_metrics  ?? {}
  const resp  = state?.response_metrics   ?? {}
  const nodes = state?.sensor_nodes       ?? []
  const units = state?.hydrochar_units    ?? []
  const events = resp?.recent_events      ?? []

  const energyPct = wsn.network_energy_pct ?? 100
  const cleanupEff = oil.cleanup_efficiency_pct ?? 0

  return (
    <div className="panel panel-right">

      {/* ── Oil Spill Metrics ──────────────────────── */}
      <div className="panel-section">
        <div className="section-title">🛢 Oil Spill Status</div>
        <div className="metric-grid">
          <div className="metric-card">
            <div className="metric-label">Spill Area</div>
            <div className={`metric-value ${oil.spill_area_km2 > 20 ? 'danger' : oil.spill_area_km2 > 5 ? 'warn' : ''}`}>
              {oil.spill_area_km2 ?? '0.000'}
            </div>
            <div className="metric-unit">km²</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Total Mass</div>
            <div className="metric-value amber">{((oil.total_mass_kg ?? 0) / 1000).toFixed(2)}</div>
            <div className="metric-unit">tonnes</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Max Conc.</div>
            <div className={`metric-value ${oil.max_concentration > 0.5 ? 'danger' : oil.max_concentration > 0.05 ? 'warn' : ''}`}>
              {(oil.max_concentration ?? 0).toFixed(4)}
            </div>
            <div className="metric-unit">kg/m²</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Eco Exposure</div>
            <div className="metric-value danger">{((oil.sensitivity_exposure ?? 0)/1000).toFixed(1)}</div>
            <div className="metric-unit">kg·km²</div>
          </div>
        </div>

        {/* Oil coverage bar */}
        <div className="progress-bar-container" style={{ marginTop: 10 }}>
          <div className="progress-label">
            <span>Spill Coverage</span>
            <span>{oil.spill_area_km2 ?? 0} km²</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill oil"
              style={{ width: `${Math.min(100, (oil.spill_area_km2 ?? 0) * 2)}%` }} />
          </div>
        </div>
      </div>

      {/* ── Cleanup Progress ────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">♻ Remediation Progress</div>
        <div className="metric-grid">
          <div className="metric-card">
            <div className="metric-label">Oil Removed</div>
            <div className="metric-value success">{((oil.oil_removed_kg ?? 0)/1000).toFixed(2)}</div>
            <div className="metric-unit">tonnes</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Cleanup Eff.</div>
            <div className={`metric-value ${cleanupEff > 60 ? 'success' : cleanupEff > 30 ? 'warn' : 'danger'}`}>
              {cleanupEff.toFixed(1)}%
            </div>
            <div className="metric-unit">efficiency</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Hydro Units</div>
            <div className="metric-value violet">{hydro.active_units ?? 0}</div>
            <div className="metric-unit">active</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Avg. Capacity</div>
            <div className="metric-value">{hydro.avg_efficiency_pct ?? 100}%</div>
            <div className="metric-unit">of q_max</div>
          </div>
        </div>
        <div className="progress-bar-container" style={{ marginTop: 10 }}>
          <div className="progress-label">
            <span>Cleanup Progress</span>
            <span>{cleanupEff.toFixed(1)}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill cleanup" style={{ width: `${cleanupEff}%` }} />
          </div>
        </div>
      </div>

      {/* ── WSN & Routing Metrics ───────────────────── */}
      <div className="panel-section">
        <div className="section-title">📡 WSN & AI Routing</div>
        <div className="metric-grid">
          <div className="metric-card">
            <div className="metric-label">Alive Nodes</div>
            <div className={`metric-value ${(wsn.alive_nodes ?? 0) < 10 ? 'danger' : (wsn.alive_nodes ?? 0) < 20 ? 'warn' : 'success'}`}>
              {wsn.alive_nodes ?? 0}<span style={{ fontSize:'0.7rem', color:'var(--clr-text-3)' }}>/{wsn.total_nodes ?? 0}</span>
            </div>
            <div className="metric-unit">nodes</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Network Energy</div>
            <div className={`metric-value ${energyPct < 20 ? 'danger' : energyPct < 50 ? 'warn' : 'success'}`}>
              {energyPct}%
            </div>
            <div className="metric-unit">residual</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Routing Algo</div>
            <div className="metric-value violet" style={{ fontSize:'0.72rem' }}>
              {route.algorithm?.split(' ')[0] ?? 'ACO'}
            </div>
            <div className="metric-unit">algorithm</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Routed Nodes</div>
            <div className="metric-value">{route.routed_nodes ?? 0}</div>
            <div className="metric-unit">with path</div>
          </div>
        </div>

        <div className="progress-bar-container" style={{ marginTop: 10 }}>
          <div className="progress-label">
            <span>Network Energy</span>
            <span>{energyPct}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill energy" style={{ width: `${energyPct}%` }} />
          </div>
        </div>

        {/* Packets sent */}
        <div style={{ marginTop: 8, fontSize:'0.68rem', color:'var(--clr-text-3)',
          display:'flex', justifyContent:'space-between' }}>
          <span>Packets Sent</span>
          <span style={{ fontFamily:'var(--ff-mono)', color:'var(--clr-accent-1)' }}>
            {wsn.total_packets_sent ?? 0}
          </span>
        </div>
        <div style={{ marginTop: 4, fontSize:'0.68rem', color:'var(--clr-text-3)',
          display:'flex', justifyContent:'space-between' }}>
          <span>Connectivity</span>
          <span style={{ fontFamily:'var(--ff-mono)', color:'var(--clr-accent-4)' }}>
            {((wsn.connectivity_ratio ?? 1) * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* ── Response System ──────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">🚨 Response System</div>
        <div className="metric-grid">
          <div className="metric-card">
            <div className="metric-label">Total Alerts</div>
            <div className={`metric-value ${resp.total_alerts > 0 ? 'danger' : ''}`}>
              {resp.total_alerts ?? 0}
            </div>
            <div className="metric-unit">generated</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Response Delay</div>
            <div className="metric-value warn">{resp.response_delay_h ?? 0}h</div>
            <div className="metric-unit">elapsed</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Agents</div>
            <div className="metric-value">{resp.active_agents ?? 0}/{resp.total_agents ?? 0}</div>
            <div className="metric-unit">active</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Skimmed</div>
            <div className="metric-value success">{((resp.total_skimmed_kg ?? 0)/1000).toFixed(2)}</div>
            <div className="metric-unit">tonnes</div>
          </div>
        </div>

        {/* Alert state pill */}
        {resp.alert_active && (
          <div style={{
            marginTop: 10, padding: '6px 10px',
            background: 'rgba(248,113,113,0.1)',
            border: '1px solid rgba(248,113,113,0.35)',
            borderRadius: 6, fontSize: '0.72rem', color: 'var(--clr-danger)',
            fontWeight: 600, textAlign: 'center',
            animation: 'pulse-dot 1.5s infinite',
          }}>
            🚨 ACTIVE SPILL ALERT — Response Mobilised
          </div>
        )}
      </div>

      {/* ── Sensor Node List ─────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">📻 Sensor Nodes (top 12)</div>
        <div className="node-list">
          {nodes.slice(0, 12).map(n => {
            const ePct = n.is_sink ? 100 : Math.min(100, (n.energy / 50000) * 100)
            return (
              <div key={n.id} className={`node-item ${!n.alive ? 'dead' : ''}`}>
                <div className="node-dot" style={{ background: energyColor(ePct) }} />
                <span className="node-id">#{n.id}</span>
                <div className="node-energy">
                  <div className="progress-bar" style={{ height: 3 }}>
                    <div className="progress-fill energy" style={{ width: `${ePct}%` }} />
                  </div>
                </div>
                <span className="node-oil">{n.oil > 0.001 ? n.oil.toFixed(3) : '—'}</span>
                {!n.alive && <span style={{ color:'var(--clr-danger)', fontSize:'0.60rem' }}>DEAD</span>}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Event Log ───────────────────────────────── */}
      <div className="panel-section">
        <div className="section-title">📋 Event Log</div>
        <div className="event-log">
          {events.length === 0 && (
            <div className="event-item" style={{ color:'var(--clr-text-3)' }}>
              No events yet. Start simulation to begin.
            </div>
          )}
          {[...events].reverse().map((ev, i) => (
            <div key={i} className="event-item">
              <span className="ev-time">{(ev.t / 3600).toFixed(2)}h</span>
              {ev.msg}
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
