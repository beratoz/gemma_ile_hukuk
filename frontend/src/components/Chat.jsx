import { useState, useRef, useEffect } from 'react'
import MessageContent from './MessageContent'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080/api/chat'
const REQUEST_TIMEOUT_MS = 660_000 // gateway 600sn (10 dk), 60 sn buffer

// Mutalaa metninden gercekten kullanilan kanun referanslarini cikarir.
// Multi-corpus destek: TCK, CMK, CGTIK, TCK_GEREKCE, TCK_DOKTRIN.
// Sirayi metindeki ilk gorunume gore tutar, mukerrerleri eler.
// Ornek: "TCK Madde 151'e gore... CMK Madde 91 uyarinca..." -> ["TCK 151", "CMK 91"]
const LEGAL_REF_REGEX = /(TCK|CMK|CGTIK|TCK_GEREKCE|TCK_DOKTRIN)\s+Madde\s+(\d+(?:\/\d+)?)/gi
function extractUsedArticles(text) {
  if (!text) return []
  const matches = [...text.matchAll(LEGAL_REF_REGEX)]
  const seen = new Set()
  const ordered = []
  for (const m of matches) {
    const ref = `${m[1].toUpperCase()} ${m[2]}` // "TCK 151", "CMK 91"
    if (!seen.has(ref)) {
      seen.add(ref)
      ordered.push(ref)
    }
  }
  return ordered
}

const HISTORY_KEY = 'tck-hukuk-chat-v1'
const SAVE_KEY = 'tck-hukuk-save-enabled'
const MAX_MESSAGES = 100

function loadMessages() {
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

function loadSavePreference() {
  try { return localStorage.getItem(SAVE_KEY) !== 'off' }
  catch { return false }
}

// SSE olaylari ag parcalari veya Turkce UTF-8 karakterleri arasindan bolunebilir.
async function readEvents(response, onEvent) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  function consume(final = false) {
    buffer = buffer.replace(/\r\n/g, '\n')
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = block.split('\n').filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart()).join('\n')
      if (data) onEvent(JSON.parse(data))
    }
    if (final && buffer.trim() && !buffer.trim().startsWith(':')) {
      throw new Error('Yanit akisi tamamlanmadan baglanti kesildi.')
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        consume(true)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      consume()
    }
  } finally {
    // Protokol/JSON hatasinda da sunucudaki istegi acik birakma.
    try { await reader.cancel() } catch { /* Baglanti zaten kapanmis olabilir. */ }
    reader.releaseLock()
  }
}

export default function Chat() {
  const [messages, setMessages] = useState(loadMessages)
  const [saveEnabled, setSaveEnabled] = useState(loadSavePreference)
  const [storageWarning, setStorageWarning] = useState('')
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [stage, setStage] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const scrollAnchorRef = useRef(null)
  const inputRef = useRef(null)
  const activeRequestRef = useRef(null)
  const lastMessage = messages.at(-1)
  const clarification = lastMessage?.clarification || null

  useEffect(() => {
    // Her token icin diske yazmak yerine kisa araliklarla kaydet.
    const timer = setTimeout(() => {
      try {
        if (saveEnabled && messages.length) {
          localStorage.setItem(HISTORY_KEY, JSON.stringify(messages.slice(-MAX_MESSAGES)))
        } else {
          localStorage.removeItem(HISTORY_KEY)
        }
      } catch {
        setStorageWarning('Sohbet kaydedilemedi. Tarayıcı depolama iznini veya boş alanını kontrol edin.')
      }
    }, 400)
    return () => clearTimeout(timer)
  }, [messages, saveEnabled])

  useEffect(() => {
    function onStorage(event) {
      // Baska sekmede silinen sohbeti bu sekme yeniden kaydetmesin.
      if ((event.key === HISTORY_KEY || event.key === null) && event.newValue === null) {
        activeRequestRef.current?.controller.abort()
        activeRequestRef.current = null
        setMessages([])
        setIsLoading(false)
        setInput('')
      }
      if (event.key === SAVE_KEY) setSaveEnabled(event.newValue !== 'off')
    }
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener('storage', onStorage)
      activeRequestRef.current?.controller.abort()
    }
  }, [])

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: isLoading ? 'instant' : 'smooth', block: 'end' })
  }, [messages, isLoading])

  useEffect(() => {
    if (!isLoading) inputRef.current?.focus()
  }, [isLoading])

  useEffect(() => {
    if (!isLoading) return
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [isLoading])

  function toggleSaving() {
    const enabled = !saveEnabled
    try {
      localStorage.setItem(SAVE_KEY, enabled ? 'on' : 'off')
      if (!enabled) localStorage.removeItem(HISTORY_KEY)
      setSaveEnabled(enabled)
      setStorageWarning('')
    } catch {
      setStorageWarning('Tarayici depolamasina erisilemiyor.')
    }
  }

  function clearChat() {
    activeRequestRef.current?.controller.abort()
    activeRequestRef.current = null
    setMessages([])
    setInput('')
    setIsLoading(false)
    setStage('')
    try {
      localStorage.removeItem(HISTORY_KEY)
      setStorageWarning('')
    } catch {
      setStorageWarning('Kayit silinemedi. Tarayicinin site verilerini temizleyin.')
    }
  }

  async function submitQuestion(text, skipClarification = false) {
    if (activeRequestRef.current || (!text && !skipClarification)) return
    const pending = clarification
    const request = {
      soru: pending ? pending.originalQuestion : text,
      ...(pending ? {
        ek_soru: pending.question, ek_bilgi: skipClarification ? '' : text,
        ek_soru_yanitlandi: true,
      } : {}),
    }
    const userMessage = {
      id: crypto.randomUUID(), role: 'user',
      content: skipClarification ? 'Mevcut bilgilerle yanitla.' : text,
    }
    const answerId = crypto.randomUUID()
    const controller = new AbortController()
    const active = { controller, timedOut: false }
    activeRequestRef.current = active
    setMessages((previous) => [...previous, userMessage].slice(-MAX_MESSAGES))
    setInput('')
    setIsLoading(true)
    setStage('Bağlantı kuruluyor…')
    setElapsed(0)
    let finished = false
    let metadata = {}
    const timeout = setTimeout(() => {
      active.timedOut = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)

    function updateAnswer(update) {
      if (activeRequestRef.current !== active) return
      setMessages((previous) => {
        const exists = previous.some((message) => message.id === answerId)
        const answer = exists ? previous.find((message) => message.id === answerId)
          : { id: answerId, role: 'assistant', content: '', status: 'streaming' }
        const next = update(answer)
        return (exists ? previous.map((message) => message.id === answerId ? next : message)
          : [...previous, next]).slice(-MAX_MESSAGES)
      })
    }

    try {
      const response = await fetch(API_URL + '/stream', {
        method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(request),
      })
      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        throw new Error(error.message || `Sunucu hatasi: HTTP ${response.status}`)
      }
      if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
        throw new Error('Sunucudan beklenen yanit akisi alinamadi.')
      }
      await readEvents(response, (event) => {
        if (activeRequestRef.current !== active) return
        if (event.type === 'progress') setStage(event.message)
        if (event.type === 'sources') metadata = event
        if (event.type === 'token') {
          updateAnswer((answer) => ({ ...answer, content: answer.content + event.content, meta: metadata }))
        }
        if (event.type === 'result') {
          finished = true
          updateAnswer((answer) => ({
            ...answer, content: event.mutalaa, meta: event, status: 'complete',
            clarification: event.ek_soru ? { originalQuestion: request.soru, question: event.ek_soru } : null,
          }))
        }
        if (event.type === 'error') throw new Error(event.message)
      })
      if (!finished) throw new Error('Baglanti yanit tamamlanmadan kesildi.')
    } catch (error) {
      if (activeRequestRef.current !== active) return
      setMessages((previous) => [
        ...previous.map((message) => message.id === answerId ? { ...message, status: 'incomplete' } : message),
        { id: crypto.randomUUID(), role: 'error', content: controller.signal.aborted
          ? (active.timedOut ? 'Analiz zaman sinirina ulasti.' : 'Analiz durduruldu.')
          : error.message },
      ].slice(-MAX_MESSAGES))
    } finally {
      clearTimeout(timeout)
      if (activeRequestRef.current === active) {
        activeRequestRef.current = null
        setIsLoading(false)
        setStage('')
      }
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    const text = input.trim()
    if (text.length >= (clarification ? 1 : 3)) submitQuestion(text)
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      handleSubmit(event)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white shadow-sm shrink-0">
        <div className="max-w-3xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-base font-semibold text-gray-900">TCK Hukuk Asistanı</h1>
            <p className="text-xs text-gray-500">Yerel kaynaklarla ceza hukuku analizi</p>
          </div>
          <button type="button" onClick={clearChat} disabled={!messages.length && !isLoading}
            className="text-sm text-red-700 border border-red-200 rounded-lg px-3 py-2 hover:bg-red-50 disabled:opacity-40">
            Sohbeti sil
          </button>
          <div className="w-full text-xs text-gray-500 flex flex-wrap items-center gap-x-4 gap-y-1">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={saveEnabled} onChange={toggleSaving} />
              Sohbeti bu tarayıcıda kaydet
            </label>
            <span>{saveEnabled ? 'Son 100 mesaj bu cihazda saklanır.' : 'Kalıcı sohbet kaydı kapalı.'}</span>
          </div>
          {storageWarning && <p role="alert" className="text-xs text-red-700">{storageWarning}</p>}
        </div>
      </header>
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {messages.length === 0 && !isLoading && <EmptyState />}
          {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
          {isLoading && <TypingIndicator stage={stage} elapsed={elapsed} />}
          <div ref={scrollAnchorRef} />
        </div>
      </main>
      <footer className="border-t border-gray-200 bg-white shrink-0">
        {clarification && !isLoading && (
          <div className="max-w-3xl mx-auto px-4 pt-3 flex flex-wrap gap-2 items-center text-xs text-gray-600">
            <span>Bir kısa ek bilgi yeterli. İsterseniz bu soruyu atlayabilirsiniz.</span>
            <button type="button" onClick={() => submitQuestion('', true)}
              className="text-blue-700 underline underline-offset-2">Mevcut bilgilerle yanıtla</button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto px-4 py-4 flex gap-2 items-end">
          <textarea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown} aria-label={clarification ? 'Ek bilgi' : 'Hukuki soru'}
            placeholder={clarification ? 'Kısa ek bilgiyi yazın…' : 'Hukuki sorunu yazın… (Enter: gönder, Shift+Enter: yeni satır)'}
            maxLength={clarification ? 1200 : 2000} rows={2} disabled={isLoading}
            className="flex-1 resize-none px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 text-sm" />
          {isLoading ? (
            <button type="button" onClick={() => activeRequestRef.current?.controller.abort()}
              className="px-4 py-3 border border-red-200 text-red-700 rounded-2xl hover:bg-red-50 text-sm">Durdur</button>
          ) : (
            <button type="submit" disabled={input.trim().length < (clarification ? 1 : 3)}
              className="px-5 py-3 bg-blue-600 text-white rounded-2xl hover:bg-blue-700 disabled:bg-gray-300 text-sm">Gönder</button>
          )}
        </form>
        <p className="text-center text-xs text-gray-400 pb-2 px-4">
          Eğitim amaçlıdır. Hukuki danışmanlık yerine geçmez. Sohbet kaydı modele geçmiş konuşmaları hatırlatmaz.
        </p>
      </footer>
    </div>
  )
}

function EmptyState() {
  const examples = [
    'Hirsizlik yapan birinin cezasi nedir?',
    'Kasten yaralama suclari nelerdir?',
    'Mesru savunma sinirlari nelerdir?',
  ]
  return (
    <div className="text-center mt-12 px-4">
      <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-100 flex items-center justify-center text-3xl">
        ⚖️
      </div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">Merhaba!</h2>
      <p className="text-sm text-gray-600 mb-6">
        Hukuki bir soru sor — ilgili TCK maddelerine dayanarak mutalaa hazirlayim.
      </p>
      <div className="space-y-2 max-w-md mx-auto">
        <p className="text-xs text-gray-400 mb-2">Ornek sorular:</p>
        {examples.map((ex) => (
          <div
            key={ex}
            className="text-sm text-gray-600 bg-white border border-gray-200 rounded-lg px-3 py-2"
          >
            {ex}
          </div>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isError = message.role === 'error'

  if (isError) {
    return (
      <div className="flex justify-center">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg text-sm max-w-xl text-center">
          ⚠️ {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-2xl rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-white border border-gray-200 text-gray-800 shadow-sm'
        }`}
      >
        {message.status === 'incomplete' && <p className="mb-2 text-xs text-amber-700">Kısmi yanıt — analiz tamamlanmadı.</p>}
        {message.clarification && <p className="mb-2 text-xs font-medium text-blue-700">Kısa bir netleştirme</p>}
        <MessageContent text={message.content} isUser={isUser} />
        {!isUser && (() => {
          // Mutalaadan gercekten kullanilan referanslari parse et: ["TCK 125", "CMK 91"]
          const usedArticles = extractUsedArticles(message.content)
          // Backend'den gelen retrieved kayitlar: ["TCK 125", "CMK 91", ...] (multi-corpus)
          const retrievedArticles = (message.meta?.bulunan_madde_numaralari || []).map(String)
          const usedSet = new Set(usedArticles.map((s) => s.toUpperCase()))
          const otherCandidates = retrievedArticles.filter(
            (ref) => !usedSet.has(String(ref).toUpperCase())
          )

          return (
            <>
              {usedArticles.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-gray-500 mr-1">Kullanilan kaynaklar:</span>
                  {usedArticles.map((ref) => (
                    <span
                      key={ref}
                      className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium"
                    >
                      {ref}
                    </span>
                  ))}
                </div>
              )}
              {otherCandidates.length > 0 && (
                <details className="mt-2 text-xs text-gray-400">
                  <summary className="cursor-pointer hover:text-gray-600 select-none">
                    Diger aday kaynaklar ({otherCandidates.length})
                  </summary>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {otherCandidates.map((ref) => (
                      <span
                        key={ref}
                        className="bg-gray-50 text-gray-500 px-1.5 py-0.5 rounded"
                      >
                        {ref}
                      </span>
                    ))}
                  </div>
                </details>
              )}
            </>
          )
        })()}
      </div>
    </div>
  )
}

function TypingIndicator({ stage, elapsed }) {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm flex items-center gap-3">
        <div role="status" aria-live="polite">
          <span className="text-sm text-gray-600">{stage || 'Analiz sürüyor…'}</span>
          <span aria-hidden="true" className="block text-xs text-gray-400 mt-1">Gecen sure: {Math.floor(elapsed / 60)} dk {elapsed % 60} sn</span>
        </div>
        <div className="flex gap-1">
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '150ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
            style={{ animationDelay: '300ms' }}
          />
        </div>
      </div>
    </div>
  )
}
