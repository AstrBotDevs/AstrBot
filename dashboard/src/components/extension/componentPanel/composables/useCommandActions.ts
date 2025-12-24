/**
 * 指令操作方法 Composable
 */
import { reactive } from 'vue';
import axios from 'axios';
import type { CommandItem, RenameDialogState, DetailsDialogState, TypeInfo, StatusInfo } from '../types';

export function useCommandActions(
  toast: (message: string, color?: string) => void,
  fetchCommands: () => Promise<void>
) {
  // 重命名对话框状态
  const renameDialog = reactive<RenameDialogState>({
    show: false,
    command: null,
    newName: '',
    aliases: [],
    loading: false
  });

  // 详情对话框状态
  const detailsDialog = reactive<DetailsDialogState>({
    show: false,
    command: null
  });

  /**
   * 切换指令启用/禁用状态
   */
  const toggleCommand = async (
    cmd: CommandItem, 
    successMessage: string, 
    errorMessage: string
  ) => {
    try {
      const res = await axios.post('/api/commands/toggle', {
        handler_full_name: cmd.handler_full_name,
        enabled: !cmd.enabled
      });
      if (res.data.status === 'ok') {
        toast(successMessage, 'success');
        await fetchCommands();
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err: any) {
      toast(err?.message || errorMessage, 'error');
    }
  };

  /**
   * 打开重命名对话框
   */
  const openRenameDialog = (cmd: CommandItem) => {
    renameDialog.command = cmd;
    renameDialog.newName = cmd.current_fragment || '';
    renameDialog.aliases = [...(cmd.aliases || [])];
    renameDialog.show = true;
  };

  /**
   * 确认重命名
   */
  const confirmRename = async (successMessage: string, errorMessage: string) => {
    if (!renameDialog.command || !renameDialog.newName.trim()) return;

    renameDialog.loading = true;
    try {
      const res = await axios.post('/api/commands/rename', {
        handler_full_name: renameDialog.command.handler_full_name,
        new_name: renameDialog.newName.trim(),
        aliases: renameDialog.aliases.filter(a => a.trim())
      });
      if (res.data.status === 'ok') {
        toast(successMessage, 'success');
        renameDialog.show = false;
        await fetchCommands();
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err: any) {
      toast(err?.message || errorMessage, 'error');
    } finally {
      renameDialog.loading = false;
    }
  };

  /**
   * 打开详情对话框
   */
  const openDetailsDialog = (cmd: CommandItem) => {
    detailsDialog.command = cmd;
    detailsDialog.show = true;
  };

  /**
   * 获取类型显示信息
   */
  const getTypeInfo = (type: string, translations: { group: string; subCommand: string; command: string }): TypeInfo => {
    switch (type) {
      case 'group':
        return { text: translations.group, color: 'info', icon: 'mdi-folder-outline' };
      case 'sub_command':
        return { text: translations.subCommand, color: 'secondary', icon: 'mdi-subdirectory-arrow-right' };
      default:
        return { text: translations.command, color: 'primary', icon: 'mdi-console-line' };
    }
  };

  /**
   * 获取权限颜色
   */
  const getPermissionColor = (permission: string): string => {
    switch (permission) {
      case 'admin': return 'error';
      default: return 'success';
    }
  };

  /**
   * 获取权限标签
   */
  const getPermissionLabel = (permission: string, translations: { admin: string; everyone: string }): string => {
    switch (permission) {
      case 'admin': return translations.admin;
      default: return translations.everyone;
    }
  };

  /**
   * 获取状态显示信息
   */
  const getStatusInfo = (
    cmd: CommandItem, 
    translations: { conflict: string; enabled: string; disabled: string }
  ): StatusInfo => {
    if (cmd.has_conflict) {
      return { text: translations.conflict, color: 'warning', variant: 'flat' };
    }
    if (cmd.enabled) {
      return { text: translations.enabled, color: 'success', variant: 'flat' };
    }
    return { text: translations.disabled, color: 'error', variant: 'outlined' };
  };

  /**
   * 获取表格行属性（用于冲突高亮和子指令样式）
   */
  const getRowProps = ({ item }: { item: CommandItem }) => {
    const classes: string[] = [];
    if (item.has_conflict) {
      classes.push('conflict-row');
    }
    if (item.type === 'sub_command') {
      classes.push('sub-command-row');
    }
    if (item.is_group) {
      classes.push('group-row');
    }
    return classes.length > 0 ? { class: classes.join(' ') } : {};
  };

  return {
    // 状态
    renameDialog,
    detailsDialog,
    
    // 方法
    toggleCommand,
    openRenameDialog,
    confirmRename,
    openDetailsDialog,
    getTypeInfo,
    getPermissionColor,
    getPermissionLabel,
    getStatusInfo,
    getRowProps
  };
}

