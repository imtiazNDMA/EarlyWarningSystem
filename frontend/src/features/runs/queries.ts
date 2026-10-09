import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api, type Run, type RunEvent } from '../../api/client'

/** Monitoring cycles, newest first. */
export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: async (): Promise<Run[]> => {
      const { data, error } = await api.GET('/api/runs')
      if (error) throw new Error('Monitoring runs could not be loaded.')
      return data
    },
    // Often enough that a cycle started elsewhere shows up while it is running
    refetchInterval: 5 * 1000,
  })
}

export type StreamState = 'connecting' | 'live' | 'ended' | 'interrupted'

/**
 * A run's event log, streamed from the server. A finished run arrives at once;
 * an active run keeps adding events until it finishes.
 */
export function useRunEvents(runId: number): { events: RunEvent[]; state: StreamState } {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [state, setState] = useState<StreamState>('connecting')

  // Callers key the component by run, so each run starts from empty state
  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/events`)

    source.onopen = () => setState('live')
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as RunEvent
      // After a dropped connection the browser resumes from the last event it
      // saw, so a repeat is not expected, but must not appear twice if it comes
      setEvents((seen) => (seen.some((other) => other.seq === event.seq) ? seen : [...seen, event]))
    }
    source.addEventListener('end', () => {
      // The server is done; closing stops the browser reconnecting
      source.close()
      setState('ended')
    })
    source.onerror = () => {
      // The browser retries by itself unless it has given up on the stream
      setState(source.readyState === EventSource.CLOSED ? 'ended' : 'interrupted')
    }

    return () => source.close()
  }, [runId])

  return { events, state }
}
