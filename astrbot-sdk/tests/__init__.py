"""Stabilize cross-test imports under pytest collection.

The MCP runtime tests reuse helpers from sibling test modules, so `tests`
needs to behave as an explicit package instead of depending on environment-
specific namespace-package discovery.
"""
