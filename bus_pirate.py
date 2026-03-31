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

    def connect(self, clock_khz=10):
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
            
            # Send Ctrl+C and Enter to clear any hanging menus
            self.send_command("\x03\r\n\r\n")
            
            # Determine I2C mode from your specific Bus Pirate menu
            # 1. Open Mode menu
            self.send_command("m")
            # 2. Select I2C (Option 5)
            self.send_command("5")
            # 3. Discard previous broken settings (which were stuck at 0kHz)
            self.send_command("n")
            # 4. Set clock rate
            self.send_command(str(clock_khz))
            time.sleep(0.5)
        

            # Bus Pirate 5/6 settings for I2C usually default to 400kHz.
            
            # Enable Bus Pirate 1.8V power supply and Pullups
            self.send_command("W")
            time.sleep(0.1)
            self.send_command("1.8")# Enable power
            time.sleep(0.1)
            self.send_command("\r")
            time.sleep(0.1)
            self.send_command("P") # Enable pullups
            time.sleep(0.1)

            self.connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.connected = False
            return False, f"Failed to connect: {str(e)}"

    def disconnect(self):
        if self.serial and self.serial.is_open:
            # Turn off power and pullups safely
            self.send_command("p")
            self.send_command("w")
            self.send_command("m 1") # HiZ
            
            self.serial.close()
        self.connected = False

    def send_command(self, cmd, wait_for_response=True):
        if not self.serial or not self.serial.is_open:
            return ""
        
        # Add a slight delay before writing and write cmd
        self.serial.write((cmd + "\r\n").encode('utf-8'))
        
        if wait_for_response:
            response = ""
            start = time.time()
            # Wait until > or I2C> prompt returns indicating command completion
            while time.time() - start < 1.0:
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
        # We split the response into lines and only parse lines that look like read data 
        # (e.g., lines containing RX:, READ:, or lines after the echoed brackets)
        
        if not response:
            return None

        # Clean up response and extract the final line or data
        hex_pattern = re.compile(r'0x[0-9a-fA-F]{2}', re.IGNORECASE)
        data_strs = []
        for line in response.split('\n'):
            line = line.strip().upper()
            
            # Bus Pirate 5/6 prints ANSI color codes (e.g. \x1b[32m) which contain `[` characters!
            # Instead of trying to filter out the command echo using `[`, we just explicitly 
            # only extract hex values from lines containing "RX:" or "READ".
            if "RX:" in line or "READ" in line:
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
        self.send_command(cmd)
        return True
