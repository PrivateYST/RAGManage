/** 词条表单的数据转换；来源仅允许选择已发布原文。 */
import type { Ref } from 'vue'
import type { WikiPayload } from '@/api/wiki'
import { computed } from 'vue'

/** 分隔符支持中文与英文逗号，避免重复存储未清洗别名。 */
const ALIAS_SEPARATOR = /[,，]/

/** 子表单使用显式模型更新，不修改父级传入的 props。 */
export function useWikiEntryForm(model: Ref<WikiPayload>) {
  const aliases = computed({
    get: () => model.value.aliases.join(', '),
    set: (value: string) => {
      model.value = {
        ...model.value,
        aliases: value
          .split(ALIAS_SEPARATOR)
          .map((item) => item.trim())
          .filter(Boolean),
      }
    },
  })
  /** 添加/移除选中证据，保留其他来源备注。 */
  function toggleSource(id: string): void {
    const chunkId = Number(id)
    const sources = model.value.sources.some((source) => source.chunk_id === chunkId)
      ? model.value.sources.filter((source) => source.chunk_id !== chunkId)
      : [...model.value.sources, { chunk_id: chunkId, note: '' }]
    model.value = { ...model.value, sources }
  }
  return { aliases, toggleSource }
}
