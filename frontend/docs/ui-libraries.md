# Reka UI 与 Tailwind CSS

前端已接入 Reka UI 和 Tailwind CSS v4。Reka UI 按需从 `reka-ui` 导入，
无需在 `main.ts` 中全局注册；交互状态由 Reka UI 管理，视觉样式由项目 CSS 或 Tailwind 工具类提供。

Reka UI 的日期、数字等可本地化组件通过根组件中的 `ConfigProvider` 继承区域设置，
当前统一使用 `src/config/locale.ts` 中的 `zh-CN`。`ConfigProvider` 是组件而不是 Vue 插件，
因此应在 `App.vue` 包裹应用，不应调用 `app.use(ConfigProvider)`。

Tailwind 使用 `@tailwindcss/vite`，入口为 `src/assets/tailwind.css`，
通过现有 `style.css` 加载。v4 使用 CSS 配置，不需要 `tailwind.config.js` 或 PostCSS 配置。
扫描范围为 `frontend/src`，模板中应使用完整类名，避免字符串拼接导致构建时无法识别。

## 与现有样式共存

- 暂不加载 Preflight，保留现有标题、表单和按钮的浏览器默认样式与项目重置。
- 边框应显式包含样式，例如 `border border-solid border-border`。
- 现有未分层 CSS 的优先级高于 Tailwind 工具层；遇到覆盖时应调整组件自身样式，避免滥用 `!important`。
- 可使用 `bg-background`、`text-foreground`、`bg-card`、`text-muted-foreground` 等语义工具类，颜色来源于现有全局变量。
- Reka UI 状态可用 `data-[state=open]:...` 等变体设置样式。
- 在 Vue 局部 CSS 中使用 `@apply` 时，先 `@reference '@/assets/tailwind.css';`；Tailwind 指令保持在普通 CSS 中，不放入 SCSS 预处理入口。
- 新组件继续遵循项目的 shadcn-vue 风格与组件目录规则。

## 验证

在仓库根目录运行 `pnpm build`、`pnpm lint` 和 `pnpm test`。
`pnpm build` 同时执行 Vue TypeScript 检查与 Tailwind 生产编译。
