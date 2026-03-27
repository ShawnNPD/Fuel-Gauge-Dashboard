import sys
from unittest.mock import patch, MagicMock, mock_open

class DummyTk:
    def __init__(self, *args, **kwargs): pass
    def title(self, *args): pass
    def geometry(self, *args): pass
    def after(self, *args): pass
    def mainloop(self): pass
    def update(self): pass
    def destroy(self): pass
    def bind(self, *args): pass

class DummyStringVar:
    def __init__(self, *args, **kwargs): self.val = ""
    def set(self, val): self.val = val
    def get(self): return self.val

class DummyBooleanVar:
    def __init__(self, *args, value=False, **kwargs): self.val = value
    def set(self, val): self.val = bool(val)
    def get(self): return self.val

tk_mock = MagicMock()
tk_mock.Tk = DummyTk
tk_mock.StringVar = DummyStringVar
tk_mock.BooleanVar = DummyBooleanVar

sys.modules['tkinter'] = tk_mock
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()

import pytest
import os
import json
from main import FuelGaugeDashboard, POLL_RATE

@pytest.fixture
def app():
    # Provide a Tkinter app instance that gets destroyed after each test
    with patch.object(FuelGaugeDashboard, 'after', create=True):
        application = FuelGaugeDashboard()
        yield application
        if hasattr(application, 'destroy'):
            application.destroy()

def test_load_config_exists(app):
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open()):
            with patch("main.json.load", return_value={"last_port": "COM4"}):
                config = app.load_config()
                assert config == {"last_port": "COM4"}

def test_load_config_not_exists(app):
    with patch("os.path.exists", return_value=False):
        config = app.load_config()
        assert config == {}

def test_save_config(app):
    with patch("builtins.open", mock_open()) as mocked_file:
        with patch("main.json.dump") as mock_dump:
            app.save_config({"last_port": "COM5"})
            mocked_file.assert_called_once_with("config.json", 'w')
            mock_dump.assert_called_once_with({"last_port": "COM5"}, mocked_file())

@patch('main.BusPirate')
@patch('main.BQ28z620')
def test_connect_success(mock_bq, mock_bp_class, app):
    mock_bp_instance = MagicMock()
    mock_bp_instance.connect.return_value = (True, "Success")
    mock_bp_class.return_value = mock_bp_instance
    app.port_var.set("COM3 - Test USB Serial")
    with patch('main.messagebox.showerror') as mock_err:
        with patch.object(app, 'poll_data') as mock_poll:
            app.connect(silent=True)
            mock_bp_class.assert_called_once_with("COM3")
            assert app.bp == mock_bp_instance
            assert app.is_polling is True
            mock_poll.assert_called_once()
            mock_err.assert_not_called()

def test_disconnect(app):
    app.bp = MagicMock()
    app.is_polling = True
    app.disconnect()
    assert app.is_polling is False
    app.bp.disconnect.assert_called_once()
    app.btn_connect.config.assert_called_with(text="Connect")
    app.lbl_voltage.config.assert_called_with(text="---")

@patch('main.time.sleep')
def test_poll_data(mock_sleep, app):
    app.is_polling = True
    app.bp = MagicMock()
    app.bp.connected = True
    app.bq = MagicMock()
    app.bq.get_voltage.return_value = (3500, "0x0DAC")
    app.bq.get_current.return_value = (-500, "0xFE0C")
    app.show_battery_status.set(False)
    app.show_safety_alert.set(False)
    app.show_safety_status.set(False)
    app.show_pf_alert.set(False)
    app.show_pf_status.set(False)
    with patch.object(app, 'after') as mock_after:
        app.poll_data()
        app.lbl_voltage.config.assert_any_call(text="3500 mV  (0x0DAC)")
        app.lbl_current.config.assert_any_call(text="-500 mA  (0xFE0C)")
        mock_after.assert_called_once_with(POLL_RATE, app.poll_data)
