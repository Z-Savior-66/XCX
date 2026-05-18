import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication

from desktop_py import app as desktop_app
from desktop_py.app import ensure_browser_runtime, load_app_icon, resolve_app_asset_path
from desktop_py.ui.workers import TaskThread


class FakeTaskThread(QObject):
    task_message = Signal(object, str)
    task_succeeded = Signal(object, object)
    task_failed = Signal(object, str)
    task_finished = Signal(object)

    def __init__(self, should_fail: bool = False):
        super().__init__()
        self._should_fail = should_fail
        self._job_builder = None
        self._task = object()
        self.shutdown_called = False
        self.wait_called = False

    def enqueue(
        self,
        *,
        job_builder,
        on_success,
        emit_log: bool,
        emit_failure_log: bool,
        update_status: bool,
        on_progress,
    ):
        self._job_builder = job_builder
        self._on_success = on_success
        return self._task

    def start(self):
        if self._should_fail:
            self.task_failed.emit(self._task, "network error")
            self.task_finished.emit(self._task)
            return
        result = self._job_builder(lambda message: self.task_message.emit(self._task, message))
        self.task_succeeded.emit(self._task, result)
        self.task_finished.emit(self._task)

    def deleteLater(self):
        return None

    def shutdown(self):
        self.shutdown_called = True

    def wait(self, _timeout):
        self.wait_called = True
        return True


class SpyTaskThread(TaskThread):
    instances: list[SpyTaskThread] = []

    def __init__(self):
        super().__init__()
        SpyTaskThread.instances.append(self)


class FakeSignalConnector:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class FakeApplication:
    def __init__(self, _argv):
        self.exec_called = False
        self.window_icon_set = False

    def setApplicationName(self, _name):
        return None

    def setQuitOnLastWindowClosed(self, _enabled):
        return None

    def setWindowIcon(self, _icon):
        self.window_icon_set = True

    def style(self):
        return self

    def standardIcon(self, _icon):
        return FakeIcon(False)

    def exec(self):
        self.exec_called = True
        return 0


class FakeIcon:
    def __init__(self, is_null: bool = False):
        self._is_null = is_null

    def isNull(self):
        return self._is_null


class FakeInstanceLock:
    def __init__(self):
        self.release_called = False

    def release(self):
        self.release_called = True


class FakeWindow:
    def __init__(self):
        self.show_called = False
        self.window_icon_set = False
        self.tray_icon = None

    def setWindowIcon(self, _icon):
        self.window_icon_set = True

    def restore_from_tray(self):
        return None

    def request_exit(self):
        return None

    def show(self):
        self.show_called = True


class FakeMenu:
    def __init__(self):
        self.actions = []
        self.separator_count = 0

    def addAction(self, action):
        self.actions.append(action)

    def addSeparator(self):
        self.separator_count += 1


class FakeAction:
    def __init__(self, _text, _parent):
        self.triggered = FakeSignalConnector()


class FakeTrayIcon:
    class ActivationReason:
        Trigger = object()

    def __init__(self, _parent):
        self.activated = FakeSignalConnector()
        self.show_called = False

    def setIcon(self, _icon):
        return None

    def setToolTip(self, _text):
        return None

    def setContextMenu(self, _menu):
        return None

    def show(self):
        self.show_called = True


class AppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ensure_browser_runtime_skips_install_when_ready(self):
        with (
            patch("desktop_py.app.playwright_browsers_ready", return_value=True),
            patch("desktop_py.app.install_playwright_browsers") as mock_install,
        ):
            self.assertTrue(ensure_browser_runtime(self.app))

        mock_install.assert_not_called()

    def test_app_icon_asset_loads(self):
        icon_path = resolve_app_asset_path("assets/app_icon.png")
        image_size = QImageReader(str(icon_path)).size()

        self.assertTrue(icon_path.is_file())
        self.assertEqual((image_size.width(), image_size.height()), (2048, 2048))
        self.assertFalse(load_app_icon().isNull())

    def test_ensure_browser_runtime_shows_warning_when_install_fails(self):
        with (
            patch("desktop_py.app.playwright_browsers_ready", return_value=False),
            patch("desktop_py.app.TaskThread", side_effect=lambda: FakeTaskThread(should_fail=True)),
            patch("desktop_py.app.MessageDialog.show_warning") as mock_warning,
        ):
            self.assertFalse(ensure_browser_runtime(self.app))

        mock_warning.assert_called_once()

    def test_ensure_browser_runtime_runs_install_in_background_thread(self):
        with (
            patch("desktop_py.app.playwright_browsers_ready", return_value=False),
            patch("desktop_py.app.TaskThread", side_effect=lambda: FakeTaskThread()),
            patch("desktop_py.app.install_playwright_browsers", return_value=(True, "ok")) as mock_install,
        ):
            self.assertTrue(ensure_browser_runtime(self.app))

        mock_install.assert_called_once()

    def test_ensure_browser_runtime_waits_for_real_install_thread_to_stop(self):
        SpyTaskThread.instances = []
        with (
            patch("desktop_py.app.playwright_browsers_ready", return_value=False),
            patch("desktop_py.app.TaskThread", side_effect=lambda: SpyTaskThread()),
            patch("desktop_py.app.install_playwright_browsers", return_value=(True, "ok")),
        ):
            self.assertTrue(ensure_browser_runtime(self.app))

        self.assertEqual(len(SpyTaskThread.instances), 1)
        self.assertFalse(SpyTaskThread.instances[0].isRunning())

    def test_main_shows_warning_and_returns_one_when_instance_lock_active(self):
        fake_app = FakeApplication([])
        with (
            patch("desktop_py.app.QApplication", side_effect=lambda _argv: fake_app),
            patch("desktop_py.app.load_app_icon", return_value=FakeIcon(False)),
            patch("desktop_py.app.acquire_app_instance_lock", side_effect=RuntimeError("小程序工具已在运行")),
            patch("desktop_py.app.ensure_browser_runtime") as mock_runtime,
            patch("desktop_py.app.MessageDialog.show_warning") as mock_warning,
        ):
            result = desktop_app.main()

        self.assertEqual(result, 1)
        mock_runtime.assert_not_called()
        mock_warning.assert_called_once()
        self.assertEqual(mock_warning.call_args.args[1], "程序已在运行")
        self.assertIn("已在运行", mock_warning.call_args.args[2])

    def test_main_releases_instance_lock_after_normal_exit(self):
        fake_app = FakeApplication([])
        fake_lock = FakeInstanceLock()
        fake_window = FakeWindow()
        fake_tray = FakeTrayIcon(fake_window)

        with (
            patch("desktop_py.app.QApplication", side_effect=lambda _argv: fake_app),
            patch("desktop_py.app.load_app_icon", return_value=FakeIcon(False)),
            patch("desktop_py.app.acquire_app_instance_lock", return_value=fake_lock),
            patch("desktop_py.app.ensure_browser_runtime", return_value=True),
            patch("desktop_py.app.MainWindow", return_value=fake_window),
            patch("desktop_py.app.QSystemTrayIcon", return_value=fake_tray),
            patch("desktop_py.app.QMenu", side_effect=lambda: FakeMenu()),
            patch("desktop_py.app.QAction", side_effect=lambda text, parent: FakeAction(text, parent)),
        ):
            result = desktop_app.main()

        self.assertEqual(result, 0)
        self.assertTrue(fake_app.exec_called)
        self.assertTrue(fake_window.show_called)
        self.assertIs(fake_window.tray_icon, fake_tray)
        self.assertTrue(fake_tray.show_called)
        self.assertTrue(fake_lock.release_called)

    def test_main_releases_instance_lock_when_browser_runtime_fails(self):
        fake_app = FakeApplication([])
        fake_lock = FakeInstanceLock()

        with (
            patch("desktop_py.app.QApplication", side_effect=lambda _argv: fake_app),
            patch("desktop_py.app.load_app_icon", return_value=FakeIcon(False)),
            patch("desktop_py.app.acquire_app_instance_lock", return_value=fake_lock),
            patch("desktop_py.app.ensure_browser_runtime", return_value=False),
            patch("desktop_py.app.MainWindow") as mock_window,
        ):
            result = desktop_app.main()

        self.assertEqual(result, 1)
        mock_window.assert_not_called()
        self.assertFalse(fake_app.exec_called)
        self.assertTrue(fake_lock.release_called)


if __name__ == "__main__":
    unittest.main()
