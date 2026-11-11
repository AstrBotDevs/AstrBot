# fish-api

大肥鱼鱼咖 **客户账号与业务 API**（FastAPI）。

产品与接口规划见仓库根目录 **[技术方案.md](../技术方案.md)**。

```bash
cp -n .env.example .env
uv sync
uv run alembic upgrade head   # optional; app startup also migrates
uv run uvicorn app.main:app --reload --port 8800
```

→ http://127.0.0.1:8800/docs

### Database (SQLAlchemy + Alembic)

Migrations live under `alembic/` (service root, not under `app/`). Models: `app/models/*`, metadata: `app.db.engine.Base`.

| Command | Purpose |
|--------|---------|
| `uv run alembic upgrade head` | Apply pending migrations |
| `uv run alembic revision --autogenerate -m "describe change"` | New migration from model diff |
| `uv run alembic current` | Show revision |
| `uv run alembic history` | List revisions |

### Admin desk (fish-console)

Set `FISH_ADMIN_EMAILS` to your login email(s). After login, sidebar shows **鱼咖收银台** (`/admin/orders`) to confirm Alipay top-ups.

**QA: adjust a user's rice bowl** (admin JWT from fish-console login):

```bash
# Look up
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://127.0.0.1:8800/api/v1/admin/wallets/by-email?email=1597006376@qq.com"

# Set bowl to 0g and disable bound AstrBot bot (default)
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"1597006376@qq.com","balance_rice_g":0}' \
  http://127.0.0.1:8800/api/v1/admin/wallets/adjust

# Restore: balance > 0 clears small arrears from balance, then re-enables bot
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"1597006376@qq.com","balance_rice_g":500,"arrears_rice_g":0}' \
  http://127.0.0.1:8800/api/v1/admin/wallets/adjust

# Simulate “negative rice”: 0g balance + 100g 欠饭 (arrears), not a negative balance column
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"email":"1597006376@qq.com","balance_rice_g":-100}' \
  http://127.0.0.1:8800/api/v1/admin/wallets/adjust
```

Fresh install: `upgrade head` creates all tables.  
If you already had `data/fish.db` from before Alembic, first app start will **stamp** the matching revision and run only deltas (e.g. missing columns).  
To reset dev data: `rm data/fish.db` then `uv run alembic upgrade head`.
