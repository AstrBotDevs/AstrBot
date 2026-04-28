"""Import smoke tests for the persona route module.

Verifies that the ``PersonaRoute`` class from ``persona.py`` can be
imported without errors.
"""

from astrbot.dashboard.routes.persona import (
    PersonaRoute,  # noqa: F401
)


def test_persona_route_class():
    assert PersonaRoute is not None
