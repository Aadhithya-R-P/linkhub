import { afterEach, expect, test, vi } from 'vitest'
import { AuthClient } from './auth.js'
import { LinksClient } from './links.js'
import { RequestCooldowns } from './requestCooldowns.js'

afterEach(() => vi.restoreAllMocks())

test('mutations share cooldown, respect expiry, and do not auto-retry', async () => {
  let now = 100000
  vi.spyOn(Date, 'now').mockImplementation(() => now)
  const request = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 429, headers: { 'Retry-After': '12' } }))
    .mockResolvedValue(new Response(null, { status: 204 }))
  const auth = new AuthClient(request)
  auth.accessToken = 'test-token'
  const links = new LinksClient(auth)
  await expect(links.create('https://example.com')).rejects.toThrow('12 seconds')
  now += 2000
  await expect(links.delete(1)).rejects.toThrow('10 seconds')
  await expect(links.update(2, { is_active: false })).rejects.toThrow('10 seconds')
  expect(request).toHaveBeenCalledTimes(1)
  now += 10000
  await expect(links.delete(1)).resolves.toBeUndefined()
  expect(request).toHaveBeenCalledTimes(2)
})

test('list and logout remain usable while mutation cooldown is active', async () => {
  const request = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 429, headers: { 'Retry-After': '60' } }))
    .mockResolvedValue(new Response(null, { status: 204 }))
  const auth = new AuthClient(request)
  await expect(auth.apiFetch('/api/links', { method: 'POST' })).rejects.toThrow('60 seconds')
  await auth.apiFetch('/api/links')
  await auth.logout()
  expect(request).toHaveBeenCalledTimes(3)
})

test('a session change clears the previous account cooldown', async () => {
  const request = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 429 }))
    .mockResolvedValue(new Response(null, { status: 204 }))
  const auth = new AuthClient(request)
  await expect(auth.apiFetch('/api/links/1', { method: 'DELETE' })).rejects.toThrow('seconds')
  auth.clearLocalSession()
  await auth.apiFetch('/api/links/1', { method: 'DELETE' })
  expect(request).toHaveBeenCalledTimes(2)
})

test('HTTP-date Retry-After is supported and malformed values use a short fallback', () => {
  vi.spyOn(Date, 'now').mockReturnValue(100000)
  const cooldowns = new RequestCooldowns()
  expect(() => cooldowns.observe('mutation', new Response('', { status: 429,
    headers: { 'Retry-After': new Date(110000).toUTCString() } }))).toThrow('10 seconds')
  expect(() => cooldowns.observe('mutation', new Response('', { status: 429,
    headers: { 'Retry-After': 'invalid' } }))).toThrow('5 seconds')
})
