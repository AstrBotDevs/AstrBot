// Author: elecvoid243, 2026-06-22
// One-off test of the formatForLLM algorithm against spec §5.1 + §8.3 #9, #10, #15.
// Run with: node --experimental-strip-types --no-warnings scripts/test-format-for-llm.ts
import { useFileComments, extractLineContext } from "../src/composables/useFileComments.ts";

let passed = 0;
let failed = 0;
const failures: string[] = [];

function check(name: string, cond: boolean, detail: string = ""): void {
  if (cond) {
    passed++;
    console.log(`  PASS: ${name}`);
  } else {
    failed++;
    failures.push(`${name}${detail ? " — " + detail : ""}`);
    console.log(`  FAIL: ${name}${detail ? " — " + detail : ""}`);
  }
}

const SAMPLE = [
  "import os",               // 1
  "import sys",              // 2
  "",                        // 3
  "def main():",             // 4
  "    pass",                // 5
  "",                        // 6
  "if __name__ == '__main__':", // 7
  "    main()",              // 8
].join("\n");

// ============================================================================
console.log("\n=== extractLineContext (helper, used by addComment) ===");
// ============================================================================
{
  const ctx = extractLineContext(SAMPLE, 4);
  check("extractLineContext: line 4", ctx?.lineContent === "def main():");
  check("extractLineContext: contextBefore = line 3", ctx?.contextBefore === "");
  check("extractLineContext: contextAfter = line 5", ctx?.contextAfter === "    pass");
}
{
  const ctx = extractLineContext(SAMPLE, 1);
  check("extractLineContext: line 1 (no before)", ctx?.contextBefore === null);
  check("extractLineContext: line 1 (after = line 2)", ctx?.contextAfter === "import sys");
}
{
  const ctx = extractLineContext(SAMPLE, 99);
  check("extractLineContext: out of range returns null", ctx === null);
}

// ============================================================================
console.log("\n=== formatForLLM — #15: only comments, no userText ===");
// ============================================================================
{
  const store = useFileComments();
  store.registerFileContent("/repo/main.py", SAMPLE);
  store.addComment({ filePath: "/repo/main.py", line: 4, text: "rename to entrypoint" });
  const out = store.formatForLLM();
  check("formatForLLM: non-empty when only comments", out.length > 0);
  check("formatForLLM: starts with [File review comments] header", out.startsWith("[File review comments]"));
  check("formatForLLM: contains 'main.py line 4:'", out.includes("`/repo/main.py` line 4:"));
  check("formatForLLM: contains 'rename to entrypoint'", out.includes("rename to entrypoint"));
  check("formatForLLM: uses 4-backtick fence", out.includes("````"));
  check("formatForLLM: uses '>' marker for commented line", /  >\s+\d+ │ def main\(\):/.test(out));
  console.log("  --- output ---");
  console.log(out.split("\n").map((l) => "  | " + l).join("\n"));
  console.log("  --- end ---");
}

// ============================================================================
console.log("\n=== formatForLLM — empty state ===");
// ============================================================================
{
  const store = useFileComments();
  check("formatForLLM: empty store returns empty string", store.formatForLLM() === "");
  store.registerFileContent("/x.py", "a\nb");
  check("formatForLLM: cache loaded but no comments returns empty string", store.formatForLLM() === "");
}

// ============================================================================
console.log("\n=== formatForLLM — #9: adjacent comments (line 100 + 102, gap 2) merge ===");
// ============================================================================
{
  const store = useFileComments();
  const lines = Array.from({ length: 110 }, (_, i) => `line${i + 1}`).join("\n");
  store.registerFileContent("/repo/big.py", lines);
  store.addComment({ filePath: "/repo/big.py", line: 100, text: "first comment" });
  store.addComment({ filePath: "/repo/big.py", line: 102, text: "second comment" });
  const out = store.formatForLLM();
  check("adjacent merge: contains 'lines 100-102:' header", out.includes("`/repo/big.py` lines 100-102:"));
  check("adjacent merge: NOT a single-line header", !out.includes("`/repo/big.py` line 100:"));
  check("adjacent merge: contains 'first comment'", out.includes("first comment"));
  check("adjacent merge: contains 'second comment'", out.includes("second comment"));
  check("adjacent merge: exactly one 4-backtick block (single window)", (out.match(/````/g) ?? []).length === 2);
  console.log("  --- output ---");
  console.log(out.split("\n").map((l) => "  | " + l).join("\n"));
  console.log("  --- end ---");
}

// ============================================================================
console.log("\n=== formatForLLM — #10: far-apart comments (line 100 + 110, gap 10) separate ===");
// ============================================================================
{
  const store = useFileComments();
  const lines = Array.from({ length: 120 }, (_, i) => `line${i + 1}`).join("\n");
  store.registerFileContent("/repo/big.py", lines);
  store.addComment({ filePath: "/repo/big.py", line: 100, text: "comment A" });
  store.addComment({ filePath: "/repo/big.py", line: 110, text: "comment B" });
  const out = store.formatForLLM();
  check("separate blocks: 'line 100:' present", out.includes("`/repo/big.py` line 100:"));
  check("separate blocks: 'line 110:' present", out.includes("`/repo/big.py` line 110:"));
  check("separate blocks: NOT a merged header", !out.includes("`/repo/big.py` lines 100-110:"));
  check("separate blocks: exactly two 4-backtick fences", (out.match(/````/g) ?? []).length === 4);
  check("separate blocks: 'comment A' present", out.includes("comment A"));
  check("separate blocks: 'comment B' present", out.includes("comment B"));
}

// ============================================================================
console.log("\n=== formatForLLM — #15: totalCount used by sendCurrentMessage guard ===");
// ============================================================================
{
  const store = useFileComments();
  check("totalCount: 0 when no comments", store.totalCount.value === 0);
  store.registerFileContent("/x.py", "a");
  store.addComment({ filePath: "/x.py", line: 1, text: "hi" });
  check("totalCount: 1 after one comment", store.totalCount.value === 1);
  store.addComment({ filePath: "/x.py", line: 1, text: "another on same line" });
  check("totalCount: 2 after two comments (even on same line)", store.totalCount.value === 2);
  // delete — capture ids before mutation because commentsForFile is reactive
  const c1 = store.findCommentById("__nope__");  // sanity: returns null
  check("findCommentById returns null for missing id", c1 === null);
  const allComments = store.commentsForFile("/x.py");
  const id1 = allComments[0].id;
  const id2 = allComments[1].id;
  store.deleteComment(id1);
  check("totalCount: 1 after delete", store.totalCount.value === 1);
  store.deleteComment(id2);
  check("totalCount: 0 after deleting all", store.totalCount.value === 0);
  check("findCommentById returns null after delete", store.findCommentById(id1) === null);
}

// ============================================================================
console.log("\n=== addComment returns null when cache empty (invariant) ===");
// ============================================================================
{
  const store = useFileComments();
  // No registerFileContent → cache empty
  const result = store.addComment({ filePath: "/missing.py", line: 1, text: "x" });
  check("addComment returns null when cache is empty", result === null);
  check("totalCount stays 0 when addComment returns null", store.totalCount.value === 0);
}

// ============================================================================
console.log("\n=== resetForSession (clears comments, preserves contentCache) ===");
// ============================================================================
{
  const store = useFileComments();
  store.registerFileContent("/x.py", "a\nb\nc");
  store.addComment({ filePath: "/x.py", line: 1, text: "first" });
  check("pre-reset: totalCount = 1", store.totalCount.value === 1);
  check("pre-reset: contentCache has /x.py", !!store.commentsForFile("/x.py").length);
  // Verify cache is preserved by re-adding (should succeed because cache still there)
  store.resetForSession();
  check("post-reset: totalCount = 0", store.totalCount.value === 0);
  const reAdd = store.addComment({ filePath: "/x.py", line: 1, text: "after reset" });
  check("post-reset: addComment still works (cache preserved)", reAdd !== null);
  check("post-reset: totalCount = 1", store.totalCount.value === 1);
}

// ============================================================================
console.log("\n=== Cross-file: multiple files, comments partition by filePath ===");
// ============================================================================
{
  const store = useFileComments();
  store.registerFileContent("/a.py", "a1\na2");
  store.registerFileContent("/b.py", "b1\nb2\nb3");
  store.addComment({ filePath: "/a.py", line: 1, text: "on a" });
  store.addComment({ filePath: "/b.py", line: 2, text: "on b" });
  check("cross-file: totalCount = 2", store.totalCount.value === 2);
  check("cross-file: /a.py has 1 comment", store.commentsForFile("/a.py").length === 1);
  check("cross-file: /b.py has 1 comment", store.commentsForFile("/b.py").length === 1);
  const out = store.formatForLLM();
  check("cross-file: output contains /a.py header", out.includes("`/a.py` line 1:"));
  check("cross-file: output contains /b.py header", out.includes("`/b.py` line 2:"));
  check("cross-file: output has 2 separate fence blocks", (out.match(/````/g) ?? []).length === 4);
}

// ============================================================================
console.log("\n=== Multi-line comment text ===");
// ============================================================================
{
  const store = useFileComments();
  store.registerFileContent("/x.py", "a\nb\nc");
  const result = store.addComment({ filePath: "/x.py", line: 2, text: "line 1\nline 2\nline 3" });
  check("addComment: multi-line text stored", result?.text === "line 1\nline 2\nline 3");
  const out = store.formatForLLM();
  check("formatForLLM: multi-line text rendered with continuations", out.includes("Comment: line 1") && out.includes("│ line 2") && out.includes("│ line 3"));
}

// ============================================================================
console.log("\n=== Edge: filePath with backticks (no escaping but no crash) ===");
// ============================================================================
{
  const store = useFileComments();
  store.registerFileContent("/path/with`backtick.py", "a");
  const r = store.addComment({ filePath: "/path/with`backtick.py", line: 1, text: "x" });
  check("addComment: filePath with backtick accepted", r !== null);
  const out = store.formatForLLM();
  // Note: backticks in filePath inside a backtick-delimited path in the header
  // will break the markdown. This is a known minor issue; the algorithm
  // doesn't escape, but it doesn't crash either.
  check("formatForLLM: handles weird filePath without crash", out.length > 0);
}

// ============================================================================
console.log(`\n=== SUMMARY: ${passed} passed, ${failed} failed ===`);
if (failed > 0) {
  console.log("\nFailures:");
  for (const f of failures) console.log("  - " + f);
  process.exit(1);
}
