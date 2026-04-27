from astrbot.core.tools.computer_tools.shell import (
    _redirect_background_stdout_command,
)


def test_background_shell_command_redirects_output_to_file():
    command = _redirect_background_stdout_command(
        "python -c 'print(123)'",
        output_path="/tmp/astrbot shell output.log",
        local_runtime=False,
    )

    assert command == (
        "python -c 'print(123)' > \"/tmp/astrbot shell output.log\" 2>&1"
    )
