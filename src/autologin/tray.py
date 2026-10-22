"""Windows 系统托盘；消息由 Tk 所在线程处理，不启动额外线程。"""
import ctypes
from ctypes import wintypes as wt
import logging
from pathlib import Path

from . import single_instance


log = logging.getLogger("auto_login")
ICON_PATH = Path(__file__).with_name("assets") / "autologin.ico"
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
        ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wt.HICON),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 显式声明指针宽度，避免 64 位窗口句柄被 ctypes 默认的 int 截断。
for library, name, arguments, result in (
    (kernel32, "GetModuleHandleW", [wt.LPCWSTR], wt.HMODULE),
    (user32, "LoadImageW", [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT], wt.HANDLE),
    (user32, "GetSystemMetrics", [ctypes.c_int], ctypes.c_int),
    (user32, "DestroyIcon", [wt.HICON], wt.BOOL),
    (user32, "RegisterWindowMessageW", [wt.LPCWSTR], wt.UINT),
    (user32, "RegisterClassW", [ctypes.POINTER(WNDCLASSW)], wt.ATOM),
    (user32, "UnregisterClassW", [wt.LPCWSTR, wt.HINSTANCE], wt.BOOL),
    (user32, "CreateWindowExW", [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID], wt.HWND),
    (user32, "DestroyWindow", [wt.HWND], wt.BOOL),
    (user32, "DefWindowProcW", [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], ctypes.c_ssize_t),
    (user32, "CreatePopupMenu", [], wt.HMENU),
    (user32, "AppendMenuW", [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR], wt.BOOL),
    (user32, "DestroyMenu", [wt.HMENU], wt.BOOL),
    (user32, "GetCursorPos", [ctypes.POINTER(wt.POINT)], wt.BOOL),
    (user32, "SetForegroundWindow", [wt.HWND], wt.BOOL),
    (user32, "TrackPopupMenu", [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wt.HWND, ctypes.c_void_p], wt.UINT),
    (user32, "PostMessageW", [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL),
    (shell32, "Shell_NotifyIconW", [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)], wt.BOOL),
):
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = result


class TrayIcon:
    CALLBACK_MESSAGE = 0x8001  # WM_APP + 1

    def __init__(self, on_show, on_exit):
        self._on_show = on_show
        self._on_exit = on_exit
        self._hwnd = None
        self._icon = None
        self._visible = False
        self._registered = False
        self._instance = kernel32.GetModuleHandleW(None)
        self._class_name = single_instance.WINDOW_CLASS
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        if not self._taskbar_created:
            raise ctypes.WinError(ctypes.get_last_error())
        self._window_proc_ref = WNDPROC(self._window_proc)
        window_class = WNDCLASSW(
            lpfnWndProc=self._window_proc_ref,
            hInstance=self._instance,
            lpszClassName=self._class_name,
        )
        self._data = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), uID=1)
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._registered = True
        try:
            self._hwnd = user32.CreateWindowExW(
                0, self._class_name, "自动登录工具", 0,
                0, 0, 0, 0, None, None, self._instance, None,
            )
            if not self._hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._data.hWnd = self._hwnd
            self._data.uFlags = 0x01 | 0x02 | 0x04 | 0x80  # MESSAGE, ICON, TIP, SHOWTIP
            self._data.uCallbackMessage = self.CALLBACK_MESSAGE
            self._icon = user32.LoadImageW(
                None, str(ICON_PATH), 1,
                user32.GetSystemMetrics(49), user32.GetSystemMetrics(50), 0x0010,
            )  # IMAGE_ICON / LR_LOADFROMFILE
            if not self._icon:
                raise ctypes.WinError(ctypes.get_last_error())
            self._data.hIcon = self._icon
            self._data.szTip = "自动登录工具 — 定时任务在后台继续运行"
            self.show()
        except Exception:
            self.close()
            raise

    def show(self):
        if not self._hwnd:
            raise OSError("托盘窗口已关闭")
        if self._visible and shell32.Shell_NotifyIconW(1, ctypes.byref(self._data)):  # NIM_MODIFY
            return
        if not shell32.Shell_NotifyIconW(0, ctypes.byref(self._data)):  # NIM_ADD
            raise OSError("无法创建系统托盘图标")
        self._visible = True
        self._data.uVersion = 4
        shell32.Shell_NotifyIconW(4, ctypes.byref(self._data))  # NIM_SETVERSION

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == single_instance.SHOW_WINDOW_MESSAGE:
                self._on_show()
                return 0
            if message == self._taskbar_created:
                self._visible = False
                self.show()
                return 0
            if message == self.CALLBACK_MESSAGE:
                event = lparam & 0xFFFF
                if event in (0x0202, 0x0203, 0x0400, 0x0401):  # 单击、双击、键盘激活
                    self._on_show()
                elif event in (0x007B, 0x0205):  # WM_CONTEXTMENU / WM_RBUTTONUP
                    self._show_menu()
                return 0
        except Exception:
            log.exception("系统托盘操作失败，恢复主窗口")
            self._on_show()
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not user32.AppendMenuW(menu, 0, 1, "显示窗口"):
                raise ctypes.WinError(ctypes.get_last_error())
            if not user32.AppendMenuW(menu, 0, 2, "退出"):
                raise ctypes.WinError(ctypes.get_last_error())
            point = wt.POINT()
            if not user32.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            user32.SetForegroundWindow(self._hwnd)
            command = user32.TrackPopupMenu(
                menu, 0x0100 | 0x0002, point.x, point.y, 0, self._hwnd, None,
            )
            user32.PostMessageW(self._hwnd, 0, 0, 0)  # 让点击菜单外部也能正常收起菜单。
        finally:
            user32.DestroyMenu(menu)
        if command == 1:
            self._on_show()
        elif command == 2:
            self._on_exit()

    def close(self):
        if self._hwnd:
            shell32.Shell_NotifyIconW(2, ctypes.byref(self._data))  # NIM_DELETE
            self._visible = False
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        if self._registered:
            user32.UnregisterClassW(self._class_name, self._instance)
            self._registered = False
        if self._icon:
            user32.DestroyIcon(self._icon)
            self._icon = None
