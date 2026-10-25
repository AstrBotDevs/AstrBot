# Unreleased

- Fetch Lark group metadata before creating inbound events, using the same one-hour success cache, five-minute failure cache, bounded size and lookup timeout as QQ Official. Automatic enrichment requests only group details; explicit `event.get_group()` continues to fetch member lists while sharing the metadata cache.

- Fetch QQ Official group names before creating inbound events in both WebSocket and Webhook adapters. Share a bounded per-bot cache with `event.get_group()`, caching successful names for one hour and failed or empty lookups for five minutes, coalescing concurrent requests and limiting each lookup to three seconds.

- Record sender IDs and names per UMO on awakened messages and include them in backups. Administrator IDs now use the dedicated `_special: sender_id` selector with nickname search, platform labels and direct ID addition when no search results match; values remain raw sender IDs. Old entry: Add More → Edit List Items. New entry: Select users (button and dialog).

- Unify bot session bindings, whitelist settings (`_special: umo`), conversation filters, custom rules/groups and future-task session choices in a shared session-selection dialog. Replace scattered dropdowns, generic list editors and group transfer lists with Select session sources (previously Select sessions); rename Known sessions to Recorded session sources and explain UMO below the dialog title; retain parent-page saving and advanced wildcard-rule editing. Bot bindings restrict results to the exact platform instance via the `platformId` prop and API filter. Future-task No delivery target filtering is a separate checkbox.
