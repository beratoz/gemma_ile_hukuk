// Mutalaa metninden gercekten kullanilan kanun referanslarini cikarir.
// Multi-corpus destek: TCK, CMK, CGTIK, TCK_GEREKCE, TCK_DOKTRIN.
// Sirayi metindeki ilk gorunume gore tutar, mukerrerleri eler.
// Ornek: "TCK Madde 151'e gore... CMK Madde 91 uyarinca..." -> ["TCK 151", "CMK 91"]
const LEGAL_REF_REGEX = /(TCK|CMK|CGTIK|TCK_GEREKCE|TCK_DOKTRIN)\s+Madde\s+(\d+(?:\/\d+)?)/gi
export function extractUsedArticles(text) {
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
