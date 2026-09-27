<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const trips = ref<any[]>([])
const events = ref<any[]>([])
const stopsByTrip = ref<Record<number, string[]>>({})
const maxHold = ref<number | null>(null)
const form = ref<Record<number, { stop_name: string; hold_min: string }>>({})
const busy = ref<number | null>(null)
const error = ref<Record<number, string>>({})
const ready = ref(false)

async function refresh() {
  ready.value = false
  trips.value = await api('/trips?line_id=1')
  try {
    const [lines, arrivals] = await Promise.all([api('/lines'), api('/arrivals?line_id=1')])
    maxHold.value = lines[0]?.max_hold_min ?? null
    const map: Record<number, string[]> = {}
    for (const a of arrivals) {
      (map[a.trip_id] ||= []).push(a)
    }
    for (const id of Object.keys(map)) {
      map[id as any] = [...new Set(map[id as any].sort((x: any, y: any) => x.stop_seq - y.stop_seq)
        .map((a: any) => a.stop_name))]
    }
    stopsByTrip.value = map
  } catch { /* 线路或到站不可用时仅禁用站点提示 */ }
  form.value = {}
  for (const t of trips.value) {
    form.value[t.id] = {
      stop_name: t.hold?.stop_name || (stopsByTrip.value[t.id]?.[1] ?? stopsByTrip.value[t.id]?.[0] ?? ''),
      hold_min: t.hold ? String(t.hold.hold_min) : '',
    }
  }
  ready.value = true
  await rerun()
}

async function rerun() {
  try {
    events.value = (await api('/reports/run?line_id=1', { method: 'POST' })).events || []
  } catch { events.value = [] }
}

async function save(t: any) {
  const f = form.value[t.id]
  const min = parseFloat(f.hold_min || '0')
  if (!f.stop_name) { error.value[t.id] = '请选择扣车站点'; return }
  if (Number.isNaN(min) || min < 0) { error.value[t.id] = '扣车分钟需为不小于 0 的数字'; return }
  busy.value = t.id; error.value[t.id] = ''
  try {
    await api(`/trips/${t.id}/hold`, {
      method: 'PUT', body: JSON.stringify({ stop_name: f.stop_name, hold_min: min }),
    })
    await refresh()
  } catch (e: any) {
    let msg = e?.message || '登记失败'
    try { msg = JSON.parse(msg).detail || msg } catch { /* 非 JSON 错误体 */ }
    error.value[t.id] = msg
  } finally { busy.value = null }
}

onMounted(refresh)
function stripClass(s: string) {
  return s === 'bunching' ? 'bg-bunch' : s === 'large_gap' ? 'bg-large' : ''
}
function label(s: string) {
  return s === 'bunching' ? '串车' : s === 'large_gap' ? '大间隔' : '正常'
}
</script>
<template>
  <h1>班次 · 间隔条带</h1>
  <p class="sub">
    左侧班次清单（可登记扣车，上限 {{ maxHold ?? '—' }} 分钟），右侧按扣车后间隔展示
  </p>
  <div v-if="ready" class="bg-split">
    <aside class="bg-trip-col">
      <h2>班次列表</h2>
      <div v-for="r in trips" :key="r.id ?? r.trip_no" class="bg-trip-row">
        <div>
          <div>{{ r.trip_no }}</div>
          <div class="bg-trip-meta">线路 {{ r.line_id }} · 车 {{ r.vehicle_no }}</div>
        </div>
        <div class="bg-trip-meta">{{ r.planned_depart }}</div>
        <div class="bg-hold-form">
          <label class="bg-trip-meta">扣车</label>
          <select v-model="form[r.id].stop_name">
            <option v-for="s in stopsByTrip[r.id] || []" :key="s" :value="s">{{ s }}</option>
          </select>
          <input
            v-model="form[r.id].hold_min"
            type="number" min="0" step="0.5"
            :placeholder="`≤${maxHold ?? ''}`"
          />
          <span class="bg-trip-meta">分</span>
          <button class="btn btn-sm" :disabled="busy === r.id" @click="save(r)">
            {{ busy === r.id ? '…' : '登记' }}
          </button>
          <div v-if="r.hold" class="bg-hold-tag">
            已扣 {{ r.hold.stop_name }} {{ r.hold.hold_min }}′
          </div>
          <div v-if="error[r.id]" class="bg-hold-err">{{ error[r.id] }}</div>
        </div>
      </div>
    </aside>
    <div class="bg-strip-col">
      <article
        v-for="(e, i) in events"
        :key="i"
        class="bg-gap-strip"
        :class="stripClass(e.status)"
      >
        <header>{{ e.stop_name }}</header>
        <div class="bg-gap-body">
          <div class="bg-gap-val">{{ e.gap_min }}′</div>
          <div>计划 {{ e.planned_headway_min }}′</div>
          <div>{{ e.earlier_trip }} → {{ e.later_trip }}</div>
          <span class="badge" :class="e.status === 'bunching' ? 'badge-bad' : e.status === 'large_gap' ? 'badge-warn' : 'badge-ok'">
            {{ label(e.status) }}
          </span>
        </div>
      </article>
      <p v-if="!events.length" class="muted">暂无间隔事件</p>
    </div>
  </div>
</template>
