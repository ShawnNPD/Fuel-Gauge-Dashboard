import pytest
from unittest.mock import MagicMock, patch
from bq28z620 import BQ28z620, BATTERY_STATUS_BITS, SAFETY_ALERT_BITS, SAFETY_STATUS_BITS

def test_bytes_to_uint_le():
    assert BQ28z620.bytes_to_uint_le([0x01]) == 1
    assert BQ28z620.bytes_to_uint_le([0x01, 0x02]) == 0x0201
    assert BQ28z620.bytes_to_uint_le([0xFF, 0x00]) == 255
    assert BQ28z620.bytes_to_uint_le([0x01, 0x02, 0x03, 0x04]) == 0x04030201
    assert BQ28z620.bytes_to_uint_le([]) is None

def test_bytes_to_int_le():
    assert BQ28z620.bytes_to_int_le([0x01, 0x00]) == 1
    assert BQ28z620.bytes_to_int_le([0xFF, 0x7F]) == 32767
    assert BQ28z620.bytes_to_int_le([0xFF, 0xFF]) == -1
    assert BQ28z620.bytes_to_int_le([0x00, 0x80]) == -32768
    assert BQ28z620.bytes_to_int_le([]) is None

def test_read_data_uint16():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0xF0, 0x00] # 240
    bq = BQ28z620(mock_bp)
    
    val, hex_str = bq.read_data(0x08, data_type='uint16')
    mock_bp.read_register.assert_called_with(0xAA, 0xAB, 0x08, length=2)
    assert val == 240
    assert hex_str == "0x00F0"

def test_read_data_int16():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0x00, 0x80] # -32768
    bq = BQ28z620(mock_bp)
    
    val, hex_str = bq.read_data(0x0C, data_type='int16')
    mock_bp.read_register.assert_called_with(0xAA, 0xAB, 0x0C, length=2)
    assert val == -32768
    assert hex_str == "0x8000"

def test_read_data_length_inference():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0xFF, 0xFF, 0xFF, 0xFF]
    bq = BQ28z620(mock_bp)
    
    val, hex_str = bq.read_data(0x10, data_type='int32')
    mock_bp.read_register.assert_called_with(0xAA, 0xAB, 0x10, length=4)
    assert val == -1
    assert hex_str == "0xFFFFFFFF"

def test_read_data_invalid_type():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0x00, 0x00]
    bq = BQ28z620(mock_bp)
    
    with pytest.raises(ValueError):
        bq.read_data(0x08, data_type='unknown')
        
def test_get_voltage():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0xE8, 0x03] # 1000 mV
    bq = BQ28z620(mock_bp)
    
    val, hex_str = bq.get_voltage()
    assert val == 1000
    assert hex_str == "0x03E8"

def test_get_current():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0x9C, 0xFF] # -100 mA
    bq = BQ28z620(mock_bp)
    
    val, hex_str = bq.get_current()
    assert val == -100
    assert hex_str == "0xFF9C"

# --- New tests for status register features ---

def test_parse_bits_all_clear():
    result = BQ28z620.parse_bits(0x0000, BATTERY_STATUS_BITS)
    for name, (active, text) in result.items():
        assert active is False

def test_parse_bits_some_set():
    # Set bit 6 (DSG) and bit 5 (FC)
    result = BQ28z620.parse_bits(0x0060, BATTERY_STATUS_BITS)
    assert result["DSG"] == (True, "Discharging")
    assert result["FC"] == (True, "Fully Charged")
    assert result["OCA"] == (False, "No Alarm")
    assert result["FD"] == (False, "OK")

def test_parse_bits_none_value():
    result = BQ28z620.parse_bits(None, BATTERY_STATUS_BITS)
    for name, (active, text) in result.items():
        assert active is False

def test_get_battery_status():
    mock_bp = MagicMock()
    mock_bp.read_register.return_value = [0x40, 0x00]  # bit 6 = DSG
    bq = BQ28z620(mock_bp)

    val, hex_str = bq.get_battery_status()
    mock_bp.read_register.assert_called_with(0xAA, 0xAB, 0x0a, length=2)
    assert val == 0x0040
    assert hex_str == "0x0040"

@patch('bq28z620.time.sleep')
def test_read_mac_subcommand(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = True
    mock_bp.read_register.side_effect = [
        [0x08],                              # MACDataLength from 0x61 = 8 (4 data + 4 overhead)
        [0x00, 0x00, 0x00, 0x00],            # 4 data bytes from 0x40
    ]
    bq = BQ28z620(mock_bp)

    data = bq.read_mac_subcommand(0x0050)
    mock_bp.write_register.assert_called_with(0xAA, 0x3E, [0x50, 0x00])
    assert data == [0x00, 0x00, 0x00, 0x00]

@patch('bq28z620.time.sleep')
def test_get_safety_alert(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = True
    mock_bp.read_register.side_effect = [
        [0x08],                              # MACDataLength = 8 (4 data + 4 overhead)
        [0x08, 0x00, 0x00, 0x00],            # COV bit set
    ]
    bq = BQ28z620(mock_bp)

    val, hex_str = bq.get_safety_alert()
    assert val == 0x00000008
    assert hex_str == "0x00000008"

@patch('bq28z620.time.sleep')
def test_get_safety_status(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = True
    mock_bp.read_register.side_effect = [
        [0x08],                              # MACDataLength = 8 (4 data + 4 overhead)
        [0x04, 0x00, 0x00, 0x00],            # CUV bit set
    ]
    bq = BQ28z620(mock_bp)

    val, hex_str = bq.get_safety_status()
    assert val == 0x00000004
    assert hex_str == "0x00000004"

@patch('bq28z620.time.sleep')
def test_get_pf_alert(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = True
    mock_bp.read_register.side_effect = [
        [0x08],                              # MACDataLength = 8 (4 data + 4 overhead)
        [0x01, 0x00, 0x00, 0x00],            # Bit 0 = SUV set
    ]
    bq = BQ28z620(mock_bp)

    val, hex_str = bq.get_pf_alert()
    assert val == 0x00000001
    assert hex_str == "0x00000001"

@patch('bq28z620.time.sleep')
def test_get_pf_status(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = True
    mock_bp.read_register.side_effect = [
        [0x08],                              # MACDataLength = 8 (4 data + 4 overhead)
        [0x10, 0x00, 0x00, 0x00],            # Bit 4 = VIMR set
    ]
    bq = BQ28z620(mock_bp)

    val, hex_str = bq.get_pf_status()
    assert val == 0x00000010
    assert hex_str == "0x00000010"

def test_pf_reset():
    mock_bp = MagicMock()
    bq = BQ28z620(mock_bp)
    bq.pf_reset()
    # Should write [0x29, 0x00] to 0x3E
    mock_bp.write_register.assert_called_with(0xAA, 0x3E, [0x29, 0x00])

def test_toggle_chg_fet():
    mock_bp = MagicMock()
    bq = BQ28z620(mock_bp)
    bq.toggle_chg_fet()
    # Should write [0x1F, 0x00] to 0x3E
    mock_bp.write_register.assert_called_with(0xAA, 0x3E, [0x1F, 0x00])

def test_toggle_dsg_fet():
    mock_bp = MagicMock()
    bq = BQ28z620(mock_bp)
    bq.toggle_dsg_fet()
    # Should write [0x20, 0x00] to 0x3E
    mock_bp.write_register.assert_called_with(0xAA, 0x3E, [0x20, 0x00])

@patch('bq28z620.time.sleep')
def test_read_mac_subcommand_write_failure(mock_sleep):
    mock_bp = MagicMock()
    mock_bp.write_register.return_value = False
    bq = BQ28z620(mock_bp)

    data = bq.read_mac_subcommand(0x0050)
    assert data is None
