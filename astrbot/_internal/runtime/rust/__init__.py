import sys

try:
    from ._core import cli as _cli

    def cli():
        if len(sys.argv) == 1:
            sys.argv.append("--help")
        return _cli()
except ImportError:
    from click import echo

    def cli():
        echo("""
            AstrBot CLI(rust) is not available.
            Developer: maturin dev
            User: uv run astrbot-rs
            """)
