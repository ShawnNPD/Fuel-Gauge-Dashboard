import serial
import time
import re

class BusPirate:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self.connected = False

    def connect(self, clock_khz=10, enable_power=False):
        try:
            for attempt in range(5):
                try:
                    self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                    time.sleep(1.5)
                    self.serial.reset_input_buffer()
                    self.serial.reset_output_buffer()
                    break
                except serial.SerialException as e:
                    if attempt < 4:
                        time.sleep(2.0)
                    else:
                        raise e
            
            # 1. Stabilization and Fast Identification
            # Send an empty line to trigger any prompt like 'VT100 compatible color mode? (Y/n)>'
            self.serial.write(b"\r\n")
            time.sleep(0.3)
            resp = b""
            if self.serial.in_waiting:
                resp = self.serial.read(self.serial.in_waiting)
            if b"VT100" in resp:
                self.serial.write(b"n\r\n")
                time.sleep(0.1)

            # Send Ctrl+C multiple times to break out of any sub-menus or help screens
            for _ in range(2):
                self.serial.write(b"\x03\r\n")
                time.sleep(0.1)
                
            self.serial.reset_input_buffer()
            is_bp, resp = self.identify(timeout=1.0)
            if not is_bp:
                self.serial.close()
                return False, "Device is not responding as a Bus Pirate. Please verify the COM port or reset the hardware."

            # Ensure we have a clean slate
            self.send_command("\x03\r\n", timeout=0.5)
            self.serial.reset_input_buffer()
            
            # 2. Configure I2C Mode
            # 1. Open Mode menu
            self.send_command("m", timeout=0.5)
            # 2. Select I2C (Option 5)
            resp_mode = self.send_command("5", timeout=0.5)
            
            # 3. Handle optional 'Discard settings? (y/n)' prompt which occurs if 
            # I2C was already configured with different settings.
            if "y/n" in resp_mode.lower() or "discard" in resp_mode.lower():
                self.send_command("n", timeout=0.5)
            
            # 4. Set clock rate (e.g., 400kHz, 100kHz, or custom)
            self.send_command(str(clock_khz), timeout=0.5)
            time.sleep(0.5)
        

            # Bus Pirate 5/6 settings for I2C usually default to 400kHz.
            
            # Optionally enable Bus Pirate 1.8V power supply and Pullups
            if enable_power:
                self.send_command("W", timeout=0.5)
                time.sleep(0.1)
                self.send_command("1.8", timeout=0.5)# Enable power
                time.sleep(0.1)
                self.send_command("\r", timeout=0.5)
                time.sleep(0.1)
                self.send_command("P", timeout=0.5) # Enable pullups
                time.sleep(0.1)

            self.connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.connected = False
            return False, f"Failed to connect: {str(e)}"

    def toggle_power_pullups(self, enable=True):
        if not self.serial or not self.serial.is_open:
            return False, "Not connected"
            
        if enable:
            self.send_command("W")
            time.sleep(0.1)
            self.send_command("1.8")
            time.sleep(0.1)
            self.send_command("\r")
            time.sleep(0.1)
            self.send_command("P")
            time.sleep(0.1)
            return True, "Enabled"
        else:
            self.send_command("p")
            time.sleep(0.1)
            self.send_command("w")
            time.sleep(0.1)
            return True, "Disabled"

    def disconnect(self):
        if self.serial and self.serial.is_open:
            # Turn off power and pullups safely
            self.send_command("p", timeout=0.2)
            self.send_command("w", timeout=0.2)
            self.send_command("m 1", timeout=0.2) # HiZ
            
            self.serial.close()
        self.connected = False

    def identify(self, timeout=0.5):
        """
        Quickly check if the connected device is a Bus Pirate.
        Returns (True, prompt) if successful, (False, last_response) otherwise.
        """
        if not self.serial or not self.serial.is_open:
            return False, "Serial port not open"
            
        self.serial.reset_input_buffer()
        # Send a carriage return to trigger the prompt re-printing
        response = self.send_command("", timeout=timeout)
        
        # Look for the common Bus Pirate prompt '>' or the specific 'I2C>' / 'HiZ>' / 'BP5>'
        if ">" in response:
            return True, response
        return False, response

    def send_command(self, cmd, wait_for_response=True, timeout=1.0):
        if not self.serial or not self.serial.is_open:
            return ""
        
        # Add a slight delay before writing and write cmd
        self.serial.write((cmd + "\r\n").encode('utf-8'))
        
        if wait_for_response:
            response = ""
            start = time.time()
            # Wait until > or I2C> prompt returns indicating command completion
            while time.time() - start < timeout:
                if self.serial.in_waiting:
                    response += self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                if ">" in response:
                    # Give it a tiny bit more time for any trailing bytes immediately after prompt
                    time.sleep(0.01)
                    if self.serial.in_waiting:
                        response += self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                    break
                time.sleep(0.01)
            return response
        return ""

    def read_register(self, write_addr, read_addr, reg, length=2, pre_write_bytes=None, pre_write_delay_ms=50):
        """
        Executes an I2C write then read using Stop-Start (not Repeated Start):
        [ write_addr reg ] [ read_addr r:length ]
        E.g.: [ 0xAA 0x1D ] [ 0xAB r:2 ]
        """
        if not self.connected:
            return None
        
        # Flush input buffer to avoid stale data
        self.serial.reset_input_buffer()
        
        response = ""
        if pre_write_bytes:
            pre_str = " ".join([hex(b) for b in pre_write_bytes])
            write_cmd = f"[ {hex(write_addr)} {pre_str} ]"
            response += self.send_command(write_cmd)
            time.sleep(pre_write_delay_ms / 1000.0)
            self.serial.reset_input_buffer()
            
        # Ensure safe STOP-START syntax is used because the BP firmware definitively drops the bus on Repeated Starts
        cmd = f"[ {hex(write_addr)} {hex(reg)} ] [ {hex(read_addr)} r:{length} ]"
        response += self.send_command(cmd)

        if reg == 0x1D or reg == 0x15:
            print(f"DEBUG READ {hex(reg)}:\n{response}\n---")

        # Look for hex values. We must ignore the first parts of the response which is 
        # the Bus Pirate echoing the `[ 0xAA 0x1D [ 0xAB R:2 ]` command we just sent.
        
        if not response or "I2C ERROR" in response.upper():
            return None
            
        # Clean up response and extract the final line or data

        # Clean up response and extract the final line or data
        hex_pattern = re.compile(r'0x[0-9a-fA-F]{2}', re.IGNORECASE)
        data_strs = []
        parsing_rx = False
        
        for line in response.split('\n'):
            line = line.strip().upper()
            
            if "RX" in line or "READ" in line:
                parsing_rx = True
            elif ("TX" in line or "WRITE" in line or "STOP" in line or 
                  line.startswith(">") or line.startswith("[")):
                if not ("RX" in line or "READ" in line):
                    parsing_rx = False
                
            if parsing_rx:
                matches = hex_pattern.findall(line)
                if matches:
                    data_strs.extend(matches)
                
        if len(data_strs) >= length:
            data_strs = data_strs[-length:]
            try:
                data = [int(x, 16) for x in data_strs]
                return data
            except ValueError:
                return None
        return None

    def write_register(self, write_addr, reg, data_bytes):
        """
        Executes an I2C write sequence.
        """
        if not self.connected:
            return False
            
        self.serial.reset_input_buffer()
        data_str = " ".join([hex(b) for b in data_bytes])
        cmd = f"[ {hex(write_addr)} {hex(reg)} {data_str} ]"
        response = self.send_command(cmd)
        
        if not response or "I2C ERROR" in response.upper():
            return False
        return True
