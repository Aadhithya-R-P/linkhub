import { expect, test, vi } from 'vitest'
import { AuthClient, RegistrationError } from './auth.js'

const reply = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body })
const account = { email: 'reader@example.com', display_name: 'Reader' }

test('registration posts JSON and returns a user without changing the session', async () => {
  const request = vi.fn().mockResolvedValue(reply(201, account))
  const client = new AuthClient(request)
  client.accessToken = 'existing-test-token'
  const data = { email: account.email, password: 'test password phrase', display_name: 'Reader' }
  expect(await client.register(data)).toEqual(account)
  expect(request).toHaveBeenCalledExactlyOnceWith('/api/auth/register', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
  expect(client.accessToken).toBe('existing-test-token')
  expect(client.sessionVersion).toBe(0)
})

test('registration preserves multiple field validation messages', async () => {
  const request = vi.fn().mockResolvedValue(reply(422, { detail: [
    { loc: ['body', 'email'], msg: 'Invalid email' },
    { loc: ['body', 'password'], msg: 'Too short' },
  ] }))
  const client = new AuthClient(request)
  await expect(client.register({})).rejects.toMatchObject({
    name: 'RegistrationError', messages: ['Email: Invalid email', 'Password: Too short'],
  })
})

test.each([
  [409, {}, 'already registered'],
  [401, {}, 'could not be completed'],
  [500, {}, 'could not be completed'],
  [201, {}, 'could not be completed'],
  [422, { detail: [] }, 'could not be completed'],
  [422, { detail: [null, {}] }, 'could not be completed'],
])('registration handles HTTP %s without token refresh', async (status, body, message) => {
  const request = vi.fn().mockResolvedValue(reply(status, body))
  await expect(new AuthClient(request).register({})).rejects.toThrow(message)
  expect(request).toHaveBeenCalledTimes(1)
})

test('registration handles non-JSON responses', async () => {
  const request = vi.fn().mockResolvedValue({ status: 502, json: async () => { throw new SyntaxError('Invalid JSON') } })
  await expect(new AuthClient(request).register({})).rejects.toThrow(RegistrationError)
})

test('registration reports connection failure', async () => {
  const request = vi.fn().mockRejectedValue(new TypeError('offline'))
  await expect(new AuthClient(request).register({})).rejects.toThrow('Unable to reach LinkHub')
})

test('separate AuthClient instances keep tokens and sessions independent', async () => {
  const firstRequest = vi.fn().mockResolvedValueOnce(reply(200, { access_token: 'first-token' }))
    .mockResolvedValueOnce(reply(200, account)).mockResolvedValue(reply(204))
  const secondRequest = vi.fn().mockResolvedValueOnce(reply(200, { access_token: 'second-token' }))
    .mockResolvedValue(reply(200, account))
  const first = new AuthClient(firstRequest)
  const second = new AuthClient(secondRequest)
  await first.login('first@example.com', 'test password')
  await second.login('second@example.com', 'test password')
  await first.logout()
  await second.apiFetch('/api/links')
  expect(first.accessToken).toBeNull()
  expect(secondRequest.mock.calls[2][1].headers.get('Authorization')).toBe('Bearer second-token')
  expect(second.sessionVersion).toBe(1)
})

test('refresh cleanup keeps its instance context after failure and allows retry', async () => {
  const request = vi.fn().mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValueOnce(reply(200, { access_token: 'recovered' }))
    .mockResolvedValueOnce(reply(200, account))
  const client = new AuthClient(request)
  await expect(client.restore()).rejects.toThrow('offline')
  expect(client.pendingRefresh).toBeNull()
  expect(await client.restore()).toEqual(account)
  expect(client.accessToken).toBe('recovered')
  expect(client.pendingRefresh).toBeNull()
})

test('concurrent logout calls share one operation and clear instance fields', async () => {
  const waiting = deferred()
  const request = vi.fn().mockReturnValue(waiting.promise)
  const client = new AuthClient(request)
  const first = client.logout()
  const second = client.logout()
  expect(first).toBe(second)
  expect(request).toHaveBeenCalledTimes(1)
  expect(await client.refreshAccessToken()).toBeNull()
  waiting.resolve(reply(204))
  await first
  expect(client.pendingLogout).toBeNull()
  expect(client.accessToken).toBeNull()
  expect(client.sessionVersion).toBe(1)
})

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

test('login sends JSON, then loads the user with bearer authorization', async () => {
  const request = vi.fn().mockResolvedValueOnce(reply(200, { access_token: 'test-access' }))
    .mockResolvedValueOnce(reply(200, account))
  const auth = new AuthClient(request)
  expect(await auth.login('reader@example.com', 'test password')).toEqual(account)
  expect(request.mock.calls[0][1].credentials).toBe('same-origin')
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ email: 'reader@example.com', password: 'test password' })
  expect(request.mock.calls[1][1].headers.get('Authorization')).toBe('Bearer test-access')
})

test('startup restoration shares one refresh and loads the user', async () => {
  const wait = deferred()
  const request = vi.fn().mockReturnValueOnce(wait.promise).mockResolvedValue(reply(200, account))
  const auth = new AuthClient(request)
  const first = auth.restore()
  const second = auth.restore()
  expect(request).toHaveBeenCalledTimes(1)
  wait.resolve(reply(200, { access_token: 'restored' }))
  expect(await first).toEqual(account)
  expect(await second).toEqual(account)
  // Refresh is shared; each restore call independently loads the user.
  expect(request.mock.calls.map(([path]) => path)).toEqual([
    '/api/auth/refresh', '/api/auth/me', '/api/auth/me',
  ])
})

test('missing or expired refresh cookie results in signed-out state', async () => {
  const request = vi.fn().mockResolvedValue(reply(401))
  expect(await new AuthClient(request).restore()).toBeNull()
  expect(request).toHaveBeenCalledTimes(1)
})

test('simultaneous 401s share refresh and a late 401 reuses the new token', async () => {
  const rotation = deferred()
  const late = deferred()
  let refreshes = 0
  const request = vi.fn(async (path, options) => {
    if (path.endsWith('/login')) return reply(200, { access_token: 'old' })
    if (path.endsWith('/me')) return reply(200, account)
    if (path.endsWith('/refresh')) { refreshes++; return rotation.promise }
    if (options.headers.get('Authorization') === 'Bearer new') return reply(200, {})
    if (path.endsWith('/late')) return late.promise
    return reply(401)
  })
  const auth = new AuthClient(request)
  await auth.login('reader@example.com', 'test')
  const pending = [auth.apiFetch('/api/links'), auth.apiFetch('/api/other'), auth.apiFetch('/api/late')]
  await vi.waitFor(() => expect(refreshes).toBe(1))
  rotation.resolve(reply(200, { access_token: 'new' }))
  expect((await pending[0]).status).toBe(200)
  late.resolve(reply(401))
  expect((await Promise.all(pending)).every((result) => result.status === 200)).toBe(true)
  expect(refreshes).toBe(1)
})

test('a rejected retry stops rather than looping', async () => {
  const request = vi.fn().mockResolvedValueOnce(reply(401))
    .mockResolvedValueOnce(reply(200, { access_token: 'new' })).mockResolvedValue(reply(401))
  expect((await new AuthClient(request).apiFetch('/api/links')).status).toBe(401)
  expect(request).toHaveBeenCalledTimes(3)
})

test('logout waits for rotation and prevents the waiting request from retrying', async () => {
  const rotation = deferred()
  const request = vi.fn().mockResolvedValueOnce(reply(401)).mockReturnValueOnce(rotation.promise)
    .mockResolvedValue(reply(204))
  const auth = new AuthClient(request)
  const protectedRequest = auth.apiFetch('/api/links')
  await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))
  const logout = auth.logout()
  expect(request).toHaveBeenCalledTimes(2)
  rotation.resolve(reply(200, { access_token: 'must-not-restore' }))
  await logout
  expect((await protectedRequest).status).toBe(401)
  expect(request.mock.calls[2][0]).toBe('/api/auth/logout')
  await auth.apiFetch('/api/links')
  expect(request.mock.calls[3][1].headers.has('Authorization')).toBe(false)
})

test('failed logout still discards access credentials and can be retried', async () => {
  const request = vi.fn().mockResolvedValueOnce(reply(200, { access_token: 'old' }))
    .mockResolvedValueOnce(reply(200, account)).mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValue(reply(204))
  const auth = new AuthClient(request)
  await auth.login('reader@example.com', 'test')
  await expect(auth.logout()).rejects.toThrow('Signed out locally')
  await auth.apiFetch('/api/links')
  expect(request.mock.calls[3][1].headers.has('Authorization')).toBe(false)
  await auth.logout()
})

test('external paths are rejected before sending bearer credentials', async () => {
  const request = vi.fn()
  await expect(new AuthClient(request).apiFetch('https://example.com/api/links')).rejects.toThrow('local API')
  expect(request).not.toHaveBeenCalled()
})
