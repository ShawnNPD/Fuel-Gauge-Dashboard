import time


# Bit definitions sourced from BQ28Z620-Status-Regs.csv
# BatteryStatus register 0x16 (16-bit, SBS standard layout)
BATTERY_STATUS_BITS = {
    15: "OCA",  14: "TCA",  12: "OTA",  11: "TDA",
     9: "RCA",   8: "RTA",   7: "INIT",   6: "DSG",
     5: "FC",    4: "FD",    3: "EC3",    2: "EC2",
     1: "EC1",   0: "EC0",
}

# SafetyAlert MAC 0x0050 (32-bit: bytes A+B = bits 0-15, C+D = bits 16-31)
SAFETY_ALERT_BITS = {
     2: "CUV",   3: "COV",   4: "OCC",   5: "OCD",
     6: "AOLD",  7: "ASCC",  8: "ASCD", 10: "OTC",  11: "OTD",
    20: "PTOS", 21: "CTOS", 26: "UTC",  27: "UTD",
}

# SafetyStatus MAC 0x0051 (32-bit: same layout, slightly different names)
SAFETY_STATUS_BITS = {
     2: "CUV",   3: "COV",   4: "OCC",   5: "OCD",
     6: "AOLD",  7: "ASCC",  8: "ASCD", 10: "OTC",  11: "OTD",
    20: "PTO",  21: "CTO",  26: "UTC",  27: "UTD",
}


class BQ28z620:
    def __init__(self, bus_pirate, i2c_addr_write=0xAA, i2c_addr_read=0xAB):
        self.bp = bus_pirate
        self.addr_w = i2c_addr_write
        self.addr_r = i2c_addr_read

    @staticmethod
    def bytes_to_uint_le(data):
        """
        Takes little-endian unsigned integer bytes and converts them to decimal.
        Handles 1, 2, or 4 byte packets.
        """
        if not data:
            return None
        val = 0
        for i, byte in enumerate(data):
            val |= (byte << (i * 8))
        return val

    @staticmethod
    def bytes_to_int_le(data):
        """
        Takes little-endian two's complement bytes and converts them to decimal.
        Handles 1, 2, or 4 byte packets.
        """
        val = BQ28z620.bytes_to_uint_le(data)
        if val is None:
            return None
        
        bits = len(data) * 8
        if val & (1 << (bits - 1)):
            val -= (1 << bits)
        return val

    def read_data(self, command, data_type='uint16'):
        """
        General function to read variable-length bytes and decode them into a specific data type.
        Available data types: 'uint8', 'int8', 'uint16', 'int16', 'uint32', 'int32'
        """
        # Determine length based on data_type
        if '8' in data_type:
            length = 1
        elif '32' in data_type:
            length = 4
        else:
            length = 2  # default 16-bit

        data = self.bp.read_register(self.addr_w, self.addr_r, command, length=length)
        if data and len(data) == length:
            # Preserve the raw hex equivalent for display
            raw_val = self.bytes_to_uint_le(data)
            hex_str = f"0x{raw_val:0{length*2}X}"
            
            if data_type.startswith('uint'):
                val = raw_val
            elif data_type.startswith('int'):
                val = self.bytes_to_int_le(data)
            else:
                raise ValueError(f"Unknown data type: {data_type}")
                
            return val, hex_str
        return None, None

    def read_word(self, command, endian='little'):
        """
        Legacy read function (defaults to uint16).
        """
        if endian != 'little':
            # Fallback for edge cases if MSB was ever used
            data = self.bp.read_register(self.addr_w, self.addr_r, command, length=2)
            if data and len(data) == 2:
                val = (data[0] << 8) | data[1]
                return val, f"0x{val:04X}"
            return None, None
        return self.read_data(command, data_type='uint16')

    def get_voltage(self):
        """
        Using 0x08 for voltage polling as requested.
        Returns unsigned voltage.
        """
        return self.read_data(0x08, data_type='uint16')

    def get_current(self):
        """
        Using raw I2C sequential memory pointer (Stop-Start), Current is mapped to 0x0C.
        Returns signed current in mA.
        """
        return self.read_data(0x0C, data_type='int16')

    def reset(self):
        """
        Sends the RESET MAC subcommand (0x0041) to the BQ28Z620.
        Writes 0x0041 (little-endian: [0x41, 0x00]) to ManufacturerAccess register 0x00.
        Returns True if the write was issued successfully.
        """
        return self.bp.write_register(self.addr_w, 0x00, [0x41, 0x00])

    def read_mac_subcommand(self, subcmd, length=4):
        """
        Reads data from a MAC subcommand.
        1. Writes the 2-byte subcommand (little-endian) to ManufacturerAccess (0x00).
        2. Waits briefly for the device to populate MACData.
        3. Reads 'length' bytes from MACData register (0x23).
        Returns the raw bytes as a list, or None on failure.
        """
        low = subcmd & 0xFF
        high = (subcmd >> 8) & 0xFF
        success = self.bp.write_register(self.addr_w, 0x00, [low, high])
        if not success:
            return None
        time.sleep(0.05)
        data = self.bp.read_register(self.addr_w, self.addr_r, 0x23, length=length)
        return data

    def get_battery_status(self):
        """
        Reads BatteryStatus register 0x0A (uint16).
        Returns (raw_value, hex_string) or (None, None).
        """
        return self.read_data(0x0a, data_type='uint16')

    def get_safety_alert(self):
        """
        Reads SafetyAlert via MAC subcommand 0x0050 (4 bytes / uint32).
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0050, length=4)
        if data and len(data) == 4:
            val = self.bytes_to_uint_le(data)
            return val, f"0x{val:08X}"
        return None, None

    def get_safety_status(self):
        """
        Reads SafetyStatus via MAC subcommand 0x0051 (4 bytes / uint32).
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0051, length=4)
        if data and len(data) == 4:
            val = self.bytes_to_uint_le(data)
            return val, f"0x{val:08X}"
        return None, None

    @staticmethod
    def parse_bits(raw_value, bit_map):
        """
        Given a raw integer value and a bit_map {bit_position: name},
        returns a dict of {name: bool} indicating whether each bit is set.
        """
        if raw_value is None:
            return {name: False for name in bit_map.values()}
        return {name: bool(raw_value & (1 << bit)) for bit, name in bit_map.items()}
