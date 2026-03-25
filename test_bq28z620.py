import pytest
from unittest.mock import MagicMock
from bq28z620 import BQ28z620

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
