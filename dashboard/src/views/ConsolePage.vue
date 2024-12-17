<script setup>
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
</script>

<template>
  <div style="height: 100%;">
    <div
      style="background-color: white; padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
      <h4>控制台</h4>
    </div>
    <ConsoleDisplayer style="height: calc(100vh - 160px); "/>
  </div>
</template>
<script>
export default {
  name: 'ConsolePage',
  components: {
    ConsoleDisplayer
  },
}

</script>

<style>
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
.fade-in {
  animation: fadeIn 0.2s ease-in-out;
}
</style>