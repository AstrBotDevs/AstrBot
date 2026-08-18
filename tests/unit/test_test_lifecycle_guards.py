"""Regression tests for pytest timeout and asynchronous resource guards."""

import tomllib
from pathlib import Path

pytest_plugins = ["pytester"]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFTEST_PATH = PROJECT_ROOT / "tests" / "conftest.py"


def _load_repository_conftest(pytester) -> None:
    source_path = repr(str(CONFTEST_PATH))
    pytester.makeconftest(
        "from importlib.util import module_from_spec, spec_from_file_location\n"
        f"_spec = spec_from_file_location('repository_test_conftest', {source_path})\n"
        "assert _spec is not None and _spec.loader is not None\n"
        "_module = module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_module)\n"
        "pytest_collection_modifyitems = _module.pytest_collection_modifyitems\n"
        "pytest_addoption = _module.pytest_addoption\n"
        "pytest_configure = _module.pytest_configure\n"
        "pytest_runtest_call = _module.pytest_runtest_call\n"
        "pytest_runtest_teardown = _module.pytest_runtest_teardown\n"
        "_cleanup_leaked_asyncio_tasks = _module._cleanup_leaked_asyncio_tasks\n"
    )


def test_async_task_guard_cancels_and_reports_leaked_tasks(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import asyncio

        import pytest


        @pytest.mark.asyncio
        async def test_leaks_task():
            task = asyncio.create_task(asyncio.Event().wait(), name="leaked-task")
            assert not task.done()
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*Leaked asyncio tasks: leaked-task*"])


def test_thread_guard_reports_leaked_daemon_thread(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import threading


        def test_leaks_thread():
            thread = threading.Thread(
                target=threading.Event().wait,
                daemon=True,
                name="leaked-thread",
            )
            thread.start()
            assert thread.is_alive()
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*Leaked threads: leaked-thread*"])


def test_thread_guard_does_not_exempt_a_non_anyio_named_thread(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import threading


        def test_leaks_named_thread():
            thread = threading.Thread(
                target=threading.Event().wait,
                daemon=True,
                name="AnyIO worker thread",
            )
            thread.start()
            assert thread.is_alive()
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*Leaked threads: AnyIO worker thread*"])


def test_thread_guard_waits_for_stopping_aiosqlite_workers(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import threading
        from queue import SimpleQueue

        import aiosqlite.core


        def test_worker_is_signaled_during_teardown():
            queue = SimpleQueue()
            thread = threading.Thread(
                target=aiosqlite.core._connection_worker_thread,
                args=(queue,),
                daemon=True,
            )
            thread.start()
            assert thread.is_alive()

            def stop():
                return aiosqlite.core._STOP_RUNNING_SENTINEL

            queue.put_nowait((None, stop))
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)


def test_thread_guard_allows_fixture_owned_module_thread(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import threading

        import pytest


        @pytest.fixture(scope="module")
        def module_thread():
            stop = threading.Event()
            thread = threading.Thread(
                target=stop.wait,
                daemon=True,
                name="fixture-thread",
            )
            thread.start()
            yield thread
            stop.set()
            thread.join(timeout=1)


        def test_fixture_is_alive(module_thread):
            assert module_thread.is_alive()


        def test_fixture_is_reused(module_thread):
            assert module_thread.is_alive()
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=2)


def test_thread_guard_ignores_setup_skips(pytester) -> None:
    _load_repository_conftest(pytester)
    pytester.makepyfile(
        """
        import pytest


        @pytest.fixture(autouse=True)
        def skip_case():
            pytest.skip("controlled setup skip")


        def test_is_skipped():
            raise AssertionError("the test body must not run")
        """
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(skipped=1)


def test_pytest_configuration_enables_timeout_and_strict_markers() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as config_file:
        pytest_config = tomllib.load(config_file)["tool"]["pytest"]["ini_options"]

    assert pytest_config["faulthandler_timeout"] == "120"
    assert pytest_config["faulthandler_exit_on_timeout"] is True
    assert "--strict-markers" in pytest_config["addopts"]
