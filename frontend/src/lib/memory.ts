const SESSION_KEY = 'literature_agent_session_id'

export function getStoredSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

export function setStoredSessionId(sessionId: string): void {
  try {
    sessionStorage.setItem(SESSION_KEY, sessionId)
  } catch {
    // ignore
  }
}

export function clearStoredSessionId(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    // ignore
  }
}
