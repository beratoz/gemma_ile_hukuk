// SSE olaylari ag parcalari veya Turkce UTF-8 karakterleri arasindan bolunebilir.
export async function readEvents(response, onEvent) {
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
