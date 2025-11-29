import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import threading
import json
import requests
import websocket
from pathlib import Path
import json as json_lib

# -------------------------------------------------
# Config & endpoints
# -------------------------------------------------
#CONFIG_PATH = Path.cwd() / "config.json"
CONFIG_DIR = Path.home() / ".echomind"
CONFIG_PATH = CONFIG_DIR / "config.json"
if CONFIG_PATH.exists():
    cfg = json_lib.loads(CONFIG_PATH.read_text())
    PORT = cfg.get("control_port", 8766)
else:
    cfg = {}
    PORT = 8766

CONTROL_URL = f"http://localhost:{PORT}"
WS_URL = f"ws://localhost:{PORT}/ws"


class TranscriptionUI:
    def __init__(self):
        self.root = None

        self.user_box = None
        self.system_box = None

        self.status_label = None
        self.is_running = True

        # Settings window state
        self.settings_window = None
        # key -> tk.Entry or ttk.Checkbutton
        self.settings_entries: dict[str, tk.Widget] = {}
        # For boolean toggles
        self.settings_bools: dict[str, tk.BooleanVar] = {}

        self.create_window()
        threading.Thread(target=self.websocket_thread, daemon=True).start()

    # -------------------------------------------------
    # UI LAYOUT
    # -------------------------------------------------
    def disable_button_temporarily(self, button: ttk.Button, delay_ms: int = 800):
        button.state(["disabled"])
        button.after(delay_ms, lambda: button.state(["!disabled"]))

    def create_window(self):
        self.root = tk.Tk()
        self.root.title("EchoMind – Dual-Channel Transcription")
        self.root.geometry("1150x700")
        self.root.minsize(800, 400)

        # Dark background
        self.root.configure(bg="#1e1e1e")

        # Make root resizable with proper weight
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Main frame
        main_frame = tk.Frame(self.root, bg="#1e1e1e")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(2, weight=1)

        # ---------- MIC (LEFT) ----------
        user_label = tk.Label(
            main_frame,
            text=" Microphone (You)",
            font=("Helvetica", 14, "bold"),
            fg="white",
            bg="#1e1e1e",
        )
        user_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.user_box = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            font=("Menlo", 11),
            width=50,
            height=22,
            bg="#2b2b2b",
            fg="white",
            insertbackground="white",
            borderwidth=1,
            relief="solid",
        )
        self.user_box.grid(row=1, column=0, sticky="nsew", padx=(0, 15))

        # ---------- DIVIDER ----------
        divider = tk.Frame(main_frame, width=4, bg="#444444")
        divider.grid(row=0, column=1, rowspan=2, sticky="ns", padx=5)

        # ---------- SYSTEM (RIGHT) ----------
        sys_label = tk.Label(
            main_frame,
            text=" 💻 System Audio",
            font=("Helvetica", 14, "bold"),
            fg="white",
            bg="#1e1e1e",
        )
        sys_label.grid(row=0, column=2, sticky="w", pady=(0, 10))

        self.system_box = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            font=("Menlo", 11),
            width=50,
            height=22,
            bg="#2b2b2b",
            fg="white",
            insertbackground="white",
            borderwidth=1,
            relief="solid",
        )
        self.system_box.grid(row=1, column=2, sticky="nsew", padx=(15, 0))

        # ---------- CONTROL BUTTONS ----------
        controls_frame = tk.Frame(self.root, bg="#1e1e1e")
        controls_frame.grid(row=1, column=0, pady=(0, 10))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Echo.TButton",
            font=("Helvetica", 11),
            padding=6,
        )

        style.configure(
            "Echo1.TButton",
            font=("Helvetica", 18, "bold"),
            padding=0,
        )



        self.start_btn = ttk.Button(
            controls_frame,
            text="Start Service",
            style="Echo.TButton",
            command=self.start_service,
        )
        self.start_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = ttk.Button(
            controls_frame,
            text="Stop Service",
            style="Echo.TButton",
            command=self.stop_service,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        clear_btn = ttk.Button(
            controls_frame,
            text="Clear Text",
            style="Echo.TButton",
            command=self.clear_text,
        )
        clear_btn.pack(side=tk.LEFT, padx=10)

        # Settings button (gear icon only)
        settings_btn = ttk.Button(
            controls_frame,
            text="⚙",
            width=3,
            style="Echo1.TButton",
            command=self.open_settings_window,
        )
        settings_btn.pack(side=tk.LEFT, padx=10)

        # ---------- STATUS LABEL ----------
        self.status_label = tk.Label(
            self.root,
            text="Status: Idle",
            fg="#cccccc",
            bg="#1e1e1e",
            font=("Helvetica", 11),
        )
        self.status_label.grid(row=2, column=0, pady=(0, 10))

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # -------------------------------------------------
    # CONTROL BUTTON HANDLERS
    # -------------------------------------------------
    def start_service(self):
        try:
            self.disable_button_temporarily(self.start_btn)
            r = requests.post(f"{CONTROL_URL}/start", timeout=15)
            data = r.json()
            self.status_label.config(text=f"Status: {data.get('status')}")
        except Exception as e:
            self.status_label.config(text=f"Error starting: {str(e)}")

    def stop_service(self):
        try:
            self.disable_button_temporarily(self.stop_btn)
            r = requests.post(f"{CONTROL_URL}/stop", timeout=15)
            data = r.json()
            self.status_label.config(text=f"Status: {data.get('status')}")
        except Exception as e:
            self.status_label.config(text=f"Error stopping: {str(e)}")

    def clear_text(self):
        self.user_box.delete("1.0", tk.END)
        self.system_box.delete("1.0", tk.END)

    # -------------------------------------------------
    # SETTINGS WINDOW
    # -------------------------------------------------
    def open_settings_window(self):
        # If already open, just bring to front
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        # Load config fresh from disk
        if CONFIG_PATH.exists():
            try:
                config_data: dict = json.loads(CONFIG_PATH.read_text())
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to read config.json:\n{exc}")
                return
        else:
            config_data = {}

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Settings")
        self.settings_window.configure(bg="#1e1e1e")
        self.settings_window.geometry("450x400")
        self.settings_window.minsize(350, 250)

        container = tk.Frame(self.settings_window, bg="#1e1e1e")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(container, bg="#1e1e1e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#1e1e1e")

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.settings_entries.clear()
        self.settings_bools.clear()

        row = 0
        for key, value in sorted(config_data.items(), key=lambda kv: kv[0]):
            label = tk.Label(
                scroll_frame,
                text=key,
                fg="white",
                bg="#1e1e1e",
                font=("Helvetica", 10),
                anchor="w",
            )
            label.grid(row=row, column=0, sticky="w", pady=4, padx=(0, 6))

            # Special handling:
            # 1) openai_api_key -> password Entry
            # 2) capture_system_audio & capture_microphone -> toggle buttons (Checkbutton)
            if key == "openai_api_key":
                entry = tk.Entry(
                    scroll_frame,
                    font=("Helvetica", 10),
                    width=40,
                    bg="#2b2b2b",
                    fg="white",
                    insertbackground="white",
                    show="•",
                )
                entry.grid(row=row, column=1, sticky="ew", pady=4)
                entry.insert(0, str(value or ""))
                self.settings_entries[key] = entry

            elif key in ("capture_system_audio", "capture_microphone"):
                bool_var = tk.BooleanVar(value=bool(value))
                # Style-like toggle using Checkbutton
                chk = ttk.Checkbutton(
                    scroll_frame,
                    text="Enabled",
                    variable=bool_var,
                    onvalue=True,
                    offvalue=False,
                )
                chk.grid(row=row, column=1, sticky="w", pady=4)
                self.settings_entries[key] = chk
                self.settings_bools[key] = bool_var

            else:
                entry = tk.Entry(
                    scroll_frame,
                    font=("Helvetica", 10),
                    width=40,
                    bg="#2b2b2b",
                    fg="white",
                    insertbackground="white",
                )
                entry.grid(row=row, column=1, sticky="ew", pady=4)

                # For simple types, just str; for others, show JSON
                if isinstance(value, (str, int, float, bool)) or value is None:
                    entry.insert(0, str(value))
                else:
                    entry.insert(0, json.dumps(value))

                self.settings_entries[key] = entry

            row += 1

        scroll_frame.columnconfigure(1, weight=1)

        # Save button
        btn_frame = tk.Frame(self.settings_window, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        save_btn = ttk.Button(
            btn_frame,
            text="Save",
            command=self.save_settings_and_restart,
        )
        save_btn.pack(side=tk.RIGHT)

    def save_settings_and_restart(self):
        new_config: dict = {}

        # Parse each field
        for key, widget in self.settings_entries.items():
            # Boolean toggles
            if key in self.settings_bools:
                new_config[key] = bool(self.settings_bools[key].get())
                continue

            if isinstance(widget, tk.Entry):
                raw_value = widget.get().strip()

                # For openai_api_key: keep raw string as is (no JSON parsing)
                if key == "openai_api_key":
                    new_config[key] = raw_value
                    continue

                # Try JSON parse (for numbers, bools, etc.)
                try:
                    parsed = json.loads(raw_value)
                    new_config[key] = parsed
                except json.JSONDecodeError:
                    # Fallback to string
                    new_config[key] = raw_value

        # Write to config.json
        try:
            CONFIG_PATH.write_text(
                json.dumps(new_config, indent=2, ensure_ascii=False)
            )
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to write config.json:\n{exc}")
            return

        # Update globals
        global cfg, PORT, CONTROL_URL, WS_URL
        cfg = new_config
        PORT = cfg.get("control_port", PORT)
        CONTROL_URL = f"http://localhost:{PORT}"
        WS_URL = f"ws://localhost:{PORT}/ws"

        # Send restart
        try:
            r = requests.post(f"{CONTROL_URL}/restart", timeout=15)
            data = r.json()
            self.status_label.config(text=f"Status: {data.get('status')}")
        except Exception as e:
            messagebox.showwarning(
                "Restart Error",
                f"Config saved, but restart request failed:\n{e}",
            )
            self.status_label.config(text=f"Config saved. Restart failed: {e}")
        else:
            messagebox.showinfo(
                "Success",
                "Settings saved and service restart requested.",
            )

        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None

    # -------------------------------------------------
    # WEBSOCKET LISTEN THREAD
    # -------------------------------------------------
    def websocket_thread(self):
        def on_message(ws, message: str):
            try:
                data = json.loads(message)
            except Exception:
                return

            text = data.get("text", "")
            source = data.get("source", "system")

            if not text:
                return

            if source == "mic":
                self.user_box.insert(tk.END, text + "\n")
                self.user_box.see(tk.END)
            else:
                self.system_box.insert(tk.END, text + "\n")
                self.system_box.see(tk.END)

        def on_error(ws, error):
            print("WebSocket error:", error)

        def on_close(ws, close_status_code, close_msg):
            print("WebSocket closed:", close_status_code, close_msg)

        def on_open(ws):
            print("WebSocket connected")

        while self.is_running:
            try:
                ws = websocket.WebSocketApp(
                    WS_URL,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open,
                )
                ws.run_forever()
            except Exception as e:
                print("WebSocket connection failed, retrying in 3s:", e)
            if self.is_running:
                import time
                time.sleep(3)

    # -------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------
    def on_closing(self):
        self.is_running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    TranscriptionUI().run()






































# import tkinter as tk
# from tkinter import scrolledtext, ttk
# import threading
# import json
# import requests
# import websocket
# from pathlib import Path
# import json as json_lib

# # -------------------------------------------------
# # Config & endpoints
# # -------------------------------------------------
# CONFIG_PATH = Path.cwd() / "config.json"
# if CONFIG_PATH.exists():
#     cfg = json_lib.loads(CONFIG_PATH.read_text())
#     PORT = cfg.get("control_port", 8766)
# else:
#     PORT = 8766

# CONTROL_URL = f"http://localhost:{PORT}"
# WS_URL = f"ws://localhost:{PORT}/ws"


# class TranscriptionUI:
#     def __init__(self):
#         self.root = None

#         self.user_box = None
#         self.system_box = None

#         self.status_label = None
#         self.is_running = True

#         self.create_window()
#         threading.Thread(target=self.websocket_thread, daemon=True).start()

#     # -------------------------------------------------
#     # UI LAYOUT
#     # -------------------------------------------------
#     def disable_button_temporarily(self, button, delay_ms=800):
#         button.state(['disabled'])
#         button.after(delay_ms, lambda: button.state(['!disabled']))

#     def create_window(self):
#         self.root = tk.Tk()
#         self.root.title("EchoMind – Dual-Channel Transcription")
#         self.root.geometry("1150x700")
#         self.root.minsize(950, 550)

#         # Dark background
#         self.root.configure(bg="#1e1e1e")

#         # Make root resizable with proper weight
#         self.root.rowconfigure(0, weight=1)
#         self.root.columnconfigure(0, weight=1)

#         # Main frame
#         main_frame = tk.Frame(self.root, bg="#1e1e1e")
#         main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

#         main_frame.rowconfigure(1, weight=1)
#         main_frame.columnconfigure(0, weight=1)
#         main_frame.columnconfigure(2, weight=1)

#         # ---------- MIC (LEFT) ----------
#         user_label = tk.Label(
#             main_frame,
#             text=" Microphone (You)",
#             font=("Helvetica", 14, "bold"),
#             fg="white",
#             bg="#1e1e1e",
#         )
#         user_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

#         self.user_box = scrolledtext.ScrolledText(
#             main_frame,
#             wrap=tk.WORD,
#             font=("Menlo", 11),
#             width=50,
#             height=22,
#             bg="#2b2b2b",
#             fg="white",
#             insertbackground="white",
#             borderwidth=1,
#             relief="solid",
#         )
#         self.user_box.grid(row=1, column=0, sticky="nsew", padx=(0, 15))

#         # ---------- DIVIDER ----------
#         divider = tk.Frame(main_frame, width=4, bg="#444444")
#         divider.grid(row=0, column=1, rowspan=2, sticky="ns", padx=5)

#         # ---------- SYSTEM (RIGHT) ----------
#         sys_label = tk.Label(
#             main_frame,
#             text=" 💻 System Audio",
#             font=("Helvetica", 14, "bold"),
#             fg="white",
#             bg="#1e1e1e",
#         )
#         sys_label.grid(row=0, column=2, sticky="w", pady=(0, 10))

#         self.system_box = scrolledtext.ScrolledText(
#             main_frame,
#             wrap=tk.WORD,
#             font=("Menlo", 11),
#             width=50,
#             height=22,
#             bg="#2b2b2b",
#             fg="white",
#             insertbackground="white",
#             borderwidth=1,
#             relief="solid",
#         )
#         self.system_box.grid(row=1, column=2, sticky="nsew", padx=(15, 0))

#         # ---------- CONTROL BUTTONS ----------
#         controls_frame = tk.Frame(self.root, bg="#1e1e1e")
#         controls_frame.grid(row=1, column=0, pady=(0, 10))

#         style = ttk.Style()
#         try:
#             style.theme_use("clam")
#         except Exception:
#             pass

#         style.configure(
#             "Echo.TButton",
#             font=("Helvetica", 11),
#             padding=6,
#         )

#         self.start_btn = ttk.Button(
#             controls_frame,
#             text="Start Service",
#             style="Echo.TButton",
#             command=self.start_service,
#         )
#         self.start_btn.pack(side=tk.LEFT, padx=10)

#         self.stop_btn = ttk.Button(
#             controls_frame,
#             text="Stop Service",
#             style="Echo.TButton",
#             command=self.stop_service,
#         )
#         self.stop_btn.pack(side=tk.LEFT, padx=10)

#         clear_btn = ttk.Button(
#             controls_frame,
#             text="Clear Text",
#             style="Echo.TButton",
#             command=self.clear_text,
#         )
#         clear_btn.pack(side=tk.LEFT, padx=10)

#         # ---------- STATUS LABEL ----------
#         self.status_label = tk.Label(
#             self.root,
#             text="Status: Idle",
#             fg="#cccccc",
#             bg="#1e1e1e",
#             font=("Helvetica", 11),
#         )
#         self.status_label.grid(row=2, column=0, pady=(0, 10))

#         self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

#     # -------------------------------------------------
#     # CONTROL BUTTON HANDLERS
#     # -------------------------------------------------
#     def start_service(self):
#         try:
#             self.disable_button_temporarily(self.start_btn)
#             r = requests.post(f"{CONTROL_URL}/start", timeout=15).json()
#             self.status_label.config(text=f"Status: {r.get('status')}")
#         except Exception as e:
#             self.status_label.config(text=f"Error starting: {str(e)}")

#     def stop_service(self):
#         try:
#             self.disable_button_temporarily(self.stop_btn)
#             r = requests.post(f"{CONTROL_URL}/stop", timeout=15).json()
#             self.status_label.config(text=f"Status: {r.get('status')}")
#         except Exception as e:
#             self.status_label.config(text=f"Error stopping: {str(e)}")

#     def clear_text(self):
#         self.user_box.delete("1.0", tk.END)
#         self.system_box.delete("1.0", tk.END)

#     # -------------------------------------------------
#     # WEBSOCKET LISTEN THREAD
#     # -------------------------------------------------
#     def websocket_thread(self):
#         def on_message(ws, message):
#             try:
#                 data = json.loads(message)
#             except Exception:
#                 return

#             text = data.get("text", "")
#             source = data.get("source", "system")

#             if not text:
#                 return

#             # Append in correct pane – backend sends source "mic" for microphone
#             if source == "mic":
#                 self.user_box.insert(tk.END, text + "\n")
#                 self.user_box.see(tk.END)
#             else:
#                 self.system_box.insert(tk.END, text + "\n")
#                 self.system_box.see(tk.END)

#         def on_error(ws, error):
#             print("WebSocket error:", error)

#         def on_close(ws, close_status_code, close_msg):
#             print("WebSocket closed:", close_status_code, close_msg)

#         def on_open(ws):
#             print("WebSocket connected")

#         while self.is_running:
#             try:
#                 ws = websocket.WebSocketApp(
#                     WS_URL,
#                     on_message=on_message,
#                     on_error=on_error,
#                     on_close=on_close,
#                     on_open=on_open,
#                 )
#                 ws.run_forever()
#             except Exception as e:
#                 print("WebSocket connection failed, retrying in 3s:", e)
#             if self.is_running:
#                 import time
#                 time.sleep(3)

#     # -------------------------------------------------
#     # SHUTDOWN
#     # -------------------------------------------------
#     def on_closing(self):
#         self.is_running = False
#         self.root.destroy()

#     def run(self):
#         self.root.mainloop()


# if __name__ == "__main__":
#     TranscriptionUI().run()



























# import tkinter as tk
# from tkinter import scrolledtext, ttk
# import threading
# import json
# import requests
# import websocket
# from pathlib import Path
# import json as json_lib

# # -------------------------------------------------
# # Config & endpoints
# # -------------------------------------------------
# CONFIG_PATH = Path.home() / ".echomind" / "config.json"
# if CONFIG_PATH.exists():
#     cfg = json_lib.loads(CONFIG_PATH.read_text())
#     PORT = cfg.get("control_port", 8766)
# else:
#     PORT = 8766

# CONTROL_URL = f"http://localhost:{PORT}"
# WS_URL = f"ws://localhost:{PORT}/ws"


# class TranscriptionUI:
#     def __init__(self):
#         self.root = None

#         self.user_box = None
#         self.system_box = None

#         self.status_label = None
#         self.is_running = True

#         self.create_window()
#         threading.Thread(target=self.websocket_thread, daemon=True).start()

#     # -------------------------------------------------
#     # UI LAYOUT
#     # -------------------------------------------------
#     def disable_button_temporarily(self, button, delay_ms=800):
#         button.state(['disabled'])
#         button.after(delay_ms, lambda: button.state(['!disabled']))
#     def create_window(self):
#         self.root = tk.Tk()
#         self.root.title("EchoMind – Dual-Channel Transcription")
#         self.root.geometry("1150x700")
#         self.root.minsize(950, 550)

#         # Dark background
#         self.root.configure(bg="#1e1e1e")

#         # Make root resizable with proper weight
#         self.root.rowconfigure(0, weight=1)
#         self.root.columnconfigure(0, weight=1)

#         # Main frame
#         main_frame = tk.Frame(self.root, bg="#1e1e1e")
#         main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

#         main_frame.rowconfigure(1, weight=1)
#         main_frame.columnconfigure(0, weight=1)
#         main_frame.columnconfigure(2, weight=1)

#         # ---------- MIC (LEFT) ----------
#         user_label = tk.Label(
#             main_frame,
#             text="🎤 Microphone (You)",
#             font=("Helvetica", 14, "bold"),
#             fg="white",
#             bg="#1e1e1e",
#         )
#         user_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

#         self.user_box = scrolledtext.ScrolledText(
#             main_frame,
#             wrap=tk.WORD,
#             font=("Menlo", 11),
#             width=50,
#             height=22,
#             bg="#2b2b2b",
#             fg="white",
#             insertbackground="white",
#             borderwidth=1,
#             relief="solid",
#         )
#         self.user_box.grid(row=1, column=0, sticky="nsew", padx=(0, 15))

#         # ---------- DIVIDER ----------
#         divider = tk.Frame(main_frame, width=4, bg="#444444")
#         divider.grid(row=0, column=1, rowspan=2, sticky="ns", padx=5)

#         # ---------- SYSTEM (RIGHT) ----------
#         sys_label = tk.Label(
#             main_frame,
#             text="💻 System Audio (YouTube / Meet / Zoom / Spotify)",
#             font=("Helvetica", 14, "bold"),
#             fg="white",
#             bg="#1e1e1e",
#         )
#         sys_label.grid(row=0, column=2, sticky="w", pady=(0, 10))

#         self.system_box = scrolledtext.ScrolledText(
#             main_frame,
#             wrap=tk.WORD,
#             font=("Menlo", 11),
#             width=50,
#             height=22,
#             bg="#2b2b2b",
#             fg="white",
#             insertbackground="white",
#             borderwidth=1,
#             relief="solid",
#         )
#         self.system_box.grid(row=1, column=2, sticky="nsew", padx=(15, 0))

#         # ---------- CONTROL BUTTONS ----------
#         controls_frame = tk.Frame(self.root, bg="#1e1e1e")
#         controls_frame.grid(row=1, column=0, pady=(0, 10))

#         # ttk style (note: on macOS, native theme may ignore bg colors but font/padding apply)
#         style = ttk.Style()
#         try:
#             style.theme_use("clam")
#         except Exception:
#             pass

#         style.configure(
#             "Echo.TButton",
#             font=("Helvetica", 11),
#             padding=6,
#         )



#         self.start_btn = ttk.Button(
#             controls_frame,
#             text="Start Service",
#             style="Echo.TButton",
#             command=self.start_service,
#         )
#         self.start_btn.pack(side=tk.LEFT, padx=10)

#         self.stop_btn = ttk.Button(
#             controls_frame,
#             text="Stop Service",
#             style="Echo.TButton",
#             command=self.stop_service,
#         )
#         self.stop_btn.pack(side=tk.LEFT, padx=10)

#         clear_btn = ttk.Button(
#             controls_frame,
#             text="Clear Text",
#             style="Echo.TButton",
#             command=self.clear_text,
#         )
#         clear_btn.pack(side=tk.LEFT, padx=10)

#         # ---------- STATUS LABEL ----------
#         self.status_label = tk.Label(
#             self.root,
#             text="Status: Idle",
#             fg="#cccccc",
#             bg="#1e1e1e",
#             font=("Helvetica", 11),
#         )
#         self.status_label.grid(row=2, column=0, pady=(0, 10))

#         self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

#     # -------------------------------------------------
#     # CONTROL BUTTON HANDLERS
#     # -------------------------------------------------
#     def start_service(self):
#         try:
#             self.disable_button_temporarily(self.start_btn)
#             r = requests.post(f"{CONTROL_URL}/start", timeout=5).json()
#             self.status_label.config(text=f"Status: {r.get('status')}")
#         except Exception as e:
#             self.status_label.config(text=f"Error starting: {str(e)}")

#     def stop_service(self):
#         try:
#             self.disable_button_temporarily(self.stop_btn)
#             r = requests.post(f"{CONTROL_URL}/stop", timeout=5).json()
#             self.status_label.config(text=f"Status: {r.get('status')}")
#         except Exception as e:
#             self.status_label.config(text=f"Error stopping: {str(e)}")

#     def clear_text(self):
#         self.user_box.delete("1.0", tk.END)
#         self.system_box.delete("1.0", tk.END)

#     # -------------------------------------------------
#     # WEBSOCKET LISTEN THREAD
#     # -------------------------------------------------
#     def websocket_thread(self):
#         def on_message(ws, message):
#             try:
#                 data = json.loads(message)
#             except Exception:
#                 return

#             text = data.get("text", "")
#             source = data.get("source", "system")

#             if not text:
#                 return

#             # Append in correct pane – this assumes backend sends source "mic" for microphone
#             if source == "mic":
#                 self.user_box.insert(tk.END, text + "\n")
#                 self.user_box.see(tk.END)
#             else:
#                 self.system_box.insert(tk.END, text + "\n")
#                 self.system_box.see(tk.END)

#         def on_error(ws, error):
#             print("WebSocket error:", error)

#         def on_close(ws, close_status_code, close_msg):
#             print("WebSocket closed:", close_status_code, close_msg)

#         def on_open(ws):
#             print("WebSocket connected")

#         while self.is_running:
#             try:
#                 ws = websocket.WebSocketApp(
#                     WS_URL,
#                     on_message=on_message,
#                     on_error=on_error,
#                     on_close=on_close,
#                     on_open=on_open,
#                 )
#                 ws.run_forever()
#             except Exception as e:
#                 print("WebSocket connection failed, retrying in 3s:", e)
#             if self.is_running:
#                 import time
#                 time.sleep(3)

#     # -------------------------------------------------
#     # SHUTDOWN
#     # -------------------------------------------------
#     def on_closing(self):
#         self.is_running = False
#         self.root.destroy()

#     def run(self):
#         self.root.mainloop()


# if __name__ == "__main__":
#     TranscriptionUI().run()