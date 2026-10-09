import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import LinkItem from './LinkItem.jsx'
import { links, SessionExpiredError } from './links.js'

vi.mock('./links.js', async (importOriginal) => ({
  ...await importOriginal(), links: { update: vi.fn(), delete: vi.fn() },
}))
beforeEach(() => vi.resetAllMocks())
const link = { id: 30, short_code: 'u', destination_url: 'https://example.com/', is_active: true, expires_at: null, total_clicks: 0 }
function setup(overrides = {}) {
  const callbacks = { onPendingChange: vi.fn(), onUpdated: vi.fn(), onDeleted: vi.fn(), onSessionExpired: vi.fn() }
  render(<ul><LinkItem link={{ ...link, ...overrides }} disabled={false} {...callbacks} /></ul>)
  return callbacks
}

test.each([[0, '0 clicks'], [1, '1 click'], [42, '42 clicks']])('displays total %s', (total_clicks, label) => {
  setup({ total_clicks })
  expect(screen.getByText(label, { exact: true })).toBeInTheDocument()
})

test('cancel discards edits and deletion requires explicit confirmation', async () => {
  const interaction = userEvent.setup()
  setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  await interaction.clear(screen.getByLabelText('Destination URL'))
  await interaction.type(screen.getByLabelText('Destination URL'), 'https://changed.com/')
  await interaction.click(screen.getByRole('button', { name: 'Cancel' }))
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  expect(screen.getByLabelText('Destination URL')).toHaveValue(link.destination_url)
  await interaction.click(screen.getByRole('button', { name: 'Cancel' }))
  await interaction.click(screen.getByRole('button', { name: 'Delete' }))
  expect(screen.getByText(/Permanently delete/)).toBeInTheDocument()
  await interaction.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(links.update).not.toHaveBeenCalled()
  expect(links.delete).not.toHaveBeenCalled()
})

test.each([null, '2027-01-01T00:00:00Z'])('saves a changed local expiration as UTC (previous: %s)', async (expires_at) => {
  const saved = { ...link, expires_at: new Date(2027, 6, 15, 18, 45).toISOString() }
  links.update.mockResolvedValue(saved)
  const callbacks = setup({ expires_at })
  const interaction = userEvent.setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.change(screen.getByLabelText('Expiration'), { target: { value: '2027-07-15T18:45' } })
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  expect(links.update).toHaveBeenCalledWith(link.id, {
    destination_url: link.destination_url, is_active: true, expires_at: saved.expires_at,
  })
  expect(callbacks.onUpdated).toHaveBeenCalledWith(saved)
})

test('prefills local time and omits unchanged expiration to preserve sub-minute precision', async () => {
  const expires_at = new Date(2027, 0, 2, 0, 15, 43, 123).toISOString()
  links.update.mockResolvedValue({ ...link, expires_at })
  setup({ expires_at })
  const interaction = userEvent.setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  expect(screen.getByLabelText('Expiration')).toHaveValue('2027-01-02T00:15')
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  expect(links.update).toHaveBeenCalledWith(link.id, { destination_url: link.destination_url, is_active: true })
})

test('clears existing expiration with null', async () => {
  links.update.mockResolvedValue(link)
  setup({ expires_at: '2027-01-01T00:00:00Z' })
  const interaction = userEvent.setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.change(screen.getByLabelText('Expiration'), { target: { value: '' } })
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  expect(links.update).toHaveBeenCalledWith(link.id, {
    destination_url: link.destination_url, is_active: true, expires_at: null,
  })
})

test('past expiration is allowed, retained after failure, and discarded on cancel', async () => {
  links.update.mockRejectedValue(new Error('Unable to confirm the update'))
  setup()
  const interaction = userEvent.setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.change(screen.getByLabelText('Expiration'), { target: { value: '2000-01-01T12:00' } })
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to confirm')
  expect(screen.getByLabelText('Expiration')).toHaveValue('2000-01-01T12:00')
  expect(links.update).toHaveBeenCalledWith(link.id, expect.objectContaining({ expires_at: new Date(2000, 0, 1, 12).toISOString() }))
  await interaction.click(screen.getByRole('button', { name: 'Cancel' }))
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  expect(screen.getByLabelText('Expiration')).toHaveValue('')
})

test('failed save retains entered fields and can be retried', async () => {
  links.update.mockRejectedValueOnce(new Error('Invalid destination'))
    .mockResolvedValueOnce({ ...link, is_active: false })
  const interaction = userEvent.setup()
  const callbacks = setup()
  await interaction.click(screen.getByRole('button', { name: 'Edit' }))
  await interaction.click(screen.getByRole('checkbox'))
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid destination')
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  expect(screen.getByLabelText('Destination URL')).toHaveValue(link.destination_url)
  expect(callbacks.onUpdated).not.toHaveBeenCalled()
  await interaction.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(callbacks.onUpdated).toHaveBeenCalledWith({ ...link, is_active: false }))
})

test.each(['update', 'delete'])('%s handles session expiry and disables repeated submission', async (method) => {
  let reject
  links[method].mockReturnValue(new Promise((resolve, fail) => { reject = fail }))
  const interaction = userEvent.setup()
  const callbacks = setup()
  await interaction.click(screen.getByRole('button', { name: method === 'update' ? 'Edit' : 'Delete' }))
  await interaction.click(screen.getByRole('button', { name: method === 'update' ? 'Save' : 'Confirm delete' }))
  const button = screen.getByRole('button', { name: method === 'update' ? 'Saving…' : 'Deleting…' })
  expect(button).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  await interaction.click(button)
  expect(links[method]).toHaveBeenCalledTimes(1)
  reject(new SessionExpiredError())
  await waitFor(() => expect(callbacks.onSessionExpired).toHaveBeenCalledTimes(1))
  expect(callbacks.onPendingChange.mock.calls).toEqual([[true], [false]])
})

test('failed deletion leaves the link and confirmation available', async () => {
  links.delete.mockRejectedValue(new Error('Unable to confirm deletion'))
  const interaction = userEvent.setup()
  const callbacks = setup()
  await interaction.click(screen.getByRole('button', { name: 'Delete' }))
  await interaction.click(screen.getByRole('button', { name: 'Confirm delete' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to confirm deletion')
  expect(screen.getByText(link.destination_url)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Confirm delete' })).toBeEnabled()
  expect(callbacks.onDeleted).not.toHaveBeenCalled()
})
