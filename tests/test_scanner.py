from types import SimpleNamespace

import app.scanner as scanner


def test_hid_key_decoding_reassembles_scan(monkeypatch):
    captured = []
    events = [
        SimpleNamespace(type=scanner.ecodes.EV_KEY, keycode="KEY_1", keystate=1, key_down=1, key_up=0),
        SimpleNamespace(type=scanner.ecodes.EV_KEY, keycode="KEY_2", keystate=1, key_down=1, key_up=0),
        SimpleNamespace(type=scanner.ecodes.EV_KEY, keycode="KEY_3", keystate=1, key_down=1, key_up=0),
        SimpleNamespace(type=scanner.ecodes.EV_KEY, keycode="KEY_ENTER", keystate=1, key_down=1, key_up=0),
    ]
    class Device:
        def __init__(self, path): pass
        def read_loop(self): return iter(events)
    monkeypatch.setattr(scanner, "InputDevice", Device)
    monkeypatch.setattr(scanner, "categorize", lambda event: event)
    reader = scanner.ScannerReader("fake", captured.append)
    reader._read_loop()
    assert captured == ["123"]
