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
        def read(self): return iter(events)
        def close(self): pass
    monkeypatch.setattr(scanner, "InputDevice", Device)
    monkeypatch.setattr(scanner, "categorize", lambda event: event)
    calls = iter([([object()], [], []), ([], [], [])])
    monkeypatch.setattr(scanner.select, "select", lambda *_: next(calls))
    monkeypatch.setattr(scanner, "IDLE_RECONNECT_SECONDS", 0)
    reader = scanner.ScannerReader("fake", captured.append)
    reader._read_loop()
    assert captured == ["123"]
