NEO_FILE_PATH_PROMPT = (
    "\n[Shipyard Neo File Path Rule]\n"
    "When using sandbox filesystem tools (upload/download/read/write/list/delete), "
    "always pass paths relative to the sandbox workspace root. "
    "Example: use `baidu_homepage.png` instead of `/workspace/baidu_homepage.png`.\n"
)

NEO_SKILL_LIFECYCLE_PROMPT = (
    "\n[Neo Skill Lifecycle Workflow]\n"
    "When user asks to create/update a reusable skill in Neo mode, use lifecycle tools instead of directly writing local skill folders.\n"
    "Preferred sequence:\n"
    "1) Use `astrbot_create_skill_payload` to store canonical payload content and get `payload_ref`.\n"
    "2) Use `astrbot_create_skill_candidate` with `skill_key` + `source_execution_ids` (and optional `payload_ref`) to create a candidate.\n"
    "3) Use `astrbot_promote_skill_candidate` to release: `stage=canary` for trial; `stage=stable` for production.\n"
    "For stable release, set `sync_to_local=true` to sync `payload.skill_markdown` into local `SKILL.md`.\n"
    "Do not treat ad-hoc generated files as reusable Neo skills unless they are captured via payload/candidate/release.\n"
    "To update an existing skill, create a new payload/candidate and promote a new release version; avoid patching old local folders directly.\n"
)
