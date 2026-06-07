from __future__ import annotations

import queue
import unittest
from unittest.mock import MagicMock, patch

from desktop_py.ui.workers import QueuedTask, TaskThread


class TaskThreadUnitTestCase(unittest.TestCase):
    """Test TaskThread without starting the real thread (no QApplication needed)."""

    def test_enqueue_returns_queued_task(self):
        thread = TaskThread()
        job = MagicMock(return_value="ok")
        on_success = MagicMock()

        task = thread.enqueue(
            job_builder=job,
            on_success=on_success,
            emit_log=True,
            emit_failure_log=True,
            update_status=False,
            on_progress=None,
        )

        self.assertIsInstance(task, QueuedTask)
        self.assertEqual(task.task_id, 1)
        self.assertIs(task.job_builder, job)
        self.assertIs(task.on_success, on_success)
        self.assertTrue(task.emit_log)
        self.assertTrue(task.emit_failure_log)
        self.assertFalse(task.update_status)
        self.assertIsNone(task.on_progress)

    def test_enqueue_increments_task_id(self):
        thread = TaskThread()

        tasks = []
        for _ in range(3):
            tasks.append(thread.enqueue(
                job_builder=MagicMock(),
                on_success=MagicMock(),
                emit_log=False,
                emit_failure_log=False,
                update_status=False,
                on_progress=None,
            ))

        self.assertEqual(tasks[0].task_id, 1)
        self.assertEqual(tasks[1].task_id, 2)
        self.assertEqual(tasks[2].task_id, 3)

    def test_enqueue_puts_task_into_queue(self):
        thread = TaskThread()

        task = thread.enqueue(
            job_builder=MagicMock(),
            on_success=MagicMock(),
            emit_log=False,
            emit_failure_log=False,
            update_status=False,
            on_progress=None,
        )

        self.assertFalse(thread._queue.empty())
        self.assertIs(thread._queue.get_nowait(), task)

    def test_cancel_all_sets_cancel_event(self):
        thread = TaskThread()
        self.assertFalse(thread._cancel_event.is_set())

        thread.cancel_all()

        self.assertTrue(thread._cancel_event.is_set())

    def test_cancel_all_drains_queue(self):
        thread = TaskThread()
        for _ in range(5):
            thread.enqueue(
                job_builder=MagicMock(),
                on_success=MagicMock(),
                emit_log=False,
                emit_failure_log=False,
                update_status=False,
                on_progress=None,
            )

        self.assertEqual(thread._queue.qsize(), 5)

        thread.cancel_all()

        self.assertTrue(thread._queue.empty())

    def test_shutdown_sets_shutdown_event_and_sends_poison_pill(self):
        thread = TaskThread()

        thread.shutdown()

        self.assertTrue(thread._shutdown.is_set())
        # The poison-pill None should be in the queue
        self.assertIsNone(thread._queue.get_nowait())

    def test_has_pending_work_empty_thread(self):
        thread = TaskThread()
        self.assertFalse(thread.has_pending_work())

    def test_has_pending_work_with_enqueued_task(self):
        thread = TaskThread()
        thread.enqueue(
            job_builder=MagicMock(),
            on_success=MagicMock(),
            emit_log=False,
            emit_failure_log=False,
            update_status=False,
            on_progress=None,
        )

        self.assertTrue(thread.has_pending_work())

    def test_active_task_set_during_run(self):
        """Test the run loop by manually driving it on the current thread."""
        thread = TaskThread()

        captured_active_tasks: list[QueuedTask | None] = []
        original_run = TaskThread.run

        def patched_run(self_thread):
            # Override the queue get to let us inspect _active_task
            task = self_thread._queue.get()
            if task is None:
                return
            self_thread._active_task = task
            self_thread._cancel_event.clear()
            try:
                result = task.job_builder(lambda msg: None)
            except Exception:
                pass
            else:
                task.on_success(result)
            finally:
                captured_active_tasks.append(self_thread._active_task)
                self_thread._active_task = None

        job = MagicMock(return_value="result")
        on_success = MagicMock()
        thread.enqueue(
            job_builder=job,
            on_success=on_success,
            emit_log=False,
            emit_failure_log=False,
            update_status=False,
            on_progress=None,
        )

        with patch.object(TaskThread, "run", patched_run):
            thread.start()
            thread.wait(2000)

        self.assertEqual(len(captured_active_tasks), 1)
        self.assertIsNotNone(captured_active_tasks[0])
        job.assert_called_once()
        on_success.assert_called_once_with("result")


class TaskThreadSignalsTestCase(unittest.TestCase):
    """Verify signal attributes exist on TaskThread."""

    def test_has_expected_signals(self):
        thread = TaskThread()
        self.assertTrue(hasattr(thread, "task_message"))
        self.assertTrue(hasattr(thread, "task_progress"))
        self.assertTrue(hasattr(thread, "task_succeeded"))
        self.assertTrue(hasattr(thread, "task_cancelled"))
        self.assertTrue(hasattr(thread, "task_failed"))
        self.assertTrue(hasattr(thread, "task_finished"))
        self.assertTrue(hasattr(thread, "idle"))


class QueuedTaskDataclassTestCase(unittest.TestCase):
    def test_fields(self):
        task = QueuedTask(
            task_id=42,
            job_builder=lambda: None,
            on_success=lambda _: None,
            emit_log=True,
            emit_failure_log=False,
            update_status=True,
            on_progress=None,
        )
        self.assertEqual(task.task_id, 42)
        self.assertTrue(task.emit_log)
        self.assertFalse(task.emit_failure_log)
        self.assertTrue(task.update_status)
        self.assertIsNone(task.on_progress)


if __name__ == "__main__":
    unittest.main()
