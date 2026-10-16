# Unreleased

- Fix welcome-page computer access setup failing to save when Local isolation is unavailable. Apply legacy role permissions at tool execution instead: workspace files without code execution for members, and entire-environment execution for administrators. Remove the permission matrix’s bottom-left isolation setup link; setup instructions remain in the Agent sandbox documentation.

- Restore workspace-scoped Local file reading, writing, and editing on Windows using Python standard-library native handle bindings. Reject reparse points and hardlink aliases without reopening checked files by path. Use platform-independent defaults: workspace files without execution for members, and entire-environment execution with networking for administrators. Preserve usable explicit policies when isolation is unavailable, and enable the Windows workspace option in the permission matrix.
