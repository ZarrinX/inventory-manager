"""Reads barcode/QR scans from a USB HID scanner device (keyboard-wedge mode).

The scanner types out the decoded payload as keystrokes followed by Enter, so
this module opens the input device directly (via evdev) and reassembles those
keystrokes into complete scan strings, decoupled from whatever window has
keyboard focus.
"""

import logging
import threading
from collections.abc import Callable

from evdev import InputDevice, categorize, ecodes

logger = logging.getLogger(__name__)

# Maps evdev key names to (unshifted, shifted) characters for a US keyboard
# layout, covering the characters typically found in UPC/QR scan payloads.
_KEYMAP: dict[str, tuple[str, str]] = {
    "KEY_0": ("0", ")"), "KEY_1": ("1", "!"), "KEY_2": ("2", "@"),
    "KEY_3": ("3", "#"), "KEY_4": ("4", "$"), "KEY_5": ("5", "%"),
    "KEY_6": ("6", "^"), "KEY_7": ("7", "&"), "KEY_8": ("8", "*"),
    "KEY_9": ("9", "("),
    "KEY_MINUS": ("-", "_"), "KEY_EQUAL": ("=", "+"),
    "KEY_SLASH": ("/", "?"), "KEY_DOT": (".", ">"), "KEY_COMMA": (",", "<"),
    "KEY_SPACE": (" ", " "), "KEY_SEMICOLON": (";", ":"),
    "KEY_APOSTROPHE": ("'", '"'),
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _KEYMAP[f"KEY_{_c.upper()}"] = (_c, _c.upper())

ScanCallback = Callable[[str], None]


class ScannerReader:
    """Reads complete scan payloads from a scanner device in a background thread."""

    def __init__(self, device_path: str, on_scan: ScanCallback):
        self._device_path = device_path
        self._on_scan = on_scan
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._read_loop()
            except OSError:
                logger.exception(
                    "Lost connection to scanner device %s; retrying", self._device_path
                )
                self._stop_event.wait(timeout=5)

    def _read_loop(self) -> None:
        device = InputDevice(self._device_path)
        buffer: list[str] = []
        shift_held = False
        for event in device.read_loop():
            if self._stop_event.is_set():
                break
            if event.type != ecodes.EV_KEY:
                continue
            key_event = categorize(event)
            key_code = key_event.keycode
            if isinstance(key_code, list):
                key_code = key_code[0]

            if key_code in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                shift_held = key_event.keystate != key_event.key_up
                continue

            if key_event.keystate != key_event.key_down:
                continue

            if key_code == "KEY_ENTER":
                if buffer:
                    self._on_scan("".join(buffer))
                    buffer.clear()
                continue

            chars = _KEYMAP.get(key_code)
            if chars:
                buffer.append(chars[1] if shift_held else chars[0])
