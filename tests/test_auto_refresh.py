"""定时执行结果自动刷新界面的检查；使用临时配置与假的登录执行器。"""
import tempfile
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from autologin import config
from autologin.config import SiteConfig
from autologin.gui import App
from autologin.scheduler import Scheduler


class AutoRefreshTests(unittest.TestCase):
    RUN_AT = "2026-01-02 09:00:00"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config_file = Path(temporary.name) / "sites.json"
        config_patch = patch.object(config, "CONFIG_FILE", str(config_file))
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.site = SiteConfig(
            name="Test", url="https://example.invalid", skip_holidays=False,
            last_run="2026-01-01 09:00:00", last_status="old",
        )
        config.save_sites([self.site])
        self.outcome = "success"

    def finish_run(self, site, on_progress=None):
        site.last_run = self.RUN_AT
        site.last_status = self.outcome
        if on_progress:
            on_progress("Finished test run")
        return self.outcome == "success", "Finished test run"

    def test_scheduled_results_refresh_without_manual_action(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with patch.object(Scheduler, "start"), patch.object(Scheduler, "_schedule_next"):
                app = App(root)
                for outcome in ("success", "failed"):
                    with self.subTest(outcome=outcome):
                        self.outcome = outcome
                        config.save_sites([self.site])
                        app._refresh_list()
                        self.assertEqual(app.tree.set(self.site.id, "last_run"), self.site.last_run)
                        errors = []
                        refresh_threads = []
                        refresh_list = app._refresh_list

                        def refresh():
                            refresh_threads.append(threading.get_ident())
                            refresh_list()

                        def execute():
                            try:
                                app.scheduler._run_job(self.site.id)
                            except Exception as error:
                                errors.append(error)
                            finally:
                                root.after(0, root.quit)

                        with patch("autologin.scheduler.run_site", side_effect=self.finish_run), patch.object(
                            app, "_refresh_list", new=refresh
                        ):
                            worker = threading.Thread(target=execute, daemon=True)
                            timeout = root.after(4000, root.quit)
                            root.after(0, worker.start)
                            root.mainloop()
                            root.after_cancel(timeout)
                            worker.join(timeout=2)

                        self.assertFalse(worker.is_alive(), "Scheduled worker did not finish")
                        self.assertEqual(errors, [])
                        self.assertEqual(config.load_sites()[0].last_run, self.RUN_AT)
                        self.assertEqual(app.tree.set(self.site.id, "last_run"), self.RUN_AT)
                        self.assertEqual(app.tree.set(self.site.id, "last_status"), outcome)
                        self.assertEqual(refresh_threads, [threading.get_ident()])
        finally:
            root.update_idletasks()
            root.destroy()

    def test_failed_save_does_not_signal_completion(self):
        completed = Mock()
        scheduler = Scheduler(on_complete=completed)
        with patch("autologin.scheduler.run_site", side_effect=self.finish_run), patch.object(
            config, "update_site", side_effect=OSError("Test write failure")
        ), patch.object(scheduler, "_schedule_next") as schedule_next:
            with self.assertRaises(OSError):
                scheduler._run_job(self.site.id)
        completed.assert_not_called()
        schedule_next.assert_called_once()
        self.assertEqual(config.load_sites()[0].last_run, self.site.last_run)


if __name__ == "__main__":
    unittest.main()
