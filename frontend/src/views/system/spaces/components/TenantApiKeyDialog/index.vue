<!-- 空间管理员 Key 配置使用 Dialog 呈现；交接校验继续由既有 Key 配置组件负责。 -->
<script setup lang="ts">
import type { TenantApiKeyDialogProps } from './type'
import { toRef } from 'vue'
import { AppDialog } from '@/components'
import TenantApiKeyConfig from '@/views/models/components/TenantApiKeyConfig/index.vue'
import { useTenantApiKeyDialog } from './index'

const props = defineProps<TenantApiKeyDialogProps>()
const emit = defineEmits<{
  close: []
  configured: []
}>()
const { title, description } = useTenantApiKeyDialog(toRef(props, 'tenantName'))
</script>

<template>
  <AppDialog
    :open="open"
    :title="title"
    :description="description"
    content-class="w-[min(820px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <TenantApiKeyConfig
      v-if="open"
      :tenant-id="tenantId"
      :tenant-name="tenantName"
      @configured="emit('configured')"
    />
  </AppDialog>
</template>
