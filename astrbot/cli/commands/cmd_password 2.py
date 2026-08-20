import click

from .cmd_conf import (
    _load_config,
    _save_config,
    _set_dashboard_password,
    _set_nested_item,
    _validate_dashboard_password,
    _validate_dashboard_username,
)


@click.command(name="password")
@click.option(
    "--username",
    help="Optional dashboard username to set together with the new password.",
)
def password(username: str | None) -> None:
    """Change the AstrBot dashboard password."""
    config = _load_config()

    new_password = click.prompt(
        "New dashboard password",
        hide_input=True,
        confirmation_prompt=True,
    )
    validated_password = _validate_dashboard_password(new_password)

    if username is not None:
        validated_username = _validate_dashboard_username(username.strip())
        _set_nested_item(config, "dashboard.username", validated_username)

    _set_dashboard_password(config, validated_password)
    _save_config(config)

    click.echo("Dashboard password updated.")
    if username is not None:
        click.echo(f"Dashboard username updated: {validated_username}")
