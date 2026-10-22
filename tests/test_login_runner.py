"""会话复用与过期回退的离线回归测试；不访问真实站点、不使用真实凭据。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from autologin import login_runner
from autologin.config import SiteConfig


class SessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base_patch = patch.object(login_runner, "BASE_DIR", temporary.name)
        base_patch.start()
        self.addCleanup(base_patch.stop)
        self.site = SiteConfig(
            id="test-site", name="Test site", url="https://example.test/login",
            username="test-user", password="test-password", menu_clicks=["#menu"],
        )
        self.state_path = Path(login_runner.session_path(self.site.id))
        self.old_state = {"cookies": [], "origins": []}
        self.new_state = {
            "cookies": [],
            "origins": [{"origin": "https://example.test", "localStorage": [
                {"name": "test-generation", "value": "refreshed"}
            ]}],
        }
        self.page = Mock()
        self.page.url = self.site.url
        self.page.click.side_effect = self.submit_successfully
        self.context = Mock()
        self.context.new_page.return_value = self.page
        self.context.storage_state.side_effect = self.save_refreshed_state
        self.browser = Mock()
        self.browser.new_context.return_value = self.context
        browser_patch = patch.object(login_runner, "_launch_browser", return_value=self.browser)
        browser_patch.start()
        self.addCleanup(browser_patch.stop)
        playwright_patch = patch.object(login_runner, "sync_playwright")
        playwright_patch.start()
        self.addCleanup(playwright_patch.stop)

    def submit_successfully(self, selector, **kwargs):
        if selector == self.site.submit_selector:
            self.page.url = "https://example.test/home"

    def save_refreshed_state(self, *, path):
        Path(path).write_text(json.dumps(self.new_state), encoding="utf-8")
        return self.new_state

    def save_old_state(self):
        self.state_path.write_text(json.dumps(self.old_state), encoding="utf-8")

    def assert_logged_in_with_credentials(self):
        self.page.fill.assert_has_calls([
            call(self.site.username_selector, self.site.username, timeout=15_000),
            call(self.site.password_selector, self.site.password, timeout=15_000),
        ])
        self.page.click.assert_has_calls([
            call(self.site.submit_selector, timeout=15_000),
            call("#menu", timeout=15_000),
        ])
        self.assertEqual(self.site.last_status, "success")
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.new_state)
        self.context.close.assert_called_once()
        self.browser.close.assert_called_once()

    def test_expired_session_uses_saved_credentials(self):
        self.save_old_state()
        ok, message = login_runner.run_site(self.site)
        self.assertTrue(ok, message)
        self.assert_logged_in_with_credentials()
        self.browser.new_context.assert_called_once_with(storage_state=str(self.state_path))

    def test_valid_session_is_refreshed_without_submitting_credentials(self):
        self.save_old_state()
        self.page.url = "https://example.test/home"
        ok, message = login_runner.run_site(self.site)
        self.assertTrue(ok, message)
        self.page.fill.assert_not_called()
        self.page.click.assert_called_once_with("#menu", timeout=15_000)
        self.context.storage_state.assert_called_once_with(path=str(self.state_path))
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.new_state)

    def test_first_login_saves_session(self):
        ok, message = login_runner.run_site(self.site)
        self.assertTrue(ok, message)
        self.assert_logged_in_with_credentials()
        self.browser.new_context.assert_called_once_with()

    def test_rejected_login_keeps_old_state_and_does_not_click_menus(self):
        self.save_old_state()
        self.page.click.side_effect = None
        ok, message = login_runner.run_site(self.site)
        self.assertFalse(ok)
        self.assertIn("登录未成功", message)
        self.assertEqual(self.site.last_status, "failed")
        self.page.click.assert_called_once_with(self.site.submit_selector, timeout=15_000)
        self.context.storage_state.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.old_state)
        self.context.close.assert_called_once()
        self.browser.close.assert_called_once()

    def test_expired_session_without_credentials_requests_authorization(self):
        self.save_old_state()
        self.site.password = ""
        with self.assertLogs("auto_login", level="ERROR"):
            ok, message = login_runner.run_site(self.site)
        self.assertFalse(ok)
        self.assertIn("账号或密码", message)
        self.assertIn("授权", message)
        self.page.fill.assert_not_called()
        self.page.click.assert_not_called()
        self.context.storage_state.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.old_state)

    def test_session_save_failure_does_not_prevent_menu_execution(self):
        self.save_old_state()
        self.page.url = "https://example.test/home"
        self.context.storage_state.side_effect = OSError("test write failure")
        with self.assertLogs("auto_login", level="INFO") as logs:
            ok, message = login_runner.run_site(self.site)
        self.assertTrue(ok, message)
        self.assertTrue(any("保存会话失败" in line for line in logs.output))
        self.page.click.assert_called_once_with("#menu", timeout=15_000)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), self.old_state)


if __name__ == "__main__":
    unittest.main()
