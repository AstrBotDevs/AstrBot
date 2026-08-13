/** Shared tool data returned by the Dashboard API. */
export interface ToolParameter {
  type?: string;
  description?: string;
}

export interface ToolConfigCondition {
  key: string;
  operator: 'truthy' | 'equals' | 'in' | 'custom' | string;
  expected?: unknown;
  actual?: unknown;
  matched: boolean;
  message?: string | null;
}

export interface BuiltinToolConfigTag {
  conf_id: string;
  conf_name: string;
  enabled: boolean;
  matched_conditions: ToolConfigCondition[];
  failed_conditions: ToolConfigCondition[];
}

export interface ToolItem {
  name: string;
  description: string;
  active: boolean;
  readonly?: boolean;
  parameters?: {
    properties?: Record<string, ToolParameter>;
  };
  origin?: string;
  origin_name?: string;
  builtin_config_statuses?: BuiltinToolConfigTag[];
  builtin_config_tags?: BuiltinToolConfigTag[];
  tool_id?: string;
  parallel_policy?: 'unknown' | 'safe' | 'serial' | 'blocked';
  parallel_eligible?: boolean;
  parallel_blocked_reason?: string | null;
  parallel_enabled?: boolean;
  parallel_execution_enabled?: boolean;
  parallel_max_calls?: number;
  parallel_mcp_max_concurrency?: number;
}
