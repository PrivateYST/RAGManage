// @vitest-environment happy-dom
/** Iconify 图标适配层回归测试，确认业务图标可以离线渲染并保留尺寸属性。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { Search } from './icons'

describe('iconify icon adapter', () => {
  // 业务页面依赖本地打包的图标数据，不能因 Iconify 公共接口不可用而产生网络请求。
  it('renders a local icon with the requested size', () => {
    const wrapper = mount(Search, { props: { size: 18 } })
    const svg = wrapper.find('svg')

    expect(svg.exists()).toBe(true)
    expect(svg.attributes('width')).toBe('18')
    expect(svg.attributes('height')).toBe('18')
  })
})
