const BASE_URL = import.meta.env.VITE_API_URL ?? ''
const TOKEN_KEY = 'mi_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Storage unavailable (private mode); the user just stays logged in for this tab.
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = {}
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(`${BASE_URL}/api${path}`, {
      method,
      headers,
      body: body === undefined || isForm ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }

  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, res.status)
  return data
}
