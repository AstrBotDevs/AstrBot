## 1. Baseline and measurement harness

- [x] 1.1 Freeze the implementation and dependency baseline, create a separate read-only v4.28.1 reproduction environment for issues #10089 and #10092, and verify both environments report their commit and dependency versions.
- [x] 1.2 Add an external-process image benchmark harness that records stage timings, RSS high-water marks, Python allocation diagnostics, child-process memory, request JSON bytes, media bytes, temporary files, and failures without printing image data or secrets.
- [x] 1.3 Generate deterministic PNG, JPEG, WebP, GIF, and screenshot fixtures with ordinary and high-entropy cases, record hashes and metadata, and verify the fixture generator is outside the measured child process.
- [ ] 1.4 Implement the eight-factor ablation runner for unified-source preparation, lazy history loading, and compression optimization; verify paired seeds, cold/warm runs, ten repetitions, and raw JSONL/CSV output.

## 2. Unified preparation and encoded-byte limits

- [x] 2.1 Define the internal image preparation descriptor and one preparation entry point for platform attachments, quoted images, plugins/MCP, file tools, and CUA screenshots; verify every listed source reaches it with source ownership and cleanup metadata.
- [x] 2.2 Extend image preparation with an encoded payload byte limit independent from pixel dimensions; verify a pixel-compliant high-entropy PNG is re-encoded or rejected instead of passed through.
- [x] 2.3 Implement candidate-size measurement without retaining all candidate bytes and preserve transparency, EXIF orientation, CUA dimensions, animation behavior, and already-compliant bytes; verify format-specific fixtures and coordinate/visual checks.
- [x] 2.4 Add typed, readable image-size and resource errors and ensure oversize input is not silently returned to the Provider or retried through unrelated fallback providers; verify #10089's request-size scenario.
- [x] 2.5 Add cancellation, timeout, decode failure, and write failure cleanup tests; verify temporary files, image-library resources, and worker tasks are released on every path.

## 3. Durable media references and lazy materialization

- [x] 3.1 Add versioned durable media objects under the configured data directory with content-hash deduplication, atomic write/verify, MIME/dimension/byte/detail metadata, and conversation-scoped access checks; verify partial writes never create usable references.
- [x] 3.2 Add a persisted image-reference representation and dual history reader for new references plus existing inline data URIs/base64; verify old histories remain readable and new histories do not embed complete base64.
- [x] 3.3 Resolve selected references only after context selection and materialize them into a request-local provider view; verify out-of-window images are not opened/decoded/encoded and B-only provider-visible bytes, order, detail, and placement match baseline.
- [x] 3.4 Keep durable media outside temporary cleanup and add missing-media, restart, unauthorized-reference, session-delete, and cross-session shared-media tests; verify missing media produces a bounded recovery result without exposing paths.
- [x] 3.5 Add explicit dry-run migration/export/repair behavior for old inline histories with backup and hash verification; verify ordinary reads never rewrite history and rollback remains possible.

## 4. Context and persistence integration

- [x] 4.1 Integrate image byte validation with the active request and summarization-provider paths without adding image eviction or changing existing truncation/summary semantics; verify image-capable summaries receive selected images and the main request receives its selected context.
- [x] 4.2 Ensure history saving persists references rather than request-time data URIs while provider adapters continue receiving their existing wire shapes; verify plugin, tool, built-in Provider, WebUI detail, and export compatibility.
- [x] 4.3 Separate 413 request-size, image-too-large, missing-media, and MemoryError handling; verify MemoryError preserves its type and does not trigger repeated oversized fallback requests.

## 5. Verification and rollout

- [ ] 5.1 Run the full matrix across single image, eight images, 50-round history, 200 fixed-window requests, four-session concurrency, restart, WebUI preview, and error workloads; verify all metrics and raw failures are retained.
- [ ] 5.2 Compare A/B/C main and marginal effects with image-count/order/content invariants; verify memory gains are not caused by silently omitting active images.
- [ ] 5.3 Validate Linux/WSL and native Windows memory behavior, run macOS functional regression, and verify normal small-image latency/peak-memory regression stays within the documented target.
- [x] 5.4 Run `ruff format --check .`, `ruff check .`, focused image/context/history tests, and the relevant full test suites; verify no source comments/logs violate repository language rules.
- [ ] 5.5 Review migration backup/rollback and media cleanup behavior, document measured results in test artifacts outside repository SUMMARY files, and only then enable new reference writes by default.
