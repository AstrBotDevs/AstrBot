import ssl

from astrbot.core.utils.http_ssl import build_ssl_context_with_certifi
from astrbot.core.zip_updator import RepoZipUpdator


def test_repo_zip_updator_defaults_to_verified_tls() -> None:
    updator = RepoZipUpdator()
    assert updator.httpx_verify is not False
    assert updator.httpx_verify is not ssl.CERT_NONE


def test_verified_ssl_context_requires_certificates() -> None:
    context = build_ssl_context_with_certifi()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
