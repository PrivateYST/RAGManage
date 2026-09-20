// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarkdownContent from './index.vue'

describe('markdown content', () => {
  it('renders common answer markdown and removes active content', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: [
          '## 业务规范',
          '',
          '**重点内容**',
          '',
          '- 第一项',
          '- 第二项',
          '',
          '| 状态 | 说明 |',
          '| --- | --- |',
          '| 正常 | 可使用 |',
          '',
          '<script>alert("xss")</script>',
          '[危险链接](javascript:alert(1))',
        ].join('\n'),
      },
    })

    expect(wrapper.get('h2').text()).toBe('业务规范')
    expect(wrapper.get('strong').text()).toBe('重点内容')
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.get('table').text()).toContain('正常')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('updates rendered markdown while a response is streaming', async () => {
    const wrapper = mount(MarkdownContent, { props: { content: '## 初始标题' } })

    await wrapper.setProps({ content: '### 更新后的标题\n\n新的正文' })

    expect(wrapper.find('h2').exists()).toBe(false)
    expect(wrapper.get('h3').text()).toBe('更新后的标题')
    expect(wrapper.text()).toContain('新的正文')
  })
})
