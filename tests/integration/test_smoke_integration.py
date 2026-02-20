import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_context_bootstrap(integration_context):
    assert integration_context is not None
    assert integration_context.provider_manager is not None
    assert integration_context.platform_manager is not None
