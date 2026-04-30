import { useEffect, useRef } from 'react'
import { Line } from 'react-chartjs-2'

const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: {
      labels: {
        color: '#94a3b8',
        font: { family: 'Inter', size: 10 },
        boxWidth: 10,
        padding: 10,
      }
    },
    tooltip: {
      backgroundColor: 'rgba(3,8,18,0.95)',
      titleColor: '#e2e8f0',
      bodyColor: '#94a3b8',
      borderColor: 'rgba(40,80,160,0.4)',
      borderWidth: 1,
    }
  },
  scales: {
    x: {
      display: true,
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: {
        color: '#64748b',
        font: { size: 9, family: 'JetBrains Mono' },
        maxTicksLimit: 8,
        maxRotation: 0,
      }
    },
    y: {
      display: true,
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: {
        color: '#64748b',
        font: { size: 9, family: 'JetBrains Mono' },
      }
    }
  }
}

function makeGradient(ctx, c1, c2) {
  const grad = ctx.createLinearGradient(0, 0, 0, 120)
  grad.addColorStop(0, c1)
  grad.addColorStop(1, c2)
  return grad
}

/**
 * AnalyticsCharts — full-width analytics strip below simulation canvas.
 * Shows three Chart.js line charts:
 *  1. Oil spill area over time
 *  2. Network energy level over time
 *  3. Cumulative oil removed over time
 */
export default function AnalyticsCharts({ state }) {
  const oil   = state?.oil_metrics       ?? {}
  const hydro = state?.hydrochar_metrics ?? {}
  const wsn   = state?.wsn_metrics       ?? {}

  const historyArea   = oil.history_area     ?? []
  const historyMass   = oil.history_mass     ?? []
  const historyRemoved = hydro.history_removed ?? []
  const historyEff    = hydro.history_efficiency ?? []
  const ticks = historyArea.map((_, i) => i)

  const labelCount = historyArea.length
  const labels = historyArea.map((_, i) => {
    const tHours = (state?.t_hours ?? 0) - (labelCount - 1 - i) * (300 / 3600)
    return tHours > 0 ? tHours.toFixed(2) + 'h' : ''
  })

  // ── Chart 1: Oil Area ──────────────────────────────────────
  const oilAreaData = {
    labels,
    datasets: [
      {
        label: 'Spill Area (km²)',
        data: historyArea,
        borderColor: '#f87171',
        backgroundColor: (ctx) => {
          const c = ctx.chart.ctx
          return makeGradient(c, 'rgba(248,113,113,0.25)', 'rgba(248,113,113,0.01)')
        },
        fill: true,
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
      }
    ]
  }

  // ── Chart 2: Cleanup ──────────────────────────────────────
  const cleanupData = {
    labels,
    datasets: [
      {
        label: 'Oil Removed (t)',
        data: historyRemoved.map(v => v / 1000),
        borderColor: '#34d399',
        backgroundColor: (ctx) => {
          const c = ctx.chart.ctx
          return makeGradient(c, 'rgba(52,211,153,0.22)', 'rgba(52,211,153,0.01)')
        },
        fill: true,
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Hydro Efficiency (%)',
        data: historyEff,
        borderColor: '#a78bfa',
        backgroundColor: 'transparent',
        tension: 0.4,
        borderWidth: 1.5,
        borderDash: [5, 3],
        pointRadius: 0,
        yAxisID: 'y2',
      }
    ]
  }

  // ── Chart 3: Mass over time ───────────────────────────────
  const massData = {
    labels,
    datasets: [
      {
        label: 'Oil Mass (t)',
        data: historyMass.map(v => v / 1000),
        borderColor: '#fb923c',
        backgroundColor: (ctx) => {
          const c = ctx.chart.ctx
          return makeGradient(c, 'rgba(251,146,60,0.22)', 'rgba(251,146,60,0.01)')
        },
        fill: true,
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 0,
      }
    ]
  }

  const cleanupOptions = {
    ...chartDefaults,
    scales: {
      ...chartDefaults.scales,
      y2: {
        position: 'right',
        display: true,
        grid: { drawOnChartArea: false },
        ticks: {
          color: '#64748b',
          font: { size: 9, family: 'JetBrains Mono' },
        },
        min: 0, max: 100,
      }
    }
  }

  return (
    <div style={{
      borderTop: '1px solid var(--clr-border)',
      background: 'rgba(8,15,30,0.6)',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr 1fr',
      gap: '0',
      height: '150px',
      flexShrink: 0,
    }}>
      {/* Oil Area */}
      <div style={{ padding:'10px 12px', borderRight:'1px solid var(--clr-border)' }}>
        <div className="section-title" style={{ marginBottom: 6 }}>
          📈 Oil Spill Area
        </div>
        <div style={{ height: 100 }}>
          <Line data={oilAreaData} options={chartDefaults} />
        </div>
      </div>

      {/* Mass */}
      <div style={{ padding:'10px 12px', borderRight:'1px solid var(--clr-border)' }}>
        <div className="section-title" style={{ marginBottom: 6 }}>
          ⚖ Oil Mass in Water
        </div>
        <div style={{ height: 100 }}>
          <Line data={massData} options={chartDefaults} />
        </div>
      </div>

      {/* Cleanup */}
      <div style={{ padding:'10px 12px' }}>
        <div className="section-title" style={{ marginBottom: 6 }}>
          ♻ Cleanup & Efficiency
        </div>
        <div style={{ height: 100 }}>
          <Line data={cleanupData} options={cleanupOptions} />
        </div>
      </div>
    </div>
  )
}
