/**
 * 前端目录结构检查：在 CI 中阻止页面子功能退回扁平文件，并确保共享组件通过公共出口使用。
 *
 * 检查范围只覆盖页面和共享组件的文件边界，不解析 Vue 模板或改变构建产物；样式文件按组件实际
 * 是否需要局部规则决定，因此不会强制所有轻量组件创建空的 index.scss。
 */
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const viewsRoot = path.join(root, 'src', 'views')
const componentsRoot = path.join(root, 'src', 'components')
const violations = []

async function readDirectory(directory) {
  return readdir(directory, { withFileTypes: true }).then((entries) =>
    entries.map((entry) => entry.name),
  )
}

async function checkViewComponents() {
  const viewNames = await readDirectory(viewsRoot)
  for (const viewName of viewNames) {
    const componentsDirectory = path.join(viewsRoot, viewName, 'components')
    let entries
    try {
      entries = await readdir(componentsDirectory, { withFileTypes: true })
    } catch {
      continue
    }

    for (const entry of entries) {
      if (entry.isFile()) {
        violations.push(
          `页面 components 根目录存在扁平文件：src/views/${viewName}/components/${entry.name}`,
        )
        continue
      }
      if (!entry.isDirectory()) continue

      const featureDirectory = path.join(componentsDirectory, entry.name)
      const featureFiles = await readDirectory(featureDirectory)
      for (const requiredFile of ['index.vue', 'index.ts', 'type.ts']) {
        if (!featureFiles.includes(requiredFile)) {
          violations.push(
            `页面子组件缺少 ${requiredFile}：src/views/${viewName}/components/${entry.name}`,
          )
        }
      }
    }
  }
}

async function checkSharedExports() {
  const entries = await readdir(componentsRoot, { withFileTypes: true })
  const publicEntry = await readFile(path.join(componentsRoot, 'index.ts'), 'utf8')
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === 'ui') continue
    const componentDirectory = path.join(componentsRoot, entry.name)
    const files = await readDirectory(componentDirectory)
    if (!files.includes('index.vue') && !files.includes('index.ts')) continue
    const exportPath = `'./${entry.name}'`
    const directExportPath = `'./${entry.name}/index.vue'`
    const typedExportPath = `'./${entry.name}/index.ts'`
    if (
      !publicEntry.includes(exportPath) &&
      !publicEntry.includes(directExportPath) &&
      !publicEntry.includes(typedExportPath)
    ) {
      violations.push(`共享组件未从 src/components/index.ts 导出：${entry.name}`)
    }
  }
}

await checkViewComponents()
await checkSharedExports()

if (violations.length) {
  console.error('Frontend structure check failed:')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exitCode = 1
} else {
  console.log('Frontend structure check passed.')
}
