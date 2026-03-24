## 1. Create Stars Directory

- [x] 1.1 Create `astrbot/_internal/stars/` directory
- [x] 1.2 Create `__init__.py` with exports

## 2. Implement RuntimeStatusStar

- [x] 2.1 Create `runtime_status_star.py` with RuntimeStatusStar class
- [x] 2.2 Implement `call_tool` method with tools:
  - `get_runtime_status`: Returns running state and uptime
  - `get_protocol_status`: Returns LSP, MCP, ACP, ABP status
  - `get_star_registry`: Returns registered star names
  - `get_stats`: Returns message counts and metrics

## 3. Register Star with Orchestrator

- [x] 3.1 Import RuntimeStatusStar in orchestrator
- [x] 3.2 Register star instance in orchestrator.__init__

## 4. Write Tests

- [x] 4.1 Create `tests/unit/test_runtime_status_star.py`
- [x] 4.2 Test get_runtime_status tool
- [x] 4.3 Test get_protocol_status tool
- [x] 4.4 Test get_star_registry tool
- [x] 4.5 Test orchestrator auto-registers the star

## 5. Verification

- [x] 5.1 Run ruff check
- [x] 5.2 Run uvx ty check
- [x] 5.3 Run pytest tests/unit/test_runtime_status_star.py
