<template>
  <div class="list-config-item">
    <v-list dense style="background-color: transparent;max-height: 300px; overflow-y: auto;">
      <v-list-item v-for="(item, index) in items" :key="index">
        <v-list-item-content style="display: flex; justify-content: space-between;">
          <v-list-item-title>
            <v-chip size="small" label color="primary">{{ item }}</v-chip>
          </v-list-item-title>
          <v-btn @click="removeItem(index)" variant="plain">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-list-item-content>
      </v-list-item>
    </v-list>
    <div style="display: flex; align-items: center;">
      <v-text-field v-model="newItem" label="添加新项，按回车确认添加" @keyup.enter="addItem" clearable dense hide-details
        variant="outlined" density="compact"></v-text-field>
      <v-btn @click="addItem" text variant="tonal">
        <v-icon>mdi-plus</v-icon>
        添加
      </v-btn>
    </div>

  </div>
</template>

<script>
export default {
  name: 'ListConfigItem',
  props: {
    value: {
      type: Array,
      default: () => [],
    },
    label: {
      type: String,
      default: '',
    },
  },
  data() {
    return {
      newItem: '',
      items: this.value,
    };
  },
  watch: {
    items(newVal) {
      this.$emit('input', newVal);
    },
  },
  methods: {
    addItem() {
      if (this.newItem.trim() !== '') {
        this.items.push(this.newItem.trim());
        this.newItem = '';
      }
    },
    removeItem(index) {
      this.items.splice(index, 1);
    },
  },
};
</script>

<style scoped>
.list-config-item {
  border: 1px solid #e0e0e0;
  padding: 16px;
  margin-bottom: 8px;
  border-radius: 10px;
  background-color: #ffffff;
}

.v-list-item {
  padding: 0;
}

.v-list-item-title {
  font-size: 14px;
}

.v-btn {
  margin-left: 8px;
}
</style>