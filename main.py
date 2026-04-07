import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
import time
import threading
import json
import os
from datetime import datetime
from bus_pirate import BusPirate
from bq28z620 import BQ28z620, BATTERY_STATUS_BITS, SAFETY_ALERT_BITS, SAFETY_STATUS_BITS, PF_ALERT_BITS, PF_STATUS_BITS, OPERATION_STATUS_BITS

CONFIG_FILE = "config.json"
POLL_RATE = 5  # ms

# Colors for bit status indicators
COLOR_ACTIVE = "#22c55e"    # green
COLOR_INACTIVE = "#6b7280"  # gray

class FuelGaugeDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BQ28Z620 Fuel Gauge Dashboard")
        self.geometry("1370x1024")
        self.pack_propagate(False)
        
        self.bp = None
        self.bq = None
        self.is_polling = False
        self.power_enabled = True
        self.fet_ctrl_enabled = False
        self.consecutive_errors = 0
        self.error_threshold = 5

        # Toggle vars for polling
        self.poll_voltage_current = tk.BooleanVar(value=True)

        # Toggle vars for status registers
        self.show_battery_status = tk.BooleanVar(value=True)
        self.show_safety_alert = tk.BooleanVar(value=True)
        self.show_safety_status = tk.BooleanVar(value=True)
        self.show_pf_alert = tk.BooleanVar(value=True)
        self.show_pf_status = tk.BooleanVar(value=True)
        self.show_operation_status = tk.BooleanVar(value=True)

        # Label references for status bit displays
        self.status_bit_labels = {}

        # Logging state
        self.is_logging = False
        self.log_entries = []
        self.prev_status = {}  # tracks previous bit values for change detection
        
        self.setup_ui()
        self.rebuild_status_display()

        # Spacebar toggles connect/disconnect
        # self.bind("<space>", lambda e: self.toggle_connection())
        
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

        self.btn_power = ttk.Button(frame_top, text="Disable Power", command=self.toggle_power)
        self.btn_power.pack(side="left", padx=5, pady=5)

        ttk.Separator(frame_top, orient="vertical").pack(side="left", padx=5, fill="y", pady=5)

        ttk.Label(frame_top, text="I2C Clock (kHz):").pack(side="left", padx=5, pady=5)
        config = self.load_config()
        self.clock_var = tk.StringVar(value=str(config.get("clock_khz", 10)))
        self.clock_entry = ttk.Entry(frame_top, textvariable=self.clock_var, width=6)
        self.clock_entry.pack(side="left", padx=2, pady=5)
        ttk.Button(frame_top, text="Set Clock", command=self.set_clock).pack(side="left", padx=5, pady=5)

        self.lbl_bus_status = ttk.Label(frame_top, text="Bus: Connected", foreground=COLOR_ACTIVE, font=("Helvetica", 10, "bold"))
        self.lbl_bus_status.pack(side="left", padx=10, pady=5)
        
        # Values Display
        frame_bot = ttk.LabelFrame(self, text="BQ28Z620 Live Metrics")
        frame_bot.pack(padx=10, pady=10, fill="both", expand=True)
        
        ttk.Label(frame_bot, text="Voltage:", font=("Helvetica", 14, "bold")).grid(row=0, column=0, sticky="w", padx=20, pady=20)
        self.lbl_voltage = ttk.Label(frame_bot, text="---", font=("Helvetica", 14))
        self.lbl_voltage.grid(row=0, column=1, sticky="w", padx=20, pady=20)
        
        ttk.Label(frame_bot, text="Current:", font=("Helvetica", 14, "bold")).grid(row=1, column=0, sticky="w", padx=20, pady=20)
        self.lbl_current = ttk.Label(frame_bot, text="---", font=("Helvetica", 14))
        self.lbl_current.grid(row=1, column=1, sticky="w", padx=20, pady=20)

        ttk.Separator(frame_bot, orient="vertical").grid(row=0, column=2, rowspan=2, sticky="ns", padx=20, pady=10)
        frame_bot.columnconfigure(3, weight=1)

        # Custom I2C Tools
        frame_custom = ttk.Frame(frame_bot)
        frame_custom.grid(row=0, column=4, rowspan=2, padx=10, pady=10, sticky="ne")
        
        ttk.Label(frame_custom, text="Raw Command (Hex):", font=("Helvetica", 10, "bold")).pack(anchor="w")
        write_frame = ttk.Frame(frame_custom)
        write_frame.pack(fill="x", pady=(0, 10))
        self.custom_write_var = tk.StringVar()
        ttk.Entry(write_frame, textvariable=self.custom_write_var, width=15).pack(side="left")
        ttk.Button(write_frame, text="Send", command=self.send_custom_write).pack(side="left", padx=5)
        
        ttk.Label(frame_custom, text="Raw Read (Hex Reg, Dec Bytes):", font=("Helvetica", 10, "bold")).pack(anchor="w")
        read_frame = ttk.Frame(frame_custom)
        read_frame.pack(fill="x")
        ttk.Label(read_frame, text="Reg:").pack(side="left")
        self.custom_read_reg_var = tk.StringVar()
        ttk.Entry(read_frame, textvariable=self.custom_read_reg_var, width=5).pack(side="left", padx=(0, 5))
        ttk.Label(read_frame, text="Bytes:").pack(side="left")
        self.custom_read_len_var = tk.StringVar(value="2")
        ttk.Entry(read_frame, textvariable=self.custom_read_len_var, width=5).pack(side="left", padx=(0, 5))
        ttk.Button(read_frame, text="Read", command=self.send_custom_read).pack(side="left", padx=5)
        
        ttk.Separator(frame_custom, orient="horizontal").pack(fill="x", pady=10)
        
        ttk.Label(frame_custom, text="MACSubcmd (Hex):", font=("Helvetica", 10, "bold")).pack(anchor="w")
        mac_frame = ttk.Frame(frame_custom)
        mac_frame.pack(fill="x", pady=(0, 10))
        self.mac_subcmd_var = tk.StringVar()
        ttk.Entry(mac_frame, textvariable=self.mac_subcmd_var, width=15).pack(side="left")
        ttk.Button(mac_frame, text="Send", command=self.send_mac_subcmd).pack(side="left", padx=5)
        ttk.Button(mac_frame, text="Read", command=self.read_mac_subcmd).pack(side="left", padx=5)

        ttk.Separator(frame_custom, orient="horizontal").pack(fill="x", pady=5)

        result_frame = ttk.Frame(frame_custom)
        result_frame.pack(fill="x", pady=5)
        ttk.Label(result_frame, text="Result:", font=("Helvetica", 10, "bold")).pack(side="left")
        
        self.custom_result_var = tk.StringVar(value="---")
        self.custom_result_var.trace_add("write", self._on_result_changed)
        
        self.text_custom_result = tk.Text(result_frame, font=("Consolas", 10), height=3, width=30, wrap="word", state="disabled")
        self.text_custom_result.pack(side="left", padx=5, fill="both", expand=True)

        # Commands
        frame_cmd = ttk.LabelFrame(self, text="Commands")
        frame_cmd.pack(padx=10, pady=5, fill="x")

        self.btn_reset = ttk.Button(frame_cmd, text="Reset BQ28Z620", command=self.send_reset)
        self.btn_reset.pack(side="left", padx=10, pady=5)

        self.btn_log = ttk.Button(frame_cmd, text="Start Log", command=self.toggle_logging)
        self.btn_log.pack(side="left", padx=10, pady=5)

        self.btn_clear_pf = ttk.Button(frame_cmd, text="Clear PF Faults", command=self.clear_pf_faults)
        self.btn_clear_pf.pack(side="left", padx=10, pady=5)

        self.btn_toggle_chg = ttk.Button(frame_cmd, text="Toggle CHG FET", command=self.toggle_chg_fet)
        self.btn_toggle_chg.pack(side="left", padx=10, pady=5)

        self.btn_toggle_dsg = ttk.Button(frame_cmd, text="Toggle DSG FET", command=self.toggle_dsg_fet)
        self.btn_toggle_dsg.pack(side="left", padx=10, pady=5)

        self.btn_fet_ctrl = ttk.Button(frame_cmd, text="FET Ctrl: ---", command=self.toggle_fet_ctrl)
        self.btn_fet_ctrl.pack(side="left", padx=10, pady=5)

        # Status Register Toggles
        frame_toggles = ttk.LabelFrame(self, text="Polling Toggles")
        frame_toggles.pack(padx=10, pady=5, fill="x")

        self.toggle_all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_toggles, text="All",
                        variable=self.toggle_all_var,
                        command=self.on_toggle_all).pack(side="left", padx=10, pady=5)

        ttk.Separator(frame_toggles, orient="vertical").pack(side="left", padx=5, fill="y", pady=5)

        ttk.Checkbutton(frame_toggles, text="Voltage & Current",
                        variable=self.poll_voltage_current,
                        command=self.on_vc_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Battery Status",
                        variable=self.show_battery_status,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Op Status",
                        variable=self.show_operation_status,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Safety Alert",
                        variable=self.show_safety_alert,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="Safety Status",
                        variable=self.show_safety_status,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="PF Alert",
                        variable=self.show_pf_alert,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(frame_toggles, text="PF Status",
                        variable=self.show_pf_status,
                        command=self.on_individual_toggle).pack(side="left", padx=10, pady=5)

        # Scrollable status display area
        self.status_frame = ttk.Frame(self)
        self.status_frame.pack(padx=10, pady=5, fill="both", expand=True)

    def on_toggle_all(self):
        state = self.toggle_all_var.get()
        self.poll_voltage_current.set(state)
        self.show_battery_status.set(state)
        self.show_safety_alert.set(state)
        self.show_safety_status.set(state)
        self.show_pf_alert.set(state)
        self.show_pf_status.set(state)
        self.show_operation_status.set(state)
        self.rebuild_status_display()
        self._resume_polling()

    def on_vc_toggle(self):
        self._sync_toggle_all_state()
        self._resume_polling()

    def on_individual_toggle(self):
        self._sync_toggle_all_state()
        self.rebuild_status_display()
        self._resume_polling()

    def _sync_toggle_all_state(self):
        any_checked = any([
            self.poll_voltage_current.get(),
            self.show_battery_status.get(),
            self.show_operation_status.get(),
            self.show_safety_alert.get(),
            self.show_safety_status.get(),
            self.show_pf_alert.get(),
            self.show_pf_status.get()
        ])
        all_checked = all([
            self.poll_voltage_current.get(),
            self.show_battery_status.get(),
            self.show_operation_status.get(),
            self.show_safety_alert.get(),
            self.show_safety_status.get(),
            self.show_pf_alert.get(),
            self.show_pf_status.get()
        ])
        
        if not any_checked:
            self.toggle_all_var.set(False)
        elif all_checked:
            self.toggle_all_var.set(True)

    def _on_result_changed(self, *args):
        text = self.custom_result_var.get()
        self.text_custom_result.config(state="normal")
        self.text_custom_result.delete("1.0", tk.END)
        self.text_custom_result.insert("1.0", text)
        self.text_custom_result.config(state="disabled")

    def rebuild_status_display(self):
        """Rebuild the status bit display based on which registers are toggled on."""
        # Clear existing widgets
        for widget in self.status_frame.winfo_children():
            widget.destroy()
        self.status_bit_labels.clear()

        row = 0
        row = self._build_register_section(
            "Battery Status (0x0A)", BATTERY_STATUS_BITS, "bat", row)
        row = self._build_register_section(
            "Operation Status (0x0054)", OPERATION_STATUS_BITS, "ops", row)
        row = self._build_register_section(
            "Safety Alert (0x0050)", SAFETY_ALERT_BITS, "sa", row)
        row = self._build_register_section(
            "Safety Status (0x0051)", SAFETY_STATUS_BITS, "ss", row)
        row = self._build_register_section(
            "PF Alert (0x0052)", PF_ALERT_BITS, "pfa", row)
        row = self._build_register_section(
            "PF Status (0x0053)", PF_STATUS_BITS, "pfs", row)

    def _build_register_section(self, title, bit_map, prefix, start_row):
        """Build a labeled grid of bit indicators for one register."""
        ttk.Label(self.status_frame, text=title,
                  font=("Helvetica", 10, "bold")).grid(
            row=start_row, column=0, columnspan=8, sticky="w", padx=5, pady=(8, 2))
        
        # Raw hex value label
        hex_key = f"{prefix}_hex"
        hex_lbl = ttk.Label(self.status_frame, text="---", font=("Helvetica", 9))
        hex_lbl.grid(row=start_row, column=8, columnspan=6, sticky="e", padx=5)
        self.status_bit_labels[hex_key] = hex_lbl

        row = start_row + 1
        col = 0
        # Sort bits by position descending for a natural MSB-first layout
        for bit_pos in sorted(bit_map.keys(), reverse=True):
            name, _high, low = bit_map[bit_pos]
            lbl = tk.Label(self.status_frame, text=f"{name}\n{low}", fg=COLOR_INACTIVE,
                           font=("Consolas", 9, "bold"), width=12, wraplength=85, anchor="center")
            lbl.grid(row=row, column=col, padx=2, pady=1)
            self.status_bit_labels[f"{prefix}_{bit_pos}"] = lbl
            col += 1
            if col >= 14:
                col = 0
                row += 1

        if col != 0:
            row += 1
        return row

    def _update_bit_labels(self, prefix, raw_value, bit_map, hex_str, enabled=True):
        """Update the text and color of each bit label based on the raw register value."""
        hex_key = f"{prefix}_hex"
        if hex_key in self.status_bit_labels:
            lbl = self.status_bit_labels[hex_key]
            if not lbl.winfo_exists(): return
            
            if not enabled:
                display_hex = "---"
            else:
                display_hex = hex_str if hex_str else "Err"
            lbl.config(text=display_hex)

        if not enabled:
            for bit_pos, (name, _high, _low) in bit_map.items():
                key = f"{prefix}_{bit_pos}"
                if key in self.status_bit_labels:
                    lbl = self.status_bit_labels[key]
                    if lbl.winfo_exists():
                        lbl.config(
                            text=f"{name}\n---",
                            fg=COLOR_INACTIVE)
            return

        bits = BQ28z620.parse_bits(raw_value, bit_map)
        for bit_pos, (name, _high, _low) in bit_map.items():
            key = f"{prefix}_{bit_pos}"
            active, state_text = bits[name]

            if key in self.status_bit_labels:
                lbl = self.status_bit_labels[key]
                if lbl.winfo_exists():
                    lbl.config(
                        text=f"{name}\n{state_text}",
                        fg=COLOR_ACTIVE if active else COLOR_INACTIVE)

            # Log state changes
            if self.is_logging:
                log_key = f"{prefix}.{name}"
                prev = self.prev_status.get(log_key)
                if prev is not None and prev != active:
                    ts = datetime.now().isoformat(timespec='milliseconds')
                    self.log_entries.append(f"{ts}  {log_key:<20s}  -> {state_text}")
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
            
        self.btn_connect.config(state="disabled", text="Connecting...")
        self.lbl_bus_status.config(text="Bus: Connecting...", foreground="orange")
        
        def do_connect():
            try:
                self.bp = BusPirate(port)
                clock_khz = int(self.clock_var.get() or 10)
                success, msg = self.bp.connect(clock_khz=clock_khz)
            except Exception as e:
                success, msg = (False, str(e))
                
            self.after(0, lambda: self._on_connect_finished(success, msg, silent))
            
        threading.Thread(target=do_connect, daemon=True).start()

    def _on_connect_finished(self, success, msg, silent):
        self.btn_connect.config(state="normal")
        if success:
            self.btn_connect.config(text="Disconnect")
            self.bq = BQ28z620(self.bp)
            self.consecutive_errors = 0
            self.lbl_bus_status.config(text="Bus: Connected", foreground=COLOR_ACTIVE)
            
            # Initial FET status check
            self.update_fet_ctrl_button_state()
            
            self.is_polling = True
            self.poll_data()
        else:
            self.btn_connect.config(text="Connect", state="normal")
            self.lbl_bus_status.config(text="Failed to Connect", foreground="red")
            if not silent:
                messagebox.showerror("Connection Error", msg)
            
    def toggle_power(self):
        """Toggle the Bus Pirate 1.8V power and I2C pullups."""
        if not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Bus Pirate not connected")
            return
            
        if self.power_enabled:
            success, msg = self.bp.toggle_power_pullups(False)
            if success:
                self.power_enabled = False
                self.btn_power.config(text="Enable Power")
                self.lbl_bus_status.config(text="Bus: Unpowered / Idle", foreground="orange")
            else:
                messagebox.showerror("Error", msg)
        else:
            success, msg = self.bp.toggle_power_pullups(True)
            if success:
                self.power_enabled = True
                self.btn_power.config(text="Disable Power")
                # Automatically resume polling when power is restored
                self.after(500, self._resume_polling)
            else:
                messagebox.showerror("Error", msg)
            
    def disconnect(self):
        self.is_polling = False
        if self.bp:
            self.bp.disconnect()
        self.btn_connect.config(text="Connect")
        self.btn_fet_ctrl.config(text="FET Ctrl: ---")
        self.lbl_voltage.config(text="---")
        self.lbl_current.config(text="---")
        self.rebuild_status_display() # This will reset bit labels to --- if polling logic handles it

    def update_fet_ctrl_button_state(self):
        """Read ManufacturingStatus and update FET Ctrl button label based on FET_EN (bit 4)."""
        if not self.bq or not self.btn_fet_ctrl.winfo_exists():
            return
            
        val, hex_str = self.bq.get_manufacturing_status()
        if val is not None:
            # Bit 4 is FET_EN
            self.fet_ctrl_enabled = bool(val & (1 << 4))
            if self.fet_ctrl_enabled:
                self.btn_fet_ctrl.config(text="Enable FET Ctrl")
            else:
                self.btn_fet_ctrl.config(text="Disable FET Ctrl")
        else:
            self.btn_fet_ctrl.config(text="FET Ctrl: Err")

    def toggle_fet_ctrl(self):
        """Toggle FET control via MAC subcommand 0x0022 and update UI."""
        if not self.bq or not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Not connected")
            return
            
        was_polling = self.is_polling
        self.is_polling = False
        
        # Send toggle command
        success = self.bq.toggle_fet_control()
        if success:
            # Give device a moment to process
            time.sleep(0.2)
            # Re-read status to update button
            self.update_fet_ctrl_button_state()
        else:
            messagebox.showerror("Error", "Failed to send FET control toggle")
            
        if was_polling:
            self._resume_polling()

    def send_reset(self):
        """Send a RESET command to the BQ28Z620."""
        if not self.bq:
            return

        self.is_polling = False
        self.bq.reset()
        # Resume polling after a brief delay to let the device restart
        self.after(2000, self._resume_polling)

    def clear_pf_faults(self):
        """Send a PF_RESET command to the BQ28Z620."""
        if not self.bq:
            return

        self.is_polling = False
        self.bq.pf_reset()
        # Resume polling after a brief delay
        self.after(2000, self._resume_polling)

    def toggle_chg_fet(self):
        """Send a CHG_FET_TOGGLE command."""
        if not self.bq: return
        self.is_polling = False
        self.bq.toggle_chg_fet()
        self.after(500, self._resume_polling)

    def toggle_dsg_fet(self):
        """Send a DSG_FET_TOGGLE command."""
        if not self.bq: return
        self.is_polling = False
        self.bq.toggle_dsg_fet()
        self.after(500, self._resume_polling)

    def send_custom_write(self):
        if not self.bq or not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Not connected")
            return
            
        hex_str = self.custom_write_var.get().strip()
        if not hex_str: return
        
        try:
            parts = [int(p, 16) for p in hex_str.split()]
        except ValueError:
            messagebox.showerror("Error", "Invalid hex format. Use e.g. '1f 00'")
            return
            
        if not parts: return
        
        reg = parts[0]
        data = parts[1:]
        
        self.is_polling = False
        self.bp.write_register(self.bq.addr_w, reg, data)
        self.custom_result_var.set(f"Sent write: {hex_str.upper()}")
        self.after(500, self._resume_polling)

    def send_custom_read(self):
        if not self.bq or not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Not connected")
            return
            
        reg_str = self.custom_read_reg_var.get().strip()
        len_str = self.custom_read_len_var.get().strip()
        
        if not reg_str or not len_str: return
        
        try:
            reg = int(reg_str, 16)
            length = int(len_str)
        except ValueError:
            messagebox.showerror("Error", "Invalid format (Hex Reg, Dec Bytes)")
            return
            
        pre_write_bytes = None
        write_hex_str = self.custom_write_var.get().strip()
        if write_hex_str:
            try:
                pre_write_bytes = [int(p, 16) for p in write_hex_str.split()]
            except ValueError:
                messagebox.showerror("Error", "Invalid hex in write field.")
                return

        self.is_polling = False
        data = self.bp.read_register(self.bq.addr_w, self.bq.addr_r, reg, length=length, pre_write_bytes=pre_write_bytes)
        if data is not None:
            res_str = " ".join([f"{b:02X}" for b in data])
            self.custom_result_var.set(res_str)
        else:
            self.custom_result_var.set("Read error")
            
        self.after(500, self._resume_polling)

    def send_mac_subcmd(self):
        if not self.bq or not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Not connected")
            return
            
        hex_str = self.mac_subcmd_var.get().strip()
        if not hex_str: return
        
        try:
            data = [int(p, 16) for p in hex_str.split()]
        except ValueError:
            messagebox.showerror("Error", "Invalid hex format. Use e.g. '1f 00'")
            return
            
        self.is_polling = False
        # send 0x3e and then the bytes
        self.bp.write_register(self.bq.addr_w, 0x3e, data)
        self.custom_result_var.set(f"Sent MAC Subcmd: {hex_str.upper()}")
        self.after(500, self._resume_polling)

    def read_mac_subcmd(self):
        if not self.bq or not self.bp or not self.bp.connected:
            messagebox.showerror("Error", "Not connected")
            return
            
        hex_str = self.mac_subcmd_var.get().strip()
        if not hex_str: return
        
        try:
            data = [int(p, 16) for p in hex_str.split()]
        except ValueError:
            messagebox.showerror("Error", "Invalid hex format. Use e.g. '1f 00'")
            return
            
        self.is_polling = False
        
        # 1. send 0x3e and the bytes
        self.bp.write_register(self.bq.addr_w, 0x3e, data)
        
        # Give it a tiny delay to process the MAC command
        time.sleep(0.05)
        
        # 2. read one byte from 0x61
        len_data = self.bp.read_register(self.bq.addr_w, self.bq.addr_r, 0x61, length=1)
        if len_data is None or len(len_data) == 0:
            self.custom_result_var.set("MAC Read Error (length)")
            self.after(500, self._resume_polling)
            return
            
        expected_bytes = len_data[0]
        if expected_bytes <= 4:
            self.custom_result_var.set("MAC Read: 0 data bytes")
            self.after(500, self._resume_polling)
            return
            
        # 3. read that many bytes from 0x40 (minus 4 for echo/footer)
        mac_data = self.bp.read_register(self.bq.addr_w, self.bq.addr_r, 0x40, length=expected_bytes - 4)
        if mac_data is not None:
            res_str = " ".join([f"{b:02X}" for b in mac_data])
            self.custom_result_var.set(f"{res_str}")
        else:
            self.custom_result_var.set("MAC Read Error (data)")
            
        self.after(500, self._resume_polling)

    def set_clock(self):
        """Save the clock rate and reconnect with the new setting."""
        try:
            clock_khz = int(self.clock_var.get())
        except ValueError:
            messagebox.showerror("Invalid", "Clock rate must be a number in kHz.")
            return

        config = self.load_config()
        config["clock_khz"] = clock_khz
        self.save_config(config)

        if self.bp and self.bp.connected:
            self.disconnect()
            self.after(500, self.connect)

    def _resume_polling(self):
        """Resume data polling after a reset."""
        if self.bp and self.bp.connected and not self.is_polling:
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
            
            any_success = False
            any_attempted = False
            
            # Read Voltage & Current
            if self.poll_voltage_current.get():
                any_attempted = True
                # Read Voltage
                v_val, v_hex = self.bq.get_voltage()
                if v_val is not None: any_success = True
                
                # Check if lbl exists before config (redundant but safe)
                if self.lbl_voltage.winfo_exists():
                    self.lbl_voltage.config(text=f"{v_val} mV  ({v_hex})" if v_val is not None else "Err")
                self.update()
                time.sleep(delay)
                    
                # Read Current
                i_val, i_hex = self.bq.get_current()
                if i_val is not None: any_success = True
                if self.lbl_current.winfo_exists():
                    self.lbl_current.config(text=f"{i_val} mA  ({i_hex})" if i_val is not None else "Err")
                self.update()
                time.sleep(delay)

            # Read status registers
            status_regs = [
                ("bat", self.show_battery_status, self.bq.get_battery_status, BATTERY_STATUS_BITS),
                ("ops", self.show_operation_status, self.bq.get_operation_status, OPERATION_STATUS_BITS),
                ("sa",  self.show_safety_alert, self.bq.get_safety_alert, SAFETY_ALERT_BITS),
                ("ss",  self.show_safety_status, self.bq.get_safety_status, SAFETY_STATUS_BITS),
                ("pfa", self.show_pf_alert, self.bq.get_pf_alert, PF_ALERT_BITS),
                ("pfs", self.show_pf_status, self.bq.get_pf_status, PF_STATUS_BITS),
            ]

            for prefix, toggle, read_fn, bit_map in status_regs:
                en = toggle.get()
                val, hex_str = (None, None)
                if en:
                    any_attempted = True
                    val, hex_str = read_fn()
                    if val is not None: any_success = True
                    time.sleep(delay)
                self._update_bit_labels(prefix, val, bit_map, hex_str, enabled=en)
                self.update()

            if any_success:
                self.consecutive_errors = 0
                self.lbl_bus_status.config(text="Bus: Connected", foreground=COLOR_ACTIVE)
            elif any_attempted:
                # If commands were attempted but all failed, assume the bus is unpowered or DSG FET is off.
                # Stop polling silently and update status.
                self.is_polling = False
                self.lbl_bus_status.config(text="Bus: Unpowered / Idle", foreground="orange")
                return
                
        # Schedule next poll
        self.after(POLL_RATE, self.poll_data)

if __name__ == "__main__":
    app = FuelGaugeDashboard()
    app.mainloop()
