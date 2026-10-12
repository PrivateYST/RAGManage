/** 将引用定位数据映射为原文位置标签，缺省时不编造页码。 */
export function locatorLabel(locator: Record<string, number>): string {
  if (locator.page !== undefined) return `第 ${locator.page} 页`
  if (locator.line_start !== undefined)
    return `第 ${locator.line_start}–${locator.line_end ?? locator.line_start} 行`
  if (locator.char_start !== undefined)
    return `字符 ${locator.char_start}–${locator.char_end ?? locator.char_start}`
  return '原文片段'
}
