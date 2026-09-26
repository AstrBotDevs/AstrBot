export type SandboxRecord = {
  sandbox_id: string
  sandbox_name?: string
  provider?: string
  managed?: boolean
  created_by_astrbot?: boolean
  is_default?: boolean
  owner_session_id?: string | null
  controller_session_id?: string | null
  lease_expires_at?: number | null
  last_used_at?: number | null
  idle_timeout?: number | null
  idle_cleanup_at?: number | null
  expires_at?: number | null
  retention_policy?: string | null
  status?: string
  connect_info?: Record<string, unknown>
  capabilities?: string[]
  tool_names?: string[]
}

export type LoadSandboxesResult = {
  ok: boolean
  records: SandboxRecord[]
  error?: string
}

export type ProviderOption = {
  title: string
  value: string
}

export type SandboxProviderInfo = {
  provider_id: string
}

export type SandboxAction =
  | 'setDefault'
  | 'configure'
  | 'console'
  | 'release'
  | 'screenshot'
  | 'destroy'

export type ConsoleHistoryEntry = {
  id: number
  cwd: string
  command: string
  stdout: string
  stderr: string
  exitCode: unknown
  running?: boolean
}
