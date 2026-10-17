import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from core.settings import app_data_dir


LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
LOG_MAX_BYTES = 1024 * 1024   # 1MB per file
LOG_BACKUPS = 3               # mp3vault.log + .1 .. .3, so at most ~4MB on disk


def log_dir():
    return os.path.join(app_data_dir(), "logs")


""" Configures the root logger once at startup: a rotating file in %APPDATA%\\MP3Vault\\logs
(what a user attaches to a bug report) plus the console. Also routes uncaught exceptions from
the main thread and from worker threads into the log, which otherwise only reach a console the
packaged .exe may not even have. Returns the log file path. """
def setup_logging(directory=None, level=logging.INFO):
    directory = directory or log_dir()
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)

    logFile = os.path.join(directory, "mp3vault.log")
    try:
        os.makedirs(directory, exist_ok=True)
        fileHandler = RotatingFileHandler(logFile, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
        fileHandler.setFormatter(formatter)
        root.addHandler(fileHandler)
    except OSError as e:
        logFile = None
        print(f"File logging disabled: {e}", file=sys.stderr)

    # sys.stderr is None in a windowed (console=False) PyInstaller build
    if sys.stderr is not None:
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        root.addHandler(consoleHandler)

    def logUncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("uncaught").critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = logUncaught
    threading.excepthook = lambda args: logUncaught(args.exc_type, args.exc_value, args.exc_traceback)
    return logFile
