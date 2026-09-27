<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/lines') })
</script>
<template>
  <h1>线路</h1>
  <p class="sub">运营线路与串车 / 大间隔判定阈值</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>计划间隔(分)</th><th>串车阈值</th><th>大间隔阈值</th><th>扣车上限(分)</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)"><td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.planned_headway_min }}</td><td>{{ r.bunch_threshold }}</td><td>{{ r.large_threshold }}</td><td>{{ r.max_hold_min }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
