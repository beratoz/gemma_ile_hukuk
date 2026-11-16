import MessageContent from './MessageContent'
import { extractUsedArticles } from '../lib/legalRefs'

export default function MessageBubble({ message }) {
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
