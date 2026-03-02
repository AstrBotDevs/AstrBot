import platform
from astrbot.core.computer.tools.python import PythonTool, LocalPythonTool

def test_python_tool_description_contains_os():
    """测试 PythonTool 的描述中是否包含当前操作系统信息"""
    tool = PythonTool()
    current_os = platform.system()
    assert current_os in tool.description
    assert "IPython" in tool.description

def test_local_python_tool_description_contains_os():
    """测试 LocalPythonTool 的描述中是否包含当前操作系统信息和兼容性提示"""
    tool = LocalPythonTool()
    current_os = platform.system()
    assert current_os in tool.description
    assert "Python environment" in tool.description
    assert "system-compatible" in tool.description
