import assert from "node:assert/strict";
import test from "node:test";

import {
  getDragSessionIds,
  getProjectDragPayload,
  toggleExpandedProject,
  shouldSuppressClickAfterLongPress,
  toggleSessionSelection,
} from "../src/utils/sessionManagement.mjs";

test("toggleSessionSelection selects and deselects one session", () => {
  assert.deepEqual(toggleSessionSelection([], "s1"), ["s1"]);
  assert.deepEqual(toggleSessionSelection(["s1", "s2"], "s1"), ["s2"]);
});

test("getDragSessionIds drags selected sessions when dragging a selected item", () => {
  assert.deepEqual(getDragSessionIds("s1", ["s1", "s2"]), ["s1", "s2"]);
});

test("getDragSessionIds drags only the source when it is not selected", () => {
  assert.deepEqual(getDragSessionIds("s3", ["s1", "s2"]), ["s3"]);
});

test("shouldSuppressClickAfterLongPress consumes only the first post-long-press click", () => {
  assert.deepEqual(shouldSuppressClickAfterLongPress(true), {
    suppress: true,
    nextSuppressState: false,
  });
  assert.deepEqual(shouldSuppressClickAfterLongPress(false), {
    suppress: false,
    nextSuppressState: false,
  });
});

test("toggleExpandedProject expands one project and collapses it when clicked again", () => {
  assert.equal(toggleExpandedProject(null, "p1"), "p1");
  assert.equal(toggleExpandedProject("p1", "p1"), null);
  assert.equal(toggleExpandedProject("p1", "p2"), "p2");
});

test("getProjectDragPayload marks dragged project sessions with their source project", () => {
  assert.deepEqual(getProjectDragPayload("s1", "p1"), {
    sessionIds: ["s1"],
    sourceProjectId: "p1",
  });
});
