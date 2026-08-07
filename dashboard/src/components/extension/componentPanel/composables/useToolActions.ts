/**
 * Tool actions composable
 */
import { ref, computed, type Ref } from 'vue';
import { toolApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { normalizeTextInput } from '@/utils/inputValue';
import type { ToolItem } from '@/domain/tools';
import type { ToolSummary } from '../types';

export function useToolActions(
  tools: Ref<ToolItem[]>,
  toast: (message: string, color?: string) => void,
) {
  const toolSearch = ref('');
  const showBuiltinTools = ref(true);

  const filteredTools = computed(() => {
    let result = tools.value;

    // Filter builtin tools
    if (!showBuiltinTools.value) {
      result = result.filter((tool) => tool.origin !== 'builtin');
    }

    // Filter by search query
    const query = normalizeTextInput(toolSearch.value).trim().toLowerCase();
    if (query) {
      result = result.filter(
        (tool) =>
          tool.name?.toLowerCase().includes(query) ||
          tool.description?.toLowerCase().includes(query),
      );
    }

    return result;
  });

  const toolSummary = computed<ToolSummary>(() => {
    const all = tools.value;
    return {
      total: all.length,
      active: all.filter((t) => t.active).length,
      inactive: all.filter((t) => !t.active).length,
    };
  });

  const parallelExecutionEnabled = computed(() =>
    tools.value.some((tool) => tool.parallel_execution_enabled),
  );

  /**
   * Toggle a tool's active state (optimistic update).
   */
  const toggleTool = async (
    tool: ToolItem,
    readonlyMessage: string,
    successMessage: string,
    errorMessage: string,
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
    } catch (error) {
      tool.active = previous;
      toast(resolveErrorMessage(error, errorMessage), 'error');
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
    errorMessage: string,
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
    } catch (error) {
      toast(resolveErrorMessage(error, errorMessage), 'error');
    }
  };

  const toggleToolParallel = async (
    tool: ToolItem,
    enabled: boolean,
    errorMessage: string,
  ) => {
    if (!tool.parallel_eligible || !tool.tool_id) {
      toast(tool.parallel_blocked_reason || errorMessage, 'info');
      return;
    }
    const previous = tool.parallel_enabled;
    tool.parallel_enabled = enabled;
    try {
      const res = await toolApi.setParallel(tool.tool_id, enabled);
      if (res.data.status === 'ok') {
        toast(res.data.message || errorMessage);
      } else {
        tool.parallel_enabled = previous;
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (error) {
      tool.parallel_enabled = previous;
      toast(resolveErrorMessage(error, errorMessage), 'error');
    }
  };

  const toggleParallelExecution = async (
    enabled: boolean,
    errorMessage: string,
  ) => {
    try {
      const res = await toolApi.setParallelEnabled(enabled);
      if (res.data.status === 'ok') {
        tools.value.forEach((tool) => {
          tool.parallel_execution_enabled = enabled;
        });
        toast(res.data.message || errorMessage);
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (error) {
      toast(resolveErrorMessage(error, errorMessage), 'error');
    }
  };

  return {
    toolSearch,
    showBuiltinTools,
    filteredTools,
    toolSummary,
    parallelExecutionEnabled,
    toggleTool,
    updateToolPermission,
    toggleToolParallel,
    toggleParallelExecution,
  };
}
