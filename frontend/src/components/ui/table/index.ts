import { defineComponent, h } from 'vue'

function createTablePart(tag: string, baseClass: string) {
  return defineComponent({
    name: `UiTable${tag[0]?.toUpperCase()}${tag.slice(1)}`,
    inheritAttrs: false,
    props: { class: { type: String, default: '' } },
    setup(props, { slots, attrs }) {
      return () => h(tag, { ...attrs, class: [baseClass, props.class] }, slots.default?.())
    },
  })
}

/** shadcn-vue Table primitives used by AppTable. */
export const Table = createTablePart('table', 'w-full caption-bottom text-sm')
export const TableHeader = createTablePart('thead', '[&_tr]:border-b')
export const TableBody = createTablePart('tbody', '[&_tr:last-child]:border-0')
export const TableFooter = createTablePart('tfoot', 'border-t bg-muted/50 font-medium')
export const TableRow = createTablePart(
  'tr',
  'border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted',
)
export const TableHead = createTablePart(
  'th',
  'h-[40px] px-[8px] text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0',
)
export const TableCell = createTablePart('td', 'p-[8px] align-middle [&:has([role=checkbox])]:pr-0')
export const TableCaption = createTablePart('caption', 'mt-[16px] text-sm text-muted-foreground')
