/** 统一浏览器 API 传输边界，集中处理 Cookie、JSON 和会话 CSRF 令牌。 */
// 只有不会改变服务端状态的方法可以跳过浏览器 CSRF 证明。
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const LOGIN_PATH = '/api/v1/auth/login'
const CSRF_BOOTSTRAP_PATH = '/api/v1/auth/csrf'
const CSRF_COOKIE_NAME = 'ragmanage_csrf'
const CSRF_HEADER_NAME = 'X-CSRF-Token'

/** 读取指定的非 HttpOnly Cookie；缺少 DOM 时视为没有可复用 token。 */
function readableCookie(name: string): string | null {
  /** Cookie 名为常量，但仍按 RFC cookie 分隔符匹配，避免相似前缀误命中。 */
  if (typeof document === 'undefined') return null
  const prefix = `${name}=`
  const entry = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
  if (!entry) return null
  try {
    return decodeURIComponent(entry.slice(prefix.length))
  } catch {
    // 无效编码不应阻断请求；服务端会拒绝不匹配的 token。
    return null
  }
}

/** 获取现有 token；登录升级前签发的 Session 通过只读接口补发 Cookie。 */
async function sessionCsrfToken(): Promise<string> {
  const cookieToken = readableCookie(CSRF_COOKIE_NAME)
  if (cookieToken) return cookieToken

  /** 旧版 Session 尚无 CSRF Cookie 时，用只读同源接口安全地补发。 */
  const response = await fetch(CSRF_BOOTSTRAP_PATH, { credentials: 'include' })
  // 未登录用户不需要 CSRF 凭据，让原写请求返回其真实 401/业务错误。
  if (response.status === 401) return ''
  if (!response.ok) throw new Error(`CSRF token 获取失败（${response.status}）`)
  const body = (await response.json()) as { csrf_token?: unknown }
  if (typeof body.csrf_token !== 'string' || body.csrf_token.length === 0)
    throw new Error('CSRF token 响应无效')
  return body.csrf_token
}

/** 发送同源 API 请求，并对所有 Cookie Session 写请求统一附加 CSRF 证明。 */
export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  const isLogin = path.split('?', 1)[0] === LOGIN_PATH
  const hasBearer =
    headers.get('Authorization')?.trim().toLowerCase().startsWith('bearer ') ?? false

  /** 客户 Bearer API 不用浏览器凭据，避免把 CSRF 引导请求绑定到错误身份。 */
  if (!isLogin && !SAFE_METHODS.has(method) && !hasBearer) {
    const csrfToken = await sessionCsrfToken()
    if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken)
  }

  const contentType = options.body instanceof FormData ? null : 'application/json'
  if (contentType && !headers.has('Content-Type')) headers.set('Content-Type', contentType)
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers,
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `请求失败（${response.status}）`)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
