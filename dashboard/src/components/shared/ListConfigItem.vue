<template>
    <div class="list-config-item">
      <h3>{{ label }}</h3>
      <v-list dense style="background-color: transparent;max-height: 300px; overflow-y: scroll;" >
        <v-list-item v-for="(item, index) in items" :key="index">
          <v-list-item-content style="display: flex; justify-content: space-between;">
            <v-list-item-title>
                <v-chip>{{ item }}</v-chip>
            </v-list-item-title>
            <v-btn @click="removeItem(index)" variant="plain">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-list-item-content>
        </v-list-item>
      </v-list>
      <v-text-field
        v-model="newItem"
        label="添加新项"
        @keyup.enter="addItem"
        clearable
        dense
        hide-details
        variant="outlined"
      ></v-text-field>
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
    margin-bottom: 16px;
    border-radius: 10px;
    background-color: #ffffff;
  }
  
  .list-config-item h3 {
    margin-top: 0;
    margin-bottom: 16px;
    font-size: 18px;
    font-weight: 500;
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