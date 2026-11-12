# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.

- Add an optional cleanup checkbox to the single and batch conversation deletion dialogs in Data & Logs → Conversations. When selected, alias and sender metadata is removed only for sessions with no remaining conversations; off by default, and metadata is retained while other conversations still reference the session. Expose the same choice through `cleanup_metadata` on the delete APIs.
