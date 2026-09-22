<!-- 根组件组装全局区域设置、反馈宿主与路由，不承载业务页面状态。 -->
<script setup lang="ts">
import { ConfigProvider } from 'reka-ui'
import AppToast from '@/components/AppToast/index.vue'
import { APP_LOCALE } from '@/config/locale'
</script>

<template>
  <ConfigProvider :locale="APP_LOCALE">
    <AppToast>
      <RouterView />
    </AppToast>
  </ConfigProvider>
</template>
