import { useEffect, useState } from 'react'
import { links, SessionExpiredError } from './links.js'
import CopyLink from './CopyLink.jsx'
import LinkItem from './LinkItem.jsx'

export default function Dashboard({ user, onLogout, onSessionExpired }) {
  const [items, setItems] = useState([])
  const [nextBeforeId, setNextBeforeId] = useState(null)
  const [beforeId, setBeforeId] = useState(null)
  const [retryCount, setRetryCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [createdLink, setCreatedLink] = useState(null)

  const [mutating, setMutating] = useState(false)

  function updateLink(updated) {
    setItems((previous) => previous.map((link) => link.id === updated.id ? updated : link))
    setCreatedLink((previous) => previous?.id === updated.id ? updated : previous)
  }

  function deleteLink(id) {
    setItems((previous) => previous.filter((link) => link.id !== id))
    setCreatedLink((previous) => previous?.id === id ? null : previous)
  }

  async function createLink(event) {
    event.preventDefault()
    if (creating || loading || mutating) return
    const form = event.currentTarget
    const destination = new FormData(form).get('destination_url').trim()
    setCreating(true)
    setCreateError('')
    setCreatedLink(null)
    try {
      const link = await links.create(destination)
      form.reset()
      setCreatedLink(link)
      // Start pagination over, including when we were already on page one.
      setItems([])
      setNextBeforeId(null)
      setBeforeId(null)
      setLoading(true)
      setRetryCount((previous) => previous + 1)
    } catch (failure) {
      if (failure instanceof SessionExpiredError) onSessionExpired()
      else setCreateError(failure.message)
    } finally {
      setCreating(false)
    }
  }

  // Changing the requested cursor loads a page. Cleanup ignores late responses
  // after logout/unmount or after this effect is replaced in StrictMode.
  useEffect(() => {
    let active = true

    async function loadPage() {
      setLoading(true)
      setError('')
      try {
        const page = await links.list(beforeId)
        if (!active) return
        if (beforeId === null) {
          setItems(page.items)
        } else {
          setItems((previous) => [...previous, ...page.items])
        }
        setNextBeforeId(page.next_before_id)
      } catch (failure) {
        if (!active) return
        if (failure instanceof SessionExpiredError) {
          onSessionExpired()
        } else {
          setError('Unable to load your links. Please try again.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadPage()
    return () => { active = false }
  }, [beforeId, retryCount, onSessionExpired])

  function loadMore() {
    if (loading || creating || mutating || nextBeforeId === null) return
    setLoading(true)
    setBeforeId(nextBeforeId)
  }

  function retry() {
    if (loading || creating || mutating) return
    setLoading(true)
    setRetryCount((previous) => previous + 1)
  }

  return <div className="page">
    <header className="dashboard-header">
      <span className="brand"><span className="brand-mark" aria-hidden="true">↗</span> LinkHub</span>
      <button className="sign-out" disabled={creating || mutating} onClick={onLogout}>Sign out</button>
    </header>
    <main className="dashboard">
      <p className="eyebrow">YOUR COLLECTION</p>
      <h1>Your links</h1>
      <p className="muted">Welcome, {user.display_name || 'link keeper'}. <span>{user.email}</span></p>
      <p className="muted">Newest first. Disabled and expired links remain here for reference.</p>

      <section className="card create-link" aria-labelledby="create-title">
        <h2 id="create-title">Create a short link</h2>
        <form onSubmit={createLink} aria-busy={creating}>
          <fieldset disabled={creating || loading || mutating}>
            <label htmlFor="destination_url">Destination URL</label>
            <input id="destination_url" name="destination_url" type="url" required maxLength={2083} placeholder="https://example.com" aria-describedby="destination-hint" />
            <p id="destination-hint" className="hint">Use an HTTP or HTTPS URL without embedded credentials.</p>
            <button type="submit">{creating ? 'Creating…' : 'Create link'}</button>
          </fieldset>
        </form>
        {createError && <p role="alert" className="errors">{createError}</p>}
        {createdLink && <div className="created-link">
          <p role="status">Link created.</p>
          <CopyLink key={createdLink.id} shortCode={createdLink.short_code} />
        </div>}
      </section>

      {items.length > 0 && <ul className="link-list" aria-label="Your links">
        {items.map((link) => <LinkItem
          key={link.id}
          link={link}
          disabled={loading || creating || mutating}
          onPendingChange={setMutating}
          onUpdated={updateLink}
          onDeleted={deleteLink}
          onSessionExpired={onSessionExpired}
        />)}
      </ul>}

      {!loading && !error && items.length === 0 && nextBeforeId === null && <div className="card empty-links">
        <h2>No links yet</h2>
        <p className="muted">Your saved links will appear here.</p>
      </div>}
      {loading && <p role="status">{items.length ? 'Loading more links…' : 'Loading your links…'}</p>}
      {error && <div className="list-error">
        <p className="errors" role="alert">{error}</p>
        <button disabled={loading || creating || mutating} onClick={retry}>Retry</button>
      </div>}
      {!error && nextBeforeId !== null && <button className="load-more" disabled={loading || creating || mutating} onClick={loadMore}>Load more</button>}
    </main>
  </div>
}
