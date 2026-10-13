/** 空间管理员 Key 弹窗逻辑：按当前空间生成清楚的可访问名称和说明。 */
import type { Ref } from 'vue'
import { computed } from 'vue'

/** 让辅助技术能辨认当前确认的是哪家医院的 Key。 */
export function useTenantApiKeyDialog(tenantName: Ref<string>) {
  const title = computed(() => `${tenantName.value || '当前空间'} API Key 配置`)
  const description = computed(
    () => `粘贴系统管理员为${tenantName.value || '当前空间'}分配的 Key 并确认配置。`,
  )

  return { title, description }
}
