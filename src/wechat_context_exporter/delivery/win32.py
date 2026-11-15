"""Minimal Win32 bridge for clipboard, window activation, and paste.

Isolated on purpose: this is the only module in the delivery layer that talks to
the operating system, and everything it exposes returns ``False`` instead of
raising.  A locked clipboard or a foreground-window restriction must degrade to
"here is the text, press Ctrl+V", never lose the export.

Prototypes are declared explicitly because the default ``ctypes`` conversion
truncates 64-bit handles to C ``int``; silently truncating an HGLOBAL produces
corrupted clipboard data rather than an error.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Sequence

CF_UNICODETEXT = 13
CF_HDROP = 15
GMEM_MOVEABLE = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


class _DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


class Win32Clipboard:
    """Best-effort clipboard + focus + paste for Windows."""

    def __init__(self) -> None:
        self._user32: ctypes.WinDLL | None = None
        self._kernel32: ctypes.WinDLL | None = None

    # -- public ----------------------------------------------------------

    def copy(self, *, text: str | None = None, files: Sequence[Path] = ()) -> bool:
        """Put text and/or file paths on the clipboard in one session."""
        payloads: list[tuple[int, bytes]] = []
        if files:
            payloads.append((CF_HDROP, self._dropfiles_payload(files)))
        if text:
            payloads.append((CF_UNICODETEXT, text.encode("utf-16-le") + b"\x00\x00"))
        if not payloads:
            return False

        try:
            user32, kernel32 = self._libraries()
        except OSError:
            return False

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            for image_format, data in payloads:
                handle = self._global_buffer(kernel32, data)
                if not handle:
                    return False
                if not user32.SetClipboardData(image_format, handle):
                    kernel32.GlobalFree(handle)
                    return False
        finally:
            user32.CloseClipboard()
        return True

    def activate(self, app: str) -> bool:
        """Bring the window of ``app`` (exe name or title fragment) to the front."""
        try:
            user32, kernel32 = self._libraries()
        except OSError:
            return False
        hwnd = self._find_window(user32, kernel32, app)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        return bool(user32.SetForegroundWindow(hwnd))

    def paste(self) -> bool:
        """Send Ctrl+V to whatever window currently has focus."""
        try:
            user32, _ = self._libraries()
        except OSError:
            return False
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        return True

    # -- internals -------------------------------------------------------

    def _libraries(self) -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
        if self._user32 is not None and self._kernel32 is not None:
            return self._user32, self._kernel32
        if sys.platform != "win32":
            raise OSError("Win32 clipboard is only available on Windows")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
        kernel32.GlobalFree.restype = wintypes.HANDLE

        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]

        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        self._user32, self._kernel32 = user32, kernel32
        return user32, kernel32

    @staticmethod
    def _global_buffer(kernel32: ctypes.WinDLL, data: bytes) -> int | None:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return None
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        return handle

    @staticmethod
    def _dropfiles_payload(files: Sequence[Path]) -> bytes:
        header = _DROPFILES()
        header.pFiles = ctypes.sizeof(_DROPFILES)
        header.fWide = True
        names = "\x00".join(str(Path(item).expanduser().resolve()) for item in files)
        return bytes(header) + (names + "\x00\x00").encode("utf-16-le")

    def _find_window(self, user32: ctypes.WinDLL, kernel32: ctypes.WinDLL, app: str) -> int:
        wanted = (app or "").strip().lower()
        if not wanted:
            return 0
        exe_target = wanted if wanted.endswith(".exe") else f"{wanted}.exe"
        title_hit = 0
        exe_hit = 0

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd, _lparam):  # noqa: ANN001 - ctypes callback signature
            nonlocal title_hit, exe_hit
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0 and not title_hit:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if wanted in buffer.value.lower():
                    title_hit = hwnd
            if not exe_hit and self._process_name(user32, kernel32, hwnd) == exe_target:
                exe_hit = hwnd
            return not (title_hit and exe_hit)

        user32.EnumWindows(enum_proc(visit), 0)
        return exe_hit or title_hit

    @staticmethod
    def _process_name(user32: ctypes.WinDLL, kernel32: ctypes.WinDLL, hwnd: int) -> str:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return ""
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value
        )
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return ""
            return Path(buffer.value).name.lower()
        finally:
            kernel32.CloseHandle(handle)
