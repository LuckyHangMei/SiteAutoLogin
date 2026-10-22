"""密码可见性切换的界面检查；使用合成数据，不启动调度器、不访问网站。"""
import copy
import tkinter as tk
import unittest
from tkinter import ttk

from autologin.config import SiteConfig
from autologin.gui import SiteEditorDialog


class PasswordVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.update_idletasks()
        self.root.destroy()

    def open_editor(self, site=None, title=None):
        dialog = SiteEditorDialog(self.root, site=site, title=title)
        dialog.withdraw()
        entry = dialog._entries["password"]
        toggle = next(
            widget for widget in entry.master.winfo_children()
            if isinstance(widget, ttk.Checkbutton)
        )
        return dialog, entry, toggle

    def test_new_edit_and_copy_toggle_preserves_password(self):
        saved = SiteConfig(password="  示例-P@ss'\"$123  ")
        for site, title in ((None, None), (saved, None), (copy.deepcopy(saved), "复制站点")):
            with self.subTest(title=title, new=site is None):
                dialog, entry, toggle = self.open_editor(site, title)
                expected = site.password if site else ""
                self.assertEqual(entry.cget("show"), "*")
                self.assertFalse(dialog.show_password_var.get())
                toggle.invoke()
                self.assertEqual(entry.cget("show"), "")
                self.assertEqual(entry.get(), expected)
                toggle.invoke()
                self.assertEqual(entry.cget("show"), "*")
                self.assertEqual(entry.get(), expected)
                self.assertEqual(dialog.site.password, expected)
                self.assertIsNone(dialog.result)
                dialog.destroy()

    def test_save_visible_edit_and_reopen_masked(self):
        site = SiteConfig(name="Test", url="https://example.invalid", password="old")
        dialog, entry, toggle = self.open_editor(site)
        toggle.invoke()
        password = "  修改后的 P@ss'\"$123  "
        entry.delete(0, "end")
        entry.insert(0, password)
        dialog._on_save()
        self.assertEqual(dialog.result.password, password)
        reopened, entry, toggle = self.open_editor(dialog.result)
        self.assertEqual(entry.get(), password)
        self.assertEqual(entry.cget("show"), "*")
        self.assertFalse(reopened.show_password_var.get())
        reopened.destroy()


if __name__ == "__main__":
    unittest.main()
