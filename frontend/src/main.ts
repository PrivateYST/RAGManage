import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from '@/App.vue'
import { installAppTable } from '@/components/AppTable'
import { APP_LOCALE } from '@/config/locale'
import router from '@/router'
import '@/assets/style.css'

/** 应用启动入口：组装根组件、全局状态、路由，并同步浏览器文档区域设置。 */
document.documentElement.lang = APP_LOCALE
const app = createApp(App)
installAppTable(app)
app.use(createPinia()).use(router).mount('#app')
