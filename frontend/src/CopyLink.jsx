import { useState } from 'react'

export default function CopyLink({ shortCode }) {
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)
  const shortUrl = new URL(`/r/${shortCode}`, window.location.origin).href

  async function copy() {
    if (pending) return
    setPending(true)
    setMessage('')
    try {
      await navigator.clipboard.writeText(shortUrl)
      setMessage('Copied!')
    } catch {
      setMessage('Could not copy. Select and copy the URL above.')
    } finally {
      setPending(false)
    }
  }

  return <div className="copy-link">
    <a href={shortUrl} target="_blank" rel="noopener noreferrer">{shortUrl}{' '}<span className="sr-only">(opens in a new tab)</span></a>
    <button type="button" disabled={pending} onClick={copy} aria-label={`Copy short URL ${shortCode}`}>{pending ? 'Copying…' : 'Copy'}</button>
    {message && <span role="status">{message}</span>}
  </div>
}
