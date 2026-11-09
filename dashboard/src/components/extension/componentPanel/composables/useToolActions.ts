/**
 * Tool actions composable
 */
import { ref, computed, type Ref } from 'vue';
import { toolApi } from '@/api/v1';
import { normalizeTextInput } from '@/utils/inputValue';
import type { ToolItem, ToolSummary } from '../types';

export function useToolActions(
  tools: Ref<ToolItem[]>,
  toast: (message: string, color?: string) => void
) {
  const toolSearch = ref('');
  const showBuiltinTools = ref(true);

  const filteredTools = computed(() => {
    let result = tools.value;

    // Filter builtin tools
    if (!showBuiltinTools.value) {
      result = result.filter(tool => tool.origin !== 'builtin');
    }

    // Filter by search query
    const query = normalizeTextInput(toolSearch.value).trim().toLowerCase();
    if (query) {
      result = result.filter(
        tool =>
          tool.name?.toLowerCase().includes(query) ||
          tool.description?.toLowerCase().includes(query)
      );
    }

    return result;
  });

  const toolSummary = computed<ToolSummary>(() => {
    const all = tools.value;
    return {
      total: all.length,
      active: all.filter(t => t.active).length,
      inactive: all.filter(t => !t.active).length,
    };
  });

  /**
   * Toggle a tool's active state (optimistic update).
   */
  const toggleTool = async (
    tool: ToolItem,
    readonlyMessage: string,
    successMessage: string,
    errorMessage: string
  ) => {
    if (tool.readonly) {
      toast(readonlyMessage, 'info');
      return;
    }
    const previous = tool.active;
    tool.active = !tool.active;
    try {
      const res = await toolApi.setEnabled(tool.name, tool.active);
      if (res.data.status === 'ok') {
        toast(res.data.message || successMessage);
      } else {
        tool.active = previous;
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (error: any) {
      tool.active = previous;
      toast(
        error?.response?.data?.message ||
          error?.message ||
          errorMessage,
        'error'
      );
    }
  };

  /**
   * Update a tool's permission level.
   */
  const updateToolPermission = async (
    tool: ToolItem,
    permission: 'admin' | 'member',
    successMessage: string,
    builtinMessage: string,
    errorMessage: string
  ) => {
    if (tool.origin === 'builtin') {
      toast(builtinMessage, 'info');
      return;
    }
    try {
      const res = await toolApi.setPermission(tool.name, permission);
      if (res.data.status === 'ok') {
        tool.permission = permission;
        tool.permission_configured = true;
        toast(successMessage, 'success');
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (error: any) {
      toast(
        error?.response?.data?.message ||
          error?.message ||
          errorMessage,
        'error'
      );
    }
  };

  return {
    toolSearch,
    showBuiltinTools,
    filteredTools,
    toolSummary,
    toggleTool,
    updateToolPermission,
  };
}
