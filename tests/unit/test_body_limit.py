from astrbot.dashboard.server import _check_body_limit
from astrbot.dashboard.services.backup_service import CHUNK_SIZE
from astrbot.dashboard.services.chat_service import MAX_UPLOAD_FILE_SIZE_BYTES

DEFAULT_LIMIT = 128 * 1024 * 1024
MULTIPART = "multipart/form-data; boundary=----test"


class TestCheckBodyLimit:
    def test_non_api_paths_pass(self):
        assert (
            _check_body_limit("/assets/index.js", None, "", default_limit=DEFAULT_LIMIT)
            is None
        )

    def test_multipart_without_content_length_is_rejected(self):
        # Multipart form parsing spools large bodies to disk before any
        # per-file size check can run, so length must be declared up front.
        result = _check_body_limit(
            "/api/v1/files", None, MULTIPART, default_limit=DEFAULT_LIMIT
        )
        assert result is not None
        assert result[0] == 411

    def test_leading_space_content_type_still_rejected(self):
        # The form parser strips surrounding whitespace, so a padded
        # Content-Type is still multipart; detection must match the parser.
        result = _check_body_limit(
            "/api/v1/files",
            None,
            " multipart/form-data; boundary=----test",
            default_limit=DEFAULT_LIMIT,
        )
        assert result is not None
        assert result[0] == 411

    def test_get_with_junk_multipart_content_type_passes(self):
        # Body-less methods never trigger form parsing, so a bogus
        # multipart Content-Type on a GET (seen in the wild from the SSE
        # log client) must not be rejected with 411.
        assert (
            _check_body_limit(
                "/api/v1/logs/live",
                None,
                MULTIPART,
                method="GET",
                default_limit=DEFAULT_LIMIT,
            )
            is None
        )

    def test_json_without_content_length_passes(self):
        # Stopgap scope: only multipart is bounded pre-parse (disk spool);
        # other lengthless bodies pass and are bounded at save time.
        assert (
            _check_body_limit(
                "/api/v1/chat", None, "application/json", default_limit=DEFAULT_LIMIT
            )
            is None
        )

    def test_over_default_limit_rejected(self):
        result = _check_body_limit(
            "/api/v1/config",
            DEFAULT_LIMIT + 1,
            "application/json",
            default_limit=DEFAULT_LIMIT,
        )
        assert result is not None
        assert result[0] == 413

    def test_exact_limit_file_passes_with_multipart_slack(self):
        # The /files override includes framing overhead, so a file exactly
        # at the 512 MiB cap is not rejected, while anything beyond the
        # slack still is.
        assert (
            _check_body_limit(
                "/api/v1/files",
                MAX_UPLOAD_FILE_SIZE_BYTES,
                MULTIPART,
                default_limit=DEFAULT_LIMIT,
            )
            is None
        )
        result = _check_body_limit(
            "/api/v1/files",
            MAX_UPLOAD_FILE_SIZE_BYTES + 2 * 1024 * 1024,
            MULTIPART,
            default_limit=DEFAULT_LIMIT,
        )
        assert result is not None
        assert result[0] == 413

    def test_chunk_route_uses_chunk_limit(self):
        assert (
            _check_body_limit(
                "/api/v1/files/upload/chunk",
                CHUNK_SIZE * 2,
                MULTIPART,
                default_limit=DEFAULT_LIMIT,
            )
            is None
        )
        result = _check_body_limit(
            "/api/v1/files/upload/chunk",
            CHUNK_SIZE * 2 + 1,
            MULTIPART,
            default_limit=DEFAULT_LIMIT,
        )
        assert result is not None
        assert result[0] == 413
