export default function TypingIndicator({ stage, elapsed }) {
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
