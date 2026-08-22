# Long-term Memory

AstrBot's long-term memory writes user facts, person profiles, and compact episode summaries from completed conversations, then retrieves relevant data for later requests. The feature is available under **Alkaid Memory / Long-term Memory** in the WebUI and is still experimental.

> [!WARNING]
> The current source initializes long-term memory unconditionally and queues writeback after a local-Agent conversation completes. There is no per-user or per-profile disable switch in the WebUI or profile configuration. Before processing sensitive, regulated, or consent-based data, evaluate this behavior together with database, backup, and log retention.

## What is currently stored

Long-term memory uses several separate record types:

- **Facts**: the current extractor uses explicit Chinese and English patterns for statements such as a name, likes, and dislikes. It does not send the entire conversation to an LLM for unrestricted fact extraction. Duplicate facts are merged with updated evidence and confidence.
- **Profiles**: a short text assembled from active facts for one user in the current isolated chat. A new fact refreshes the profile automatically, and the WebUI can queue a manual refresh.
- **Episodes**: a compact title and summary for completed turns that meet a minimum length. The summary contains truncated user text, assistant text, and extracted facts.
- **Operation logs**: audit records for create, merge, update, soft-delete, restore, and profile-refresh operations, including the operator, reason, and parts of the payload.

These records live in AstrBot's main SQLite database, normally `data/data_v4.db` under the runtime root. `ASTRBOT_ROOT` can relocate that root. Backing up the database also backs up long-term memory. From 4.27.5, schema changes no longer patch an old file; upgrading requires deleting `data/data_v4.db*` and recreating an empty database, so long-term memory is not migrated from the previous file.

## How memory enters model context

Before each local-Agent request, AstrBot retrieves for the current user and message session:

- one person profile;
- up to 3 facts relevant to the request;
- up to 1 relevant episode.

They are added to the request as temporary `<memory_context>` content with an instruction to use them only as internal context and not quote them verbatim. This temporary content is not written back as an ordinary conversation message, but it is sent to the active chat Provider.

When a Persona allows all tools, the Agent also receives these tools automatically:

- `search_memory` searches current-user facts;
- `get_person_profile` reads the current profile;
- `query_episode` searches episode summaries;
- `maintain_memory` previews, soft-deletes, or restores a fact.

These tools are not automatically added when a Persona uses an explicit tool allowlist; select them explicitly if needed. Automatic retrieval and writeback still run without the tools.

## User identity and scope

`person_id` uses the sender ID supplied by the platform adapter when available and falls back to the unified message origin. `chat_id` is the unified message origin (UMO), which carries platform, message-type, and routing identity.

The default scope is `isolated:<chat_id>`: facts, profiles, and episodes are retrieved only inside the same message session. The code supports explicit cross-scope sharing policies, but the current long-term-memory page does not manage them. Normal deployments should not assume memory is shared across groups, direct messages, or platforms.

## Auditing in the WebUI

The current page can:

- filter facts by Person ID, Chat ID, status, or text;
- inspect fact details, source identifiers, confidence, and operation logs;
- soft-delete or restore a fact with an optional reason;
- view profiles and queue profile-refresh tasks;
- inspect recent operations and writeback-queue status.

The page currently shows only an episode count; it does not provide per-episode management. It also has no general fact-create, fact-edit, or permanent-delete button.

## Deletion and privacy boundaries

**Delete** in the WebUI is a soft delete. It changes a fact from `active` to `deleted`, so normal retrieval ignores it, while the database row remains restorable.

Soft-deleting a fact does not automatically remove:

- an already generated profile;
- generated episodes;
- operation logs and their audit payloads;
- copies in existing backups.

You can manually refresh a profile after deleting facts. The current implementation rebuilds a profile only when active facts remain, so deleting the final fact does not hard-delete the old profile. Do not treat WebUI soft deletion as data erasure or a complete right-to-be-forgotten implementation.

Deployments that require permanent erasure, user opt-out, or retention limits must design database-level cleanup, profile and episode coordination, audit-log minimization, and backup expiry before enabling the feature. Stop AstrBot, create a verified backup, and test the cleanup against an isolated copy before any database-level operation.

## Operational guidance

- Tell users what derived conversation data is retained and obtain consent where required.
- Do not send passwords, API keys, identity documents, or other secrets that should never be retained.
- Audit facts, profiles, episode counts, and operation logs regularly instead of checking only Agent response quality.
- Fact extraction and retrieval are currently lightweight rules and text matching, so memories can be missed, misclassified, or become stale. Do not rely on memory alone for important decisions.
- A [Persona](./persona) defines role and permissions; long-term memory is stored by user and message session. They are separate data sets.
