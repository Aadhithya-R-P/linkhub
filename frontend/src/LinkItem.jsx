import { useState } from 'react'
import { links, SessionExpiredError } from './links.js'
import CopyLink from './CopyLink.jsx'

export default function LinkItem({ link, disabled, onPendingChange, onUpdated, onDeleted, onSessionExpired }) {
  const [mode, setMode] = useState('view')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  function changeMode(nextMode) {
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
      const updated = await links.update(link.id, {
        destination_url: data.get('destination_url').trim(),
        is_active: data.get('is_active') === 'on',
      })
      onUpdated(updated)
      setMode('view')
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
    </div>
    <CopyLink shortCode={link.short_code} />
    <p className="destination">{link.destination_url}</p>
    <p className="muted">{link.expires_at ? `Expires: ${new Date(link.expires_at).toLocaleString()}` : 'No expiration'}</p>

    {mode === 'view' && <div className="link-actions">
      <button disabled={disabled} onClick={() => changeMode('edit')}>Edit</button>
      <button className="danger" disabled={disabled} onClick={() => changeMode('delete')}>Delete</button>
    </div>}
    {mode === 'edit' && <form onSubmit={save} aria-label={`Edit link ${link.short_code}`} aria-busy={pending}>
      <fieldset disabled={pending || disabled}>
        <label htmlFor={`destination-${link.id}`}>Destination URL</label>
        <input id={`destination-${link.id}`} name="destination_url" type="url" required maxLength={2083} defaultValue={link.destination_url} />
        <label className="checkbox-label">
          <input name="is_active" type="checkbox" defaultChecked={link.is_active} /> Enabled
        </label>
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
        <button disabled={pending || disabled} onClick={() => changeMode('view')}>Cancel</button>
      </div>
    </div>}
    {error && <p role="alert" className="errors">{error}</p>}
  </li>
}
