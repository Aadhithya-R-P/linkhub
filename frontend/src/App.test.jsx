import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import App from './Registration.jsx'

async function fillForm(displayName = '') {
  const user = userEvent.setup()
  render(<App />)
  if (displayName) await user.type(screen.getByLabelText(/Display name/), displayName)
  await user.type(screen.getByLabelText('Email'), 'Reader@example.com')
  await user.type(screen.getByLabelText('Password'), 'a long test phrase 123')
  return user
}

test('submits registration, omits blank optional name, and shows normalized email', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ status: 201, json: async () => ({ email: 'reader@example.com' }) })
  vi.stubGlobal('fetch', fetchMock)
  const user = await fillForm()
  await user.click(screen.getByRole('button', { name: /Create account/ }))
  expect(await screen.findByRole('status')).toHaveTextContent('reader@example.com')
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('/api/auth/register', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'Reader@example.com', password: 'a long test phrase 123' }),
  })
})

test.each([
  [409, { detail: 'Email is already registered' }, /already registered/],
  [422, { detail: [{ loc: ['body', 'email'], msg: 'Invalid email address' }] }, /Email: Invalid email address/],
  [500, null, /could not be completed/],
])('shows API error %s and lets the user retry', async (status, body, message) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, json: async () => body }))
  const user = await fillForm()
  await user.click(screen.getByRole('button', { name: /Create account/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent(message)
  expect(screen.getByRole('button', { name: /Create account/ })).toBeEnabled()
})

test('handles connection failure without losing the entered email', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  const user = await fillForm()
  await user.click(screen.getByRole('button', { name: /Create account/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach LinkHub')
  expect(screen.getByLabelText('Email')).toHaveValue('Reader@example.com')
})

test('disables submission while waiting and sends the trimmed optional name', async () => {
  let resolve
  const fetchMock = vi.fn().mockReturnValue(new Promise((done) => { resolve = done }))
  vi.stubGlobal('fetch', fetchMock)
  const user = await fillForm('  Reader  ')
  await user.click(screen.getByRole('button', { name: /Create account/ }))
  expect(screen.getByRole('button', { name: /Creating account/ })).toBeDisabled()
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).display_name).toBe('Reader')
  resolve({ status: 201, json: async () => ({ email: 'reader@example.com' }) })
  expect(await screen.findByRole('status')).toHaveTextContent('Your account is ready')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
