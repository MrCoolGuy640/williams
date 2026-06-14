import win32gui
import win32ui
import numpy as np
from ctypes import windll
import importlib

from williams.io.types import Image
import win32process

class Window:
    """
    Represents a window on the system, given its title.
    Provides methods to interact with it, including capturing its contents.
    """

    def __init__(self, title: str):
        self.title = title
        self.hwnd = win32gui.FindWindow(None, title)
        if not self.hwnd:
            raise ValueError(f"Window with title '{title}' not found.")

    def capture(self) -> np.ndarray | None:
        """
        Capture the window's current content as a numpy array (BGR format).
        Returns None if the capture fails.
        """
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = right - left
        height = bottom - top

        hwndDC = win32gui.GetWindowDC(self.hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)

        result = windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 2)
        if result != 1:
            # Cleanup resources
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwndDC)
            return None

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8).reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))
        img = img[:, :, :3]  # BGRA -> BGR

        # Cleanup resources
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hwndDC)

        return Image(img)

    def exists(self) -> bool:
        """Check if the window still exists."""
        return bool(win32gui.IsWindow(self.hwnd))

    def get_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, right, bottom) of the window as a tuple."""
        return win32gui.GetWindowRect(self.hwnd)
    
    def get_process(self):
        from williams.windows import Process

        _, pid = win32process.GetWindowThreadProcessId(self.hwnd)
        return Process(pid)
