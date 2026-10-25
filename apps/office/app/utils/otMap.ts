// Copyright 2026 Signet Team
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

// Sơ đồ cảm biến kho (/cam-bien, F3.10): dạng dữ liệu của Action otSensorMap (svc-workflow đọc broker NGSI-LD ở tenant
// của đơn vị người xem), sơ đồ mặt bằng mẫu và các hàm thuần tô màu. Cờ chất lượng do svc-workflow tính
// (ot.py, sensor_view); ở đây chỉ đọc cờ để chọn màu và nhãn. Sơ đồ là SVG vẽ trong trang: không tải ảnh, tile hay
// thư viện bản đồ nào, CSP của giao diện giữ nguyên.

export const SENSOR_REFRESH_MS = 30_000
// Dải "gần ngưỡng" chỉ để nhìn trên sơ đồ, không gửi cảnh báo: cảnh báo (dự thảo "Báo cáo sự cố") chỉ khi vượt ngưỡng
export const NEAR_BAND = 2
// Giờ đo muộn hơn giờ máy chủ quá chừng này phút là ở tương lai (cờ future_time): đúng FUTURE_SLACK của svc-workflow
// (ot.py), chỉ để ghi trong chú giải
export const FUTURE_SLACK_MIN = 2

export type SensorFlag = 'stale' | 'out_of_range' | 'duplicate_time' | 'future_time'
export type MapStatus = 'ready' | 'off' | 'unavailable'
export type Level = 'over' | 'near' | 'normal' | 'unknown' | 'empty'

export const FLAG_ORDER: SensorFlag[] = ['stale', 'out_of_range', 'duplicate_time', 'future_time']
export const LEVEL_ORDER: Level[] = ['over', 'near', 'normal', 'unknown', 'empty']

export interface OtSensor {
  id: string
  room: string | null
  name: string
  value: number | null
  observed_at: string | null
  flags: string[]
}

export interface OtSensorMap {
  status: MapStatus
  threshold: number
  stale_after_min: number
  range_min: number
  range_max: number
  checked_at: string
  sensors: OtSensor[]
}

export interface PlanRoom {
  code: string
  x: number
  y: number
  w: number
  h: number
  // cửa ra hành lang ở cạnh trên hay cạnh dưới của phòng
  door: 'top' | 'bottom'
}

export interface Box { x: number; y: number; w: number; h: number }

export interface Plan {
  view: { width: number; height: number }
  outline: Box
  corridor: Box
  rooms: PlanRoom[]
}

// Sơ đồ mẫu: một tầng kho lưu trữ, hai dãy phòng hai bên hành lang. Mã phòng trùng Property `room` mà cảm biến khai
// (sensor.py --room); muốn sơ đồ khác thì sửa danh sách này và nhãn sensors.room.<mã> trong locales. Một đối tượng
// thay vì nhiều hằng một dòng: bộ quét tự import của Nuxt (mlly) đọc lố qua các dòng `export const X = { a, b }` liền
// nhau (tests/autoImports.test.ts)
export const PLAN: Plan = {
  view: { width: 760, height: 440 },
  outline: { x: 10, y: 10, w: 740, h: 420 },
  corridor: { x: 20, y: 200, w: 720, h: 40 },
  rooms: [
    { code: 'kho-1', x: 20, y: 20, w: 230, h: 170, door: 'bottom' },
    { code: 'kho-2', x: 260, y: 20, w: 230, h: 170, door: 'bottom' },
    { code: 'kho-3', x: 500, y: 20, w: 240, h: 170, door: 'bottom' },
    { code: 'phong-doc', x: 20, y: 250, w: 270, h: 170, door: 'top' },
    { code: 'xu-ly', x: 300, y: 250, w: 200, h: 170, door: 'top' },
    { code: 'may-chu', x: 510, y: 250, w: 230, h: 170, door: 'top' },
  ],
}

// Màu của từng mức: nền, viền phòng trên sơ đồ, nhãn trong bảng
export const LEVEL_TONE: Record<Level, { fill: string; stroke: string; chip: string }> = {
  over: { fill: 'fill-red-100', stroke: 'stroke-red-500', chip: 'bg-red-100 text-red-800' },
  near: { fill: 'fill-amber-100', stroke: 'stroke-amber-500', chip: 'bg-amber-100 text-amber-800' },
  normal: { fill: 'fill-emerald-50', stroke: 'stroke-emerald-500', chip: 'bg-emerald-100 text-emerald-800' },
  unknown: { fill: 'fill-stone-200', stroke: 'stroke-stone-400', chip: 'bg-stone-200 text-stone-700' },
  empty: { fill: 'fill-white', stroke: 'stroke-stone-300', chip: 'bg-stone-100 text-stone-500' },
}

const SEVERITY: Record<Level, number> = { empty: 0, unknown: 1, normal: 2, near: 3, over: 4 }

// Cờ đã biết, đúng thứ tự FLAG_ORDER; cờ lạ (svc-workflow mới hơn giao diện) bỏ qua
export function knownFlags(flags: Iterable<string>): SensorFlag[] {
  const set = new Set(flags)
  return FLAG_ORDER.filter((f) => set.has(f))
}

// Mức của một cảm biến: không có số, mất tín hiệu hay ngoài dải thì không tin được số đo; vượt ngưỡng theo đúng luật
// của subscription (temperature > ngưỡng); trùng giờ đo, giờ đo ở tương lai vẫn tô theo số, chỉ thêm dấu cờ (số đo
// mới tới broker, chỉ giờ của thiết bị sai; thiết bị đó mất tín hiệu thì có thêm cờ mất tín hiệu)
export function sensorLevel(sensor: Pick<OtSensor, 'value' | 'flags'>, threshold: number): Level {
  if (sensor.value === null || sensor.flags.includes('stale') || sensor.flags.includes('out_of_range')) return 'unknown'
  if (sensor.value > threshold) return 'over'
  if (sensor.value > threshold - NEAR_BAND) return 'near'
  return 'normal'
}

// Mức của một phòng: mức nặng nhất trong các cảm biến của phòng; chỉ "không tin được" khi không cảm biến nào tin được
export function roomLevel(sensors: Pick<OtSensor, 'value' | 'flags'>[], threshold: number): Level {
  let level: Level = 'empty'
  for (const s of sensors) {
    const next = sensorLevel(s, threshold)
    if (SEVERITY[next] > SEVERITY[level]) level = next
  }
  return level
}

export interface RoomView {
  room: PlanRoom
  sensors: OtSensor[]
  level: Level
  flags: SensorFlag[]
}

// Gắn cảm biến vào phòng theo mã; cảm biến không khai phòng hoặc mã không có trên sơ đồ thì vào `outside`
export function placeSensors(map: Pick<OtSensorMap, 'sensors' | 'threshold'>,
  rooms: PlanRoom[] = PLAN.rooms): { rooms: RoomView[]; outside: OtSensor[] } {
  const byCode = new Map(rooms.map((r) => [r.code, [] as OtSensor[]]))
  const outside: OtSensor[] = []
  for (const s of map.sensors) {
    const list = s.room ? byCode.get(s.room) : undefined
    if (list) list.push(s)
    else outside.push(s)
  }
  return {
    rooms: rooms.map((room) => {
      const sensors = byCode.get(room.code)!
      const flags = knownFlags(sensors.flatMap((s) => s.flags))
      return { room, sensors, level: roomLevel(sensors, map.threshold), flags }
    }),
    outside,
  }
}

// Ô cửa: một đoạn trên cạnh giáp hành lang, giữa cạnh, rộng 36
export function doorOf(room: PlanRoom): { x1: number; y1: number; x2: number; y2: number } {
  const y = room.door === 'top' ? room.y : room.y + room.h
  const mid = room.x + room.w / 2
  return { x1: mid - 18, y1: y, x2: mid + 18, y2: y }
}

// Nhiệt độ theo ngôn ngữ đang chọn: 22,5 °C (vi), 22.5 °C (en); không có số thì gạch ngang
export function fmtTemp(value: number | null, locale: string): string {
  if (value === null || !Number.isFinite(value)) return '—'
  const n = new Intl.NumberFormat(locale === 'vi' ? 'vi-VN' : 'en-GB', { maximumFractionDigits: 1 }).format(value)
  return `${n} °C`
}
