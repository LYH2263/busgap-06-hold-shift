<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
const trips = ref<any[]>([])
const events = ref<any[]>([])
const arrivals = ref<any[]>([])
const lines = ref<any[]>([])
const holdForm = reactive<Record<number, { stop_name: string; hold_minutes: number }>>({})
const holdErr = ref<Record<number, string>>({})
const saving = ref<Record<number, boolean>>({})

const stopsByLine = computed(() => {
  const m: Record<number, string[]> = {}
  for (const a of arrivals.value) {
    const list = (m[a.line_id] ||= [])
    if (!list.includes(a.stop_name)) list.push(a.stop_name)
  }
  return m
})
const maxHoldByLine = computed(() =>
  Object.fromEntries(lines.value.map((l: any) => [l.id, l.max_hold_min])))

async function refreshEvents() {
  try {
    events.value = (await api('/reports/run?line_id=1', { method: 'POST' })).events || []
  } catch { events.value = [] }
}
onMounted(async () => {
  const [t, a, l] = await Promise.all([api('/trips'), api('/arrivals'), api('/lines')])
  trips.value = t
  arrivals.value = a
  lines.value = l
  for (const trip of trips.value) {
    holdForm[trip.id] = { stop_name: (stopsByLine.value[trip.line_id] || [])[0] || '', hold_minutes: 0 }
  }
  await refreshEvents()
})
function errText(e: any) {
  try {
    const d = JSON.parse(e.message).detail
    return typeof d === 'string' ? d : e.message
  } catch { return e.message }
}
async function register(t: any) {
  const f = holdForm[t.id]
  if (!f || !f.stop_name) return
  saving.value = { ...saving.value, [t.id]: true }
  holdErr.value = { ...holdErr.value, [t.id]: '' }
  try {
    const updated = await api(`/trips/${t.id}/holds`, {
      method: 'PUT',
      body: JSON.stringify({ stop_name: f.stop_name, hold_minutes: Number(f.hold_minutes) || 0 }),
    })
    t.holds = updated.holds
    await refreshEvents()
  } catch (e: any) {
    holdErr.value = { ...holdErr.value, [t.id]: errText(e) }
  } finally {
    saving.value = { ...saving.value, [t.id]: false }
  }
}
function stripClass(s: string) {
  return s === 'bunching' ? 'bg-bunch' : s === 'large_gap' ? 'bg-large' : ''
}
function label(s: string) {
  return s === 'bunching' ? '串车' : s === 'large_gap' ? '大间隔' : '正常'
}
</script>
<template>
  <h1>班次 · 间隔条带</h1>
  <p class="sub">左侧班次清单(可登记扣车),右侧串车/间隔竖直条带</p>
  <div class="bg-split">
    <aside class="bg-trip-col">
      <h2>班次列表</h2>
      <div v-for="r in trips" :key="r.id ?? r.trip_no" class="bg-trip-row">
        <div class="bg-trip-top">
          <div>
            <div>{{ r.trip_no }}</div>
            <div class="bg-trip-meta">线路 {{ r.line_id }} · 车 {{ r.vehicle_no }}</div>
          </div>
          <div class="bg-trip-meta">{{ r.planned_depart }}</div>
        </div>
        <div v-if="r.holds?.length" class="bg-hold-chips">
          <span v-for="h in r.holds" :key="h.stop_name" class="bg-hold-chip">
            {{ h.stop_name }} 扣 {{ h.hold_minutes }}′
          </span>
        </div>
        <div class="bg-hold-form">
          <select v-model="holdForm[r.id].stop_name">
            <option v-for="s in stopsByLine[r.line_id] || []" :key="s" :value="s">{{ s }}</option>
          </select>
          <input v-model.number="holdForm[r.id].hold_minutes" type="number" min="0" step="1" placeholder="分钟" />
          <button class="btn bg-hold-btn" :disabled="saving[r.id]" @click="register(r)">扣车</button>
        </div>
        <div class="bg-trip-meta">扣车上限 {{ maxHoldByLine[r.line_id] ?? '—' }}′ · 0 分为不扣</div>
        <div v-if="holdErr[r.id]" class="bg-hold-err">{{ holdErr[r.id] }}</div>
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
