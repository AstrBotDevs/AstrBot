<template>
  <div class="list-config-item">
    <v-list dense style="background-color: transparent;max-height: 300px; overflow-y: auto;">
      <v-list-item v-for="(item, index) in items" :key="index">
        <v-list-item-content style="display: flex; justify-content: space-between;">
          <v-list-item-title v-if="editIndex !== index">
            <v-chip size="small" label color="primary">{{ item }}</v-chip>
          </v-list-item-title>
          <v-text-field 
            v-else
            v-model="editItem" 
            dense 
            hide-details 
            variant="outlined" 
            density="compact"
            @keyup.enter="saveEdit" 
            @keyup.esc="cancelEdit"
            autofocus
          ></v-text-field>
          <div v-if="editIndex !== index">
            <v-btn @click="startEdit(index, item)" variant="plain" class="edit-btn" icon size="small">
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn @click="removeItem(index)" variant="plain" icon size="small">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </div>
          <div v-else>
            <v-btn @click="saveEdit" variant="plain" color="success" icon size="small">
              <v-icon>mdi-check</v-icon>
            </v-btn>
            <v-btn @click="cancelEdit" variant="plain" color="error" icon size="small">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </div>
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
      editIndex: -1,
      editItem: '',
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
    startEdit(index, item) {
      this.editIndex = index;
      this.editItem = item;
    },
    saveEdit() {
      if (this.editItem.trim() !== '') {
        this.items[this.editIndex] = this.editItem.trim();
        this.cancelEdit();
      }
    },
    cancelEdit() {
      this.editIndex = -1;
      this.editItem = '';
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

.edit-btn {
  margin-right: -8px;
}
</style>