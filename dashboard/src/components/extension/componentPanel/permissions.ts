import type { CommandPermission, PermissionType } from './types';

export const commandPermissionOptions: CommandPermission[] = ['member', 'admin', 'group_admin'];

export const commandPermissions = {
  member: { label: 'permission.everyone', color: 'success' },
  everyone: { label: 'permission.everyone', color: 'success' },
  admin: { label: 'permission.admin', color: 'error' },
  group_admin: { label: 'permission.groupAdmin', color: 'warning' },
} satisfies Record<PermissionType, { label: string; color: string }>;
