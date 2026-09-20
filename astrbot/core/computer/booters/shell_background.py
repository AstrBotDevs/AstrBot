import shlex

_BACKGROUND_SPAWN_SCRIPT = (
    "import subprocess, sys; "
    "p = subprocess.Popen("
    "['bash', '-lc', sys.argv[1]], "
    "stdin=subprocess.DEVNULL, "
    "stdout=subprocess.DEVNULL, "
    "stderr=subprocess.DEVNULL, "
    "start_new_session=True, "
    "close_fds=True"
    "); "
    "print(p.pid)"
)


def build_detached_shell_command(command: str) -> str:
    return f"python3 -c {shlex.quote(_BACKGROUND_SPAWN_SCRIPT)} {shlex.quote(command)}"
