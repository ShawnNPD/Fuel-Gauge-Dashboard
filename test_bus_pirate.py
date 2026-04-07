import pytest
from unittest.mock import patch, MagicMock
import serial
from bus_pirate import BusPirate

@patch('bus_pirate.serial.Serial')
def test_connect_success(mock_serial_class):
    mock_serial_instance = MagicMock()
    mock_serial_class.return_value = mock_serial_instance
    
    # Mock hardware responses for identification and command prompts
    # Return '>' for any read attempts to simulate a responsive Bus Pirate
    mock_serial_instance.in_waiting = 1
    mock_serial_instance.read.return_value = b">"
    
    bp = BusPirate("COM3", baudrate=115200, timeout=1)
    success, msg = bp.connect()
    
    assert success is True
    assert bp.connected is True
    assert "Connected successfully" in msg
    mock_serial_class.assert_called_with("COM3", 115200, timeout=1)
    
    # Verify initialization sequences were sent
    assert mock_serial_instance.write.call_count >= 5

@patch('bus_pirate.serial.Serial')
def test_connect_failure(mock_serial_class):
    mock_serial_class.side_effect = serial.SerialException("Port busy")
    
    bp = BusPirate("COM3")
    success, msg = bp.connect()
    
    assert success is False
    assert bp.connected is False
    assert "Failed to connect" in msg

def test_read_register_success():
    bp = BusPirate("COM3")
    bp.connected = True
    bp.serial = MagicMock()
    
    with patch.object(bp, 'send_command') as mock_send_command:
        # Simulate Bus Pirate returning two HEX bytes
        mock_send_command.return_value = "RX: 0x1A \n RX: 0x2B \n>"
        
        data = bp.read_register(write_addr=0xAA, read_addr=0xAB, reg=0x08, length=2)
        
        assert data == [0x1A, 0x2B]
        mock_send_command.assert_called_once()
        sent_cmd = mock_send_command.call_args[0][0]
        assert "[ 0xaa 0x8 ] [ 0xab r:2 ]" in sent_cmd

def test_read_register_invalid_response():
    bp = BusPirate("COM3")
    bp.connected = True
    bp.serial = MagicMock()
    
    with patch.object(bp, 'send_command') as mock_send_command:
        mock_send_command.return_value = "NACK\n>"
        
        data = bp.read_register(0xAA, 0xAB, 0x08, length=2)
        assert data is None

def test_write_register():
    bp = BusPirate("COM3")
    bp.connected = True
    bp.serial = MagicMock()
    
    with patch.object(bp, 'send_command') as mock_send_command:
        success = bp.write_register(0xAA, 0x1D, [0x01, 0x02])
        
        assert success is True
        mock_send_command.assert_called_once()
        sent_cmd = mock_send_command.call_args[0][0]
        assert "[ 0xaa 0x1d 0x1 0x2 ]" in sent_cmd
