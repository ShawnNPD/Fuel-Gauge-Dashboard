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
