<template>
  <article class="panel">
    <div class="panel-title">
      <span></span>
      <b>{{ title }}</b>
      <em v-if="note">{{ note }}</em>
    </div>
    <div class="panel-body">
      <slot />
    </div>
  </article>
</template>

<script setup>
/* 全站统一面板：渐变描边 + 四角饰件 + 标题装饰条（样式见 styles.css .panel） */
defineProps({
  title: { type: String, required: true },
  note: { type: String, default: "" },
});
</script>
