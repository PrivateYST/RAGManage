# Business Page File Structure Rule

When creating or modifying any business page, including its subpages, you MUST separate UI, logic, types, and styles into the following files in that page's directory:

- `index.vue`: UI template and component wiring only. Import page logic and styles from the corresponding files; do not embed business logic or styles here.
- `index.ts`: Page JavaScript/TypeScript logic, including state, computed values, event handlers, and business operations.
- `type.ts`: Page-specific type and interface definitions.
- `enum.ts`: Page-specific enumerable types and enum definitions. This file is required when such definitions exist; otherwise, it may be omitted.
- `index.scss`: Page styles.

Each business subpage MUST follow this structure independently. Do not combine a page's UI, business logic, type definitions, enums, and styles in a single Vue file.
