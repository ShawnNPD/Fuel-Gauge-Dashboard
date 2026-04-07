import time


# Bit definitions sourced from BQ28Z620-Status-Regs.csv
# Format: {bit_position: (abbreviation, high_state_meaning, low_state_meaning)}

# BatteryStatus register 0x0A (16-bit, SBS standard layout)
BATTERY_STATUS_BITS = {
    15: ("OCA",  "Over Charge Alarm",          "No Alarm"),
    14: ("TCA",  "Terminate Charge Alarm",     "No Alarm"),
    12: ("OTA",  "Over Temp Alarm",            "No Alarm"),
    11: ("TDA",  "Terminate Discharge Alarm",  "No Alarm"),
     9: ("RCA",  "Remaining Capacity Alarm",   "No Alarm"),
     8: ("RTA",  "Remaining Time Alarm",       "No Alarm"),
     7: ("INIT", "Initialized",                "Not Initialized"),
     6: ("DSG",  "Discharging",                "Charging"),
     5: ("FC",   "Fully Charged",              "Not Full"),
     4: ("FD",   "Fully Depleted",             "OK"),
     3: ("EC3",  "Error",                      "OK"),
     2: ("EC2",  "Error",                      "OK"),
     1: ("EC1",  "Error",                      "OK"),
     0: ("EC0",  "Error",                      "OK"),
}

# SafetyAlert MAC 0x0050 (32-bit: bytes A+B = bits 0-15, C+D = bits 16-31)
SAFETY_ALERT_BITS = {
     2: ("CUV",  "Cell Undervoltage",          "Not Detected"),
     3: ("COV",  "Cell Overvoltage",           "Not Detected"),
     4: ("OCC",  "Overcurrent Charge",         "Not Detected"),
     5: ("OCD",  "Overcurrent Discharge",      "Not Detected"),
     6: ("AOLD", "Overload Discharge",         "Not Detected"),
     7: ("ASCC", "Short-Circuit Charge",       "Not Detected"),
     8: ("ASCD", "Short-Circuit Discharge",    "Not Detected"),
    10: ("OTC",  "Overtemp Charge",            "Not Detected"),
    11: ("OTD",  "Overtemp Discharge",         "Not Detected"),
    20: ("PTOS", "Precharge Timeout Suspend",  "Not Detected"),
    21: ("CTOS", "Charge Timeout Suspend",     "Not Detected"),
    26: ("UTC",  "Undertemp Charge",           "Not Detected"),
    27: ("UTD",  "Undertemp Discharge",        "Not Detected"),
}

# SafetyStatus MAC 0x0051 (32-bit: same bit layout as SafetyAlert)
SAFETY_STATUS_BITS = {
     2: ("CUV",  "Cell Undervoltage",          "Not Detected"),
     3: ("COV",  "Cell Overvoltage",           "Not Detected"),
     4: ("OCC",  "Overcurrent Charge",         "Not Detected"),
     5: ("OCD",  "Overcurrent Discharge",      "Not Detected"),
     6: ("AOLD", "Overload Discharge",         "Not Detected"),
     7: ("ASCC", "Short-Circuit Charge",       "Not Detected"),
     8: ("ASCD", "Short-Circuit Discharge",    "Not Detected"),
    10: ("OTC",  "Overtemp Charge",            "Not Detected"),
    11: ("OTD",  "Overtemp Discharge",         "Not Detected"),
    20: ("PTO",  "Precharge Timeout",          "Not Detected"),
    21: ("CTO",  "Charge Timeout",             "Not Detected"),
    26: ("UTC",  "Undertemp Charge",           "Not Detected"),
    27: ("UTD",  "Undertemp Discharge",        "Not Detected"),
}

# PFAlert MAC 0x0052 (32-bit: bytes A+B = bits 0-15, C+D = bits 16-31)
PF_ALERT_BITS = {
     0: ("SUV",   "Safety Cell Undervoltage",   "Not Detected"),
     1: ("SOV",   "Safety Cell Overvoltage",    "Not Detected"),
     4: ("VIMR",  "Voltage Imbalance Rest",     "Not Detected"),
     5: ("VIMA",  "Voltage Imbalance Active",   "Not Detected"),
    16: ("CFETF", "Charge FET Failure",         "Not Detected"),
    17: ("DFETF", "Discharge FET Failure",      "Not Detected"),
}

# PFStatus MAC 0x0053 (32-bit: same layout as PFAlert)
PF_STATUS_BITS = {
     0: ("SUV",   "Safety Cell Undervoltage",   "Not Detected"),
     1: ("SOV",   "Safety Cell Overvoltage",    "Not Detected"),
     4: ("VIMR",  "Voltage Imbalance Rest",     "Not Detected"),
     5: ("VIMA",  "Voltage Imbalance Active",   "Not Detected"),
    16: ("CFETF", "Charge FET Failure",         "Not Detected"),
    17: ("DFETF", "Discharge FET Failure",      "Not Detected"),
}

# OperationStatus MAC 0x0054 (32-bit: B-byte = bits 16-31, A-byte = bits 0-15)
OPERATION_STATUS_BITS = {
    29: ("EMSHUT",     "Emerg FET Shutdown",             "Inactive"),
    28: ("CB",         "Cell Balancing Active",          "Inactive"),
    27: ("SLPCC",      "CC meas in SLEEP",               "Inactive"),
    26: ("SLPAD",      "ADC meas in SLEEP",              "Inactive"),
    25: ("SMBLCAL",    "Auto-offset cal bus low",        "Inactive"),
    24: ("INIT",       "Init after full reset",          "Inactive"),
    23: ("SLEEPM",     "SLEEP mode",                     "Inactive"),
    22: ("XL",         "400-kHz mode",                   "Inactive"),
    21: ("CAL_OFFSET", "Cal Output (raw CC Offset)",     "Inactive"),
    20: ("CAL",        "Cal Output (raw ADC & CC)",      "Inactive"),
    19: ("AUTHCALM",   "Auto CC Offset Cal",             "Inactive"),
    18: ("AUTH",       "Authentication in prog",         "Inactive"),
    16: ("SDM",        "SHUTDOWN cmd triggered",         "Inactive"),
    15: ("SLEEP",      "SLEEP conditions met",           "Inactive"),
    14: ("SEC1_H",     "SEC_H[1]=1",                     "SEC_H[1]=0"),
    13: ("SEC0_H",     "SEC_H[0]=1",                     "SEC_H[0]=0"),
    12: ("PF",         "Permanent Failure Mode",         "Inactive"),
    11: ("SS",         "Safety Mode Active",             "Inactive"),
    10: ("SDV",        "SHUTDOWN low pack vol",          "Inactive"),
     9: ("SEC1_L",     "SEC_L[1]=1",                     "SEC_L[1]=0"),
     8: ("SEC0_L",     "SEC_L[0]=1",                     "SEC_L[0]=0"),
     2: ("CHG",        "CHG Active",                     "CHG Inactive"),
     1: ("DSG",        "DSG Active",                     "DSG Inactive"),
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

    def read_mac_subcommand(self, subcmd):
        """
        Reads data from a MAC subcommand.
        1. Writes the 2-byte subcommand (little-endian) to MACSubcmd register (0x3E).
        2. Waits briefly for the device to populate MACData.
        3. Reads MACDataLength from register 0x61 to determine response size.
        4. Reads that exact number of bytes from MACData register (0x40).
        Returns the data bytes as a list, or None on failure.
        """
        low = subcmd & 0xFF
        high = (subcmd >> 8) & 0xFF
        success = self.bp.write_register(self.addr_w, 0x3E, [low, high])
        if not success:
            return None
        time.sleep(0.05)

        # Read MACDataLength from 0x61
        len_data = self.bp.read_register(self.addr_w, self.addr_r, 0x61, length=1)
        if not len_data:
            return None
        mac_data_len = len_data[0]
        if mac_data_len <= 4:
            return None

        # Read MACData from 0x40. Total length includes 2-byte echo + 2-byte footer.
        # Register 0x40 starts at data, so reading (len - 4) gets only the data.
        data = self.bp.read_register(self.addr_w, self.addr_r, 0x40, length=mac_data_len - 4)
        if not data or len(data) < (mac_data_len - 4):
            return None

        return data

    def get_battery_status(self):
        """
        Reads BatteryStatus register 0x0A (uint16).
        Returns (raw_value, hex_string) or (None, None).
        """
        return self.read_data(0x0a, data_type='uint16')

    def get_safety_alert(self):
        """
        Reads SafetyAlert via MAC subcommand 0x0050.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0050)
        if data and len(data) >= 4:
            val = self.bytes_to_uint_le(data[:4])
            return val, f"0x{val:08X}"
        return None, None

    def get_safety_status(self):
        """
        Reads SafetyStatus via MAC subcommand 0x0051.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0051)
        if data and len(data) >= 4:
            val = self.bytes_to_uint_le(data[:4])
            return val, f"0x{val:08X}"
        return None, None

    def get_pf_alert(self):
        """
        Reads PFAlert via MAC subcommand 0x0052.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0052)
        if data and len(data) >= 4:
            val = self.bytes_to_uint_le(data[:4])
            return val, f"0x{val:08X}"
        return None, None

    def get_pf_status(self):
        """
        Reads PFStatus via MAC subcommand 0x0053.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0053)
        if data and len(data) >= 4:
            val = self.bytes_to_uint_le(data[:4])
            return val, f"0x{val:08X}"
        return None, None

    def get_operation_status(self):
        """
        Reads OperationStatus via MAC subcommand 0x0054.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0054)
        if data and len(data) >= 4:
            val = self.bytes_to_uint_le(data[:4])
            return val, f"0x{val:08X}"
        return None, None

    def pf_reset(self):
        """
        Sends PF_RESET MAC subcommand (0x0029) to clear permanent failures.
        """
        return self.bp.write_register(self.addr_w, 0x3E, [0x29, 0x00])

    def toggle_chg_fet(self):
        """Toggle the Charge FET via MAC subcommand 0x001F."""
        return self.bp.write_register(self.addr_w, 0x3E, [0x1F, 0x00])

    def toggle_dsg_fet(self):
        """Toggle the Discharge FET via MAC subcommand 0x0020."""
        return self.bp.write_register(self.addr_w, 0x3E, [0x20, 0x00])

    def get_manufacturing_status(self):
        """
        Reads ManufacturingStatus via MAC subcommand 0x0057.
        Returns (raw_value, hex_string) or (None, None).
        """
        data = self.read_mac_subcommand(0x0057)
        if data and len(data) >= 2:
            val = self.bytes_to_uint_le(data[:2])
            return val, f"0x{val:04X}"
        return None, None

    def toggle_fet_control(self):
        """Toggle FET control via MAC subcommand 0x0022."""
        return self.bp.write_register(self.addr_w, 0x3E, [0x22, 0x00])

    @staticmethod
    def parse_bits(raw_value, bit_map):
        """
        Given a raw integer value and a bit_map {bit_position: (name, high_text, low_text)},
        returns a dict of {name: (is_active, display_text)}.
        """
        if raw_value is None:
            return {entry[0]: (False, entry[2])
                    for entry in bit_map.values()}
        result = {}
        for bit, (name, high_text, low_text) in bit_map.items():
            active = bool(raw_value & (1 << bit))
            result[name] = (active, high_text if active else low_text)
        return result
