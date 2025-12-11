/**
 * 指令过滤逻辑 Composable
 */
import { ref, computed, type Ref } from 'vue';
import type { CommandItem, FilterState } from '../types';

export function useCommandFilters(commands: Ref<CommandItem[]>) {
  // 过滤状态
  const searchQuery = ref('');
  const pluginFilter = ref('all');
  const permissionFilter = ref('all');
  const statusFilter = ref('all');
  const typeFilter = ref('all');
  const showSystemPlugins = ref(false);

  // 展开的指令组
  const expandedGroups = ref<Set<string>>(new Set());

  /**
   * 检查是否有涉及系统插件的冲突
   */
  const hasSystemPluginConflict = computed(() => {
    return commands.value.some(cmd => cmd.has_conflict && cmd.reserved);
  });

  /**
   * 实际是否显示系统插件（如果有系统插件冲突则强制显示）
   */
  const effectiveShowSystemPlugins = computed(() => {
    return showSystemPlugins.value || hasSystemPluginConflict.value;
  });

  /**
   * 获取可用的插件列表（用于过滤下拉框）
   */
  const availablePlugins = computed(() => {
    const plugins = new Set(
      commands.value
        .filter(cmd => effectiveShowSystemPlugins.value || !cmd.reserved)
        .map(cmd => cmd.plugin)
    );
    return Array.from(plugins).sort();
  });

  /**
   * 检查指令是否匹配过滤条件
   */
  const matchesFilters = (cmd: CommandItem, query: string): boolean => {
    // 系统插件过滤（除非显示系统插件）
    if (!effectiveShowSystemPlugins.value && cmd.reserved) {
      return false;
    }

    // 搜索过滤
    if (query) {
      const matchesSearch = 
        cmd.effective_command?.toLowerCase().includes(query) ||
        cmd.description?.toLowerCase().includes(query) ||
        cmd.plugin?.toLowerCase().includes(query);
      if (!matchesSearch) return false;
    }

    // 插件过滤
    if (pluginFilter.value !== 'all' && cmd.plugin !== pluginFilter.value) {
      return false;
    }

    // 权限过滤
    if (permissionFilter.value !== 'all') {
      if (permissionFilter.value === 'everyone') {
        if (cmd.permission !== 'everyone' && cmd.permission !== 'member') return false;
      } else if (cmd.permission !== permissionFilter.value) {
        return false;
      }
    }

    // 状态过滤
    if (statusFilter.value !== 'all') {
      if (statusFilter.value === 'enabled' && !cmd.enabled) return false;
      if (statusFilter.value === 'disabled' && cmd.enabled) return false;
      if (statusFilter.value === 'conflict' && !cmd.has_conflict) return false;
    }

    // 类型过滤
    if (typeFilter.value !== 'all') {
      if (typeFilter.value === 'group' && cmd.type !== 'group') return false;
      if (typeFilter.value === 'command' && cmd.type !== 'command') return false;
      if (typeFilter.value === 'sub_command' && cmd.type !== 'sub_command') return false;
    }

    return true;
  };

  /**
   * 过滤后的指令列表（支持层级结构）
   */
  const filteredCommands = computed(() => {
    const query = searchQuery.value.toLowerCase();
    const conflictCmds: CommandItem[] = [];
    const normalCmds: CommandItem[] = [];

    for (const cmd of commands.value) {
      // 对于指令组，检查组本身或子指令是否匹配
      if (cmd.is_group) {
        const groupMatches = matchesFilters(cmd, query);
        const matchingSubCmds = (cmd.sub_commands || []).filter(sub => matchesFilters(sub, query));
        
        // 如果组匹配或有匹配的子指令，则包含它
        if (groupMatches || matchingSubCmds.length > 0) {
          if (cmd.has_conflict) {
            conflictCmds.push(cmd);
          } else {
            normalCmds.push(cmd);
          }
          
          // 如果组已展开，添加匹配的子指令
          if (expandedGroups.value.has(cmd.handler_full_name)) {
            const subsToShow = query ? matchingSubCmds : (cmd.sub_commands || []);
            for (const sub of subsToShow) {
              if (sub.has_conflict) {
                conflictCmds.push(sub);
              } else {
                normalCmds.push(sub);
              }
            }
          }
        }
      } else if (cmd.type !== 'sub_command') {
        // 普通指令（子指令通过组处理）
        if (matchesFilters(cmd, query)) {
          if (cmd.has_conflict) {
            conflictCmds.push(cmd);
          } else {
            normalCmds.push(cmd);
          }
        }
      }
    }

    // 按 effective_command 排序冲突指令，使其分组在一起
    conflictCmds.sort((a, b) => (a.effective_command || '').localeCompare(b.effective_command || ''));

    return [...conflictCmds, ...normalCmds];
  });

  /**
   * 切换指令组的展开/折叠状态
   */
  const toggleGroupExpand = (cmd: CommandItem) => {
    if (!cmd.is_group) return;
    if (expandedGroups.value.has(cmd.handler_full_name)) {
      expandedGroups.value.delete(cmd.handler_full_name);
    } else {
      expandedGroups.value.add(cmd.handler_full_name);
    }
  };

  /**
   * 检查指令组是否已展开
   */
  const isGroupExpanded = (cmd: CommandItem): boolean => {
    return expandedGroups.value.has(cmd.handler_full_name);
  };

  return {
    // 状态
    searchQuery,
    pluginFilter,
    permissionFilter,
    statusFilter,
    typeFilter,
    showSystemPlugins,
    expandedGroups,
    
    // 计算属性
    hasSystemPluginConflict,
    effectiveShowSystemPlugins,
    availablePlugins,
    filteredCommands,
    
    // 方法
    matchesFilters,
    toggleGroupExpand,
    isGroupExpanded
  };
}

