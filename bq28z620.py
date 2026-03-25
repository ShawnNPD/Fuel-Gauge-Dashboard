class BQ28z620:
    def __init__(self, bus_pirate, i2c_addr_write=0xAA, i2c_addr_read=0xAB):
        self.bp = bus_pirate
        self.addr_w = i2c_addr_write
        self.addr_r = i2c_addr_read

    def read_word(self, command, endian='little'):
        """
        Standard SMBus strictly dictates Little Endian format (LSB transmitted first).
        Reads a 16-bit word from the given command code.
        """
        data = self.bp.read_register(self.addr_w, self.addr_r, command, length=2)
        if data and len(data) == 2:
            if endian == 'little':
                # LSB transmitted first
                val = (data[1] << 8) | data[0]
            else:
                # MSB transmitted first
                val = (data[0] << 8) | data[1]
            hex_str = f"0x{val:04X}"
            return val, hex_str
        return None, None

    def get_voltage(self):
        """
        Using 0x08 for voltage polling as requested.
        Returns unsigned voltage.
        """
        val, hex_str = self.read_word(0x08, endian='little')
        return val, hex_str

    def get_current(self):
        """
        Using raw I2C sequential memory pointer (Stop-Start), Current is mapped to 0x0C.
        Returns signed current in mA.
        """
        val, hex_str = self.read_word(0x0C, endian='little')
        if val is not None:
            # Current is signed (Two's Complement)
            # Positive = Charging, Negative = Discharging
            if val & 0x8000:
                val -= 0x10000
        return val, hex_str
