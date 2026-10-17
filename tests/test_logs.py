import logging
import sys
import threading

import pytest

from core import logs


@pytest.fixture
def isolated_logging():
    # setup_logging changes process-wide state; restore it so other tests are unaffected
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    excepthook, threadHook = sys.excepthook, threading.excepthook
    yield
    for handler in root.handlers[:]:
        if handler not in handlers:
            handler.close()
            root.removeHandler(handler)
    root.setLevel(level)
    sys.excepthook, threading.excepthook = excepthook, threadHook


def _read(path):
    for handler in logging.getLogger().handlers:
        handler.flush()
    return open(path, encoding="utf-8").read()


def test_messages_reach_log_file(tmp_path, isolated_logging):
    logFile = logs.setup_logging(str(tmp_path))
    logging.getLogger("mp3vault").warning("Descarga falló: canción ñ")
    assert "Descarga falló: canción ñ" in _read(logFile)


def test_uncaught_thread_exception_is_logged(tmp_path, isolated_logging):
    logFile = logs.setup_logging(str(tmp_path))

    def boom():
        raise RuntimeError("worker exploded")

    thread = threading.Thread(target=boom)
    thread.start()
    thread.join()

    content = _read(logFile)
    assert "Uncaught exception" in content
    assert "RuntimeError: worker exploded" in content


def test_uncaught_main_exception_is_logged(tmp_path, isolated_logging):
    logFile = logs.setup_logging(str(tmp_path))
    try:
        raise ValueError("main exploded")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert "ValueError: main exploded" in _read(logFile)


def test_unwritable_log_dir_does_not_crash(tmp_path, isolated_logging):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert logs.setup_logging(str(blocker / "logs")) is None
