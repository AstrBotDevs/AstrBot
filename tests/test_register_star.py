"""Import smoke tests for astrbot.core.star.register.star."""
from astrbot.core.star.register.star import register_star


def test_register_star_is_callable():
    """register_star is importable and is a callable."""
    assert callable(register_star)


def test_register_star_returns_decorator():
    """register_star returns a decorator when called with args."""
    decorator = register_star(
        name="test", author="me", desc="test plugin", version="1.0.0"
    )
    assert callable(decorator)
