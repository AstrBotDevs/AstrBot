"""Import smoke tests for astrbot.core.star.register.star_handler."""
from astrbot.core.star.register.star_handler import (
    register_command,
    register_command_group,
    register_custom_filter,
    register_event_message_type,
    register_platform_adapter_type,
    register_regex,
    register_permission_type,
    register_on_astrbot_loaded,
    register_on_platform_loaded,
    register_on_plugin_loaded,
    register_on_plugin_unloaded,
    register_on_plugin_error,
    register_on_llm_request,
    register_on_llm_response,
    register_on_waiting_llm_request,
    register_on_agent_begin,
    register_on_agent_done,
    register_on_using_llm_tool,
    register_on_llm_tool_respond,
    register_llm_tool,
    register_agent,
    register_on_decorating_result,
    register_after_message_sent,
    RegisteringCommandable,
    RegisteringAgent,
    get_handler_full_name,
    get_handler_or_create,
)


def test_register_command_is_callable():
    """register_command is importable and callable."""
    assert callable(register_command)


def test_register_command_group_is_callable():
    """register_command_group is importable and callable."""
    assert callable(register_command_group)


def test_register_custom_filter_is_callable():
    """register_custom_filter is importable and callable."""
    assert callable(register_custom_filter)


def test_register_event_message_type_is_callable():
    """register_event_message_type is importable and callable."""
    assert callable(register_event_message_type)


def test_register_platform_adapter_type_is_callable():
    """register_platform_adapter_type is importable and callable."""
    assert callable(register_platform_adapter_type)


def test_register_regex_is_callable():
    """register_regex is importable and callable."""
    assert callable(register_regex)


def test_register_permission_type_is_callable():
    """register_permission_type is importable and callable."""
    assert callable(register_permission_type)


def test_register_on_astrbot_loaded_is_callable():
    """register_on_astrbot_loaded is importable and callable."""
    assert callable(register_on_astrbot_loaded)


def test_register_on_platform_loaded_is_callable():
    """register_on_platform_loaded is importable and callable."""
    assert callable(register_on_platform_loaded)


def test_register_on_plugin_loaded_is_callable():
    """register_on_plugin_loaded is importable and callable."""
    assert callable(register_on_plugin_loaded)


def test_register_on_plugin_unloaded_is_callable():
    """register_on_plugin_unloaded is importable and callable."""
    assert callable(register_on_plugin_unloaded)


def test_register_on_plugin_error_is_callable():
    """register_on_plugin_error is importable and callable."""
    assert callable(register_on_plugin_error)


def test_register_on_llm_request_is_callable():
    """register_on_llm_request is importable and callable."""
    assert callable(register_on_llm_request)


def test_register_on_llm_response_is_callable():
    """register_on_llm_response is importable and callable."""
    assert callable(register_on_llm_response)


def test_register_on_waiting_llm_request_is_callable():
    """register_on_waiting_llm_request is importable and callable."""
    assert callable(register_on_waiting_llm_request)


def test_register_on_agent_begin_is_callable():
    """register_on_agent_begin is importable and callable."""
    assert callable(register_on_agent_begin)


def test_register_on_agent_done_is_callable():
    """register_on_agent_done is importable and callable."""
    assert callable(register_on_agent_done)


def test_register_on_using_llm_tool_is_callable():
    """register_on_using_llm_tool is importable and callable."""
    assert callable(register_on_using_llm_tool)


def test_register_on_llm_tool_respond_is_callable():
    """register_on_llm_tool_respond is importable and callable."""
    assert callable(register_on_llm_tool_respond)


def test_register_llm_tool_is_callable():
    """register_llm_tool is importable and callable."""
    assert callable(register_llm_tool)


def test_register_agent_is_callable():
    """register_agent is importable and callable."""
    assert callable(register_agent)


def test_register_on_decorating_result_is_callable():
    """register_on_decorating_result is importable and callable."""
    assert callable(register_on_decorating_result)


def test_register_after_message_sent_is_callable():
    """register_after_message_sent is importable and callable."""
    assert callable(register_after_message_sent)


def test_registering_commandable_class():
    """RegisteringCommandable is importable and is a class."""
    assert isinstance(RegisteringCommandable, type)


def test_registering_agent_class():
    """RegisteringAgent is importable and is a class."""
    assert isinstance(RegisteringAgent, type)


def test_get_handler_full_name_is_callable():
    """get_handler_full_name is importable and callable."""
    assert callable(get_handler_full_name)


def test_get_handler_or_create_is_callable():
    """get_handler_or_create is importable and callable."""
    assert callable(get_handler_or_create)
