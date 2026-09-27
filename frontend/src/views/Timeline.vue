<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<{ stop_name: string; marks: any[] }>({ stop_name: '', marks: [] })
onMounted(async () => { data.value = await api('/reports/timeline?line_id=1') })
function markColor(m: any) {
  if (m.hold_min > 0) return 'var(--bg-amber)'
  return m.pct < 15 ? 'var(--bg-red)' : 'var(--bg-cyan)'
}
</script>
<template>
  <h1>时间轴明细</h1>
  <p class="sub">站点「{{ data.stop_name }}」到站分布(按扣车后时刻计算,顶部已展示发车间隔轴)</p>
  <div class="card">
    <div class="tl-track">
      <div v-for="m in data.marks" :key="m.trip_no" class="tl-mark"
        :style="{ left: m.pct + '%', background: markColor(m) }"
        :title="m.trip_no + ' ' + m.actual_arrive + (m.hold_min > 0 ? ` (扣 ${m.hold_min}′)` : '')" />
    </div>
    <table>
      <thead><tr><th>班次</th><th>到站时间</th><th>扣车</th><th>相对位置</th></tr></thead>
      <tbody>
        <tr v-for="m in data.marks" :key="m.trip_no">
          <td>{{ m.trip_no }}</td><td>{{ m.actual_arrive }}</td>
          <td><span v-if="m.hold_min > 0" class="badge badge-warn">扣 {{ m.hold_min }}′</span><span v-else class="muted">—</span></td>
          <td>{{ m.pct }}%</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
