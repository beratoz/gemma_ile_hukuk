export default function EmptyState() {
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
