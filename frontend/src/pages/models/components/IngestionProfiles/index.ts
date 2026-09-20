import { reactive } from 'vue'

export function useIngestionProfileForm() {
  const form = reactive({ maxChars: 1800, overlapChars: 0 })
  return { form }
}
