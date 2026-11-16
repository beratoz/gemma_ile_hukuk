export const HISTORY_KEY = 'tck-hukuk-chat-v1'
export const SAVE_KEY = 'tck-hukuk-save-enabled'
export const MAX_MESSAGES = 100

export function loadMessages() {
  try {
    if (localStorage.getItem(SAVE_KEY) === 'off') return []
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    if (!Array.isArray(saved)) return []
    return saved.filter((message) =>
      message && typeof message.content === 'string' &&
      ['user', 'assistant', 'error'].includes(message.role)
    ).slice(-MAX_MESSAGES).map((message) => ({
      ...message, id: message.id || crypto.randomUUID(),
      status: message.status === 'streaming' ? 'incomplete' : message.status,
    }))
  } catch {
    return []
  }
}

export function loadSavePreference() {
  try { return localStorage.getItem(SAVE_KEY) !== 'off' }
  catch { return false }
}
