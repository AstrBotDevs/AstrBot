# Unreleased

- Retain traces only for Agent invocations or delivered command responses. Buffer bounded candidate snapshots until admission instead of persisting or publishing ordinary messages, then discard unqualified events on completion. Recognize direct Agent runners through their shared lifecycle hook without adding timeline nodes or rewriting existing history.

- Expose Enable Trace Recording under Settings → General → Logs, backed by the same trace_enable setting as the trace toolbar's start/pause button.

- Stop recording redundant plugin handler module metadata without rewriting or filtering historical data.

- Remove response-source bookkeeping and System/Plugin sender chips. Record successful proactive sends in Context.send_message rather than the send-message tool, correlate them with the active event, and deduplicate nested event forwarding. Preserve final-only streaming summaries and independent tool deliveries; do not create traces for unscoped sends or rewrite historical data.

- Remove the execution-mode prefix from Agent chips, retaining only the configured runner's display name.

- Prefix Agent model, persona, and tool-call chips with box, heart, and wrench icons; use a consistent 5px icon-to-label gap for trace metadata chips, including plugin names.

- Add a puzzle icon before plugin names in grouped and individual trace plugin chips, retaining timeline plugin logos.

- Add model and persona ID chips to Agent execution headings, show provider IDs on model hover, and count actual tool calls separately for each Agent while folded or expanded.

- Record successful send_message_to_user deliveries as response events on the originating trace, including message-chain outlines and destination UMO. Do not record failed sends as delivered responses; leave cron Agent instrumentation unchanged.

- Present trace-detail UMO and sender on separate icon-and-value rows instead of a dot-separated line, preserving UMO alias tooltips.

- Use native system fonts throughout trace text and tooltips instead of Outfit, without changing text sizing or icon fonts. Change running status chips and detail badges from amber to blue.

- Include month and day in trace timestamps (MM-DD HH:mm:ss.SSS), including detail timestamps and timeline tooltips.

- Add independent Group chat / Private chat chips to the trace Type column, using summary message types with a legacy UMO fallback and leaving unknown types unlabeled.

- Reduce trace table header height to 40px using Vuetify's native header-height variable; preserve body row and pager sizing.

- Show the Tokens card total with two-decimal k/M notation while keeping precise counts in its tooltip.

- Add an Agent-only Tokens statistics card with input/output/cache breakdown, latest-snapshot deduplication, and an unavailable-state placeholder instead of a misleading zero.

- Add Type before UMO in the trace table, with independent blue Agent and green Command chips. Persist command flags in summaries and derive legacy flags for the current page; use explicit colors because the generic Vuetify color pack is disabled.

- Use flat status chips in the trace table and narrow the platform column to 80px, retaining a non-wrapping header.

- Set trace table header and cell text to 13px without changing timeline text or table density.

- Load more → Vuetify server-side datatable pagination: support page navigation and 25/50/100 rows, reset on search/filter changes, and retain only the current page. Keep first-page live refresh without inserting into historical pages. Remove borders from the three trace statistics blocks while retaining their subtle backgrounds.

- Remove persisted trace action/end-action and redundant duration attributes. Keep transition matching internal, set call kinds explicitly, retain handler types, and derive UI call completion and durations from canonical span timestamps/status. Preserve reads of legacy history.

- Hide the redundant AdapterMessageEvent type label on plugin listener nodes; keep handler names, category chips, and hook event types.

- Remove the standalone Select persona trace node and include its resolved persona ID in Agent request prepared details. Fold long trace titles and received/sent text previews with explicit expansion, without truncating recorded content.

- Log & Cache Cleanup → Log, Cache & Trace Cleanup: include trace database/sidecar usage, add Clear Trace Data, and include finished trace history in Clean All. Confirm irreversible removal, retain running traces, and compact through the existing database writer without unlinking live database files.

## Logs

- Add structured source, plugin, platform, and category metadata for in-memory log filtering.
- Logs: top-row filters → the Filters sidebar, with combined level/source/plugin/platform/keyword filtering and an option to hide user-chat logs.
- Core source label → System; plugin selectors prefer display names and show IDs as subtitles.
- Auto-scroll switch → automatic bottom following, preserving the reading position when viewing older logs.
- Add 8–16px font controls (12px default, 2px steps) alongside fullscreen and Pip installation.

## Trace

- Finish message and Cron traces through the shared event execution lifecycle, after awaited processing, delivery, and history saving. Close failures and cancellations without swallowing them; preserve the existing root completion signal.

- Plugin handler triggered → Call plugin: compact the trace timeline with short titles, neutral category/metadata chips, platform IDs on a secondary line, relative times with exact timestamps on hover, and a consistent heading/chevron interaction instead of repeated View details rows.
- Start Agent → Agent execution: collapse descendants using actual span ancestry, retain responses on the main line and error indicators on collapsed headers, and preserve chronological ordering for concurrent/interleaved branches. Folding does not alter trace/span/call counts.

- Expose SQLite trace settings under Settings → General → Logs, replacing the obsolete JSONL settings whitelist.
- Remove the per-field 4 KB text truncation limit for trace attributes while retaining whole-trace, writer-queue, and storage budgets.

- Expand message traces to include plugin handlers and their categories, event hooks, Agent requests, response outlines, and completion status.
- Trace table with expandable message rows → full-width tracing list with an opt-in execution timeline inspector. Columns: status chip, platform logo, timestamp, live duration, message, UMO, sender, and Spans.
- Add a Filters sidebar with combinable Has errors / Has model calls / Has plugin calls conditions; counts refer to message traces, not internal steps.
- Prefer session aliases and plugin display names with hover details; show platform/plugin logos and lazily load handler descriptions from plugin details.
- Collapse consecutive same-type timeline nodes with stacked icons and visible error counts.
- Record only the final streaming-response summary, excluding adapter chunks and protocol closing frames while retaining independent tool/plugin replies.
- Replace the in-memory trace record cache and JSONL sink with dedicated SQLite history at `data/logs/traces.db`, using bounded asynchronous writes, whole-trace retention, and a default 80 MB capacity target / 7-day retention. Preserve legacy files without importing or appending them.
- Align trace/span IDs, parent relationships, timestamps, status, attributes, and events with the OpenTelemetry core model, and correlate structured logs with the active trace/span context. This does not add an OTel SDK, OTLP transport, or external export.
- Migrate `trace_log_enable/path/max_mb` to `trace_db_path/max_mb` and `trace_retention_days`; keep `trace_enable`. New database settings take precedence. Protect SQLite files and sidecars from log cleanup.
- Show execution mode, plugin names, and response ownership as timeline chips. Reuse profile runner labels and classify built-in Agent replies as system/core while preserving plugin senders.
- Remove the outer gray trace card and tinted list shell, using a flat tab layout with toolbar/table separators in both themes.
- Top hint and separate recording switch → a toolbar Start/Pause/Connecting button. Filters, recording, and refresh share gray icon-and-text styling and 36px input height; search fills available width and includes the message count in its placeholder.
- Use Vuetify datatable with native rows, typography, spacing, and hover styling for the trace list; retain fixed headers, stable trace row IDs, keyboard activation, and explicit detail selection. Read history in keyset pages, cap browser summaries at 300, and lazily fetch only the selected trace's detail. Spans now counts actual spans, excluding events.
- Shorten the Chinese duration column label and prevent the platform column header from wrapping with a minimum width.
