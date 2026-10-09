import { expect, test, vi } from 'vitest'
import { LinksClient, SessionExpiredError } from './links.js'

test('creates a link through apiFetch with only its destination', async () => {
  const link = { id: 125, short_code: '21', destination_url: 'https://example.com/' }
  const auth = { apiFetch: vi.fn().mockResolvedValue({ status: 201, json: async () => link }) }
  expect(await new LinksClient(auth).create('https://example.com')).toEqual(link)
  expect(auth.apiFetch).toHaveBeenCalledExactlyOnceWith('/api/links', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ destination_url: 'https://example.com' }),
  })
})

test.each([
  [401, {}, 'session has expired'],
  [422, { detail: [{ msg: 'Invalid URL' }] }, 'Invalid URL'],
  [500, {}, 'Unable to confirm creation'],
  [201, {}, 'Unable to confirm creation'],
])('creation handles status %s', async (status, body, message) => {
  const client = new LinksClient({ apiFetch: vi.fn().mockResolvedValue({ status, json: async () => body }) })
  await expect(client.create('https://example.com')).rejects.toThrow(message)
})

test('ambiguous network failure does not automatically create another link', async () => {
  const auth = { apiFetch: vi.fn().mockRejectedValue(new Error('offline')) }
  await expect(new LinksClient(auth).create('https://example.com')).rejects.toThrow('Reload your links')
  expect(auth.apiFetch).toHaveBeenCalledTimes(1)
})

test('lists the first and next page through the authenticated client', async () => {
  const page = { items: [], next_before_id: null }
  const auth = { apiFetch: vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => page }) }
  const client = new LinksClient(auth)
  expect(await client.list()).toEqual(page)
  await client.list(125)
  expect(auth.apiFetch.mock.calls.map(([url]) => url)).toEqual([
    '/api/links?limit=20', '/api/links?limit=20&before_id=125',
  ])
})

test('a final 401 reports session expiration', async () => {
  const client = new LinksClient({ apiFetch: vi.fn().mockResolvedValue({ status: 401 }) })
  await expect(client.list()).rejects.toThrow(SessionExpiredError)
})

test.each([403, 500])('HTTP %s is a recoverable listing error', async (status) => {
  const client = new LinksClient({ apiFetch: vi.fn().mockResolvedValue({ status, ok: false }) })
  await expect(client.list()).rejects.toThrow('Unable to load')
})

test('network failure produces a readable error', async () => {
  const client = new LinksClient({ apiFetch: vi.fn().mockRejectedValue(new TypeError('offline')) })
  await expect(client.list()).rejects.toThrow('Unable to load')
})


test('update sends PATCH and returns the server link', async () => {
  const link = { id: 30, short_code: 'u', destination_url: 'https://example.com/', is_active: false }
  const data = { destination_url: link.destination_url, is_active: false }
  const auth = { apiFetch: vi.fn().mockResolvedValue({ status: 200, json: async () => link }) }
  expect(await new LinksClient(auth).update(30, data)).toEqual(link)
  expect(auth.apiFetch).toHaveBeenCalledExactlyOnceWith('/api/links/30', {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
})

test('delete sends DELETE and accepts an empty 204 response', async () => {
  const auth = { apiFetch: vi.fn().mockResolvedValue({ status: 204 }) }
  await expect(new LinksClient(auth).delete(30)).resolves.toBeUndefined()
  expect(auth.apiFetch).toHaveBeenCalledExactlyOnceWith('/api/links/30', { method: 'DELETE' })
})

test.each([
  ['update', 401, {}, 'session has expired'],
  ['delete', 401, {}, 'session has expired'],
  ['update', 404, {}, 'no longer available'],
  ['delete', 404, {}, 'no longer available'],
  ['update', 422, { detail: [{ msg: 'Invalid URL' }] }, 'Invalid URL'],
  ['update', 500, {}, 'Unable to confirm'],
  ['delete', 500, {}, 'Unable to confirm'],
  ['update', 200, {}, 'Unable to confirm'],
  ['delete', 200, {}, 'Unable to confirm'],
])('%s handles status %s', async (method, status, body, message) => {
  const client = new LinksClient({ apiFetch: vi.fn().mockResolvedValue({ status, json: async () => body }) })
  await expect(client[method](30, {})).rejects.toThrow(message)
})

test.each(['update', 'delete'])('%s explains ambiguous network failures without retrying', async (method) => {
  const auth = { apiFetch: vi.fn().mockRejectedValue(new TypeError('offline')) }
  await expect(new LinksClient(auth)[method](30, {})).rejects.toThrow('Reload your links')
  expect(auth.apiFetch).toHaveBeenCalledTimes(1)
})
