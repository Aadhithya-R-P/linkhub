import { useState } from 'react'

import { auth, RegistrationError } from './auth.js'

export default function Registration({ onLogin }) {
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState([])
  const [createdEmail, setCreatedEmail] = useState('')

  async function register(event) {
    event.preventDefault()
    if (pending) return
    const form = event.currentTarget
    const fields = new FormData(form)
    const data = {
      email: fields.get('email').trim(),
      password: fields.get('password'),
    }
    const displayName = fields.get('display_name').trim()
    if (displayName) data.display_name = displayName
    setPending(true)
    setErrors([])

    try {
      const user = await auth.register(data)
      form.reset()
      setCreatedEmail(user.email)
    } catch (failure) {
      if (failure instanceof RegistrationError) {
        setErrors(failure.messages)
      } else {
        setErrors(['Registration could not be completed. Please try again.'])
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="page">
      <header className="brand"><span className="brand-mark" aria-hidden="true">↗</span> LinkHub</header>
      <main className="layout">
        <section className="intro" aria-labelledby="intro-title">
          <p className="eyebrow">A HOME FOR YOUR LINKS</p>
          <h1 id="intro-title">Small links.<br />Simple sharing.</h1>
          <p className="description">Create short links and keep their destinations, availability, and expiration in one place.</p>
          <div className="link-example" aria-hidden="true">
            <span>YOUR NEXT GREAT FIND</span>
            <div>example.com/articles/something-worth-sharing</div>
            <strong>↳ &nbsp; /r/21</strong>
          </div>
        </section>
        <section className="card" aria-labelledby="form-title">
          {createdEmail ? (
            <div role="status">
              <span className="success-mark" aria-hidden="true">✓</span>
              <h2 id="form-title">Your account is ready.</h2>
              <p>Registered as <strong>{createdEmail}</strong>.</p>
              <p className="muted">You can now sign in to your account.</p>
              <button onClick={onLogin}>Sign in</button>
            </div>
          ) : (
            <>
              <p className="eyebrow">GET STARTED</p>
              <h2 id="form-title">Create your account</h2>
              <p className="muted">A little less URL. A little more control.</p>
              <form onSubmit={register} aria-busy={pending}>
                <fieldset disabled={pending}>
                  <label htmlFor="display_name">Display name <span className="optional">(optional)</span></label>
                  <input id="display_name" name="display_name" autoComplete="nickname" maxLength={100} />
                  <label htmlFor="email">Email</label>
                  <input id="email" name="email" type="email" autoComplete="email" required maxLength={254} />
                  <label htmlFor="password">Password</label>
                  <input id="password" name="password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} aria-describedby="password-hint" />
                  <p id="password-hint" className="hint">Use 15–128 characters. A memorable phrase works well.</p>
                  {errors.length > 0 && <div className="errors" role="alert"><ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul></div>}
                  <button type="submit">{pending ? 'Creating account…' : 'Create account'}<span aria-hidden="true"> →</span></button>
                </fieldset>
              </form>
              <button className="secondary" onClick={onLogin} disabled={pending}>Already registered? Sign in</button>
            </>
          )}
        </section>
      </main>
      <footer>LinkHub · Keep good links close.</footer>
    </div>
  )
}
