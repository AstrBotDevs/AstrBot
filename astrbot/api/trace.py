"""Public tracing API for AstrBot plugins.

Plugin authors can import from this module to instrument their code with
trace spans that automatically appear in the AstrBot trace dashboard.

Quick start::

    from astrbot.api.trace import span_record, span_context

    class MyPlugin(Star):

        @command("weather")
        @span_record("plugin.weather", span_type="plugin_call", record_input=True)
        async def get_weather(self, event: AstrMessageEvent, city: str):
            result = await self._fetch(city)
            yield event.plain_result(result)

        async def _fetch(self, city: str):
            async with span_context("http_fetch", span_type="io_call") as s:
                s.set_input(city=city)
                data = await httpx.get(f"https://wttr.in/{city}?format=3")
                s.set_output(status=data.status_code)
                return data.text

All spans created this way are automatically attached to the trace for the
currently-processed request (via a ``contextvars.ContextVar``) and will show
up in the span tree on the Trace page.  When tracing is disabled in the
dashboard settings, all functions are called with zero overhead.
"""

from astrbot.core.utils.trace import (
    TraceSpan,
    _NullSpan,
    get_current_span,
    span_context,
    span_record,
)

__all__ = [
    "span_context",  # async with span_context("name", span_type="io_call") as s:
    "span_record",  # @span_record("name", span_type="plugin_call")
    "get_current_span",  # TraceSpan | None — manual span manipulation
    "TraceSpan",  # type hint
    "_NullSpan",  # type hint (returned when tracing is disabled)
]
