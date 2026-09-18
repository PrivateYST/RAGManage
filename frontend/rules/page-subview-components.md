# Page Subview and Overlay Components Rule

Business subpages, form dialogs, detail dialogs, and drawers MUST be implemented as independent components under the current page's local `components/` directory. Each component MUST have its own directory named after the component, for example:

```text
src/views/system/app/
├── index.vue
└── components/
    └── AppFormDialog/
```

These components MUST follow the file separation requirements defined in [`business-page-file-structure.md`](business-page-file-structure.md), using `index.vue`, `index.ts`, `type.ts`, `enum.ts` when applicable, and `index.scss` when styles are needed.

Simple confirmation popovers and lightweight inline prompts MAY remain in the parent page when extracting them would add unnecessary structure. This exception does not apply to a business subpage, form dialog, detail dialog, or drawer.
