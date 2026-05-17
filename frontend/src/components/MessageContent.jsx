// "TCK/CMK/CGTIK Madde X" gibi multi-corpus referanslarini bold + renkli render eder.
// Ornek: "CMK Madde 91'e gore..." -> "CMK Madde 91" kismi <strong> ile sarilir.
// Desteklenen kaynak kodlari: TCK, CMK, CGTIK, TCK_GEREKCE, TCK_DOKTRIN

const LEGAL_REF_PATTERN = /(?:TCK|CMK|CGTIK|TCK_GEREKCE|TCK_DOKTRIN)\s+Madde\s+\d+(?:\/\d+)?/
const LEGAL_REF_SPLIT_REGEX = /((?:TCK|CMK|CGTIK|TCK_GEREKCE|TCK_DOKTRIN)\s+Madde\s+\d+(?:\/\d+)?)/g

export default function MessageContent({ text, isUser }) {
  if (!text) return null

  const parts = text.split(LEGAL_REF_SPLIT_REGEX)

  return (
    <div className="whitespace-pre-wrap leading-relaxed">
      {parts.map((part, i) =>
        LEGAL_REF_PATTERN.test(part) ? (
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
