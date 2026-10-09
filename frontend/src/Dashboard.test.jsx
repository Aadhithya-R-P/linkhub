import { StrictMode } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import Dashboard from './Dashboard.jsx'
import { links, SessionExpiredError } from './links.js'

vi.mock('./links.js', async (importOriginal) => {
  const original = await importOriginal()
  return { ...original, links: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() } }
})
beforeEach(() => vi.resetAllMocks())
const user = { email: 'reader@example.com', display_name: 'Reader' }
const link = (id, extra = {}) => ({ id, short_code: String(id), destination_url: `https://example.com/${id}`, is_active: true, expires_at: null, ...extra })

test('creation resets an expanded list and uses the new first-page cursor', async () => {
  links.list.mockResolvedValueOnce({ items: [link(30)], next_before_id: 30 })
    .mockResolvedValueOnce({ items: [link(20)], next_before_id: null })
    .mockResolvedValueOnce({ items: [link(40)], next_before_id: 40 })
    .mockResolvedValueOnce({ items: [link(30)], next_before_id: null })
  links.create.mockResolvedValue(link(40))
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('https://example.com/30')
  await interaction.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('https://example.com/20')
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://example.com/new')
  await interaction.click(screen.getByRole('button', { name: 'Create link' }))
  await screen.findByText('https://example.com/40')
  expect(links.create).toHaveBeenCalledWith('https://example.com/new')
  expect(screen.getByLabelText('Destination URL')).toHaveValue('')
  expect(screen.queryByText('https://example.com/20')).not.toBeInTheDocument()
  await interaction.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('https://example.com/30')
  expect(links.list.mock.calls.map(([cursor]) => cursor)).toEqual([null, 30, null, 40])
})

test('successful creation remains visible if reloading page one fails', async () => {
  links.list.mockResolvedValueOnce({ items: [], next_before_id: null }).mockRejectedValueOnce(new Error('offline'))
  links.create.mockResolvedValue(link(40))
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('No links yet')
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://example.com/new')
  await interaction.click(screen.getByRole('button', { name: 'Create link' }))
  await screen.findByRole('alert')
  expect(screen.getByText('Link created.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Copy short URL 40' })).toBeInTheDocument()
  expect(links.list.mock.calls.map(([cursor]) => cursor)).toEqual([null, null])
})

test('creation validation failure preserves input and existing links', async () => {
  links.list.mockResolvedValue({ items: [link(30)], next_before_id: null })
  links.create.mockRejectedValue(new Error('Destination URL must not contain credentials'))
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('https://example.com/30')
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://user@example.com')
  await interaction.click(screen.getByRole('button', { name: 'Create link' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('must not contain credentials')
  expect(screen.getByLabelText('Destination URL')).toHaveValue('https://user@example.com')
  expect(screen.getByText('https://example.com/30')).toBeInTheDocument()
})

test('creation disables conflicting actions while waiting and reports session expiration', async () => {
  let reject
  links.list.mockResolvedValue({ items: [link(30)], next_before_id: 30 })
  links.create.mockReturnValue(new Promise((resolve, fail) => { reject = fail }))
  const expired = vi.fn()
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={expired} />)
  await screen.findByText('https://example.com/30')
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://example.com')
  await interaction.click(screen.getByRole('button', { name: 'Create link' }))
  expect(screen.getByRole('button', { name: 'Creating…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Load more' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeDisabled()
  reject(new SessionExpiredError())
  await waitFor(() => expect(expired).toHaveBeenCalledTimes(1))
})

test('shows loading followed by an empty state', async () => {
  let finish
  links.list.mockReturnValue(new Promise((resolve) => { finish = resolve }))
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading your links')
  finish({ items: [], next_before_id: null })
  expect(await screen.findByText('No links yet')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
})

test('appends pages, displays disabled/expiration fields, and stops at the final page', async () => {
  links.list.mockResolvedValueOnce({ items: [link(30)], next_before_id: 30 })
    .mockResolvedValueOnce({ items: [link(20, { is_active: false, expires_at: '2000-01-01T00:00:00Z' })], next_before_id: null })
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('https://example.com/30')
  await interaction.click(screen.getByRole('button', { name: 'Load more' }))
  expect(await screen.findByText('https://example.com/20')).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.getByText('Disabled')).toBeInTheDocument()
  expect(screen.getByText(/Expires:/)).toBeInTheDocument()
  expect(links.list.mock.calls.map(([cursor]) => cursor)).toEqual([null, 30])
  expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
})

test('failed next page preserves links and retries the same cursor', async () => {
  links.list.mockResolvedValueOnce({ items: [link(30)], next_before_id: 30 })
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ items: [link(20)], next_before_id: null })
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('https://example.com/30')
  await interaction.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByRole('alert')
  expect(screen.getByText('https://example.com/30')).toBeInTheDocument()
  await interaction.click(screen.getByRole('button', { name: 'Retry' }))
  await screen.findByText('https://example.com/20')
  expect(links.list.mock.calls.map(([cursor]) => cursor)).toEqual([null, 30, 30])
})

test('initial error retries and recovers', async () => {
  links.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ items: [], next_before_id: null })
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByRole('alert')
  await interaction.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('No links yet')).toBeInTheDocument()
})

test('ignores an expired-session response after unmount', async () => {
  let fail
  links.list.mockReturnValue(new Promise((resolve, reject) => { fail = reject }))
  const expired = vi.fn()
  const page = render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={expired} />)
  page.unmount()
  fail(new SessionExpiredError())
  await waitFor(() => expect(links.list).toHaveBeenCalledTimes(1))
  expect(expired).not.toHaveBeenCalled()
})

test('StrictMode replay does not duplicate displayed links', async () => {
  links.list.mockResolvedValue({ items: [link(30)], next_before_id: null })
  render(<StrictMode><Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} /></StrictMode>)
  await screen.findByText('https://example.com/30')
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
})


test('editing replaces a row, deleting removes it, and pagination keeps its cursor', async () => {
  links.list.mockResolvedValueOnce({ items: [link(30)], next_before_id: 30 })
    .mockResolvedValueOnce({ items: [link(20)], next_before_id: null })
  links.update.mockResolvedValue(link(30, { destination_url: 'https://changed.com/', is_active: false }))
  links.delete.mockResolvedValue(undefined)
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  const row = within(await screen.findByRole('listitem', { name: 'Link 30' }))
  await interaction.click(row.getByRole('button', { name: 'Edit' }))
  await interaction.clear(row.getByLabelText('Destination URL'))
  await interaction.type(row.getByLabelText('Destination URL'), 'https://changed.com/')
  await interaction.click(row.getByRole('checkbox'))
  await interaction.click(row.getByRole('button', { name: 'Save' }))
  expect(await row.findByText('https://changed.com/')).toBeInTheDocument()
  expect(row.getByText('Disabled')).toBeInTheDocument()
  expect(links.update).toHaveBeenCalledWith(30, { destination_url: 'https://changed.com/', is_active: false })
  await interaction.click(row.getByRole('button', { name: 'Delete' }))
  await interaction.click(row.getByRole('button', { name: 'Confirm delete' }))
  await waitFor(() => expect(screen.queryByRole('listitem')).not.toBeInTheDocument())
  expect(screen.queryByText('No links yet')).not.toBeInTheDocument()
  await interaction.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('https://example.com/20')
  expect(links.list.mock.calls.map(([cursor]) => cursor)).toEqual([null, 30])
})

test('deleting a just-created link also clears its success message', async () => {
  links.list.mockResolvedValueOnce({ items: [], next_before_id: null })
    .mockResolvedValueOnce({ items: [link(40)], next_before_id: null })
  links.create.mockResolvedValue(link(40))
  links.delete.mockResolvedValue(undefined)
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  await screen.findByText('No links yet')
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://example.com/')
  await interaction.click(screen.getByRole('button', { name: 'Create link' }))
  const row = within(await screen.findByRole('listitem'))
  await interaction.click(row.getByRole('button', { name: 'Delete' }))
  await interaction.click(row.getByRole('button', { name: 'Confirm delete' }))
  await screen.findByText('No links yet')
  expect(screen.queryByText('Link created.')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Copy short URL 40' })).not.toBeInTheDocument()
})

test('a pending row request blocks creation, pagination, other rows and logout', async () => {
  let finish
  links.list.mockResolvedValue({ items: [link(30), link(29)], next_before_id: 29 })
  links.delete.mockReturnValue(new Promise((resolve) => { finish = resolve }))
  const interaction = userEvent.setup()
  render(<Dashboard user={user} onLogout={vi.fn()} onSessionExpired={vi.fn()} />)
  const row = within(await screen.findByRole('listitem', { name: 'Link 30' }))
  await interaction.click(row.getByRole('button', { name: 'Delete' }))
  await interaction.click(row.getByRole('button', { name: 'Confirm delete' }))
  for (const name of ['Create link', 'Load more', 'Sign out', 'Edit', 'Deleting…', 'Cancel']) {
    expect(screen.getByRole('button', { name })).toBeDisabled()
  }
  finish()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Create link' })).toBeEnabled())
})
