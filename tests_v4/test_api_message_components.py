"""
Tests for legacy message component compatibility helpers.
"""

from __future__ import annotations

from astrbot_sdk.api import message_components as Comp


class TestLegacyMessageComponentAliases:
    """Tests for legacy constructor aliases."""

    def test_at_accepts_qq_alias(self):
        """At should accept the legacy qq field name."""
        component = Comp.At(qq="123456", name="Tester")

        assert component.user_id == "123456"
        assert component.user_name == "Tester"

    def test_file_accepts_name_alias(self):
        """File should accept the legacy name field name."""
        component = Comp.File(file="/tmp/demo.txt", name="demo.txt")

        assert component.file == "/tmp/demo.txt"
        assert component.file_name == "demo.txt"

    def test_node_accepts_uin_and_name_aliases(self):
        """Node should accept the legacy uin/name constructor fields."""
        component = Comp.Node(uin="10001", name="AstrBot")

        assert component.sender_id == "10001"
        assert component.nickname == "AstrBot"


class TestLegacyMessageComponentFactories:
    """Tests for legacy media helper factories."""

    def test_image_from_url(self):
        """Image.fromURL() should create a component with file payload."""
        component = Comp.Image.fromURL("https://example.com/image.png")

        assert component.file == "https://example.com/image.png"

    def test_image_from_file_system(self):
        """Image.fromFileSystem() should create a component with file payload."""
        component = Comp.Image.fromFileSystem("C:/tmp/image.png")

        assert component.file == "C:/tmp/image.png"

    def test_video_from_url(self):
        """Video.fromURL() should create a component with file payload."""
        component = Comp.Video.fromURL("https://example.com/video.mp4")

        assert component.file == "https://example.com/video.mp4"

    def test_record_from_file_system(self):
        """Record.fromFileSystem() should create a component with file payload."""
        component = Comp.Record.fromFileSystem("C:/tmp/audio.wav")

        assert component.file == "C:/tmp/audio.wav"
