import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import MessageContent from './MessageContent'

const API_URL = 'http://localhost:8080/api/chat'
const REQUEST_TIMEOUT_MS = 660_000 // gateway 600sn (10 dk), 60 sn buffer

// Mutalaa metninden gercekten kullanilan TCK madde numaralarini cikarir.
// Sirayi metindeki ilk gorunume gore tutar, mukerrerleri eler.
// Ornek: "TCK Madde 151'e gore... TCK Madde 106 uyarinca..." -> ["151", "106"]
const TCK_NUMBER_REGEX = /TCK\s+Madde\s+(\d+(?:\/\d+)?)/gi
function extractUsedArticles(text) {
  if (!text) return []
  const matches = [...text.matchAll(TCK_NUMBER_REGEX)]
  const seen = new Set()
  const ordered = []
  for (const m of matches) {
    const no = m[1]
    if (!seen.has(no)) {
      seen.add(no)
      ordered.push(no)
    }
  }
  return ordered
}

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const scrollAnchorRef = useRef(null)
  const inputRef = useRef(null)

  // Yeni mesaj geldiginde / loading degisince en alta scroll
  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading])

  // Loading bittiginde input'a tekrar focus ver
  useEffect(() => {
    if (!isLoading) inputRef.current?.focus()
  }, [isLoading])

  async function handleSubmit(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isLoading) return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInput('')
    setIsLoading(true)

    try {
      const res = await axios.post(
        API_URL,
        { soru: text },
        { timeout: REQUEST_TIMEOUT_MS, headers: { 'Content-Type': 'application/json' } }
      )
      const {
        mutalaa,
        bulunan_madde_numaralari = [],
        cikarilan_kavramlar = [],
      } = res.data ?? {}

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: mutalaa || '(Bos cevap)',
          meta: { bulunan_madde_numaralari, cikarilan_kavramlar },
        },
      ])
    } catch (err) {
      let errorMsg
      if (err.code === 'ECONNABORTED') {
        errorMsg = 'Sunucu cevap vermedi (timeout). Lutfen tekrar deneyin.'
      } else if (err.response?.data?.message) {
        errorMsg = err.response.data.message
      } else if (err.response?.status) {
        errorMsg = `Sunucu hatasi: HTTP ${err.response.status}`
      } else {
        errorMsg = `Baglanti hatasi: ${err.message}`
      }
      setMessages((prev) => [...prev, { role: 'error', content: errorMsg }])
    } finally {
      setIsLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white shadow-sm shrink-0">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm">
            TCK
          </div>
          <div>
            <h1 className="text-base font-semibold text-gray-900 leading-tight">
              TCK Hukuk Asistani
            </h1>
            <p className="text-xs text-gray-500 leading-tight">
              Turk Ceza Kanunu uzerinde RAG tabanli analiz
            </p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {messages.length === 0 && !isLoading && <EmptyState />}

          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {isLoading && <TypingIndicator />}

          <div ref={scrollAnchorRef} />
        </div>
      </main>

      {/* Input */}
      <footer className="border-t border-gray-200 bg-white shrink-0">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto px-4 py-4 flex gap-2 items-end"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Hukuki sorunu yaz... (Enter ile gonder, Shift+Enter ile yeni satir)"
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed text-sm"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-5 py-3 bg-blue-600 text-white rounded-2xl hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition text-sm font-medium"
          >
            Gonder
          </button>
        </form>
        <p className="text-center text-xs text-gray-400 pb-2 px-4">
          Bu asistan egitim amaclidir, hukuki danismanlik yerine gecmez.
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
        <MessageContent text={message.content} isUser={isUser} />
        {!isUser && (() => {
          // Mutalaadan gercekten kullanilan maddeleri parse et
          const usedArticles = extractUsedArticles(message.content)
          // Backend'den gelen retrieved maddeleri al, kullanilmayanlari "diger aday" olarak goster
          const retrievedArticles = (message.meta?.bulunan_madde_numaralari || []).map(String)
          const usedSet = new Set(usedArticles)
          const otherCandidates = retrievedArticles.filter((no) => !usedSet.has(no))

          return (
            <>
              {usedArticles.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-gray-500 mr-1">Kullanilan maddeler:</span>
                  {usedArticles.map((no) => (
                    <span
                      key={no}
                      className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium"
                    >
                      Madde {no}
                    </span>
                  ))}
                </div>
              )}
              {otherCandidates.length > 0 && (
                <details className="mt-2 text-xs text-gray-400">
                  <summary className="cursor-pointer hover:text-gray-600 select-none">
                    Diger aday maddeler ({otherCandidates.length})
                  </summary>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {otherCandidates.map((no) => (
                      <span
                        key={no}
                        className="bg-gray-50 text-gray-500 px-1.5 py-0.5 rounded"
                      >
                        M.{no}
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

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm flex items-center gap-3">
        <span className="text-sm text-gray-500">Asistan dusunuyor</span>
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
