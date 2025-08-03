<template>
  <div class="pa-4">
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title class="d-flex align-center">
            <v-icon start>mdi-shield-key</v-icon>
            指令权限管理
          </v-card-title>
          <v-card-subtitle>
            管理所有指令的访问权限，控制哪些指令需要管理员权限
          </v-card-subtitle>
        </v-card>
      </v-col>
    </v-row>

    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-row class="align-center">
              <v-col cols="6">
                <span>指令列表</span>
              </v-col>
              <v-col cols="6" class="text-right">
                <v-btn 
                  color="primary" 
                  @click="loadCommands"
                  :loading="loading"
                  variant="outlined"
                >
                  <v-icon start>mdi-refresh</v-icon>
                  刷新列表
                </v-btn>
              </v-col>
            </v-row>
          </v-card-title>

          <v-card-text>
            <!-- 搜索和过滤 -->
            <v-row class="mb-4">
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="searchText"
                  label="搜索指令或插件"
                  prepend-inner-icon="mdi-magnify"
                  clearable
                  variant="outlined"
                  density="compact"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="3">
                <v-select
                  v-model="filterPlugin"
                  :items="pluginOptions"
                  label="筛选插件"
                  clearable
                  variant="outlined"
                  density="compact"
                ></v-select>
              </v-col>
              <v-col cols="12" md="3">
                <v-select
                  v-model="filterPermission"
                  :items="permissionOptions"
                  label="筛选权限"
                  clearable
                  variant="outlined"
                  density="compact"
                ></v-select>
              </v-col>
            </v-row>

            <!-- 数据表格 -->
            <v-data-table
              :headers="headers"
              :items="filteredCommands"
              :loading="loading"
              :search="searchText"
              class="elevation-1"
            >
              <template v-slot:item.command_name="{ item }">
                <v-chip 
                  :color="item.is_group ? 'purple' : 'blue'"
                  variant="outlined"
                  size="small"
                >
                  <v-icon start>{{ item.is_group ? 'mdi-folder' : 'mdi-console' }}</v-icon>
                  {{ item.command_name }}
                </v-chip>
              </template>

              <template v-slot:item.plugin_name="{ item }">
                <v-chip 
                  color="green"
                  variant="tonal"
                  size="small"
                >
                  {{ item.plugin_name }}
                </v-chip>
              </template>

              <template v-slot:item.current_permission="{ item }">
                <v-chip 
                  :color="item.current_permission === 'admin' ? 'red' : 'blue'"
                  :variant="item.current_permission === 'admin' ? 'flat' : 'tonal'"
                  size="small"
                >
                  <v-icon start>
                    {{ item.current_permission === 'admin' ? 'mdi-shield-crown' : 'mdi-account-group' }}
                  </v-icon>
                  {{ item.current_permission === 'admin' ? '管理员' : '所有用户' }}
                </v-chip>
              </template>

              <template v-slot:item.actions="{ item }">
                <v-btn-toggle
                  :model-value="item.current_permission"
                  @update:model-value="changePermission(item, $event)"
                  mandatory
                  variant="outlined"
                  size="small"
                  divided
                >
                  <v-btn value="member" size="small">
                    <v-icon>mdi-account-group</v-icon>
                    所有用户
                  </v-btn>
                  <v-btn value="admin" size="small">
                    <v-icon>mdi-shield-crown</v-icon>
                    管理员
                  </v-btn>
                </v-btn-toggle>
              </template>

              <template v-slot:item.description="{ item }">
                <span class="text-body-2">{{ item.description || '无描述' }}</span>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 成功/错误提示 -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
    >
      {{ snackbar.message }}
      <template v-slot:actions>
        <v-btn
          color="white"
          variant="text"
          @click="snackbar.show = false"
        >
          关闭
        </v-btn>
      </template>
    </v-snackbar>

    <!-- 确认对话框 -->
    <v-dialog v-model="confirmDialog.show" max-width="400">
      <v-card>
        <v-card-title class="headline">确认修改</v-card-title>
        <v-card-text>
          确定要将指令 <strong>{{ confirmDialog.command }}</strong> 的权限修改为 
          <strong>{{ confirmDialog.permission === 'admin' ? '管理员' : '所有用户' }}</strong> 吗？
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="grey"
            text
            @click="confirmDialog.show = false"
          >
            取消
          </v-btn>
          <v-btn
            color="primary"
            @click="confirmPermissionChange"
            :loading="confirmDialog.loading"
          >
            确认
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import axios from 'axios'

// 响应式数据
const loading = ref(false)
const commands = ref([])
const searchText = ref('')
const filterPlugin = ref('')
const filterPermission = ref('')

const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

const confirmDialog = reactive({
  show: false,
  command: '',
  permission: '',
  item: null,
  loading: false
})

// 表格头部定义
const headers = [
  { title: '指令名称', key: 'command_name', align: 'start' },
  { title: '所属插件', key: 'plugin_name', align: 'start' },
  { title: '当前权限', key: 'current_permission', align: 'center' },
  { title: '描述', key: 'description', align: 'start' },
  { title: '操作', key: 'actions', align: 'center', sortable: false, width: '200px' }
]

// 权限选项
const permissionOptions = [
  { title: '管理员', value: 'admin' },
  { title: '所有用户', value: 'member' }
]

// 计算属性
const pluginOptions = computed(() => {
  const plugins = [...new Set(commands.value.map(cmd => cmd.plugin_name))]
  return plugins.map(plugin => ({ title: plugin, value: plugin }))
})

const filteredCommands = computed(() => {
  let filtered = commands.value

  if (filterPlugin.value) {
    filtered = filtered.filter(cmd => cmd.plugin_name === filterPlugin.value)
  }

  if (filterPermission.value) {
    filtered = filtered.filter(cmd => cmd.current_permission === filterPermission.value)
  }

  return filtered
})

// 方法
const showSnackbar = (message, color = 'success') => {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

const loadCommands = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/command_permission/get_commands')
    if (response.data.status === 'ok') {
      commands.value = response.data.data.commands
    } else {
      showSnackbar('加载指令列表失败: ' + response.data.message, 'error')
    }
  } catch (error) {
    console.error('加载指令列表失败:', error)
    showSnackbar('加载指令列表失败', 'error')
  } finally {
    loading.value = false
  }
}

const changePermission = (item, newPermission) => {
  confirmDialog.command = item.command_name
  confirmDialog.permission = newPermission
  confirmDialog.item = item
  confirmDialog.show = true
}

const confirmPermissionChange = async () => {
  confirmDialog.loading = true
  try {
    const response = await axios.post('/api/command_permission/set', {
      plugin_name: confirmDialog.item.plugin_name,
      handler_name: confirmDialog.item.handler_name,
      permission: confirmDialog.permission
    })

    if (response.data.status === 'ok') {
      // 更新本地数据
      confirmDialog.item.current_permission = confirmDialog.permission
      showSnackbar(response.data.data.message, 'success')
      confirmDialog.show = false
    } else {
      showSnackbar('修改权限失败: ' + response.data.message, 'error')
    }
  } catch (error) {
    console.error('修改权限失败:', error)
    showSnackbar('修改权限失败', 'error')
  } finally {
    confirmDialog.loading = false
  }
}

// 生命周期
onMounted(() => {
  loadCommands()
})
</script>

<style scoped>
.v-card {
  transition: all 0.3s ease;
}

.v-data-table {
  border-radius: 8px;
}

.v-chip {
  font-weight: 500;
}
</style>