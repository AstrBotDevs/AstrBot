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
  const deletingSavedTools = ref(new Set<string>());
  const managedTools = computed(() => tools.value.filter(tool =>
    tool.origin === 'plugin' || tool.origin === 'mcp' || tool.registered === false
    || tool.inactive_configured || tool.permission_configured
  ));

  const filteredTools = computed(() => {
    let result = managedTools.value;

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
    const all = managedTools.value.filter(tool => tool.registered !== false);
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
    successMessage: string,
    errorMessage: string
  ) => {
    const previous = tool.active;
    tool.active = !tool.active;
    try {
      const res = await toolApi.setEnabled(tool.name, tool.active, tool.capability?.key);
      if (res.data.status === 'ok') {
        tool.inactive_configured = !tool.active;
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
    errorMessage: string
  ) => {
    try {
      const res = await toolApi.setPermission(tool.name, permission, tool.capability?.key);
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

  const deleteSavedToolSettings = async (
    tool: ToolItem,
    successMessage: string,
    errorMessage: string,
  ) => {
    if (tool.registered !== false || deletingSavedTools.value.has(tool.name)) return;
    deletingSavedTools.value.add(tool.name);
    try {
      const res = await toolApi.deleteSavedSettings(tool.name, tool.resource_key);
      if (res.data.status === 'ok') {
        tools.value = tools.value.filter(item => item.registered !== false || (item.resource_key || item.name) !== (tool.resource_key || tool.name));
        toast(successMessage, 'success');
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (error: any) {
      toast(error?.response?.data?.message || error.message || errorMessage, 'error');
    } finally {
      deletingSavedTools.value.delete(tool.name);
    }
  };

  return {
    toolSearch,
    filteredTools,
    toolSummary,
    toggleTool,
    updateToolPermission,
    deletingSavedTools,
    deleteSavedToolSettings,
  };
}
