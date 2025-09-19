import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# 导入我们需要测试的函数和相关类
# 注意：由于这是正式的测试文件，我们需要确保导入路径正确
from astrbot.core.pipeline.process_stage.method.llm_request import run_agent
from astrbot.core.message.message_event_result import MessageEventResult, MessageChain
from astrbot.core.message.components import Plain


# 1. 定义模拟对象
class MockAgentRunner:
    """
    模拟 AgentRunner 类，用于测试 run_agent 的行为。
    """

    def __init__(self, fail_times=0, streaming=False):
        self.step_calls = 0
        self.fail_times = fail_times
        self.streaming = streaming
        self._done = False

        self.provider = MagicMock()
        self.provider.get_model.return_value = "test-model"
        mock_provider_meta = MagicMock()
        mock_provider_meta.type = "test-provider-type"
        self.provider.meta.return_value = mock_provider_meta

        self.run_context = MagicMock()
        self.run_context.event = MockEvent()

    async def step(self):
        """
        模拟 agent_runner.step() 方法。
        """
        self.step_calls += 1
        if self.step_calls <= self.fail_times:
            raise ValueError(f"Simulated step failure on call #{self.step_calls}")

        # 如果成功，就标记为完成
        self._done = True
        mock_resp = MagicMock()
        mock_resp.type = "llm_result"
        mock_chain = MessageChain([Plain("Test LLM response")])
        mock_resp.data = {"chain": mock_chain}
        yield mock_resp

    def done(self):
        """
        修改 done() 逻辑：当 step 成功返回时，标记为完成。
        """
        return self._done


class MockEvent:
    """
    简化的模拟 Event 类。
    """

    def __init__(self):
        self.sent_messages = []
        self.final_result = None
        self._is_stopped = False

    async def send(self, message: MessageChain):
        self.sent_messages.append(message)

    def set_result(self, result: MessageEventResult):
        self.final_result = result

    def is_stopped(self):
        return self._is_stopped

    def clear_result(self):
        self.final_result = None

    def get_platform_name(self):
        return "test_platform"


# 2. 编写测试用例


@patch(
    "astrbot.core.pipeline.process_stage.method.llm_request.Metric.upload",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_run_agent_success_on_first_try(mock_metric_upload):
    """
    测试用例 1: 成功执行 (无异常)
    """
    agent_runner = MockAgentRunner(fail_times=0)
    event = agent_runner.run_context.event

    async for _ in run_agent(agent_runner, max_step=1):
        assert event.final_result is not None
        assert event.final_result.result_content_type.name == "LLM_RESULT"

    assert event.final_result is None
    assert agent_runner.step_calls == 1
    mock_metric_upload.assert_called_once()


@patch(
    "astrbot.core.pipeline.process_stage.method.llm_request.Metric.upload",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_run_agent_retry_and_succeed(mock_metric_upload):
    """
    测试用例 2: 重试并最终成功
    """
    agent_runner = MockAgentRunner(fail_times=1)
    event = agent_runner.run_context.event

    async for _ in run_agent(agent_runner, retry_on_failure=1, max_step=1):
        assert event.final_result is not None
        assert event.final_result.result_content_type.name == "LLM_RESULT"
        assert "Test LLM response" in event.final_result.chain[0].text

    assert agent_runner.step_calls == 2
    mock_metric_upload.assert_called_once()


@patch(
    "astrbot.core.pipeline.process_stage.method.llm_request.Metric.upload",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_run_agent_retry_exhausted_with_error_report(mock_metric_upload):
    """
    测试用例 3: 重试耗尽并报告错误
    """
    # 总是失败
    agent_runner = MockAgentRunner(fail_times=10)
    event = agent_runner.run_context.event

    async for _ in run_agent(
        agent_runner, retry_on_failure=1, report_error_message=True, max_step=1
    ):
        pass

    assert agent_runner.step_calls == 2
    assert event.final_result is not None
    assert "AstrBot 请求失败" in event.final_result.chain[0].text


@patch(
    "astrbot.core.pipeline.process_stage.method.llm_request.Metric.upload",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_run_agent_retry_exhausted_with_fallback_response(mock_metric_upload):
    """
    测试用例 4: 重试耗尽并返回备用响应
    """
    agent_runner = MockAgentRunner(fail_times=10)
    fallback_text = "Sorry, I am busy."
    event = agent_runner.run_context.event

    async for _ in run_agent(
        agent_runner,
        retry_on_failure=1,
        report_error_message=False,
        fallback_response=fallback_text,
        max_step=1,
    ):
        pass

    assert agent_runner.step_calls == 2
    assert event.final_result is not None
    assert event.final_result.chain[0].text == fallback_text


@patch(
    "astrbot.core.pipeline.process_stage.method.llm_request.Metric.upload",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_run_agent_retry_exhausted_with_silent_fail(mock_metric_upload):
    """
    测试用例 5: 重试耗尽并静默失败
    """
    agent_runner = MockAgentRunner(fail_times=10)
    event = agent_runner.run_context.event

    async for _ in run_agent(
        agent_runner,
        retry_on_failure=1,
        report_error_message=False,
        fallback_response="",
        max_step=1,
    ):
        pass

    assert agent_runner.step_calls == 2
    assert event.final_result is None
