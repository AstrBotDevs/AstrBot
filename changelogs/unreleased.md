# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.
- Gemini Embedding now conditions query and document embeddings separately (`task_type` for `gemini-embedding-001`, text prefixes for `gemini-embedding-2`), and FAISS vectors are L2-normalized on write and search so `1 - distance / 2` is a real cosine score. Previously both sides used the same encoding and unnormalized vectors made similarity scores drift with text length, so no fixed threshold could separate relevant from irrelevant memories. Existing indexes are re-normalized once on load.
