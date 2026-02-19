"""CLI Client 连接模块单元测试"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from astrbot.cli.client.connection import (
    _receive_json_response,
    connect_to_server,
    get_data_path,
    get_logs,
    get_temp_path,
    load_auth_token,
    load_connection_info,
    send_message,
)


class TestGetDataPath:
    """get_data_path 路径解析测试"""

    def test_env_var_priority(self, tmp_path):
        """环境变量 ASTRBOT_ROOT 优先"""
        with patch.dict(os.environ, {"ASTRBOT_ROOT": str(tmp_path)}):
            result = get_data_path()
            assert result == os.path.join(str(tmp_path), "data")

    def test_fallback_to_source_root(self):
        """回退到源码安装目录"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASTRBOT_ROOT", None)
            result = get_data_path()
            assert result.endswith("data")

    def test_no_env_returns_data_suffix(self):
        """返回路径以 data 结尾"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASTRBOT_ROOT", None)
            result = get_data_path()
            assert os.path.basename(result) == "data"


class TestGetTempPath:
    """get_temp_path 测试"""

    def test_env_var_priority(self, tmp_path):
        """环境变量优先"""
        with patch.dict(os.environ, {"ASTRBOT_ROOT": str(tmp_path)}):
            result = get_temp_path()
            assert result == os.path.join(str(tmp_path), "data", "temp")


class TestLoadAuthToken:
    """load_auth_token 测试"""

    def test_token_found(self, tmp_path):
        """正确读取 token"""
        token_file = tmp_path / "data" / ".cli_token"
        token_file.parent.mkdir(parents=True)
        token_file.write_text("test_token_123")

        with patch(
            "astrbot.cli.client.connection.get_data_path",
            return_value=str(tmp_path / "data"),
        ):
            assert load_auth_token() == "test_token_123"

    def test_token_not_found(self, tmp_path):
        """token 文件不存在返回空字符串"""
        with patch(
            "astrbot.cli.client.connection.get_data_path",
            return_value=str(tmp_path / "nonexistent"),
        ):
            assert load_auth_token() == ""

    def test_token_strip_whitespace(self, tmp_path):
        """去除 token 两端空白"""
        token_file = tmp_path / "data" / ".cli_token"
        token_file.parent.mkdir(parents=True)
        token_file.write_text("  token_with_spaces  \n")

        with patch(
            "astrbot.cli.client.connection.get_data_path",
            return_value=str(tmp_path / "data"),
        ):
            assert load_auth_token() == "token_with_spaces"


class TestLoadConnectionInfo:
    """load_connection_info 测试"""

    def test_unix_connection(self, tmp_path):
        """读取 Unix Socket 配置"""
        conn_file = tmp_path / ".cli_connection"
        conn_file.write_text(json.dumps({"type": "unix", "path": "/tmp/test.sock"}))

        result = load_connection_info(str(tmp_path))
        assert result == {"type": "unix", "path": "/tmp/test.sock"}

    def test_tcp_connection(self, tmp_path):
        """读取 TCP 配置"""
        conn_file = tmp_path / ".cli_connection"
        conn_file.write_text(
            json.dumps({"type": "tcp", "host": "127.0.0.1", "port": 12345})
        )

        result = load_connection_info(str(tmp_path))
        assert result == {"type": "tcp", "host": "127.0.0.1", "port": 12345}

    def test_file_not_found(self, tmp_path):
        """文件不存在返回 None"""
        result = load_connection_info(str(tmp_path))
        assert result is None

    def test_invalid_json(self, tmp_path):
        """无效 JSON 返回 None"""
        conn_file = tmp_path / ".cli_connection"
        conn_file.write_text("not json")

        result = load_connection_info(str(tmp_path))
        assert result is None


class TestConnectToServer:
    """connect_to_server 测试"""

    def test_invalid_socket_type(self):
        """无效连接类型抛出 ValueError"""
        with pytest.raises(ValueError, match="Invalid socket type"):
            connect_to_server({"type": "invalid"})

    def test_unix_missing_path(self):
        """Unix Socket 缺少路径抛出 ValueError"""
        with pytest.raises(ValueError, match="path is missing"):
            connect_to_server({"type": "unix"})

    def test_tcp_missing_host(self):
        """TCP 缺少 host 抛出 ValueError"""
        with pytest.raises(ValueError, match="host or port is missing"):
            connect_to_server({"type": "tcp", "host": "", "port": 1234})

    def test_tcp_missing_port(self):
        """TCP 缺少 port 抛出 ValueError"""
        with pytest.raises(ValueError, match="host or port is missing"):
            connect_to_server({"type": "tcp", "host": "127.0.0.1"})


class TestReceiveJsonResponse:
    """_receive_json_response 测试"""

    def test_single_chunk(self):
        """单次接收完整 JSON"""
        mock_socket = MagicMock()
        data = json.dumps({"status": "success", "response": "hello"}).encode("utf-8")
        mock_socket.recv.side_effect = [data, b""]

        result = _receive_json_response(mock_socket)
        assert result["status"] == "success"
        assert result["response"] == "hello"

    def test_multi_chunk(self):
        """分多次接收 JSON"""
        mock_socket = MagicMock()
        data = json.dumps({"status": "success", "response": "hello"}).encode("utf-8")
        # 分两块发送
        mid = len(data) // 2
        mock_socket.recv.side_effect = [data[:mid], data[mid:], b""]

        result = _receive_json_response(mock_socket)
        assert result["status"] == "success"


class TestSendMessage:
    """send_message 测试"""

    @patch("astrbot.cli.client.connection._get_connected_socket")
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="")
    def test_success(self, mock_token, mock_socket):
        """成功发送消息"""
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        response_data = json.dumps({"status": "success", "response": "hi"}).encode(
            "utf-8"
        )
        mock_sock.recv.side_effect = [response_data, b""]

        result = send_message("hello")
        assert result["status"] == "success"
        assert result["response"] == "hi"
        mock_sock.close.assert_called_once()

    @patch("astrbot.cli.client.connection._get_connected_socket")
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="token123")
    def test_with_auth_token(self, mock_token, mock_socket):
        """带 token 发送"""
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        response_data = json.dumps({"status": "success"}).encode("utf-8")
        mock_sock.recv.side_effect = [response_data, b""]

        send_message("hello")

        # 验证 sendall 包含 auth_token
        sent_data = mock_sock.sendall.call_args[0][0]
        sent_json = json.loads(sent_data)
        assert sent_json["auth_token"] == "token123"

    @patch(
        "astrbot.cli.client.connection._get_connected_socket",
        side_effect=ConnectionError("refused"),
    )
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="")
    def test_connection_error(self, mock_token, mock_socket):
        """连接失败返回错误"""
        result = send_message("hello")
        assert result["status"] == "error"
        assert "refused" in result["error"]

    @patch("astrbot.cli.client.connection._get_connected_socket")
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="")
    def test_timeout(self, mock_token, mock_socket):
        """超时返回错误"""
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.sendall.side_effect = TimeoutError()

        result = send_message("hello")
        assert result["status"] == "error"
        assert "timeout" in result["error"].lower()
        mock_sock.close.assert_called_once()


class TestGetLogs:
    """get_logs 测试"""

    @patch("astrbot.cli.client.connection._get_connected_socket")
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="")
    def test_success(self, mock_token, mock_socket):
        """成功获取日志"""
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        response_data = json.dumps(
            {"status": "success", "response": "log lines..."}
        ).encode("utf-8")
        mock_sock.recv.side_effect = [response_data, b""]

        result = get_logs(lines=50, level="ERROR")
        assert result["status"] == "success"

        # 验证请求参数
        sent_data = mock_sock.sendall.call_args[0][0]
        sent_json = json.loads(sent_data)
        assert sent_json["action"] == "get_logs"
        assert sent_json["lines"] == 50
        assert sent_json["level"] == "ERROR"

    @patch(
        "astrbot.cli.client.connection._get_connected_socket",
        side_effect=ConnectionError("no server"),
    )
    @patch("astrbot.cli.client.connection.load_auth_token", return_value="")
    def test_connection_error(self, mock_token, mock_socket):
        """连接失败返回错误"""
        result = get_logs()
        assert result["status"] == "error"
