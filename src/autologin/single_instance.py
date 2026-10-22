"""Windows 单实例锁；进程结束时由系统释放，不依赖锁文件。"""
import ctypes
from ctypes import wintypes as wt
import os


# 默认全局唯一；AUTOLOGIN_MUTEX_NAME 可覆盖，用于同机并行跑多套实例（测试/多配置）。
MUTEX_NAME = os.environ.get("AUTOLOGIN_MUTEX_NAME") or r"Local\AutoLogin.SingleInstance"
WINDOW_CLASS = "AutoLoginTrayWindow"
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

for library, name, arguments, result in (
    (kernel32, "CreateMutexW", [wt.LPVOID, wt.BOOL, wt.LPCWSTR], wt.HANDLE),
    (kernel32, "CloseHandle", [wt.HANDLE], wt.BOOL),
    (user32, "FindWindowW", [wt.LPCWSTR, wt.LPCWSTR], wt.HWND),
    (user32, "GetWindowThreadProcessId", [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD),
    (user32, "AllowSetForegroundWindow", [wt.DWORD], wt.BOOL),
    (user32, "RegisterWindowMessageW", [wt.LPCWSTR], wt.UINT),
    (user32, "PostMessageW", [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL),
):
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = result

SHOW_WINDOW_MESSAGE = user32.RegisterWindowMessageW("AutoLogin.ShowExistingWindow")
if not SHOW_WINDOW_MESSAGE:
    raise ctypes.WinError(ctypes.get_last_error())


class InstanceLock:
    """命名互斥量实现单实例；acquired 为 False 表示已有实例在运行。"""

    def __init__(self):
        ctypes.set_last_error(0)
        self._handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.acquired = ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
        if not self.acquired:
            self.close()

    def close(self):
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None


def activate_existing():
    """唤起已在运行的实例：把它的主窗口提到前台。"""
    hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    if hwnd:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        user32.AllowSetForegroundWindow(pid.value)
        user32.PostMessageW(hwnd, SHOW_WINDOW_MESSAGE, 0, 0)
