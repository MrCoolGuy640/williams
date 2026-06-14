import ctypes
from ctypes import wintypes

import psutil
import win32gui
import win32process

from williams.windows import Window

PROCESS_ALL_ACCESS = 0x1F0FFF

kernel32 = ctypes.windll.kernel32


class Process:
    def __init__(self, pid: int):
        self.pid = pid

        self.handle = kernel32.OpenProcess(
            PROCESS_ALL_ACCESS,
            False,
            pid
        )

        if not self.handle:
            raise ValueError(f"Could not open process {pid}")

    @classmethod
    def from_name(cls, name: str):
        name = name.lower()

        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info["name"] and proc.info["name"].lower() == name:
                return cls(proc.info["pid"])

        raise ValueError(f"Process '{name}' not found")

    @property
    def base_address(self) -> int:
        hmods = (wintypes.HMODULE * 1024)()
        needed = wintypes.DWORD()

        ctypes.windll.psapi.EnumProcessModules(
            self.handle,
            ctypes.byref(hmods),
            ctypes.sizeof(hmods),
            ctypes.byref(needed)
        )

        return hmods[0]

    def get_windows(self):
        hwnds = []

        def callback(hwnd, _):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == self.pid:
                hwnds.append(hwnd)

        win32gui.EnumWindows(callback, None)

        return [Window(hwnd) for hwnd in hwnds]

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __del__(self):
        self.close()