"""跨进程检查单实例锁；不创建调度器、不读取站点配置。"""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from autologin import __main__ as main
from autologin import single_instance


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

CHILD = r"""
import sys
from types import SimpleNamespace
from autologin import __main__ as main
from autologin import single_instance
single_instance.MUTEX_NAME = sys.argv[1]
def fail():
    raise RuntimeError('test startup failure')
sys.modules['autologin.gui'] = SimpleNamespace(run=fail if sys.argv[2] == 'fail' else lambda: None)
main.setup_logging = lambda: None
main.main()
print('ready', flush=True)
sys.stdin.readline()
"""


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.name = "Local\\AutoLogin.Test." + uuid.uuid4().hex
        name_patch = patch.object(single_instance, "MUTEX_NAME", self.name)
        name_patch.start()
        self.addCleanup(name_patch.stop)

    def lock(self):
        lock = single_instance.InstanceLock()
        self.addCleanup(lock.close)
        return lock

    def start_child(self):
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", CHILD, self.name, "hold"],
            cwd=ROOT, env=ENV,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.stop_child, child)
        self.assertEqual(child.stdout.readline().strip(), "ready")
        return child

    @staticmethod
    def stop_child(child):
        if child.poll() is None:
            child.stdin.write("\n")
            child.stdin.flush()
            child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()

    def test_guard_remains_held_after_main_returns_until_process_exit(self):
        child = self.start_child()
        self.assertFalse(self.lock().acquired)
        child.stdin.write("\n")
        child.stdin.flush()
        self.assertEqual(child.wait(timeout=5), 0)
        self.assertTrue(self.lock().acquired)

    def test_forced_process_exit_releases_guard(self):
        child = self.start_child()
        self.assertFalse(self.lock().acquired)
        child.kill()
        child.wait(timeout=5)
        self.assertTrue(self.lock().acquired)

    def test_failed_start_releases_guard_when_process_exits(self):
        child = subprocess.run(
            [sys.executable, "-B", "-c", CHILD, self.name, "fail"],
            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("test startup failure", child.stderr)
        self.assertTrue(self.lock().acquired)

    def test_repeated_rejections_do_not_leave_a_stale_lock(self):
        first = self.lock()
        self.assertTrue(first.acquired)
        for _ in range(3):
            self.assertFalse(self.lock().acquired)
        first.close()
        first.close()
        self.assertTrue(self.lock().acquired)

    def test_duplicate_launch_does_not_initialize_logging_or_gui(self):
        self.assertTrue(self.lock().acquired)
        gui = SimpleNamespace(run=Mock())
        with patch.object(sys, "argv", ["AutoLogin.exe"]), patch.dict(sys.modules, {"autologin.gui": gui}):
            with patch.object(main, "setup_logging") as logging, patch.object(
                single_instance, "activate_existing"
            ) as activate, patch.object(main.atexit, "register") as register:
                self.assertEqual(main.main(), 0)
        logging.assert_not_called()
        gui.run.assert_not_called()
        register.assert_not_called()
        activate.assert_called_once()

    def test_mutex_error_does_not_start_an_unprotected_instance(self):
        def denied(*args):
            ctypes.set_last_error(5)
            return None

        gui = SimpleNamespace(run=Mock())
        with patch.object(sys, "argv", ["AutoLogin.exe"]), patch.dict(sys.modules, {"autologin.gui": gui}):
            with patch.object(single_instance.kernel32, "CreateMutexW", side_effect=denied):
                with patch.object(main, "setup_logging") as logging, self.assertRaises(OSError):
                    main.main()
        logging.assert_not_called()
        gui.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
