import { useState, useEffect, useRef } from 'react'

/**
 * AlertSystem — floating toast notifications for real-time events.
 * Watches the response_metrics.recent_events array and displays
 * new events as timed, auto-dismissing toast banners.
 */
export default function AlertSystem({ state }) {
  const [toasts, setToasts]     = useState([])
  const seenRef                 = useRef(new Set())
  const events = state?.response_metrics?.recent_events ?? []

  useEffect(() => {
    events.forEach(ev => {
      // Use t + msg as unique key to avoid duplicate toasts
      const key = `${ev.t}-${ev.type}`
      if (seenRef.current.has(key)) return
      seenRef.current.add(key)

      const id = Date.now() + Math.random()
      setToasts(prev => [...prev, { ...ev, id }])

      // Auto-dismiss after 6 seconds
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, 6000)
    })
  }, [events])

  const dismiss = (id) => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <div className="alert-container">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`alert-item ${toast.type}`}
          onClick={() => dismiss(toast.id)}
          title="Click to dismiss"
        >
          <div className="alert-msg">{toast.msg}</div>
          <div className="alert-time">
            T = {(toast.t / 3600).toFixed(2)}h &nbsp;·&nbsp; click to dismiss
          </div>
        </div>
      ))}
    </div>
  )
}
