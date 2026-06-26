"""Import smoke tests for the persona route module.

Verifies that the ``PersonaRoute`` class from ``persona.py`` can be
imported without errors, and checks key method signatures.
"""

import inspect

from astrbot.dashboard.routes.persona import (
    PersonaRoute,
)
from astrbot.dashboard.routes.route import Route


def test_persona_route_class():
    assert PersonaRoute is not None
    assert issubclass(PersonaRoute, Route)


def test_persona_route_init_signature():
    sig = inspect.signature(PersonaRoute.__init__)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "context" in params
    assert "db_helper" in params
    assert "core_lifecycle" in params


def test_persona_route_list_personas_signature():
    sig = inspect.signature(PersonaRoute.list_personas)
    params = list(sig.parameters.keys())
    assert "self" in params


def test_persona_route_create_persona_signature():
    sig = inspect.signature(PersonaRoute.create_persona)
    params = list(sig.parameters.keys())
    assert "self" in params


def test_persona_route_update_persona_signature():
    sig = inspect.signature(PersonaRoute.update_persona)
    params = list(sig.parameters.keys())
    assert "self" in params
