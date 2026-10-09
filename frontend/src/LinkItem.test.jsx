import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import LinkItem from './LinkItem.jsx'
import { links, SessionExpiredError } from './links.js'

vi.mock('./links.js', async (importOriginal) => ({
  ...await importOriginal(), links: { update: vi.fn(), delete: vi.fn() },
}))
beforeEach(() => vi.resetAllMocks())
const link = { id: 30, short_code: 'u', destination_url: 'https://example.com/', is_active: true, expires_at: null }
function setup() {
  const callbacks = { onPendingChange: vi.fn(), onUpdated: vi.fn(), onDeleted: vi.fn(), onSessionExpired: vi.fn() }
  render(<ul><LinkItem link={link} disabled={false} {...callbacks} /></ul>)
  return callbacks
}

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
