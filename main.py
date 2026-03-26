import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
import time
import json
import os
from datetime import datetime
from bus_pirate import BusPirate
from bq28z620 import BQ28z620, BATTERY_STATUS_BITS, SAFETY_ALERT_BITS, SAFETY_STATUS_BITS

CONFIG_FILE = "config.json"
POLL_RATE = 100  # ms

# Colors for bit status indicators
COLOR_ACTIVE = "#22c55e"    # green
COLOR_INACTIVE = "#6b7280"  # gray

class FuelGaugeDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BQ28Z620 Fuel Gauge Dashboard")
        self.geometry("550x600")
        
        self.bp = None
        self.bq = None
        self.is_polling = False

        # Toggle vars for status registers
        self.show_battery_status = tk.BooleanVar(value=False)
        self.show_safety_alert = tk.BooleanVar(value=False)
        self.show_safety_status = tk.BooleanVar(value=False)

        # Label references for status bit displays
        self.status_bit_labels = {}

        # Logging state
        self.is_logging = False
        self.log_entries = []
        self.prev_status = {}  # tracks previous bit values for change detection
        
        self.setup_ui()
        
        # Schedule auto-connect shortly after UI loads
        self.after(100, lambda: self.connect(silent=True))
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, config_data):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config_data, f)
        except Exception:
            pass

    def setup_ui(self):
        # COM Port Selection
        frame_top = ttk.LabelFrame(self, text="Connection")
        frame_top.pack(padx=10, pady=10, fill="x")
        
        ttk.Label(frame_top, text="Select COM Port:").pack(side="left", padx=5, pady=5)
        
        self.port_var = tk.StringVar()
        self.port_dropdown = ttk.Combobox(frame_top, textvariable=self.port_var, state="readonly", width=20)
        self.port_dropdown.pack(side="left", padx=5, pady=5)
        self.refresh_ports()
        
        ttk.Button(frame_top, text="Refresh", command=self.refresh_ports).pack(side="left", padx=5, pady=5)
        
        self.btn_connect = ttk.Button(frame_top, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=5, pady=5)
        
        # Values Display
        frame_bot = ttk.LabelFrame(self, text="BQ28Z620 Live Metrics")
        frame_bot.pack(padx=10, pady=10, fill="both", expand=True)
        
        ttk.Label(frame_bot, text="Voltage:", font=("Helvetica", 14, "bold")).grid(row=0, column=0, sticky="w", padx=20, pady=20)
        self.lbl_voltage = ttk.Label(frame_bot, text="---", font=("Helvetica", 14))
        self.lbl_voltage.grid(row=0, column=1, sticky="w", padx=20, pady=20)
        
        ttk.Label(frame_bot, text="Current:", font=("Helvetica", 14, "bold")).grid(row=1, column=0, sticky="w", padx=20, pady=20)
        self.lbl_current = ttk.Label(frame_bot, text="---", font=("Helvetica", 14))
        self.lbl_current.grid(row=1, column=1, sticky="w", padx=20, pady=20)

        # Commands
        frame_cmd = ttk.LabelFrame(self, text="Commands")
        frame_cmd.pack(padx=10, pady=5, fill="x")

        self.btn_reset = ttk.Button(frame_cmd, text="Reset BQ28Z620", command=self.send_reset)
        self.btn_reset.pack(side="left", padx=10, pady=5)

        self.btn_log = ttk.Button(frame_cmd, text="Start Log", command=self.toggle_logging)
        self.btn_log.pack(side="left", padx=10, pady=5)

        # Status Register Toggles
        frame_toggles = ttk.LabelFrame(self, text="Status Registers")
        frame_toggles.pack(padx=10, pady=5, fill="x")

        ttk.Checkbutton(frame_toggles, text="Battery Status",
                        variable=self.show_battery_status,
                        command=self.rebuild_status_display).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Safety Alert",
                        variable=self.show_safety_alert,
                        command=self.rebuild_status_display).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Safety Status",
                        variable=self.show_safety_status,
                        command=self.rebuild_status_display).pack(side="left", padx=10, pady=5)

        # Scrollable status display area
        self.status_frame = ttk.Frame(self)
        self.status_frame.pack(padx=10, pady=5, fill="both", expand=True)

    def rebuild_status_display(self):
        """Rebuild the status bit display based on which registers are toggled on."""
        # Clear existing widgets
        for widget in self.status_frame.winfo_children():
            widget.destroy()
        self.status_bit_labels.clear()

        row = 0
        if self.show_battery_status.get():
            row = self._build_register_section(
                "Battery Status (0x0A)", BATTERY_STATUS_BITS, "bat", row)

        if self.show_safety_alert.get():
            row = self._build_register_section(
                "Safety Alert (0x0050)", SAFETY_ALERT_BITS, "sa", row)

        if self.show_safety_status.get():
            row = self._build_register_section(
                "Safety Status (0x0051)", SAFETY_STATUS_BITS, "ss", row)

    def _build_register_section(self, title, bit_map, prefix, start_row):
        """Build a labeled grid of bit indicators for one register."""
        ttk.Label(self.status_frame, text=title,
                  font=("Helvetica", 10, "bold")).grid(
            row=start_row, column=0, columnspan=8, sticky="w", padx=5, pady=(8, 2))
        
        # Raw hex value label
        hex_key = f"{prefix}_hex"
        hex_lbl = ttk.Label(self.status_frame, text="---", font=("Helvetica", 9))
        hex_lbl.grid(row=start_row, column=8, columnspan=2, sticky="e", padx=5)
        self.status_bit_labels[hex_key] = hex_lbl

        row = start_row + 1
        col = 0
        # Sort bits by position descending for a natural MSB-first layout
        for bit_pos in sorted(bit_map.keys(), reverse=True):
            name = bit_map[bit_pos]
            lbl = tk.Label(self.status_frame, text=name, fg=COLOR_INACTIVE,
                           font=("Consolas", 9, "bold"), width=6, anchor="center")
            lbl.grid(row=row, column=col, padx=2, pady=1)
            self.status_bit_labels[f"{prefix}_{bit_pos}"] = lbl
            col += 1
            if col >= 8:
                col = 0
                row += 1

        if col != 0:
            row += 1
        return row

    def _update_bit_labels(self, prefix, raw_value, bit_map, hex_str):
        """Update the color of each bit label based on the raw register value."""
        hex_key = f"{prefix}_hex"
        if hex_key in self.status_bit_labels:
            self.status_bit_labels[hex_key].config(
                text=hex_str if hex_str else "Err")

        bits = BQ28z620.parse_bits(raw_value, bit_map)
        for bit_pos, name in bit_map.items():
            key = f"{prefix}_{bit_pos}"
            if key in self.status_bit_labels:
                active = bits[name]
                self.status_bit_labels[key].config(
                    fg=COLOR_ACTIVE if active else COLOR_INACTIVE)

            # Log state changes
            if self.is_logging:
                log_key = f"{prefix}.{name}"
                prev = self.prev_status.get(log_key)
                if prev is not None and prev != active:
                    ts = datetime.now().isoformat(timespec='milliseconds')
                    state_str = "ACTIVE" if active else "INACTIVE"
                    self.log_entries.append(f"{ts}  {log_key:<20s}  -> {state_str}")
                self.prev_status[log_key] = active

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = [f"{port.device} - {port.description}" for port in ports]
        self.port_dropdown['values'] = port_list
        
        config = self.load_config()
        last_port = config.get("last_port", "")
        
        for p in port_list:
            if p.startswith(last_port + " -") or p == last_port:
                self.port_dropdown.set(p)
                return
                
        if port_list:
            self.port_dropdown.set(port_list[0])
            
    def toggle_connection(self):
        if self.bp and self.bp.connected:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self, silent=False):
        selection = self.port_var.get()
        if not selection:
            if not silent:
                messagebox.showerror("Error", "Please select a COM port")
            return
            
        port = selection.split(" - ")[0]
        
        config = self.load_config()
        config["last_port"] = port
        self.save_config(config)
            
        self.bp = BusPirate(port)
        success, msg = self.bp.connect()
        
        if success:
            self.btn_connect.config(text="Disconnect")
            self.bq = BQ28z620(self.bp)
            self.is_polling = True
            self.poll_data()
        else:
            if not silent:
                messagebox.showerror("Connection Error", msg)
            
    def disconnect(self):
        self.is_polling = False
        if self.bp:
            self.bp.disconnect()
        self.btn_connect.config(text="Connect")
        self.lbl_voltage.config(text="---")
        self.lbl_current.config(text="---")

    def send_reset(self):
        """Send a RESET command to the BQ28Z620."""
        if not self.bq:
            return

        self.is_polling = False
        self.bq.reset()
        # Resume polling after a brief delay to let the device restart
        self.after(2000, self._resume_polling)

    def _resume_polling(self):
        """Resume data polling after a reset."""
        if self.bp and self.bp.connected:
            self.is_polling = True
            self.poll_data()

    def toggle_logging(self):
        """Toggle status change logging on/off."""
        if self.is_logging:
            self.stop_logging()
        else:
            self.start_logging()

    def start_logging(self):
        """Begin logging status changes."""
        self.log_entries = []
        self.prev_status = {}  # reset so first poll establishes baseline
        self.is_logging = True
        self.btn_log.config(text="Stop Log")

    def stop_logging(self):
        """Stop logging and write entries to a file in the logs/ directory."""
        self.is_logging = False
        self.btn_log.config(text="Start Log")

        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)

        filename = datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + "_status_log.txt"
        filepath = os.path.join(log_dir, filename)

        with open(filepath, 'w') as f:
            f.write(f"BQ28Z620 Status Change Log\n")
            f.write(f"Created: {datetime.now().isoformat()}\n")
            f.write(f"{'=' * 60}\n\n")
            if self.log_entries:
                for entry in self.log_entries:
                    f.write(entry + "\n")
            else:
                f.write("No status changes detected during this session.\n")

        self.log_entries = []
            
    def poll_data(self):
        if not self.is_polling:
            return
            
        if self.bp and self.bp.connected and self.bq:
            delay = 0.05
            
            # Read Voltage
            val, hex_str = self.bq.get_voltage()
            self.lbl_voltage.config(text=f"{val} mV  ({hex_str})" if val is not None else "Err")
            self.update()
            time.sleep(delay)
                
            # Read Current
            val, hex_str = self.bq.get_current()
            self.lbl_current.config(text=f"{val} mA  ({hex_str})" if val is not None else "Err")
            self.update()
            time.sleep(delay)

            # Read toggled status registers
            if self.show_battery_status.get():
                val, hex_str = self.bq.get_battery_status()
                self._update_bit_labels("bat", val, BATTERY_STATUS_BITS, hex_str)
                self.update()
                time.sleep(delay)

            if self.show_safety_alert.get():
                val, hex_str = self.bq.get_safety_alert()
                self._update_bit_labels("sa", val, SAFETY_ALERT_BITS, hex_str)
                self.update()
                time.sleep(delay)

            if self.show_safety_status.get():
                val, hex_str = self.bq.get_safety_status()
                self._update_bit_labels("ss", val, SAFETY_STATUS_BITS, hex_str)
                self.update()
                time.sleep(delay)
                
        # Schedule next poll
        self.after(POLL_RATE, self.poll_data)

if __name__ == "__main__":
    app = FuelGaugeDashboard()
    app.mainloop()
