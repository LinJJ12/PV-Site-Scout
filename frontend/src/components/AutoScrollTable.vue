<template>
  <div class="board-head">
    <span v-for="col in columns" :key="col.key" :style="{ textAlign: col.align || 'left' }">{{ col.label }}</span>
  </div>
  <div class="board-viewport">
    <div class="board-empty" v-if="!rows.length">该省暂无站点进入榜单</div>
    <div class="board-list" v-else>
      <div class="board-row" v-for="(row, index) in doubledRows" :key="index">
        <span class="rk" :class="rankClass(row.rank)">{{ row.rank }}</span>
        <span v-for="col in bodyColumns" :key="col.key" :style="{ textAlign: col.align || 'left' }">
          <b v-if="col.colorKey && row[col.colorKey]" :style="{ color: row[col.colorKey] }">{{ row[col.key] }}</b>
          <template v-else>{{ row[col.key] }}</template>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

/* 轮播滚动榜（参照 DataV scrollBoard）：列表复制一份实现无缝向上滚动，hover 暂停 */
const props = defineProps({
  columns: { type: Array, default: () => [] },      // [{ key, label, align, colorKey? }]
  rows: { type: Array, default: () => [] },          // 每行含 columns 的 key 字段
});

const bodyColumns = computed(() => props.columns.filter((col) => col.key !== "rank"));
const doubledRows = computed(() => {
  const rows = props.rows.map((row, index) => ({ ...row, rank: row.rank ?? index + 1 }));
  return [...rows, ...rows];
});
const rankClass = (rank) => (rank <= 3 ? `top r${rank}` : "");
</script>
