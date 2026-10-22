"""Windows 托盘与 Tk 生命周期检查；不读取真实配置、不访问网站。"""
import ctypes
from ctypes import wintypes as wt
import threading
import tkinter as tk
import unittest
from unittest.mock import patch

from autologin import config, single_instance
from autologin.gui import App, SiteEditorDialog
from autologin.scheduler import Scheduler
from autologin.tray import NOTIFYICONDATAW, shell32, user32


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


shell32.Shell_NotifyIconGetRect.argtypes = [
    ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wt.RECT),
]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL


class TrayTests(unittest.TestCase):
    def setUp(self):
        window_class = patch.object(single_instance, "WINDOW_CLASS", f"AutoLoginTrayTest_{id(self)}")
        window_class.start()
        self.addCleanup(window_class.stop)
        empty_sites = patch.object(config, "load_sites", return_value=[])
        empty_sites.start()
        self.addCleanup(empty_sites.stop)
        no_jobs = patch.object(Scheduler, "start")
        no_jobs.start()
        self.addCleanup(no_jobs.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root)
        self.addCleanup(self.app._on_exit)
        self.assertIsNotNone(self.app.tray, "Native tray initialization failed")
        self.callback_errors = []
        self.root.report_callback_exception = lambda *error: self.callback_errors.append(error)

    def tearDown(self):
        self.assertEqual(self.callback_errors, [])

    def show_window(self):
        self.app._show_window()
        self.root.update()

    def pump_events(self):
        timeout = self.root.after(250, self.root.quit)
        self.root.mainloop()
        self.root.after_cancel(timeout)

    def post_tray_event(self, event):
        tray = self.app.tray
        self.assertTrue(user32.PostMessageW(
            tray._hwnd, tray.CALLBACK_MESSAGE, 0, (1 << 16) | event,
        ))
        self.pump_events()

    def icon_rect_result(self, hwnd):
        identifier = NOTIFYICONIDENTIFIER(
            cbSize=ctypes.sizeof(NOTIFYICONIDENTIFIER), hWnd=hwnd, uID=1,
        )
        rect = wt.RECT()
        return shell32.Shell_NotifyIconGetRect(ctypes.byref(identifier), ctypes.byref(rect))

    def test_second_launch_notification_restores_existing_window(self):
        self.app._hide_to_tray()
        single_instance.activate_existing()
        self.pump_events()
        self.assertEqual(self.root.state(), "normal")

    def test_native_icon_is_registered_and_removed(self):
        self.assertEqual(ctypes.sizeof(NOTIFYICONDATAW), 976 if ctypes.sizeof(ctypes.c_void_p) == 8 else 956)
        self.root.update()
        tray = self.app.tray
        hwnd = tray._hwnd
        self.assertTrue(user32.IsWindow(hwnd))
        self.assertGreaterEqual(self.icon_rect_result(hwnd), 0)
        icon = tray._icon
        self.assertTrue(icon)
        with patch.object(user32, "DestroyIcon", wraps=user32.DestroyIcon) as destroy_icon:
            tray.close()
            tray.close()
            destroy_icon.assert_called_once_with(icon)
        self.assertIsNone(tray._icon)
        self.assertFalse(user32.IsWindow(hwnd))
        self.assertLess(self.icon_rect_result(hwnd), 0)

    def test_minimize_and_close_keep_scheduler_and_icon(self):
        self.show_window()
        tray = self.app.tray
        with patch.object(self.app.scheduler, "shutdown") as shutdown:
            for _ in range(2):
                self.root.iconify()
                self.root.update()
                self.assertEqual(self.root.state(), "withdrawn")
                self.assertIs(self.app.tray, tray)
                self.show_window()
                self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))
                self.root.update()
                self.assertEqual(self.root.state(), "withdrawn")
                self.assertGreaterEqual(self.icon_rect_result(tray._hwnd), 0)
                self.show_window()
            shutdown.assert_not_called()

    def test_mouse_keyboard_and_menu_restore_on_gui_thread(self):
        ui_thread = threading.get_ident()
        threads = []
        show = self.app._show_window

        def restore():
            threads.append(threading.get_ident())
            show()

        with patch.object(self.app, "_show_window", new=restore):
            for event in (0x0203, 0x0400, 0x0401):
                self.app._hide_to_tray()
                self.post_tray_event(event)
                self.assertEqual(self.root.state(), "normal")
            self.app._hide_to_tray()
            with patch.object(user32, "TrackPopupMenu", return_value=1):
                self.post_tray_event(0x007B)
            self.assertEqual(self.root.state(), "normal")
        self.assertEqual(threads, [ui_thread] * 4)

    def test_tray_exit_cleans_up_once_even_when_shutdown_fails(self):
        tray = self.app.tray
        hwnd = tray._hwnd
        with patch.object(self.app.scheduler, "shutdown", side_effect=RuntimeError("test")) as shutdown:
            with patch.object(user32, "TrackPopupMenu", return_value=2), self.assertLogs("auto_login", "ERROR"):
                self.post_tray_event(0x007B)
            self.app._on_exit()
            shutdown.assert_called_once()
        self.assertTrue(self.app._closing)
        self.assertIsNone(self.app.tray)
        self.assertFalse(user32.IsWindow(hwnd))
        self.assertLess(self.icon_rect_result(hwnd), 0)

    def test_icon_failure_does_not_strand_hidden_window(self):
        self.app._hide_to_tray()
        with patch.object(self.app.tray, "show", side_effect=OSError("test")):
            with patch("autologin.gui.messagebox.showwarning") as warning, self.assertLogs("auto_login", "ERROR"):
                self.app._hide_to_tray()
        self.root.update()
        self.assertEqual(self.root.state(), "normal")
        warning.assert_called_once()

    def test_explorer_restart_recreates_icon_or_restores_window(self):
        self.app._hide_to_tray()
        tray = self.app.tray
        self.assertTrue(shell32.Shell_NotifyIconW(2, ctypes.byref(tray._data)))
        user32.PostMessageW(tray._hwnd, tray._taskbar_created, 0, 0)
        self.pump_events()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertGreaterEqual(self.icon_rect_result(tray._hwnd), 0)

        self.assertTrue(shell32.Shell_NotifyIconW(2, ctypes.byref(tray._data)))
        with patch.object(shell32, "Shell_NotifyIconW", return_value=False), self.assertLogs("auto_login", "ERROR"):
            user32.PostMessageW(tray._hwnd, tray._taskbar_created, 0, 0)
            self.pump_events()
        self.assertEqual(self.root.state(), "normal")

    def test_maximized_window_restores_maximized(self):
        self.show_window()
        self.root.state("zoomed")
        self.root.update()
        self.root.iconify()
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        self.show_window()
        self.assertEqual(self.root.state(), "zoomed")

    def test_editor_survives_hide_and_restore(self):
        self.show_window()
        dialog = SiteEditorDialog(self.root)
        dialog._entries["name"].insert(0, "未保存的编辑")
        self.root.update()
        self.app._hide_to_tray()
        self.root.update()
        self.assertFalse(dialog.winfo_viewable())
        self.show_window()
        self.assertTrue(dialog.winfo_viewable())
        self.assertIs(self.root.grab_current(), dialog)
        self.assertEqual(dialog._entries["name"].get(), "未保存的编辑")
        dialog.destroy()
        self.root.update()
        self.assertEqual(self.root.state(), "normal")

    def test_startup_failure_preserves_normal_close(self):
        self.app._on_exit()
        self.root = tk.Tk()
        self.root.withdraw()
        with patch("autologin.tray.TrayIcon", side_effect=OSError("test")), self.assertLogs("auto_login", "ERROR"):
            self.app = App(self.root)
        self.addCleanup(self.app._on_exit)
        self.assertIsNone(self.app.tray)
        with patch.object(self.app.scheduler, "shutdown") as shutdown:
            self.app._on_close()
            shutdown.assert_called_once()
        self.assertTrue(self.app._closing)


if __name__ == "__main__":
    unittest.main()
