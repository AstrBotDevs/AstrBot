# Unreleased

- Simplify Context Management Strategy settings: Handling for History Limits or Context Window Pressure → Compression Strategy; Model Provider ID for Context Compression → Compression Model. Move maximum turns, discarded turns, compression instruction, recent-context ratio and fallback context window size under the collapsed More Settings section. Preserve existing configuration keys, defaults and runtime behavior.

- Add SerpApi Google News search with publisher, author, publication time, and WebUI citation support.

- Add compact data-cleanup checkboxes to the existing bot deletion dialog. Custom rules, preferences, configuration routes and scheduled tasks are selected by default; AI conversations, message history, local traces and usage statistics are retained unless selected. Preserve shared resources and match adapter IDs exactly.

- Resolve Lark group-message sender names through the existing user-info lookup, sharing the same per-user cache with private chats (30 minutes for successful names and one minute for failures). Application senders skip user-directory lookups.

- Sort session-source candidates by the latest existing conversation, alias or sender `updated_at`, descending. Deduplicate user suggestions by platform instance and sender ID before applying the result limit, retaining the newest matching record while preserving per-session metadata in storage.

- Fetch Lark group metadata before creating inbound events, using the same one-hour success cache, five-minute failure cache, bounded size and lookup timeout as QQ Official. Automatic enrichment requests only group details; explicit `event.get_group()` continues to fetch member lists while sharing the metadata cache.

- Fetch QQ Official group names before creating inbound events in both WebSocket and Webhook adapters. Share a bounded per-bot cache with `event.get_group()`, caching successful names for one hour and failed or empty lookups for five minutes, coalescing concurrent requests and limiting each lookup to three seconds.

- Add hover copy icon buttons to both user and session-source entries, including selected entries. Hidden copy buttons take no layout space, matching the ChatUI session-list behavior. Copy raw sender IDs or full UMOs without changing selections; support keyboard focus and touch devices.

- Display full UMOs in gray parentheses beside session names, with platform logos and plain bot IDs below. Use the interface font throughout the list. Keep candidate titles on one line and selected titles on at most two lines, ellipsizing long values while exposing the full name and UMO on hover. Add blue group-chat and green private-chat badges using the same colors as Agent/Command badges on the trace page.

- Paginate user suggestions after platform-aware deduplication, with 50 results per page, previous/next controls and selections preserved across pages. Searching and refreshing return to the first page.

- Record sender IDs and names per UMO on awakened messages and include them in backups. Administrator IDs now use the dedicated `_special: sender_id` selector with nickname search, platform labels and direct ID addition when no search results match; values remain raw sender IDs. Old entry: Add More → Edit List Items. New entry: Select users (button and dialog).

- Unify bot session bindings, whitelist settings (`_special: umo`), conversation filters, custom rules/groups and future-task session choices in a shared session-selection dialog. Replace scattered dropdowns, generic list editors and group transfer lists with Select session sources (previously Select sessions); rename Known sessions to Recorded session sources and explain UMO below the dialog title; retain parent-page saving and advanced wildcard-rule editing. Bot bindings restrict results to the exact platform instance via the `platformId` prop and API filter. Future-task No delivery target filtering is a separate checkbox.
