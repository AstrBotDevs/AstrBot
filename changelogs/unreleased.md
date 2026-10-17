# Unreleased

- Fix welcome-page computer access setup failing to save when Local isolation is unavailable. Resolve isolation requirements at tool execution instead. If required isolation is unavailable, disable execution for both roles while preserving their saved file scope; explain the cause in the permission matrix and LLM system/tool messages. Remove the permission matrix’s bottom-left isolation setup link; setup instructions remain in the Agent sandbox documentation.

- Restore workspace-scoped Local file reading, writing, and editing on Windows using Python standard-library native handle bindings. Reject reparse points and hardlink aliases without reopening checked files by path. Use platform-independent defaults: workspace files without execution for members, and entire-environment execution with networking for administrators. Preserve usable explicit policies when isolation is unavailable, and enable the Windows workspace option in the permission matrix.

- Migrate the old Windows member policy with execution, execution networking, and file access disabled to workspace file access once per global configuration or profile. Identical manually disabled policies are also migrated because their origin is not stored. Keep administrator and other member policies unchanged, and preserve later choices to disable file access.
