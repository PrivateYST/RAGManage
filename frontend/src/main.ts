import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from '@/App.vue'
import router from '@/router'
import '@/assets/style.css'

/** 应用启动入口：只组装根组件、Pinia 和路由，不承载路由表或业务守卫。 */
createApp(App).use(createPinia()).use(router).mount('#app')
