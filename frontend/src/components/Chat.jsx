import { useState, useRef, useEffect } from 'react'
import EmptyState from './EmptyState'
import MessageBubble from './MessageBubble'
import TypingIndicator from './TypingIndicator'
import { HISTORY_KEY, SAVE_KEY, MAX_MESSAGES, loadMessages, loadSavePreference } from '../lib/history'
import { readEvents } from '../lib/sse'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1/analyze'
const REQUEST_TIMEOUT_MS = 660_000 // LM Studio istemcisi 600 sn, 60 sn buffer

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
        throw new Error(error.message || (typeof error.detail === 'string' && error.detail) || `Sunucu hatasi: HTTP ${response.status}`)
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
