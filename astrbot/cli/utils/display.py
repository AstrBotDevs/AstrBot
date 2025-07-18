"""Display utilities for CLI output with colors"""

from typing import Any
import click


def display_plugins(plugins: list[dict[str, Any]], title: str, color: str = "white"):
    """
    Display a list of plugins with colored output
    
    Args:
        plugins: List of plugin dictionaries
        title: Title to display above the plugin list
        color: Color for the title (red, green, blue, yellow, cyan, magenta, white, etc.)
    """
    if not plugins:
        return

    # Display colored title
    click.echo(f"\n{click.style(title, fg=color, bold=True)}")
    click.echo(click.style("=" * len(title), fg=color))

    # Display plugins in a formatted table
    for plugin in plugins:
        name = plugin.get("name", "Unknown")
        desc = plugin.get("desc", "No description")
        version = plugin.get("version", "Unknown")
        author = plugin.get("author", "Unknown")
        status = plugin.get("status", "Unknown")

        # Color the plugin name based on its status if available
        if hasattr(status, "value"):
            status_str = status.value
        else:
            status_str = str(status)

        name_color = "green"
        if "未安装" in status_str or "NOT_INSTALLED" in str(status):
            name_color = "blue"
        elif "需更新" in status_str or "NEED_UPDATE" in str(status):
            name_color = "yellow"
        elif "未发布" in status_str or "NOT_PUBLISHED" in str(status):
            name_color = "red"

        # Display plugin information
        click.echo(f"  {click.style(name, fg=name_color, bold=True)} ({version}) - {author}")
        click.echo(f"    {desc}")
        click.echo(f"    Status: {click.style(status_str, fg=name_color)}")
        click.echo()
