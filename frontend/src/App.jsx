import { useEffect, useState } from 'react'
import Registration from './Registration.jsx'
import { auth } from './auth.js'

export default function App() {
  const [view, setView] = useState('loading')
  const [user, setUser] = useState(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    let active = true
    auth.restore().then((account) => {
      if (active) { setUser(account); setView(account ? 'account' : 'login') }
    }).catch(() => {
      if (active) { setError('Unable to restore your session. Please sign in or reload to retry.'); setView('login') }
    })
    return () => { active = false }
  }, [])

  async function login(event) {
    event.preventDefault()
    if (pending) return
    const form = event.currentTarget
    const fields = new FormData(form)
    setPending(true)
    setError('')
    try {
      const account = await auth.login(fields.get('email').trim(), fields.get('password'))
      form.reset()
      setUser(account)
      setView('account')
    } catch (failure) {
      setError(failure instanceof TypeError ? 'Unable to reach LinkHub. Please try again.' : failure.message)
    } finally { setPending(false) }
  }

  async function logout() {
    if (pending) return
    setPending(true)
    setError('')
    setUser(null)
    setView('logout')
    try { await auth.logout(); setView('login') }
    catch (failure) { setError(failure.message) }
    finally { setPending(false) }
  }

  if (view === 'register') return <Registration onLogin={() => { setError(''); setView('login') }} />

  return <div className="page">
    <header className="brand"><span className="brand-mark" aria-hidden="true">↗</span> LinkHub</header>
    <main className="auth-layout">
      <section className="card" aria-labelledby="auth-title">
        {view === 'loading' ? <h1 id="auth-title" role="status">Restoring your session…</h1> :
          view === 'account' ? <>
            <p className="eyebrow">YOUR ACCOUNT</p>
            <h1 id="auth-title">Welcome, {user.display_name || 'link keeper'}.</h1>
            <p>{user.email}</p>
            <p className="muted">You are signed in. Link management is the next step.</p>
            <button onClick={logout}>Sign out</button>
          </> : view === 'logout' ? <>
            <h1 id="auth-title">Signing out</h1>
            <p role="status">{pending ? 'Ending your session…' : 'Your local session has been cleared.'}</p>
            {!pending && <button onClick={logout}>Retry logout</button>}
          </> : <>
            <p className="eyebrow">WELCOME BACK</p>
            <h1 id="auth-title">Sign in to LinkHub</h1>
            <form onSubmit={login} aria-busy={pending}>
              <fieldset disabled={pending}>
                <label htmlFor="email">Email</label>
                <input id="email" name="email" type="email" autoComplete="email" required maxLength={254} />
                <label htmlFor="password">Password</label>
                <input id="password" name="password" type="password" autoComplete="current-password" required maxLength={128} />
                <button className="submit" type="submit">{pending ? 'Signing in…' : 'Sign in'}</button>
              </fieldset>
            </form>
            <button className="secondary" disabled={pending} onClick={() => { setError(''); setView('register') }}>Create an account</button>
          </>}
        {error && <p className="errors" role="alert">{error}</p>}
      </section>
    </main>
  </div>
}
