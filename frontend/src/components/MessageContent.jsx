// "TCK Madde X" referanslarini bold + renkli render eder.
// Ornek: "TCK Madde 141'e gore..." -> "TCK Madde 141" kismi <strong> ile sarilir.

const TCK_PATTERN = /TCK\s+Madde\s+\d+(?:\/\d+)?/
const TCK_SPLIT_REGEX = /(TCK\s+Madde\s+\d+(?:\/\d+)?)/g

export default function MessageContent({ text, isUser }) {
  if (!text) return null

  const parts = text.split(TCK_SPLIT_REGEX)

  return (
    <div className="whitespace-pre-wrap leading-relaxed">
      {parts.map((part, i) =>
        TCK_PATTERN.test(part) ? (
          <strong
            key={i}
            className={
              isUser
                ? 'font-bold underline decoration-2 underline-offset-2'
                : 'font-bold text-blue-600'
            }
          >
            {part}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </div>
  )
}
