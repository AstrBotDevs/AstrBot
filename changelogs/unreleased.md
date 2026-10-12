# Unreleased

## Logs

- Add structured source, plugin, platform, and category metadata for in-memory log filtering.
- Logs: top-row filters → the Filters sidebar, with combined level/source/plugin/platform/keyword filtering and an option to hide user-chat logs.
- Core source label → System; plugin selectors prefer display names and show IDs as subtitles.
- Auto-scroll switch → automatic bottom following, preserving the reading position when viewing older logs.
- Add 8–16px font controls (12px default, 2px steps) alongside fullscreen and Pip installation.

## Trace

- Expand message traces to include plugin handlers and their categories, event hooks, Agent requests, response outlines, and completion status.
- Trace table with expandable message rows → full-width tracing list with an opt-in execution timeline inspector. Columns: status chip, platform logo, timestamp, live duration, message, UMO, sender, and Spans.
- Add a Filters sidebar with combinable Has errors / Has model calls / Has plugin calls conditions; counts refer to message traces, not internal steps.
- Prefer session aliases and plugin display names with hover details; show platform/plugin logos and lazily load handler descriptions from plugin details.
- Collapse consecutive same-type timeline nodes with stacked icons and visible error counts.
- Record only the final streaming-response summary, excluding adapter chunks and protocol closing frames while retaining independent tool/plugin replies.
- Keep the existing in-memory trace storage; no new database persistence.
- Show execution mode, plugin names, and response ownership as timeline chips. Reuse profile runner labels and classify built-in Agent replies as system/core while preserving plugin senders.
- Remove the outer gray trace card and tinted list shell, using a flat tab layout with toolbar/table separators in both themes.
- Top hint and separate recording switch → a toolbar Start/Pause/Connecting button. Filters, recording, and refresh share gray icon-and-text styling and 36px input height; search fills available width and includes the message count in its placeholder.
- Use Vuetify datatable with native rows, typography, spacing, and hover styling for the trace list; customize individual cells while retaining fixed headers, stable trace row IDs, keyboard activation, and explicit detail selection without adding pagination or automatic selection.
- Shorten the Chinese duration column label and prevent the platform column header from wrapping with a minimum width.
