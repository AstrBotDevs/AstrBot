/**
 * 指令数据管理 Composable
 */
import { ref, reactive } from 'vue';
import axios from 'axios';
import type { CommandItem, CommandSummary, SnackbarState, ToolItem } from '../types';

export function useComponentData() {
  const loading = ref(false);
  const commands = ref<CommandItem[]>([]);
  const tools = ref<ToolItem[]>([]);
  const toolsLoading = ref(false);
  const summary = reactive<CommandSummary>({
    disabled: 0,
    conflicts: 0
  });

  const snackbar = reactive<SnackbarState>({
    show: false,
    message: '',
    color: 'success'
  });

  /**
   * 显示 Toast 消息
   */
  const toast = (message: string, color: string = 'success') => {
    snackbar.message = message;
    snackbar.color = color;
    snackbar.show = true;
  };

  /**
   * 获取指令列表
   */
  const fetchCommands = async (errorMessage: string) => {
    loading.value = true;
    try {
      const res = await axios.get('/api/commands');
      if (res.data.status === 'ok') {
        commands.value = res.data.data.items || [];
        const s = res.data.data.summary || {};
        summary.disabled = s.disabled || 0;
        summary.conflicts = s.conflicts || 0;
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err: any) {
      toast(err?.message || errorMessage, 'error');
    } finally {
      loading.value = false;
    }
  };

  const fetchTools = async (errorMessage: string) => {
    toolsLoading.value = true;
    try {
      const res = await axios.get('/api/tools/list');
      if (res.data.status === 'ok') {
        tools.value = res.data.data || [];
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err: any) {
      toast(err?.message || errorMessage, 'error');
    } finally {
      toolsLoading.value = false;
    }
  };

  return {
    loading,
    commands,
    tools,
    toolsLoading,
    summary,
    snackbar,
    toast,
    fetchCommands,
    fetchTools
  };
}

