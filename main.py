import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
import time
import json
import os
from bus_pirate import BusPirate
from bq28z620 import BQ28z620

CONFIG_FILE = "config.json"
POLL_RATE = 100  # ms

class FuelGaugeDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BQ28Z620 Fuel Gauge Dashboard")
        self.geometry("450x350")
        
        self.bp = None
        self.bq = None
        self.is_polling = False
        
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
                
        # Schedule next poll once per second (1000ms)
        self.after(POLL_RATE, self.poll_data)

if __name__ == "__main__":
    app = FuelGaugeDashboard()
    app.mainloop()
