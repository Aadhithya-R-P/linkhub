import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import CopyLink from './CopyLink.jsx'

test('copies the full same-origin short URL and reports success', async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  render(<CopyLink shortCode="2B" />)
  const url = `${window.location.origin}/r/2B`
  expect(screen.getByRole('link')).toHaveAttribute('href', url)
  expect(screen.getByRole('link')).toHaveAccessibleName(`${url} (opens in a new tab)`)
  await user.click(screen.getByRole('button', { name: 'Copy short URL 2B' }))
  expect(write).toHaveBeenCalledWith(url)
  expect(await screen.findByRole('status')).toHaveTextContent('Copied!')
  write.mockRestore()
})

test('clipboard denial keeps the URL available for manual copying', async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
  render(<CopyLink shortCode="2B" />)
  await user.click(screen.getByRole('button'))
  expect(await screen.findByRole('status')).toHaveTextContent('Select and copy the URL above')
  expect(screen.getByRole('link')).toHaveTextContent('/r/2B')
  write.mockRestore()
})
