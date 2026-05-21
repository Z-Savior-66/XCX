import os
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from desktop_py.core.models import AccountConfig, AppSettings, FetchResult
from desktop_py.core.store import SHARED_BROWSER_PROFILE_DIR_NAME
from desktop_py.ui.account_dialog import AccountDialog
from desktop_py.ui.main_window import AUTO_RENEW_INTERVAL_MAX_MS, AUTO_RENEW_INTERVAL_MIN_MS, MainWindow


class UiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])


__all__ = [
    "os",
    "unittest",
    "datetime",
    "Path",
    "TemporaryDirectory",
    "patch",
    "Qt",
    "QTimer",
    "QCloseEvent",
    "QKeyEvent",
    "QApplication",
    "QSystemTrayIcon",
    "AccountConfig",
    "AppSettings",
    "FetchResult",
    "SHARED_BROWSER_PROFILE_DIR_NAME",
    "AccountDialog",
    "AUTO_RENEW_INTERVAL_MAX_MS",
    "AUTO_RENEW_INTERVAL_MIN_MS",
    "MainWindow",
    "UiTestBase",
]
