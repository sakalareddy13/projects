import { describe, it, expect } from 'vitest'
import { OWNER_LINKEDIN, validateOwnership } from '../ownership'

describe('ownership', () => {
  it('exports the LinkedIn URL', () => {
    expect(OWNER_LINKEDIN).toBe('www.linkedin.com/in/sakala-reddy')
  })

  it('validateOwnership resolves without throwing', async () => {
    await expect(validateOwnership()).resolves.toBeUndefined()
  })
})
