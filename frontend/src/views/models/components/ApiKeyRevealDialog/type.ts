/** 一次性明文 Key 弹窗的只读属性。 */
import type { CreatedApiKey } from '@/api/apiKeys'

export interface ApiKeyRevealDialogProps {
  apiKey: CreatedApiKey | null
}
