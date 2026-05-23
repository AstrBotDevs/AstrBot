"""Tests for DiscoveryState -- append-only session tracker (DSC-01, DSC-02, DSC-03)."""

from astrbot.core.tools.discovery_state import DiscoveryState


# ===========================================================================
# DSC-01: Append-only list with deduplication
# ===========================================================================


class TestAppendOnly:
    """DSC-01: DiscoveryState.add() appends names; get_discovered_names() returns ordered tuple."""

    def test_add_and_get(self):
        """add("alpha"), add("beta") -> get_discovered_names() == ("alpha", "beta")."""
        state = DiscoveryState()
        state.add("alpha")
        state.add("beta")

        assert state.get_discovered_names() == ("alpha", "beta")

    def test_add_returns_true_on_new(self):
        """add("alpha") returns True when the name is new."""
        state = DiscoveryState()
        result = state.add("alpha")

        assert result is True

    def test_preserves_insertion_order(self):
        """Tools are returned in the order they were added, not alphabetical."""
        state = DiscoveryState()
        state.add("charlie")
        state.add("alpha")
        state.add("bravo")

        assert state.get_discovered_names() == ("charlie", "alpha", "bravo")

    def test_len(self):
        """len(state) equals the number of unique names added."""
        state = DiscoveryState()
        state.add("alpha")
        state.add("beta")
        state.add("gamma")

        assert len(state) == 3

    def test_contains(self):
        """'alpha' in state is True after add; 'beta' in state is False if not added."""
        state = DiscoveryState()
        state.add("alpha")

        assert "alpha" in state
        assert "beta" not in state

    def test_empty_initial(self):
        """A fresh DiscoveryState has no discovered names."""
        state = DiscoveryState()

        assert state.get_discovered_names() == ()


# ===========================================================================
# DSC-02: Monotonic append (no removal)
# ===========================================================================


class TestMonotonicAppend:
    """DSC-02: No remove/clear/pop methods; duplicate add is no-op."""

    def test_duplicate_add_is_noop(self):
        """add("alpha") twice results in only one entry."""
        state = DiscoveryState()
        state.add("alpha")
        state.add("alpha")

        assert state.get_discovered_names() == ("alpha",)
        assert len(state) == 1

    def test_duplicate_returns_false(self):
        """Second add("alpha") returns False."""
        state = DiscoveryState()
        state.add("alpha")
        result = state.add("alpha")

        assert result is False

    def test_no_remove_method(self):
        """DiscoveryState has no remove method."""
        state = DiscoveryState()

        assert not hasattr(state, "remove")

    def test_no_clear_method(self):
        """DiscoveryState has no clear method."""
        state = DiscoveryState()

        assert not hasattr(state, "clear")

    def test_no_pop_method(self):
        """DiscoveryState has no pop method."""
        state = DiscoveryState()

        assert not hasattr(state, "pop")


# ===========================================================================
# DSC-03: Independence (standalone object)
# ===========================================================================


class TestIndependence:
    """DSC-03: DiscoveryState is standalone, not embedded in message history."""

    def test_standalone_object(self):
        """DiscoveryState() is constructible with no arguments."""
        state = DiscoveryState()

        assert state is not None
        assert isinstance(state, DiscoveryState)

    def test_get_returns_immutable_snapshot(self):
        """get_discovered_names() returns a tuple; modifying caller's copy has no effect."""
        state = DiscoveryState()
        state.add("alpha")
        state.add("beta")

        snapshot = state.get_discovered_names()
        assert isinstance(snapshot, tuple)

        # Tuples are immutable, but verify the internal state is not affected
        # by any attempt to reference the snapshot
        state.add("gamma")
        assert state.get_discovered_names() == ("alpha", "beta", "gamma")
        # Original snapshot is unchanged
        assert snapshot == ("alpha", "beta")
