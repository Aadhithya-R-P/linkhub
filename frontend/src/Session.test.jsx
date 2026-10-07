import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { StrictMode } from 'react'
import App from './App.jsx'
import { auth } from './auth.js'

vi.mock('./auth.js', async (importOriginal) => {
  const original = await importOriginal()
  return { ...original, auth: { restore: vi.fn(), login: vi.fn(), logout: vi.fn() } }
})
beforeEach(() => { vi.resetAllMocks(); auth.restore.mockResolvedValue(null) })

test('sign in shows account and logout clears it', async () => {
  auth.login.mockResolvedValue({ email: 'reader@example.com', display_name: 'Reader' })
  auth.logout.mockResolvedValue()
  const user = userEvent.setup()
  render(<App />)
  await user.type(await screen.findByLabelText('Email'), 'reader@example.com')
  await user.type(screen.getByLabelText('Password'), 'test password phrase')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('reader@example.com')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  expect(screen.queryByText('reader@example.com')).not.toBeInTheDocument()
})

test('invalid credentials are displayed and can be corrected', async () => {
  auth.login.mockRejectedValue(new Error('Invalid email or password.'))
  const user = userEvent.setup()
  render(<App />)
  await user.type(await screen.findByLabelText('Email'), 'reader@example.com')
  await user.type(screen.getByLabelText('Password'), 'wrong password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
})

test('restores a signed-in account under StrictMode', async () => {
  auth.restore.mockResolvedValue({ email: 'reader@example.com' })
  render(<StrictMode><App /></StrictMode>)
  expect(await screen.findByText('reader@example.com')).toBeInTheDocument()
})

test('logout failure hides account and offers a retry', async () => {
  auth.restore.mockResolvedValue({ email: 'reader@example.com' })
  auth.logout.mockRejectedValueOnce(new Error('Signed out locally. Retry logout.')).mockResolvedValue()
  const user = userEvent.setup()
  render(<App />)
  await user.click(await screen.findByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Signed out locally')
  expect(screen.queryByText('reader@example.com')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry logout' }))
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
})

test('can switch between registration and login', async () => {
  const user = userEvent.setup()
  render(<App />)
  await user.click(await screen.findByRole('button', { name: 'Create an account' }))
  expect(screen.getByLabelText(/Display name/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Already registered? Sign in' }))
  expect(screen.queryByLabelText(/Display name/)).not.toBeInTheDocument()
})
