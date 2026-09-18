# Shared Business Component Rule

Business components that are used across a broad scope MUST be placed in the root-level `components/` directory.

Each shared business component MUST have its own directory named after the component, for example:

```text
components/
└── ComponentName/
```

After creating the component, it MUST be imported into and re-exported from the shared public entry file `src/components/index.ts`. Consumers MUST use this public entry point for the component's unified export.

The component directory and its related files MUST continue to follow the file separation requirements defined in [`business-page-file-structure.md`](business-page-file-structure.md):

- `index.vue`: UI template and component wiring.
- `index.ts`: Component logic.
- `type.ts`: Type and interface definitions.
- `enum.ts`: Enum definitions when applicable.
- `index.scss`: Component styles.
