import { useState, useEffect, useRef, useCallback } from 'react'

// Backend URL — override via VITE_WS_URL in .env or Netlify env settings
const WS_URL  = import.meta.env.VITE_WS_URL  || 'ws://localhost:8000/ws/simulation'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const RECONNECT_DELAY_MS = 2000

/**
 * Custom hook that maintains a resilient WebSocket connection
 * to the simulation backend and exposes the latest state.
 *
 * Returns:
 *   state       — latest parsed JSON payload from server
 *   connected   — boolean connection status
 *   error       — last error message string | null
 */
export function useWebSocket() {
  const [state, setState]         = useState(null)
  const [connected, setConnected] = useState(false)
  const [error, setError]         = useState(null)
  const wsRef                     = useRef(null)
  const reconnectTimer            = useRef(null)
  const mountedRef                = useRef(true)

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnected(true)
        setError(null)
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current)
          reconnectTimer.current = null
        }
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const data = JSON.parse(event.data)
          setState(data)
        } catch (e) {
          console.warn('[WS] Parse error', e)
        }
      }

      ws.onerror = () => {
        if (!mountedRef.current) return
        setError('WebSocket connection error. Is the backend running?')
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        // Auto-reconnect
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  return { state, connected, error }
}

/** Simple REST helpers */
export const api = {
  async post(path, body = {}) {
    const res = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return res.json()
  },
  async get(path) {
    const res = await fetch(`${API_URL}${path}`)
    return res.json()
  }
}
