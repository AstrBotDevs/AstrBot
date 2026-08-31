# AstrBot documentation

This directory contains the documentation sources for the current
[Xero-Team/AstrBot](https://github.com/Xero-Team/AstrBot) branch. When this
fork differs from upstream tutorials, the code, configuration defaults, API
specification, and deployment files in this repository are authoritative.

- Chinese sources: `docs/zh/`
- English sources: `docs/en/`
- Site navigation and theme: `docs/.vitepress/`
- Published developer OpenAPI document: `docs/public/openapi.json`

## Local preview

The pinned pnpm version is declared in `docs/package.json`. Use the globally
installed pnpm command so the
same toolchain is used locally and in CI.

```bash
cd docs
pnpm install --frozen-lockfile
pnpm run docs:dev
```

Build the production site with:

```bash
cd docs
pnpm run docs:build
```

Do not edit `docs/.vitepress/dist/`; it is generated and ignored. When a
backend route or OpenAPI schema changes, regenerate the published API document
from the repository root:

```bash
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

The formatting step uses the root repository tooling installed by
`make bootstrap` or `npm ci`.

User-facing changes should update both language trees when an equivalent page
exists. Keep internal links extensionless so VitePress validates them during
the production build.

The production Dashboard serves this site at `/help/`. `make build-docs` and
`make run` set `ASTRBOT_DOCS_BASE=/help/` and copy the VitePress build into the
WebUI `help/` directory. `make docs` / `pnpm run docs:dev` is a standalone
preview with base `/`. This fork does not operate a user-support queue;
development Issues track defects and features, not deployment support.
