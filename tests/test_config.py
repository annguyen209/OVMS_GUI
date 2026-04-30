from app.config import AppConfig


def test_ovms_device_default():
    cfg = AppConfig.__new__(AppConfig)
    cfg._data = {}
    assert cfg.ovms_device == "GPU"


def test_ovms_device_reads_from_data():
    cfg = AppConfig.__new__(AppConfig)
    cfg._data = {"ovms_device": "CPU"}
    assert cfg.ovms_device == "CPU"


def test_ovms_device_valid_choices():
    cfg = AppConfig.__new__(AppConfig)
    for device in ("GPU", "CPU", "NPU", "AUTO"):
        cfg._data = {"ovms_device": device}
        assert cfg.ovms_device == device
