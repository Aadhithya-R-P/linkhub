import { auth } from './auth.js'

export class SessionExpiredError extends Error {
  constructor() {
    super('Your session has expired. Please sign in again.')
    this.name = 'SessionExpiredError'
  }
}

export class LinksClient {
  constructor(authClient = auth) {
    this.authClient = authClient
  }

  async update(id, data) {
    let response
    try {
      response = await this.authClient.apiFetch(`/api/links/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
    } catch {
      throw new Error('Unable to confirm the update. Reload your links before trying again.')
    }
    if (response.status === 401) throw new SessionExpiredError()
    if (response.status === 404) throw new Error('This link is no longer available. Reload your links.')
    const body = await response.json().catch(() => null)
    if (response.status === 200 && body?.id === id &&
        typeof body.destination_url === 'string' && typeof body.is_active === 'boolean' &&
        typeof body.short_code === 'string') return body
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const messages = body.detail.filter((error) => typeof error?.msg === 'string').map((error) => error.msg)
      if (messages.length) throw new Error(messages.join(' '))
    }
    throw new Error('Unable to confirm the update. Reload your links before trying again.')
  }

  async delete(id) {
    let response
    try {
      response = await this.authClient.apiFetch(`/api/links/${id}`, { method: 'DELETE' })
    } catch {
      throw new Error('Unable to confirm deletion. Reload your links before trying again.')
    }
    if (response.status === 401) throw new SessionExpiredError()
    if (response.status === 404) throw new Error('This link is no longer available. Reload your links.')
    if (response.status !== 204) {
      throw new Error('Unable to confirm deletion. Reload your links before trying again.')
    }
  }

  async create(destinationUrl) {
    let response
    try {
      response = await this.authClient.apiFetch('/api/links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ destination_url: destinationUrl }),
      })
    } catch {
      throw new Error('Unable to confirm creation. Reload your links before trying again.')
    }
    if (response.status === 401) throw new SessionExpiredError()
    const body = await response.json().catch(() => null)
    if (response.status === 201 && typeof body?.short_code === 'string') return body
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const messages = body.detail.filter((error) => typeof error?.msg === 'string').map((error) => error.msg)
      if (messages.length) throw new Error(messages.join(' '))
    }
    throw new Error('Unable to confirm creation. Reload your links before trying again.')
  }

  async list(beforeId = null) {
    const params = new URLSearchParams({ limit: '20' })
    if (beforeId !== null) {
      params.set('before_id', String(beforeId))
    }

    let response
    try {
      response = await this.authClient.apiFetch(`/api/links?${params}`)
    } catch {
      throw new Error('Unable to load your links. Please try again.')
    }
    if (response.status === 401) {
      throw new SessionExpiredError()
    }
    if (!response.ok) {
      throw new Error('Unable to load your links. Please try again.')
    }
    const page = await response.json()
    if (!Array.isArray(page.items) ||
        !(page.next_before_id === null || Number.isInteger(page.next_before_id))) {
      throw new Error('The server returned an invalid links page. Please try again.')
    }
    return page
  }
}

export const links = new LinksClient()
