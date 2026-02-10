import ssl

import aiohttp.connector as aiohttp_connector
import certifi


def configure_runtime_ca_bundle() -> None:
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(cafile=certifi.where())

        if hasattr(aiohttp_connector, "_SSL_CONTEXT_VERIFIED"):
            aiohttp_connector._SSL_CONTEXT_VERIFIED = ssl_context
    except Exception:
        return


configure_runtime_ca_bundle()
