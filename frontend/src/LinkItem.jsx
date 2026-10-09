import { useEffect, useRef, useState } from 'react'
import { links, SessionExpiredError } from './links.js'
import CopyLink from './CopyLink.jsx'

// datetime-local expects local calendar fields, not a UTC ISO string.
function localExpiration(value) {
  if (!value) return ''
  const date = new Date(value)
  const pad = (part) => String(part).padStart(2, '0')
  return `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export default function LinkItem({ link, disabled, onPendingChange, onUpdated, onDeleted, onSessionExpired }) {
  const [mode, setMode] = useState('view')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now)
  const editButton = useRef(null)
  const deleteButton = useRef(null)
  const destinationInput = useRef(null)
  const deleteCancel = useRef(null)
  const focusAfterChange = useRef(null)
  const expiration = link.expires_at ? new Date(link.expires_at).getTime() : null
  const expired = expiration !== null && expiration <= now

  useEffect(() => {
    if (expiration === null || expiration <= now) return
    const timer = setTimeout(() => setNow(Date.now()), Math.min(Math.max(expiration - Date.now(), 0), 2147483647))
    return () => clearTimeout(timer)
  }, [expiration, now])

  useEffect(() => {
    if (pending || disabled) return
    focusAfterChange.current?.current?.focus()
    focusAfterChange.current = null
  }, [mode, pending, disabled])

  function changeMode(nextMode) {
    focusAfterChange.current = nextMode === 'edit' ? destinationInput
      : nextMode === 'delete' ? deleteCancel
      : mode === 'delete' ? deleteButton : editButton
    setError('')
    setMode(nextMode)
  }

  async function save(event) {
    event.preventDefault()
    if (pending || disabled) return
    const data = new FormData(event.currentTarget)
    setPending(true)
    onPendingChange(true)
    setError('')
    try {
      const changes = {
        destination_url: data.get('destination_url').trim(),
        is_active: data.get('is_active') === 'on',
      }
      const expiration = data.get('expires_at')
      // Preserve stored seconds/precision when the displayed minute is unchanged.
      if (expiration !== localExpiration(link.expires_at)) {
        const date = expiration ? new Date(expiration) : null
        if (date && (Number.isNaN(date.getTime()) || localExpiration(date) !== expiration)) {
          throw new Error('Enter a valid expiration date and time in your local timezone.')
        }
        changes.expires_at = date ? date.toISOString() : null
      }
      const updated = await links.update(link.id, changes)
      onUpdated(updated)
      changeMode('view')
    } catch (failure) {
      if (failure instanceof SessionExpiredError) onSessionExpired()
      else setError(failure.message)
    } finally {
      setPending(false)
      onPendingChange(false)
    }
  }

  async function remove() {
    if (pending || disabled) return
    setPending(true)
    onPendingChange(true)
    setError('')
    try {
      await links.delete(link.id)
      onDeleted(link.id)
    } catch (failure) {
      if (failure instanceof SessionExpiredError) onSessionExpired()
      else setError(failure.message)
    } finally {
      setPending(false)
      onPendingChange(false)
    }
  }

  return <li className="link-card" aria-label={`Link ${link.short_code}`}>
    <div className="link-heading">
      <code>{link.short_code}</code>
      <span className={link.is_active ? 'badge' : 'badge disabled'}>{link.is_active ? 'Enabled' : 'Disabled'}</span>
      {expired && <span className="badge expired">Expired</span>}
    </div>
    <CopyLink shortCode={link.short_code} />
    <p className="destination">{link.destination_url}</p>
    <p className="muted">{link.total_clicks} {link.total_clicks === 1 ? 'click' : 'clicks'}</p>
    <p className="muted">{link.expires_at ? `${expired ? 'Expired on' : 'Expires'}: ${new Date(link.expires_at).toLocaleString()}` : 'No expiration'}</p>

    {mode === 'view' && <div className="link-actions">
      <button ref={editButton} aria-label={`Edit link ${link.short_code}`} disabled={disabled} onClick={() => changeMode('edit')}>Edit</button>
      <button ref={deleteButton} aria-label={`Delete link ${link.short_code}`} className="danger" disabled={disabled} onClick={() => changeMode('delete')}>Delete</button>
    </div>}
    {mode === 'edit' && <form onSubmit={save} aria-label={`Edit link ${link.short_code}`} aria-busy={pending}>
      <fieldset disabled={pending || disabled}>
        <label htmlFor={`destination-${link.id}`}>Destination URL</label>
        <input ref={destinationInput} id={`destination-${link.id}`} name="destination_url" type="url" required maxLength={2083} defaultValue={link.destination_url} />
        <label className="checkbox-label">
          <input name="is_active" type="checkbox" defaultChecked={link.is_active} /> Enabled
        </label>
        <label htmlFor={`expiration-${link.id}`}>Expiration</label>
        <input id={`expiration-${link.id}`} name="expires_at" type="datetime-local" defaultValue={localExpiration(link.expires_at)} aria-describedby={`expiration-hint-${link.id}`} />
        <p id={`expiration-hint-${link.id}`} className="hint">Your local time. Leave blank for no expiration. Past dates expire immediately.</p>
        <div className="link-actions">
          <button type="submit">{pending ? 'Saving…' : 'Save'}</button>
          <button type="button" onClick={() => changeMode('view')}>Cancel</button>
        </div>
      </fieldset>
    </form>}
    {mode === 'delete' && <div>
      <p>Permanently delete this link? Its short URL will stop working.</p>
      <div className="link-actions">
        <button className="danger" disabled={pending || disabled} onClick={remove}>{pending ? 'Deleting…' : 'Confirm delete'}</button>
        <button ref={deleteCancel} disabled={pending || disabled} onClick={() => changeMode('view')}>Cancel</button>
      </div>
    </div>}
    {error && <p role="alert" className="errors">{error}</p>}
  </li>
}
