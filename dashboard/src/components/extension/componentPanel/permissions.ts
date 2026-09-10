import type { CommandPermission, PermissionType } from './types';

export const commandPermissionOptions: CommandPermission[] = ['member', 'admin', 'group_admin', 'shared_group_admin'];

export const commandPermissions: Record<PermissionType, { label: string; color: string; hint?: string }> = {
  member: { label: 'permission.everyone', color: 'success' },
  everyone: { label: 'permission.everyone', color: 'success' },
  admin: { label: 'permission.admin', color: 'error', hint: 'permission.adminHint' },
  group_admin: { label: 'permission.groupAdmin', color: 'warning', hint: 'permission.groupAdminHint' },
  shared_group_admin: { label: 'permission.followIsolation', color: 'info', hint: 'permission.followIsolationHint' },
};
