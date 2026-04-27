import assert from "node:assert/strict";
import test from "node:test";

import {
  configureSessionDrag,
  getDragSessionIds,
  getProjectDragPayload,
  moveSessionIdsBefore,
  toggleExpandedProjectIds,
  shouldSuppressClickAfterLongPress,
  toggleSessionSelection,
} from "../src/utils/sessionManagement.mjs";

test("configureSessionDrag writes session ids and move effect", () => {
  const writes = new Map();
  const event = {
    dataTransfer: {
      effectAllowed: "",
      setData(type, value) {
        writes.set(type, value);
      },
    },
  };

  configureSessionDrag(event, ["s1", "s2"]);

  assert.equal(
    writes.get("application/x-astrbot-session-ids"),
    JSON.stringify(["s1", "s2"]),
  );
  assert.equal(event.dataTransfer.effectAllowed, "move");
});

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

test("toggleExpandedProjectIds supports multiple expanded projects", () => {
  assert.deepEqual(toggleExpandedProjectIds([], "p1"), ["p1"]);
  assert.deepEqual(toggleExpandedProjectIds(["p1"], "p2"), ["p1", "p2"]);
  assert.deepEqual(toggleExpandedProjectIds(["p1", "p2"], "p1"), ["p2"]);
});

test("getProjectDragPayload marks dragged project sessions with their source project", () => {
  assert.deepEqual(getProjectDragPayload("s1", "p1"), {
    sessionIds: ["s1"],
    sourceProjectId: "p1",
  });
});

test("getProjectDragPayload drags selected project sessions together", () => {
  assert.deepEqual(getProjectDragPayload("s1", "p1", ["s1", "s2"]), {
    sessionIds: ["s1", "s2"],
    sourceProjectId: "p1",
  });
});

test("moveSessionIdsBefore moves one or more sessions before a target", () => {
  assert.deepEqual(moveSessionIdsBefore(["s1", "s2", "s3"], ["s3"], "s1"), [
    "s3",
    "s1",
    "s2",
  ]);
  assert.deepEqual(
    moveSessionIdsBefore(["s1", "s2", "s3", "s4"], ["s2", "s4"], "s1"),
    ["s2", "s4", "s1", "s3"],
  );
});
