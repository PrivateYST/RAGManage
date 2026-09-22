// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
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

    expect(wrapper.text()).toContain('业务规范')
    expect(wrapper.text()).toContain('重点内容')
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.get('table').text()).toContain('正常')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('updates rendered markdown while a response is streaming', async () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '## 初始标题', final: false },
    })

    await wrapper.setProps({ content: '### 更新后的标题\n\n新的正文' })
    await nextTick()
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(wrapper.find('h2').exists()).toBe(false)
    expect(wrapper.text()).toContain('更新后的标题')
    expect(wrapper.text()).toContain('新的正文')
  })
})
