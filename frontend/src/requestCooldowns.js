export class RequestDelayError extends Error {
  constructor(retryAt) {
    const seconds = Math.max(1, Math.ceil((retryAt - Date.now()) / 1000))
    super(`Too many link changes. Try again in ${seconds} seconds.`)
    this.retryAt = retryAt
  }
}

// A client-side convenience only: Redis enforces limits across tabs and devices.
export class RequestCooldowns {
  constructor() { this.delays = new Map() }

  check(scope) {
    const delay = this.delays.get(scope)
    if (delay?.retryAt > Date.now()) throw new RequestDelayError(delay.retryAt)
    this.delays.delete(scope)
  }

  observe(scope, response) {
    if (response.status !== 429) return
    const header = response.headers?.get('Retry-After')
    const seconds = header && /^\d+$/.test(header) ? Number(header) : NaN
    const deadline = Number.isFinite(seconds) ? Date.now() + seconds * 1000 : Date.parse(header)
    const retryAt = Number.isFinite(deadline) ? Math.max(Date.now() + 1000, deadline) : Date.now() + 5000
    const delay = { retryAt }
    this.delays.set(scope, delay)
    throw new RequestDelayError(delay.retryAt)
  }
}
