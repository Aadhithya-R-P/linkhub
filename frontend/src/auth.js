// Browser requests by default; tests can supply a fake request function.
function browserRequest(url, options) {
  return fetch(url, options)
}

// Registration can fail with several field-validation messages at once.
export class RegistrationError extends Error {
  constructor(messages) {
    super(messages.join('\n'))
    this.name = 'RegistrationError'
    this.messages = messages
  }
}

export class AuthClient {
  constructor(request = browserRequest) {
    this.request = request

    // Instance fields, not React state. The browser manages the refresh cookie.
    this.accessToken = null
    this.pendingRefresh = null
    this.pendingLogout = null

    // Login/logout change this number, making older requests obsolete.
    this.sessionVersion = 0
  }

  // REGISTER: create an account without signing in or refreshing credentials.
  async register(data) {
    let response
    try {
      response = await this.postAuthRequest('register', data)
    } catch {
      throw new RegistrationError(['Unable to reach LinkHub. Check your connection and try again.'])
    }

    const body = await response.json().catch(() => null)
    if (response.status === 201 && typeof body?.email === 'string') {
      return body
    }
    if (response.status === 409) {
      throw new RegistrationError(['This email is already registered. Please use another email.'])
    }
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fieldNames = { email: 'Email', password: 'Password', display_name: 'Display name' }
      const messages = []
      for (const error of body.detail) {
        if (typeof error?.msg === 'string') {
          const field = fieldNames[error.loc?.[1]] ?? 'Form'
          messages.push(`${field}: ${error.msg}`)
        }
      }
      if (messages.length > 0) {
        throw new RegistrationError(messages)
      }
    }
    throw new RegistrationError(['Registration could not be completed. Please try again.'])
  }

  // LOGIN: send credentials, remember the token, then load the user.
  async login(email, password) {
    if (this.pendingLogout) {
      await this.pendingLogout
    }
    if (this.pendingRefresh) {
      await this.waitForPendingRefresh()
    }

    this.sessionVersion += 1
    this.accessToken = null

    const credentials = { email: email, password: password }
    const response = await this.postAuthRequest('login', credentials)
    this.accessToken = await this.readAccessToken(response)

    const user = await this.getCurrentUser()
    if (!user) {
      throw new Error('Your session could not be started. Please sign in again.')
    }
    return user
  }

  // RESTORE: on page load, exchange the remaining cookie for a new token.
  async restore() {
    const token = await this.refreshAccessToken()
    if (!token) {
      return null
    }
    return this.getCurrentUser()
  }

  // LOGOUT: clear local credentials immediately, then revoke the server session.
  logout() {
    if (this.pendingLogout) {
      return this.pendingLogout
    }
    this.sessionVersion += 1
    this.accessToken = null

    this.pendingLogout = this.endServerSession().finally(() => {
      this.accessToken = null
      this.pendingLogout = null
    })
    return this.pendingLogout
  }

  async endServerSession() {
    const failureMessage = 'Signed out locally, but the server could not end the session. Retry logout before reloading.'
    try {
      // Wait for any replacement cookie before sending it to logout.
      if (this.pendingRefresh) {
        await this.waitForPendingRefresh()
      }
      const response = await this.postAuthRequest('logout')
      if (!response.ok) {
        throw new Error(failureMessage)
      }
    } catch {
      // HTTP errors and connection failures need the same explanation.
      throw new Error(failureMessage)
    }
  }

  // PROTECTED REQUESTS: send the token and retry once after a 401 if possible.
  async apiFetch(path, options = {}) {
    if (!path.startsWith('/api/') || path.includes('..')) {
      throw new Error('Expected a local API path.')
    }
    const requestSessionVersion = this.sessionVersion
    const originalToken = this.accessToken
    const response = await this.sendWithToken(path, options, originalToken)

    if (response.status !== 401) {
      return response
    }
    if (this.sessionVersion !== requestSessionVersion || this.pendingLogout) {
      return response
    }

    let retryToken
    if (this.accessToken && this.accessToken !== originalToken) {
      // Another request already refreshed while this response was arriving.
      retryToken = this.accessToken
    } else {
      retryToken = await this.refreshAccessToken()
    }
    if (!retryToken || this.sessionVersion !== requestSessionVersion) {
      return response
    }
    // Do not call apiFetch again: a second 401 must not start a retry loop.
    return this.sendWithToken(path, options, retryToken)
  }

  sendWithToken(path, options, token) {
    const headers = new Headers(options.headers)
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    } else {
      headers.delete('Authorization')
    }
    const requestOptions = { ...options }
    requestOptions.headers = headers
    requestOptions.credentials = 'same-origin'
    return this.request(path, requestOptions)
  }

  async getCurrentUser() {
    const response = await this.apiFetch('/api/auth/me')
    if (response.status === 401) {
      this.accessToken = null
      return null
    }
    if (!response.ok) {
      throw new Error('Unable to load your account. Please try again.')
    }
    return response.json()
  }

  // REFRESH: callers in this tab share one pending refresh operation.
  refreshAccessToken() {
    if (this.pendingLogout) {
      return Promise.resolve(null)
    }
    if (this.pendingRefresh) {
      return this.pendingRefresh
    }
    this.pendingRefresh = this.requestNewAccessToken().finally(() => {
      this.pendingRefresh = null
    })
    return this.pendingRefresh
  }

  async requestNewAccessToken() {
    const refreshSessionVersion = this.sessionVersion
    const response = await this.postAuthRequest('refresh')
    if (response.status === 401) {
      if (this.sessionVersion === refreshSessionVersion) {
        this.accessToken = null
      }
      return null
    }
    const token = await this.readAccessToken(response)
    if (this.sessionVersion !== refreshSessionVersion) {
      // For example, logout started while we waited. Discard this token.
      return null
    }
    this.accessToken = token
    return token
  }

  async waitForPendingRefresh() {
    try {
      await this.pendingRefresh
    } catch {
      // A failed refresh must not prevent a fresh login or a logout attempt.
    }
  }

  // HTTP HELPERS: request formatting and token-response parsing.
  postAuthRequest(endpoint, data) {
    const options = {
      method: 'POST',
      credentials: 'same-origin',
    }
    if (data) {
      options.headers = { 'Content-Type': 'application/json' }
      options.body = JSON.stringify(data)
    }
    return this.request(`/api/auth/${endpoint}`, options)
  }

  async readAccessToken(response) {
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Invalid email or password.')
      }
      throw new Error('Unable to sign in. Please try again.')
    }
    const body = await response.json()
    if (typeof body.access_token !== 'string' || !body.access_token) {
      throw new Error('The server returned an invalid sign-in response.')
    }
    return body.access_token
  }

}

// Components share this instance; tests create isolated instances.
export const auth = new AuthClient()
