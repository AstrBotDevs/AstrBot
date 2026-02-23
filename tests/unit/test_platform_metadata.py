"""Tests for PlatformMetadata class."""

from astrbot.core.platform.platform_metadata import PlatformMetadata


class TestPlatformMetadata:
    """Tests for PlatformMetadata dataclass."""

    def test_platform_metadata_creation_basic(self):
        """Test creating PlatformMetadata with required fields."""
        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
        )

        assert meta.name == "test_platform"
        assert meta.description == "A test platform"
        assert meta.id == "test_platform_id"

    def test_platform_metadata_default_values(self):
        """Test PlatformMetadata default values."""
        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
        )

        # Default values
        assert meta.default_config_tmpl is None
        assert meta.adapter_display_name is None
        assert meta.logo_path is None
        assert meta.support_streaming_message is True
        assert meta.support_proactive_message is True
        assert meta.module_path is None
        assert meta.i18n_resources is None
        assert meta.config_metadata is None

    def test_platform_metadata_with_all_fields(self):
        """Test creating PlatformMetadata with all fields."""
        default_config = {"type": "test", "enable": True}
        i18n = {"zh-CN": {"name": "测试平台"}, "en-US": {"name": "Test Platform"}}
        config_meta = {"fields": [{"name": "token", "type": "string"}]}

        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            default_config_tmpl=default_config,
            adapter_display_name="Test Platform Display",
            logo_path="logos/test.png",
            support_streaming_message=False,
            support_proactive_message=False,
            module_path="test.module.path",
            i18n_resources=i18n,
            config_metadata=config_meta,
        )

        assert meta.name == "test_platform"
        assert meta.description == "A test platform"
        assert meta.id == "test_platform_id"
        assert meta.default_config_tmpl == default_config
        assert meta.adapter_display_name == "Test Platform Display"
        assert meta.logo_path == "logos/test.png"
        assert meta.support_streaming_message is False
        assert meta.support_proactive_message is False
        assert meta.module_path == "test.module.path"
        assert meta.i18n_resources == i18n
        assert meta.config_metadata == config_meta

    def test_platform_metadata_support_streaming_message(self):
        """Test support_streaming_message field."""
        meta_streaming = PlatformMetadata(
            name="streaming_platform",
            description="Supports streaming",
            id="streaming_id",
            support_streaming_message=True,
        )

        meta_no_streaming = PlatformMetadata(
            name="no_streaming_platform",
            description="No streaming support",
            id="no_streaming_id",
            support_streaming_message=False,
        )

        assert meta_streaming.support_streaming_message is True
        assert meta_no_streaming.support_streaming_message is False

    def test_platform_metadata_support_proactive_message(self):
        """Test support_proactive_message field."""
        meta_proactive = PlatformMetadata(
            name="proactive_platform",
            description="Supports proactive messages",
            id="proactive_id",
            support_proactive_message=True,
        )

        meta_no_proactive = PlatformMetadata(
            name="no_proactive_platform",
            description="No proactive message support",
            id="no_proactive_id",
            support_proactive_message=False,
        )

        assert meta_proactive.support_proactive_message is True
        assert meta_no_proactive.support_proactive_message is False

    def test_platform_metadata_with_default_config_tmpl(self):
        """Test PlatformMetadata with default config template."""
        config_tmpl = {
            "type": "test_platform",
            "enable": False,
            "id": "test_platform",
            "token": "",
            "secret": "",
        }

        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            default_config_tmpl=config_tmpl,
        )

        assert meta.default_config_tmpl == config_tmpl
        assert meta.default_config_tmpl["type"] == "test_platform"
        assert meta.default_config_tmpl["enable"] is False

    def test_platform_metadata_with_i18n_resources(self):
        """Test PlatformMetadata with i18n resources."""
        i18n = {
            "zh-CN": {
                "name": "测试平台",
                "description": "这是一个测试平台",
            },
            "en-US": {
                "name": "Test Platform",
                "description": "This is a test platform",
            },
        }

        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            i18n_resources=i18n,
        )

        assert meta.i18n_resources == i18n
        assert meta.i18n_resources["zh-CN"]["name"] == "测试平台"
        assert meta.i18n_resources["en-US"]["name"] == "Test Platform"

    def test_platform_metadata_with_config_metadata(self):
        """Test PlatformMetadata with config metadata."""
        config_meta = {
            "fields": [
                {"name": "token", "type": "string", "label": "Token", "required": True},
                {
                    "name": "secret",
                    "type": "string",
                    "label": "Secret",
                    "required": False,
                },
            ]
        }

        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            config_metadata=config_meta,
        )

        assert meta.config_metadata == config_meta
        assert len(meta.config_metadata["fields"]) == 2

    def test_platform_metadata_module_path(self):
        """Test PlatformMetadata module_path field."""
        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            module_path="astrbot.core.platform.sources.test",
        )

        assert meta.module_path == "astrbot.core.platform.sources.test"

    def test_platform_metadata_adapter_display_name(self):
        """Test adapter_display_name field."""
        meta_with_display = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            adapter_display_name="My Test Platform",
        )

        meta_without_display = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
        )

        assert meta_with_display.adapter_display_name == "My Test Platform"
        assert meta_without_display.adapter_display_name is None

    def test_platform_metadata_logo_path(self):
        """Test logo_path field."""
        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            logo_path="assets/logo.png",
        )

        assert meta.logo_path == "assets/logo.png"

    def test_platform_metadata_accepts_empty_strings(self):
        """Test metadata object accepts empty-string identity fields."""
        meta = PlatformMetadata(name="", description="", id="")
        assert meta.name == ""
        assert meta.description == ""
        assert meta.id == ""

    def test_platform_metadata_accepts_nonstandard_i18n_resources(self):
        """Test metadata keeps i18n_resources as-is without runtime validation."""
        malformed_i18n = {"zh-CN": "invalid-format"}
        meta = PlatformMetadata(
            name="test_platform",
            description="A test platform",
            id="test_platform_id",
            i18n_resources=malformed_i18n,
        )
        assert meta.i18n_resources == malformed_i18n
