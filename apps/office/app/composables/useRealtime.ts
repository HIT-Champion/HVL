// Copyright 2026 Mộc Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

// Thông báo realtime (F2.5): một kết nối WebSocket tới Centrifugo qua APISIX (/realtime) cho cả ứng dụng.
//
// Dùng thẳng giao thức JSON của Centrifugo (client protocol v2), chỉ phần cần để NHẬN tin: connect kèm access
// token Keycloak, làm mới token trước khi hết hạn, trả lời ping, nhận tin của kênh riêng mà máy chủ tự đưa kết nối
// vào. Không dùng thư viện centrifuge-js vì nó kéo theo protobufjs (có script postinstall) và hơn chục gói khác
// cho một việc chỉ cần nhận tin.
//
// Mất kết nối thì tự nối lại, chờ lâu dần (1 → 20 giây). Tin đẩy lúc mất kết nối không mất: thông báo đã lưu ở
// core.notifications, nên mỗi lần nối lại, nơi nghe sự kiện "connected" tải lại danh sách.

export interface RealtimeMessage {
  id: number
  kind: string
  document_id: string | null
  data: Record<string, unknown>
  created_at: string
}

type State = 'off' | 'connecting' | 'online' | 'offline'
type Listener = (msg: RealtimeMessage) => void

const state = ref<State>('off')
const messageListeners = new Set<Listener>()
const connectedListeners = new Set<() => void>()

let socket: WebSocket | null = null
let stopped = true
let generation = 0 // mỗi lần connect một số mới; lần connect cũ còn đang chờ token thì tự bỏ
let nextId = 1
let attempt = 0
let timers: ReturnType<typeof setTimeout>[] = []
let lastSeen = 0
let pingInterval = 25

function later(ms: number, fn: () => void) {
  const id = setTimeout(() => {
    timers = timers.filter((t) => t !== id)
    fn()
  }, ms)
  timers.push(id)
}

function clearTimers() {
  timers.forEach(clearTimeout)
  timers = []
}

async function freshToken(): Promise<string | null> {
  // Token còn hạn thì dùng, sắp hết thì gia hạn im lặng. Không qua useAuth().restore(): nó coi mọi lỗi (kể cả mất
  // mạng) là hết phiên và xóa người dùng khỏi giao diện; ở đây lỗi chỉ có nghĩa là thử lại sau.
  try {
    const m = await getManager()
    const u = await m.getUser()
    if (u && !u.expired && (u.expires_in ?? 0) > 30) return u.access_token
    if (u?.refresh_token) return (await m.signinSilent())?.access_token ?? null
  } catch {
    // mạng lỗi hoặc phiên Keycloak đã hết: thử lại sau
  }
  return null
}

function send(cmd: Record<string, unknown>) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(cmd))
}

function scheduleRefresh(ttl: number) {
  // gia hạn sau khi oidc-client-ts đã lấy token mới (60 giây trước khi hết hạn)
  later(Math.max(ttl - 30, 10) * 1000, refresh)
}

async function refresh() {
  const gen = generation
  const token = await freshToken()
  if (stopped || gen !== generation) return
  // chưa có token mới (mất mạng): thử lại; quá hạn thì máy chủ đóng kết nối và vòng nối lại lo tiếp
  if (token) send({ id: nextId++, refresh: { token } })
  else later(10_000, refresh)
}

function reconnect() {
  generation += 1
  socket?.close()
  socket = null
  clearTimers()
  if (stopped) return
  state.value = 'offline'
  const delay = Math.min(1000 * 2 ** attempt, 20000) * (0.75 + Math.random() / 2)
  attempt += 1
  later(delay, connect)
}

function watchdog() {
  // không nhận gì quá một chu kỳ ping và 10 giây: kết nối đã chết dù trình duyệt chưa báo
  later(5000, () => {
    if (Date.now() - lastSeen > (pingInterval + 10) * 1000) reconnect()
    else watchdog()
  })
}

function handle(msg: Record<string, any>) {
  if (Object.keys(msg).length === 0) {
    send({}) // ping của máy chủ → pong
    return
  }
  if (msg.error) {
    // 109: token hết hạn → nối lại với token mới; lỗi khác cũng thử lại sau
    reconnect()
    return
  }
  if (msg.connect) {
    state.value = 'online'
    attempt = 0
    pingInterval = msg.connect.ping || 25
    if (msg.connect.expires) scheduleRefresh(msg.connect.ttl)
    watchdog()
    connectedListeners.forEach((fn) => fn())
    return
  }
  if (msg.refresh?.expires) {
    scheduleRefresh(msg.refresh.ttl)
    return
  }
  const data = msg.push?.pub?.data as RealtimeMessage | undefined
  if (data) messageListeners.forEach((fn) => fn(data))
}

async function connect() {
  if (stopped) return
  const gen = ++generation
  const token = await freshToken()
  // đã dừng (đăng xuất, rời trang) hoặc có lần connect mới hơn trong lúc chờ token
  if (stopped || gen !== generation) return
  if (!token) {
    reconnect()
    return
  }
  state.value = 'connecting'
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/realtime`)
  socket = ws
  ws.onopen = () => {
    if (ws !== socket) {
      ws.close()
      return
    }
    lastSeen = Date.now()
    ws.send(JSON.stringify({ id: nextId++, connect: { token, name: 'moc-office' } }))
  }
  ws.onmessage = (e) => {
    if (ws !== socket) return
    lastSeen = Date.now()
    // máy chủ có thể gộp nhiều lệnh trong một khung, mỗi lệnh một dòng
    for (const line of String(e.data).split('\n')) {
      if (!line.trim()) continue
      try {
        handle(JSON.parse(line))
      } catch {
        // bỏ qua dòng hỏng
      }
    }
  }
  ws.onclose = (e) => {
    if (ws !== socket) return
    // 3500–3999: máy chủ bảo đừng nối lại (token sai, yêu cầu sai) — chỉ thử lại khi người dùng tải lại trang
    if (e.code >= 3500 && e.code < 4000) {
      generation += 1
      socket = null
      clearTimers()
      state.value = 'offline'
      return
    }
    reconnect()
  }
}

function start() {
  if (!stopped || typeof WebSocket === 'undefined') return
  stopped = false
  attempt = 0
  void connect()
}

function stop() {
  stopped = true
  generation += 1
  clearTimers()
  const ws = socket
  socket = null
  ws?.close(1000)
  state.value = 'off'
}

export function useRealtime() {
  // nối lại ngay khi có mạng trở lại thay vì chờ hết thời gian chờ (connect mới làm lần chờ cũ tự bỏ)
  function online() {
    if (!stopped && state.value === 'offline') {
      clearTimers()
      attempt = 0
      void connect()
    }
  }

  function onMessage(fn: Listener) {
    messageListeners.add(fn)
    if (getCurrentInstance()) onBeforeUnmount(() => messageListeners.delete(fn))
    return () => messageListeners.delete(fn)
  }

  function onConnected(fn: () => void) {
    connectedListeners.add(fn)
    if (getCurrentInstance()) onBeforeUnmount(() => connectedListeners.delete(fn))
    return () => connectedListeners.delete(fn)
  }

  return { state, start, stop, online, onMessage, onConnected }
}
