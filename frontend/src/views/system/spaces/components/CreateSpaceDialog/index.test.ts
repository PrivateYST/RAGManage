// @vitest-environment happy-dom
/** 新建空间表单回归：编码统一小写，避免大小写造成 422 创建失败。 */
import { describe, expect, it } from 'vitest'
import { useCreateSpaceDialog } from './index'

describe('create space dialog', () => {
  it('normalizes upper-case space codes before submission', () => {
    const { form, handleCodeInput } = useCreateSpaceDialog()
    const input = document.createElement('input')
    input.value = 'HospitalA'

    handleCodeInput({ currentTarget: input } as unknown as Event)

    expect(input.value).toBe('hospitala')
    expect(form.value.code).toBe('hospitala')
  })
})
