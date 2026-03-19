#!/usr/bin/env python3
"""
AirGUI v2 — Modern Wireless Security Auditing GUI
pip install customtkinter matplotlib
sudo python3 airgui.py   (Linux · aircrack-ng suite required)
For authorized security testing only.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess, threading, os, csv, io, time, tempfile, signal, re
import json, urllib.request, webbrowser
from datetime import datetime
from pathlib import Path
from collections import deque, defaultdict

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ── Palettes ──────────────────────────────────────────────────────────────────
_TTK = {
    "dark": {
        "bg":        "#0b0b16",  "surface":   "#13132a",  "card":      "#1c1c38",
        "border":    "#2d2d58",  "accent":    "#7c5cbf",  "text":      "#e2e8f0",
        "dim":       "#8895aa",  "green":     "#22c55e",  "red":       "#ef4444",
        "yellow":    "#f59e0b",  "blue":      "#38bdf8",  "tree_bg":   "#13132a",
        "tree_sel":  "#6d5acd",  "tree_head": "#1c1c38",  "term_bg":   "#07070f",
        "term_fg":   "#a0ffa0",  "plot_bg":   "#0d0d22",  "plot_fg":   "#e2e8f0",
        "plot_grid": "#2d2d58",  "plot_line": "#7c5cbf",  "plot_fill": "#6d5acd33",
    },
    "light": {
        "bg":        "#eef0f7",  "surface":   "#ffffff",  "card":      "#f5f7ff",
        "border":    "#d0d5e8",  "accent":    "#5b50c8",  "text":      "#1e293b",
        "dim":       "#64748b",  "green":     "#15803d",  "red":       "#dc2626",
        "yellow":    "#b45309",  "blue":      "#0284c7",  "tree_bg":   "#ffffff",
        "tree_sel":  "#5b50c8",  "tree_head": "#eef0f7",  "term_bg":   "#0f0f1e",
        "term_fg":   "#a0ffa0",  "plot_bg":   "#f5f7ff",  "plot_fg":   "#1e293b",
        "plot_grid": "#d0d5e8",  "plot_line": "#5b50c8",  "plot_fill": "#5b50c820",
    },
}

# ── OUI Database (IEEE manufacturer lookup) ───────────────────────────────────
_OUI_DB:    dict = {}
_OUI_READY: bool = False

def _load_oui_bg():
    global _OUI_DB, _OUI_READY
    cache = Path.home() / ".airgui_oui.json"
    if cache.exists():
        try:
            _OUI_DB    = json.loads(cache.read_text())
            _OUI_READY = bool(_OUI_DB)
            return
        except Exception:
            pass
    try:
        url = "https://standards-oui.ieee.org/oui/oui.csv"
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        db: dict = {}
        for line in data.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 3:
                prefix = parts[1].strip().upper().replace("-", "")[:6]
                vendor = parts[2].strip().strip('"')
                if prefix:
                    db[prefix] = vendor
        _OUI_DB    = db
        _OUI_READY = True
        cache.write_text(json.dumps(db))
    except Exception:
        _OUI_READY = False

def oui_lookup(mac: str) -> str:
    if not _OUI_READY or not mac:
        return ""
    prefix = re.sub(r"[:\-.]", "", mac.upper())[:6]
    v = _OUI_DB.get(prefix, "")
    return v[:24] if v else ""

# ── Helpers ───────────────────────────────────────────────────────────────────

def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return "", "Timeout"
    except FileNotFoundError:
        return "", f"{cmd[0]}: not found"
    except Exception as e:
        return "", str(e)

def get_wireless_interfaces():
    out, _ = run_cmd(["iw", "dev"])
    return re.findall(r"Interface\s+(\S+)", out)

# ── Custom Widgets ────────────────────────────────────────────────────────────

class Card(ctk.CTkFrame):
    def __init__(self, parent, title="", **kw):
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width",  1)
        kw.setdefault("fg_color",      ("#f0f4ff", "#1c1c38"))
        kw.setdefault("border_color",  ("#c8cfe8", "#2d2d58"))
        super().__init__(parent, **kw)
        if title:
            ctk.CTkLabel(self, text=title.upper(),
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=("gray55", "gray50"),
                         anchor="w").pack(anchor="w", padx=14, pady=(10, 0))

class Dot(ctk.CTkLabel):
    def on(self,   t=""): self.configure(text=f"●  {t}", text_color="#22c55e")
    def off(self,  t=""): self.configure(text=f"●  {t}", text_color="#ef4444")
    def warn(self, t=""): self.configure(text=f"●  {t}", text_color="#f59e0b")

class IconButton(ctk.CTkButton):
    def __init__(self, parent, icon, cmd, **kw):
        kw.setdefault("width", 34);  kw.setdefault("height", 34)
        kw.setdefault("text", icon)
        kw.setdefault("fg_color",    ("#dde2f0", "#252545"))
        kw.setdefault("hover_color", ("#c8ceea", "#333360"))
        kw.setdefault("text_color",  ("#333",    "#ccc"))
        kw.setdefault("corner_radius", 8)
        super().__init__(parent, command=cmd, **kw)

# ── Main Application ──────────────────────────────────────────────────────────

class AirGUI(ctk.CTk):
    _THEME = "dark"

    def __init__(self):
        super().__init__()
        self.title("AirGUI")
        self.geometry("1440x900")
        self.minsize(1160, 760)

        # Scan state
        self.iface_var     = tk.StringVar()
        self.iface_var2    = tk.StringVar()
        self.mon_iface     = None
        self.scan_proc     = None
        self.scan_tmpdir   = None
        self.band_var      = tk.StringVar(value="abg")
        self.networks:  dict = {}
        self.clients:   dict = {}
        self.selected_net   = None
        self._companion_net = None
        self._running       = False
        self._scan_start    = 0
        self._sig_history: dict = defaultdict(lambda: deque(maxlen=120))
        self._pmkid_proc    = None

        # Form vars
        self.channel_var  = tk.StringVar()
        self.deauth_count = tk.StringVar(value="0")
        self.client_mac   = tk.StringVar(value="FF:FF:FF:FF:FF:FF")
        self.cap_path     = tk.StringVar()
        self.wl_path      = tk.StringVar()
        self.pmkid_out    = tk.StringVar()
        self.pmkid_hash   = tk.StringVar()
        self.valid_result = tk.StringVar(value="")

        # Target display vars
        self.t_ssid   = tk.StringVar(value="—")
        self.t_bssid  = tk.StringVar(value="—")
        self.t_ch     = tk.StringVar(value="—")
        self.t_enc    = tk.StringVar(value="—")
        self.t_band   = tk.StringVar(value="—")
        self.t_pwr    = tk.StringVar(value="—")
        self.t_vendor = tk.StringVar(value="—")

        # Companion display vars
        self.c_bssid  = tk.StringVar(value="None detected")
        self.c_band   = tk.StringVar(value="—")
        self.c_ch     = tk.StringVar(value="—")

        self._build_ttk_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._refresh_interfaces)

        # Load OUI in background
        threading.Thread(target=self._load_oui_then_log, daemon=True).start()

    def _load_oui_then_log(self):
        _load_oui_bg()
        msg = f"OUI database loaded ({len(_OUI_DB):,} entries)." if _OUI_READY \
              else "OUI database unavailable (check internet connection)."
        self.after(0, self.log, msg, "info" if _OUI_READY else "warn")

    # ── TTK Styles ────────────────────────────────────────────────────────────

    def _build_ttk_style(self):
        ttk.Style().theme_use("clam")
        self._apply_ttk_theme()

    def _apply_ttk_theme(self):
        t = _TTK[self._THEME]
        s = ttk.Style()
        s.configure(".",
            background=t["surface"], foreground=t["text"],
            fieldbackground=t["card"], bordercolor=t["border"],
            troughcolor=t["card"], relief="flat")
        s.configure("Treeview",
            background=t["tree_bg"], foreground=t["text"],
            fieldbackground=t["tree_bg"], rowheight=25,
            bordercolor=t["border"], relief="flat", font=("Segoe UI", 9))
        s.configure("Treeview.Heading",
            background=t["tree_head"], foreground=t["dim"],
            relief="flat", bordercolor=t["border"],
            font=("Segoe UI", 9, "bold"))
        s.map("Treeview",
            background=[("selected", t["tree_sel"])],
            foreground=[("selected", "#ffffff")])
        for orient in ("Vertical", "Horizontal"):
            s.configure(f"{orient}.TScrollbar",
                background=t["card"], troughcolor=t["surface"],
                bordercolor=t["border"], arrowcolor=t["dim"])

    # ── Root Layout ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._sidebar = ctk.CTkScrollableFrame(
            body, width=295, corner_radius=0, fg_color="transparent",
            scrollbar_button_color=("gray75", "#2d2d58"),
            scrollbar_button_hover_color=("gray65", "#3d3d70"))
        self._sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._build_sidebar(self._sidebar)
        self._build_main(right)
        self._build_terminal(right)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, height=56, corner_radius=0,
                           fg_color=("gray92", "#0a0a18"))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(hdr, fg_color="transparent")
        logo.grid(row=0, column=0, padx=18, pady=10, sticky="w")
        ctk.CTkLabel(logo, text="✦", font=ctk.CTkFont(size=22),
                     text_color=("#6d5acd", "#9d8ae8")).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(logo, text="AirGUI",
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color=("gray10", "#e2e8f0")).pack(side="left")

        ctk.CTkLabel(hdr,
                     text="Wireless Security Auditing  ·  Authorized Testing Only",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray55", "#5a5a80")).grid(
            row=0, column=1, pady=10, sticky="w")

        tr = ctk.CTkFrame(hdr, fg_color="transparent")
        tr.grid(row=0, column=2, padx=16, pady=10, sticky="e")
        ctk.CTkLabel(tr, text="☀", font=ctk.CTkFont(size=14),
                     text_color=("gray55", "#5a5a80")).pack(side="left", padx=(0, 2))
        self._theme_sw = ctk.CTkSwitch(
            tr, text="", width=48, height=24,
            command=self._toggle_theme,
            button_color=("#6d5acd", "#6d5acd"),
            button_hover_color=("#5a4ab0", "#8470e0"),
            progress_color=("#c8c0f0", "#3a2d7a"))
        self._theme_sw.pack(side="left")
        self._theme_sw.select()
        ctk.CTkLabel(tr, text="🌙", font=ctk.CTkFont(size=14),
                     text_color=("gray55", "#5a5a80")).pack(side="left", padx=(2, 0))

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        G = {"padx": 5, "pady": 4, "fill": "x"}

        # Interface
        ic = Card(parent, title=" Interface")
        ic.pack(**G)

        irow = ctk.CTkFrame(ic, fg_color="transparent")
        irow.pack(fill="x", padx=10, pady=(4, 6))
        irow.grid_columnconfigure(0, weight=1)
        self.iface_cb = ctk.CTkComboBox(
            irow, variable=self.iface_var, values=[], state="readonly", height=32,
            fg_color=("gray92", "#12122a"), border_color=("gray78", "#2d2d58"),
            button_color=("gray78", "#2d2d58"), button_hover_color=("gray68", "#3d3d70"),
            dropdown_fg_color=("white", "#1c1c38"), text_color=("gray10", "#e2e8f0"))
        self.iface_cb.grid(row=0, column=0, sticky="ew")
        IconButton(irow, "⟳", self._refresh_interfaces).grid(row=0, column=1, padx=(6, 0))

        self.mon_btn = ctk.CTkButton(
            ic, text="▶  Start Monitor Mode", height=36,
            fg_color=("#6d5acd", "#6d5acd"), hover_color=("#5a4ab0", "#8470e0"),
            font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=self._toggle_monitor)
        self.mon_btn.pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(
            ic, text="✕  Kill Interfering Processes", height=32,
            fg_color="transparent", hover_color=("#fde8e8", "#3d1515"),
            border_color=("#dc2626", "#7f2020"), border_width=1,
            text_color=("#dc2626", "#ff8080"), corner_radius=10,
            command=self._check_kill).pack(fill="x", padx=10, pady=(0, 4))

        self._mon_dot = Dot(ic, text="●  Monitor OFF",
                            font=ctk.CTkFont(size=12), text_color="#ef4444")
        self._mon_dot.off("Monitor OFF")
        self._mon_dot.pack(anchor="w", padx=14, pady=(0, 10))

        # Band
        bc = Card(parent, title=" Band Filter")
        bc.pack(**G)
        self._band_seg = ctk.CTkSegmentedButton(
            bc, values=["All", "2.4 GHz", "5 GHz"],
            command=self._on_band_change, height=32, corner_radius=10,
            fg_color=("gray85", "#1a1a35"),
            selected_color=("#6d5acd", "#6d5acd"),
            selected_hover_color=("#5a4ab0", "#8470e0"),
            unselected_color=("gray85", "#1a1a35"),
            unselected_hover_color=("gray78", "#252550"),
            text_color=("gray10", "#bcc6d8"),
            font=ctk.CTkFont(size=12, weight="bold"))
        self._band_seg.pack(fill="x", padx=10, pady=(4, 10))
        self._band_seg.set("All")

        # Scan
        sc = Card(parent, title=" Scan")
        sc.pack(**G)
        crow = ctk.CTkFrame(sc, fg_color="transparent")
        crow.pack(fill="x", padx=10, pady=(4, 6))
        crow.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(crow, text="Channel:", font=ctk.CTkFont(size=11),
                     text_color=("gray50", "gray55"), width=64, anchor="w").grid(row=0, column=0)
        ctk.CTkEntry(crow, textvariable=self.channel_var, placeholder_text="all", height=30,
                     fg_color=("gray92", "#10102a"), border_color=("gray78", "#2d2d58"),
                     text_color=("gray10", "#e2e8f0"),
                     placeholder_text_color=("gray60", "gray55")).grid(row=0, column=1, sticky="ew")

        self._scan_btn = ctk.CTkButton(
            sc, text="▶  Start Scan", height=36,
            fg_color=("#166534", "#166534"), hover_color=("#15803d", "#22c55e"),
            text_color="#ffffff", font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=self._toggle_scan)
        self._scan_btn.pack(fill="x", padx=10, pady=(0, 4))
        self._scan_dot = Dot(sc, text="●  Not scanning",
                             font=ctk.CTkFont(size=11), text_color="#f59e0b")
        self._scan_dot.warn("Not scanning")
        self._scan_dot.pack(anchor="w", padx=14, pady=(0, 10))

        # Target
        tc = Card(parent, title=" Selected Target")
        tc.pack(**G)
        for label, var in [
            ("SSID",    self.t_ssid),  ("BSSID",  self.t_bssid),
            ("Channel", self.t_ch),    ("Band",   self.t_band),
            ("Signal",  self.t_pwr),   ("Enc",    self.t_enc),
            ("Vendor",  self.t_vendor),
        ]:
            r = ctk.CTkFrame(tc, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=1)
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=f"{label}:", width=60, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(r, textvariable=var, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=("#5b50c8", "#a78bfa")).grid(row=0, column=1, sticky="w")
        ctk.CTkFrame(tc, height=6, fg_color="transparent").pack()

        # Deauth
        dc = Card(parent, title=" Deauth Attack")
        dc.pack(**G)
        for label, var, hint in [
            ("Packets:", self.deauth_count, "0=∞"),
            ("Client:",  self.client_mac,  None),
        ]:
            r = ctk.CTkFrame(dc, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=(4, 0))
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, width=64, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).grid(row=0, column=0)
            ctk.CTkEntry(r, textvariable=var, height=30,
                         fg_color=("gray92", "#10102a"),
                         border_color=("gray78", "#2d2d58"),
                         text_color=("gray10", "#e2e8f0")).grid(row=0, column=1, sticky="ew")
            if hint:
                ctk.CTkLabel(r, text=f"({hint})", width=36,
                             font=ctk.CTkFont(size=10),
                             text_color=("gray55", "gray50")).grid(row=0, column=2, padx=4)

        ctk.CTkButton(
            dc, text="⚡  Deauth Attack", height=36,
            fg_color=("#7f1d1d", "#7f1d1d"), hover_color=("#b91c1c", "#ef4444"),
            text_color="#ffffff", font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=self._deauth).pack(fill="x", padx=10, pady=(6, 10))

        # Dual-Band Deauth
        dbc = Card(parent, title=" Dual-Band Deauth")
        dbc.pack(**G)

        ctk.CTkLabel(dbc,
                     text="Auto-detected companion AP (same SSID, other band).",
                     font=ctk.CTkFont(size=10), text_color=("gray50", "gray55"),
                     wraplength=250).pack(anchor="w", padx=14, pady=(2, 6))

        for label, var in [("BSSID:", self.c_bssid), ("Band:", self.c_band), ("CH:", self.c_ch)]:
            r = ctk.CTkFrame(dbc, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=1)
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, width=44, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(r, textvariable=var, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=("#5b50c8", "#a78bfa")).grid(row=0, column=1, sticky="w")

        ir2 = ctk.CTkFrame(dbc, fg_color="transparent")
        ir2.pack(fill="x", padx=10, pady=(6, 2))
        ir2.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ir2, text="2nd Iface:", width=68, anchor="w",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50", "gray55")).grid(row=0, column=0)
        self.iface_cb2 = ctk.CTkComboBox(
            ir2, variable=self.iface_var2, values=[], height=28,
            fg_color=("gray92", "#12122a"), border_color=("gray78", "#2d2d58"),
            button_color=("gray78", "#2d2d58"), button_hover_color=("gray68", "#3d3d70"),
            dropdown_fg_color=("white", "#1c1c38"), text_color=("gray10", "#e2e8f0"))
        self.iface_cb2.grid(row=0, column=1, sticky="ew")

        self._deauth_both_btn = ctk.CTkButton(
            dbc, text="⚡⚡  Deauth Both Bands", height=36,
            fg_color=("#6b21a8", "#6b21a8"), hover_color=("#7e22ce", "#a855f7"),
            text_color="#ffffff", font=ctk.CTkFont(weight="bold"), corner_radius=10,
            state="disabled", command=self._deauth_both)
        self._deauth_both_btn.pack(fill="x", padx=10, pady=(6, 4))

        self._companion_dot = Dot(dbc, text="●  No companion found",
                                  font=ctk.CTkFont(size=11), text_color="#f59e0b")
        self._companion_dot.warn("No companion found")
        self._companion_dot.pack(anchor="w", padx=14, pady=(0, 8))

        # Capture
        hc = Card(parent, title=" Handshake Capture")
        hc.pack(**G)
        ctk.CTkButton(
            hc, text="📡  Capture Handshake", height=34,
            fg_color=("#1e3a8a", "#1e3a8a"), hover_color=("#1d4ed8", "#3b82f6"),
            corner_radius=10, command=self._capture_handshake).pack(
            fill="x", padx=10, pady=(4, 3))
        ctk.CTkButton(
            hc, text="⚡ + 📡  Deauth & Capture", height=34,
            fg_color=("#6b21a8", "#6b21a8"), hover_color=("#7e22ce", "#a855f7"),
            corner_radius=10, command=self._deauth_and_capture).pack(
            fill="x", padx=10, pady=(0, 10))

        # Crack
        cc = Card(parent, title=" Crack Handshake")
        cc.pack(**G)
        for label, var, browse in [
            ("Capture:",  self.cap_path, self._browse_cap),
            ("Wordlist:", self.wl_path,  self._browse_wordlist),
        ]:
            ctk.CTkLabel(cc, text=label, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).pack(anchor="w", padx=14, pady=(6, 0))
            r = ctk.CTkFrame(cc, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=(1, 0))
            r.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(r, textvariable=var, height=30,
                         fg_color=("gray92", "#10102a"),
                         border_color=("gray78", "#2d2d58"),
                         text_color=("gray10", "#e2e8f0")).grid(row=0, column=0, sticky="ew")
            IconButton(r, "…", browse).grid(row=0, column=1, padx=(5, 0))
        ctk.CTkButton(
            cc, text="🔑  Crack with Aircrack-ng", height=36,
            fg_color=("#6d5acd", "#6d5acd"), hover_color=("#5a4ab0", "#8470e0"),
            font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=self._crack).pack(fill="x", padx=10, pady=(8, 10))

        # WPS
        wc = Card(parent, title=" WPS")
        wc.pack(**G)
        ctk.CTkButton(
            wc, text="📶  WPS Scan (wash)", height=34,
            fg_color=("#0c4a6e", "#0c4a6e"), hover_color=("#0369a1", "#0ea5e9"),
            corner_radius=10, command=self._wps_scan).pack(fill="x", padx=10, pady=(4, 3))
        ctk.CTkButton(
            wc, text="🔓  WPS Attack (reaver)", height=34,
            fg_color=("#7f1d1d", "#7f1d1d"), hover_color=("#b91c1c", "#ef4444"),
            corner_radius=10, command=self._wps_attack).pack(fill="x", padx=10, pady=(0, 10))

    # ── Main Tabs ─────────────────────────────────────────────────────────────

    def _build_main(self, parent):
        self._tabs = ctk.CTkTabview(
            parent, corner_radius=14, border_width=1,
            fg_color=("gray95", "#0f0f20"), border_color=("gray80", "#2d2d58"),
            segmented_button_fg_color=("gray88", "#16162e"),
            segmented_button_selected_color=("#6d5acd", "#6d5acd"),
            segmented_button_selected_hover_color=("#5a4ab0", "#8470e0"),
            segmented_button_unselected_color=("gray88", "#16162e"),
            segmented_button_unselected_hover_color=("gray80", "#252548"),
            text_color=("gray20", "#bcc6d8"))
        self._tabs.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        for name in ["  Networks  ", "  Clients  ", "  Signal Graph  ", "  Tools  "]:
            self._tabs.add(name)

        self._build_network_table(self._tabs.tab("  Networks  "))
        self._build_client_table(self._tabs.tab("  Clients  "))
        self._build_signal_graph_tab(self._tabs.tab("  Signal Graph  "))
        self._build_tools_tab(self._tabs.tab("  Tools  "))

    # ── Networks Table ────────────────────────────────────────────────────────

    def _build_network_table(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_columnconfigure(0, weight=1)

        cols   = ("ssid","bssid","ch","pwr","enc","cipher","auth","band","clients","vendor")
        heads  = ("SSID","BSSID","CH","PWR","Privacy","Cipher","Auth","Band","Clients","Vendor")
        widths = (180, 152, 40, 58, 88, 72, 50, 68, 58, 130)

        t = _TTK[self._THEME]
        wrap = tk.Frame(parent, bg=t["tree_bg"], bd=0, highlightthickness=0)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        self._net_wrap = wrap

        self.net_tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for col, head, w in zip(cols, heads, widths):
            self.net_tree.heading(col, text=head,
                                  command=lambda c=col: self._sort_tree(c))
            self.net_tree.column(col, width=w, minwidth=28,
                                  anchor="w" if col in ("ssid","vendor") else "center")

        ysb = ttk.Scrollbar(wrap, orient="vertical",   command=self.net_tree.yview)
        xsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.net_tree.xview)
        self.net_tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.net_tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        self.net_tree.bind("<<TreeviewSelect>>", self._on_net_select)
        self.net_tree.tag_configure("wpa3", foreground="#22c55e")
        self.net_tree.tag_configure("wpa2", foreground="#38bdf8")
        self.net_tree.tag_configure("wpa",  foreground="#f59e0b")
        self.net_tree.tag_configure("wep",  foreground="#ef4444")
        self.net_tree.tag_configure("open", foreground="#8895aa")

        self._net_sb = tk.Frame(parent, bg=t["surface"], height=28, bd=0)
        self._net_sb.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.net_count_lbl = tk.Label(self._net_sb, text="0 networks",
                                       bg=t["surface"], fg=t["dim"], font=("Segoe UI", 9))
        self.net_count_lbl.pack(side="left", padx=10)
        self.elapsed_lbl = tk.Label(self._net_sb, text="",
                                     bg=t["surface"], fg=t["dim"], font=("Segoe UI", 9))
        self.elapsed_lbl.pack(side="right", padx=10)

    # ── Clients Table ─────────────────────────────────────────────────────────

    def _build_client_table(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_columnconfigure(0, weight=1)

        cols   = ("mac","bssid","ssid","pwr","packets","vendor","probes")
        heads  = ("Client MAC","AP BSSID","AP SSID","PWR","Packets","Vendor","Probed SSIDs")
        widths = (152, 152, 175, 58, 66, 120, 230)

        t = _TTK[self._THEME]
        wrap = tk.Frame(parent, bg=t["tree_bg"], bd=0, highlightthickness=0)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        self._cli_wrap = wrap

        self.cli_tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for col, head, w in zip(cols, heads, widths):
            self.cli_tree.heading(col, text=head)
            self.cli_tree.column(col, width=w, minwidth=28,
                                  anchor="w" if col in ("ssid","probes","vendor") else "center")

        ysb = ttk.Scrollbar(wrap, orient="vertical",   command=self.cli_tree.yview)
        xsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.cli_tree.xview)
        self.cli_tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.cli_tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        self.cli_tree.bind("<<TreeviewSelect>>", self._on_cli_select)

        self._cli_sb = tk.Frame(parent, bg=t["surface"], height=28, bd=0)
        self._cli_sb.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.cli_count_lbl = tk.Label(self._cli_sb, text="0 clients",
                                       bg=t["surface"], fg=t["dim"], font=("Segoe UI", 9))
        self.cli_count_lbl.pack(side="left", padx=10)

    # ── Signal Graph Tab ──────────────────────────────────────────────────────

    def _build_signal_graph_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        if not HAS_MPL:
            ctk.CTkLabel(parent,
                         text="matplotlib not installed.\n\npip install matplotlib",
                         font=ctk.CTkFont(size=14),
                         text_color=("gray50", "gray55")).pack(expand=True)
            return

        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl, text="Showing signal history for:",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50", "gray55")).grid(row=0, column=0, padx=(0, 8))
        self._graph_label = ctk.CTkLabel(ctrl, text="(select a network)",
                                          font=ctk.CTkFont(size=11, weight="bold"),
                                          text_color=("#5b50c8", "#a78bfa"), anchor="w")
        self._graph_label.grid(row=0, column=1, sticky="w")
        ctk.CTkButton(ctrl, text="Clear History", width=110, height=28,
                      fg_color=("gray82", "#252545"), hover_color=("gray72", "#333365"),
                      text_color=("gray20", "#9090b8"), corner_radius=8,
                      font=ctk.CTkFont(size=11),
                      command=self._clear_sig_history).grid(row=0, column=2)

        t = _TTK[self._THEME]
        self._fig = Figure(figsize=(8, 3.2), dpi=96, facecolor=t["plot_bg"])
        self._ax  = self._fig.add_subplot(111)
        self._fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.14)

        fig_frame = tk.Frame(parent, bg=t["plot_bg"], bd=0, highlightthickness=0)
        fig_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self._fig_frame = fig_frame

        self._canvas = FigureCanvasTkAgg(self._fig, master=fig_frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._style_graph()

    def _style_graph(self):
        if not HAS_MPL or not hasattr(self, "_ax"):
            return
        t = _TTK[self._THEME]
        self._ax.set_facecolor(t["plot_bg"])
        self._fig.patch.set_facecolor(t["plot_bg"])
        self._ax.tick_params(colors=t["dim"], labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_color(t["plot_grid"])
        self._ax.set_xlabel("Time (seconds ago)", color=t["dim"], fontsize=9)
        self._ax.set_ylabel("RSSI (dBm)", color=t["dim"], fontsize=9)
        self._ax.grid(True, color=t["plot_grid"], alpha=0.5, linestyle="--", linewidth=0.8)
        if hasattr(self, "_fig_frame"):
            self._fig_frame.configure(bg=t["plot_bg"])
            self._canvas.get_tk_widget().configure(bg=t["plot_bg"])

    def _update_signal_graph(self):
        if not HAS_MPL or not hasattr(self, "_ax"):
            return
        t     = _TTK[self._THEME]
        bssid = self.selected_net["bssid"] if self.selected_net else None
        self._ax.clear()
        self._style_graph()

        if bssid and bssid in self._sig_history and self._sig_history[bssid]:
            hist = list(self._sig_history[bssid])
            now  = time.time()
            xs   = [h[0] - now for h in hist]
            ys   = [h[1] for h in hist]
            self._ax.plot(xs, ys, color=t["plot_line"], linewidth=2.2, zorder=3)
            self._ax.fill_between(xs, ys, min(ys) - 5, alpha=0.18, color=t["plot_line"])
            ssid = self.selected_net.get("ssid", bssid)
            self._ax.set_title(f"{ssid}  [{bssid}]",
                               color=t["plot_fg"], fontsize=10, pad=6)
            if ys:
                self._ax.set_ylim(min(ys) - 5, max(ys) + 5)
        else:
            self._ax.set_title("Select a network in the Networks tab to view its signal history",
                                color=t["dim"], fontsize=10, pad=6)
        self._canvas.draw_idle()

    def _clear_sig_history(self):
        self._sig_history.clear()
        self._update_signal_graph()
        self.log("Signal history cleared.", "warn")

    # ── Tools Tab ─────────────────────────────────────────────────────────────

    def _build_tools_tab(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        # Left: PMKID
        lf = ctk.CTkFrame(parent, fg_color="transparent")
        lf.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        lf.grid_rowconfigure(0, weight=0)
        lf.grid_columnconfigure(0, weight=1)

        pc = Card(lf, title=" PMKID Attack  (hcxdumptool)")
        pc.grid(row=0, column=0, sticky="new")

        ctk.CTkLabel(pc, anchor="w", wraplength=280,
                     text="Capture PMKID from target AP — no client needed.\n"
                          "Requires: hcxdumptool, hcxpcapngtool",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray45", "gray55")).pack(anchor="w", padx=14, pady=(2, 8))

        for label, var, ph, browse in [
            ("Output file (.pcapng):", self.pmkid_out,  "/tmp/pmkid.pcapng",  self._browse_pmkid_out),
            ("Hash file (.hc22000):", self.pmkid_hash, "/tmp/pmkid.hc22000", self._browse_pmkid_hash),
        ]:
            ctk.CTkLabel(pc, text=label, anchor="w", font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).pack(anchor="w", padx=14)
            r = ctk.CTkFrame(pc, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=(2, 6))
            r.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(r, textvariable=var, height=30, placeholder_text=ph,
                         fg_color=("gray92", "#10102a"), border_color=("gray78", "#2d2d58"),
                         text_color=("gray10", "#e2e8f0")).grid(row=0, column=0, sticky="ew")
            IconButton(r, "…", browse).grid(row=0, column=1, padx=(5, 0))

        btn_row = ctk.CTkFrame(pc, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkButton(btn_row, text="▶  Start Capture", height=34,
                      fg_color=("#166534", "#166534"), hover_color=("#15803d", "#22c55e"),
                      corner_radius=10, font=ctk.CTkFont(weight="bold"),
                      command=self._pmkid_start).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ctk.CTkButton(btn_row, text="■  Stop", height=34, width=70,
                      fg_color=("#7f1d1d", "#7f1d1d"), hover_color=("#b91c1c", "#ef4444"),
                      corner_radius=10, command=self._pmkid_stop).pack(side="left", padx=(3, 0))

        ctk.CTkButton(pc, text="⚙  Convert → .hc22000  (hcxpcapngtool)", height=34,
                      fg_color=("#0c4a6e", "#0c4a6e"), hover_color=("#0369a1", "#0ea5e9"),
                      corner_radius=10, command=self._pmkid_convert).pack(
            fill="x", padx=10, pady=(0, 10))

        # Right: Validator + Export
        rf = ctk.CTkFrame(parent, fg_color="transparent")
        rf.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        rf.grid_rowconfigure(0, weight=0)
        rf.grid_rowconfigure(1, weight=0)
        rf.grid_columnconfigure(0, weight=1)

        # Handshake Validator
        vc = Card(rf, title=" Handshake Validator")
        vc.grid(row=0, column=0, sticky="new", pady=(0, 6))

        ctk.CTkLabel(vc, anchor="w",
                     text="Check if a .cap file contains a valid 4-way handshake.",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray45", "gray55")).pack(anchor="w", padx=14, pady=(2, 6))

        vr = ctk.CTkFrame(vc, fg_color="transparent")
        vr.pack(fill="x", padx=10, pady=(0, 6))
        vr.grid_columnconfigure(0, weight=1)
        self._vcap_var = tk.StringVar()
        ctk.CTkEntry(vr, textvariable=self._vcap_var, height=30,
                     placeholder_text="Select .cap file…",
                     fg_color=("gray92", "#10102a"), border_color=("gray78", "#2d2d58"),
                     text_color=("gray10", "#e2e8f0")).grid(row=0, column=0, sticky="ew")
        IconButton(vr, "…", self._browse_vcap).grid(row=0, column=1, padx=(5, 0))

        ctk.CTkButton(vc, text="✔  Validate Handshake", height=34,
                      fg_color=("#6d5acd", "#6d5acd"), hover_color=("#5a4ab0", "#8470e0"),
                      corner_radius=10, font=ctk.CTkFont(weight="bold"),
                      command=self._validate_handshake).pack(fill="x", padx=10, pady=(0, 6))

        self._valid_lbl = ctk.CTkLabel(vc, textvariable=self.valid_result,
                                        font=ctk.CTkFont(size=12, weight="bold"),
                                        text_color=("gray50", "gray50"))
        self._valid_lbl.pack(anchor="w", padx=14, pady=(0, 10))

        # Export
        ec = Card(rf, title=" Export Report")
        ec.grid(row=1, column=0, sticky="new")

        ctk.CTkLabel(ec, anchor="w", wraplength=280,
                     text="Generate a report from the current scan session.\n"
                          "HTML report opens in your browser automatically.",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray45", "gray55")).pack(anchor="w", padx=14, pady=(2, 8))

        ctk.CTkButton(ec, text="🌐  Export HTML Report", height=36,
                      fg_color=("#6d5acd", "#6d5acd"), hover_color=("#5a4ab0", "#8470e0"),
                      font=ctk.CTkFont(weight="bold"), corner_radius=10,
                      command=self._export_html).pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(ec, text="📄  Export CSV", height=34,
                      fg_color=("#0c4a6e", "#0c4a6e"), hover_color=("#0369a1", "#0ea5e9"),
                      corner_radius=10, command=self._export_csv).pack(
            fill="x", padx=10, pady=(0, 10))

    # ── Terminal ──────────────────────────────────────────────────────────────

    def _build_terminal(self, parent):
        wrap = ctk.CTkFrame(parent, corner_radius=14, border_width=1,
                            border_color=("gray80", "#2d2d58"),
                            fg_color=("gray92", "#08080f"))
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        th = ctk.CTkFrame(wrap, fg_color="transparent", height=34)
        th.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 0))
        th.grid_propagate(False)
        th.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(th, text="⬛  Terminal Output",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray50", "gray45"), anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(th, text="Clear", width=64, height=26,
                      fg_color=("gray82", "#252545"), hover_color=("gray72", "#333365"),
                      text_color=("gray20", "#9090b8"), corner_radius=8,
                      font=ctk.CTkFont(size=11),
                      command=self._clear_terminal).grid(row=0, column=1, sticky="e")

        t = _TTK[self._THEME]
        self.terminal = tk.Text(wrap, height=8, bg=t["term_bg"], fg=t["term_fg"],
                                font=("Consolas", 9), insertbackground="#ffffff",
                                relief="flat", bd=10, state="disabled",
                                selectbackground="#3d3d70", wrap="word")
        tsb = ttk.Scrollbar(wrap, orient="vertical", command=self.terminal.yview)
        self.terminal.configure(yscrollcommand=tsb.set)
        self.terminal.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(4, 10))
        tsb.grid(row=1, column=1, sticky="ns", pady=(4, 10), padx=(0, 6))

        self.terminal.tag_configure("info", foreground="#38bdf8")
        self.terminal.tag_configure("ok",   foreground="#22c55e")
        self.terminal.tag_configure("warn", foreground="#f59e0b")
        self.terminal.tag_configure("err",  foreground="#ef4444")
        self.terminal.tag_configure("cmd",  foreground="#c084fc")

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._THEME = "light" if self._THEME == "dark" else "dark"
        ctk.set_appearance_mode("light" if self._THEME == "light" else "dark")
        self._apply_ttk_theme()
        t = _TTK[self._THEME]
        for wrap in (self._net_wrap, self._cli_wrap):
            wrap.configure(bg=t["tree_bg"])
        for sb in (self._net_sb, self._cli_sb):
            sb.configure(bg=t["surface"])
        for lbl in (self.net_count_lbl, self.elapsed_lbl, self.cli_count_lbl):
            lbl.configure(bg=t["surface"], fg=t["dim"])
        self.terminal.configure(bg=t["term_bg"])
        if HAS_MPL and hasattr(self, "_ax"):
            self._update_signal_graph()

    def _on_band_change(self, val):
        self.band_var.set({"All": "abg", "2.4 GHz": "bg", "5 GHz": "a"}.get(val, "abg"))

    # ── Interface ─────────────────────────────────────────────────────────────

    def _refresh_interfaces(self):
        ifaces = get_wireless_interfaces()
        for cb in (self.iface_cb, self.iface_cb2):
            cb.configure(values=ifaces)
        if ifaces:
            if not self.iface_var.get() or self.iface_var.get() not in ifaces:
                self.iface_cb.set(ifaces[0])
            self.log(f"Interfaces: {', '.join(ifaces)}", "info")
        else:
            self.log("No wireless interfaces found. aircrack-ng + Linux required.", "warn")

    def _toggle_monitor(self):
        if self.mon_iface:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _start_monitor(self):
        iface = self.iface_var.get()
        if not iface:
            messagebox.showerror("Error", "Select a wireless interface first.")
            return
        cmd = ["airmon-ng", "start", iface]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        out, err = run_cmd(cmd)
        self.log(out or err or "Done.")
        mon = re.search(r"monitor mode vif enabled.*?(\w+mon\w*)", out + err)
        self.mon_iface = (mon.group(1) if mon else
                          next((i for i in get_wireless_interfaces() if "mon" in i),
                               iface + "mon"))
        self.log(f"Monitor interface: {self.mon_iface}", "ok")
        self.mon_btn.configure(text="■  Stop Monitor Mode",
                               fg_color=("#7f1d1d","#7f1d1d"),
                               hover_color=("#b91c1c","#ef4444"))
        self._mon_dot.on(f"Monitor ON  ({self.mon_iface})")
        self._refresh_interfaces()

    def _stop_monitor(self):
        out, err = run_cmd(["airmon-ng", "stop", self.mon_iface])
        self.log(out or err or "Done.")
        self.mon_iface = None
        self.mon_btn.configure(text="▶  Start Monitor Mode",
                               fg_color=("#6d5acd","#6d5acd"),
                               hover_color=("#5a4ab0","#8470e0"))
        self._mon_dot.off("Monitor OFF")
        self._refresh_interfaces()

    def _check_kill(self):
        out, err = run_cmd(["airmon-ng", "check", "kill"])
        self.log(out or err or "Done.", "warn")

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _toggle_scan(self):
        if self._running:
            self._stop_scan()
        else:
            self._start_scan()

    def _start_scan(self):
        iface = self.mon_iface or self.iface_var.get()
        if not iface:
            messagebox.showerror("Error", "No interface selected.")
            return
        self.scan_tmpdir = tempfile.mkdtemp(prefix="airgui_")
        prefix = os.path.join(self.scan_tmpdir, "scan")
        cmd    = ["airodump-ng", "--output-format", "csv", "-w", prefix]
        band   = self.band_var.get()
        if band != "abg":
            cmd += ["--band", band]
        ch = self.channel_var.get().strip()
        if ch:
            cmd += ["-c", ch]
        cmd.append(iface)
        self.log(f"$ {' '.join(cmd)}", "cmd")
        try:
            kw = {"preexec_fn": os.setsid} if hasattr(os, "setsid") else {}
            self.scan_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        except FileNotFoundError:
            self.log("airodump-ng not found. Install aircrack-ng suite.", "err")
            return
        self._running    = True
        self._scan_start = time.time()
        self._scan_btn.configure(text="■  Stop Scan",
                                  fg_color=("#7f1d1d","#7f1d1d"),
                                  hover_color=("#b91c1c","#ef4444"))
        self._scan_dot.on("Scanning…")
        threading.Thread(target=self._scan_loop, args=(self.scan_tmpdir,), daemon=True).start()

    def _stop_scan(self):
        self._running = False
        if self.scan_proc:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self.scan_proc.pid), signal.SIGTERM)
                else:
                    self.scan_proc.terminate()
            except Exception:
                pass
            self.scan_proc = None
        self._scan_btn.configure(text="▶  Start Scan",
                                  fg_color=("#166534","#166534"),
                                  hover_color=("#15803d","#22c55e"))
        self._scan_dot.warn("Scan stopped.")
        self.log("Scan stopped.", "warn")

    def _scan_loop(self, tmpdir):
        while self._running:
            time.sleep(2)
            try:
                csvs = sorted(f for f in os.listdir(tmpdir) if f.endswith(".csv"))
                if csvs:
                    self._parse_csv(os.path.join(tmpdir, csvs[-1]))
            except Exception:
                pass

    def _parse_csv(self, path):
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read()
        except Exception:
            return
        sep   = "\r\n\r\n" if "\r\n\r\n" in content else "\n\n"
        parts = content.split(sep, 1)
        ap_sec, cli_sec = parts[0], (parts[1] if len(parts) > 1 else "")
        networks, clients = {}, {}

        for i, row in enumerate(csv.reader(io.StringIO(ap_sec))):
            if i == 0 or len(row) < 14:
                continue
            try:
                bssid = row[0].strip()
                if not bssid or bssid == "BSSID":
                    continue
                ch, privacy   = row[3].strip(), row[5].strip()
                cipher, auth  = row[6].strip(), row[7].strip()
                power, beacons = row[8].strip(), row[9].strip()
                essid = row[13].strip() or "<hidden>"
                try:
                    band = "5 GHz" if int(ch) > 14 else "2.4 GHz"
                except ValueError:
                    band = "?"
                enc_tag = ("wpa3" if "WPA3" in privacy else
                           "wpa2" if "WPA2" in privacy else
                           "wpa"  if "WPA"  in privacy else
                           "wep"  if "WEP"  in privacy else "open")
                networks[bssid] = dict(ssid=essid, bssid=bssid, ch=ch, pwr=power,
                                       enc=privacy, cipher=cipher, auth=auth, band=band,
                                       beacons=beacons, enc_tag=enc_tag, clients=0)
            except Exception:
                continue

        for i, row in enumerate(csv.reader(io.StringIO(cli_sec))):
            if i == 0 or len(row) < 6:
                continue
            try:
                mac = row[0].strip()
                if not mac or mac == "Station MAC":
                    continue
                pwr, packets = row[3].strip(), row[4].strip()
                ap_bssid = row[5].strip()
                probes   = ", ".join(r.strip() for r in row[6:] if r.strip())
                ap_ssid  = networks.get(ap_bssid, {}).get("ssid", "?")
                clients[mac] = dict(mac=mac, bssid=ap_bssid, ssid=ap_ssid,
                                    pwr=pwr, packets=packets, probes=probes)
                if ap_bssid in networks:
                    networks[ap_bssid]["clients"] += 1
            except Exception:
                continue

        self.networks, self.clients = networks, clients
        self.after(0, self._update_trees)

    def _update_trees(self):
        sel       = self.net_tree.selection()
        sel_bssid = self.net_tree.item(sel[0])["values"][1] if sel else None
        now       = time.time()

        self.net_tree.delete(*self.net_tree.get_children())
        for bssid, n in self.networks.items():
            try:
                self._sig_history[bssid].append((now, int(n["pwr"])))
            except (ValueError, TypeError):
                pass
            vendor = oui_lookup(bssid)
            self.net_tree.insert("", "end", iid=bssid, tags=(n["enc_tag"],),
                                 values=(n["ssid"], n["bssid"], n["ch"], n["pwr"],
                                         n["enc"], n["cipher"], n["auth"],
                                         n["band"], n["clients"], vendor))

        if sel_bssid and self.net_tree.exists(sel_bssid):
            self.net_tree.selection_set(sel_bssid)
            self.net_tree.see(sel_bssid)

        self.cli_tree.delete(*self.cli_tree.get_children())
        for mac, c in self.clients.items():
            vendor = oui_lookup(mac)
            self.cli_tree.insert("", "end", values=(c["mac"], c["bssid"], c["ssid"],
                                                     c["pwr"], c["packets"],
                                                     vendor, c["probes"]))

        nc, cc = len(self.networks), len(self.clients)
        self.net_count_lbl.config(text=f"{nc} network{'s' if nc!=1 else ''}")
        self.cli_count_lbl.config(text=f"{cc} client{'s' if cc!=1 else ''}")
        self._update_elapsed()

        if HAS_MPL and hasattr(self, "_ax"):
            self._update_signal_graph()

    def _update_elapsed(self):
        if self._scan_start:
            e    = int(time.time() - self._scan_start)
            m, s = divmod(e, 60)
            self.elapsed_lbl.config(text=f"Elapsed: {m:02d}:{s:02d}")

    def _sort_tree(self, col):
        data = [(self.net_tree.set(k, col), k) for k in self.net_tree.get_children("")]
        try:
            data.sort(key=lambda x: int(x[0]))
        except ValueError:
            data.sort()
        for i, (_, k) in enumerate(data):
            self.net_tree.move(k, "", i)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_net_select(self, _event):
        sel = self.net_tree.selection()
        if not sel:
            return
        n = self.networks.get(sel[0])
        if not n:
            return
        self.selected_net = n
        self.t_ssid.set(n["ssid"])
        self.t_bssid.set(n["bssid"])
        self.t_ch.set(n["ch"])
        self.t_enc.set(n["enc"])
        self.t_band.set(n["band"])
        self.t_pwr.set(f"{n['pwr']} dBm")
        self.t_vendor.set(oui_lookup(n["bssid"]) or "Unknown")
        self._update_companion(n)
        if HAS_MPL and hasattr(self, "_ax"):
            ssid = n.get("ssid", n["bssid"])
            self._graph_label.configure(text=f"{ssid}  [{n['bssid']}]")
            self._update_signal_graph()

    def _on_cli_select(self, _event):
        sel = self.cli_tree.selection()
        if sel:
            vals = self.cli_tree.item(sel[0])["values"]
            if vals:
                self.client_mac.set(str(vals[0]))

    def _find_companion(self, n: dict):
        ssid, band = n["ssid"], n["band"]
        for bssid, net in self.networks.items():
            if net["ssid"] == ssid and net["band"] != band and bssid != n["bssid"]:
                return net
        return None

    def _update_companion(self, n: dict):
        comp = self._find_companion(n)
        self._companion_net = comp
        if comp:
            self.c_bssid.set(comp["bssid"])
            self.c_band.set(comp["band"])
            self.c_ch.set(comp["ch"])
            self._companion_dot.on(f"Companion found  ({comp['band']})")
            self._deauth_both_btn.configure(state="normal")
        else:
            self.c_bssid.set("None detected")
            self.c_band.set("—")
            self.c_ch.set("—")
            self._companion_dot.warn("No companion found")
            self._deauth_both_btn.configure(state="disabled")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _need_target(self):
        if not self.selected_net:
            messagebox.showerror("No Target", "Select a network from the table first.")
            return False
        return True

    def _get_iface(self, override=None):
        iface = override or self.mon_iface or self.iface_var.get()
        if not iface:
            messagebox.showerror("No Interface", "No interface selected.")
            return None
        return iface

    def _deauth(self):
        if not self._need_target():
            return
        iface  = self._get_iface()
        if not iface:
            return
        bssid  = self.selected_net["bssid"]
        client = self.client_mac.get().strip() or "FF:FF:FF:FF:FF:FF"
        count  = self.deauth_count.get().strip() or "0"
        cmd = ["aireplay-ng", "--deauth", count, "-a", bssid, "-c", client, iface]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    def _deauth_both(self):
        if not self._need_target() or not self._companion_net:
            return
        iface1 = self._get_iface()
        if not iface1:
            return
        iface2 = self.iface_var2.get().strip() or iface1
        client = self.client_mac.get().strip() or "FF:FF:FF:FF:FF:FF"
        count  = self.deauth_count.get().strip() or "0"
        for bssid, iface in [
            (self.selected_net["bssid"], iface1),
            (self._companion_net["bssid"], iface2),
        ]:
            cmd = ["aireplay-ng", "--deauth", count, "-a", bssid, "-c", client, iface]
            self.log(f"$ {' '.join(cmd)}", "cmd")
            threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()
        self.log(f"Dual-band deauth → {self.selected_net['band']} + {self._companion_net['band']}", "warn")

    def _capture_handshake(self):
        if not self._need_target():
            return
        iface = self._get_iface()
        if not iface:
            return
        bssid  = self.selected_net["bssid"]
        ch     = self.selected_net["ch"]
        outdir = filedialog.askdirectory(title="Save capture to…")
        if not outdir:
            return
        prefix = os.path.join(outdir, f"cap_{bssid.replace(':','-')}")
        cmd    = ["airodump-ng", "-c", ch, "--bssid", bssid, "-w", prefix, iface]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        self.cap_path.set(prefix + "-01.cap")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    def _deauth_and_capture(self):
        if not self._need_target():
            return
        self._capture_handshake()
        time.sleep(0.8)
        self._deauth()

    def _crack(self):
        cap, wl = self.cap_path.get().strip(), self.wl_path.get().strip()
        if not cap or not wl:
            messagebox.showerror("Missing", "Set both a capture file and wordlist.")
            return
        cmd = ["aircrack-ng", cap, "-w", wl]
        if self.selected_net:
            cmd += ["-b", self.selected_net["bssid"]]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    def _wps_scan(self):
        iface = self._get_iface()
        if not iface:
            return
        cmd = ["wash", "-i", iface]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    def _wps_attack(self):
        if not self._need_target():
            return
        iface = self._get_iface()
        if not iface:
            return
        cmd = ["reaver", "-i", iface, "-b", self.selected_net["bssid"], "-vv"]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    # ── PMKID ─────────────────────────────────────────────────────────────────

    def _pmkid_start(self):
        iface = self._get_iface()
        if not iface:
            return
        out = self.pmkid_out.get().strip() or "/tmp/pmkid_capture.pcapng"
        self.pmkid_out.set(out)
        cmd = ["hcxdumptool", "-i", iface, "-o", out, "--enable_status=1"]
        if self.selected_net:
            cmd += [f"--filterlist_ap={self.selected_net['bssid']}", "--filtermode=2"]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        try:
            kw = {"preexec_fn": os.setsid} if hasattr(os, "setsid") else {}
            self._pmkid_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
            threading.Thread(target=self._run_async_proc,
                             args=(self._pmkid_proc,), daemon=True).start()
        except FileNotFoundError:
            self.log("hcxdumptool not found. Install: apt install hcxdumptool", "err")

    def _pmkid_stop(self):
        if self._pmkid_proc:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self._pmkid_proc.pid), signal.SIGTERM)
                else:
                    self._pmkid_proc.terminate()
            except Exception:
                pass
            self._pmkid_proc = None
            self.log("PMKID capture stopped.", "warn")

    def _pmkid_convert(self):
        src  = self.pmkid_out.get().strip()
        dest = self.pmkid_hash.get().strip()
        if not src:
            messagebox.showerror("Missing", "Set the .pcapng output path first.")
            return
        if not dest:
            dest = src.replace(".pcapng", ".hc22000")
            self.pmkid_hash.set(dest)
        cmd = ["hcxpcapngtool", src, "-o", dest]
        self.log(f"$ {' '.join(cmd)}", "cmd")
        threading.Thread(target=self._run_async, args=(cmd,), daemon=True).start()

    # ── Handshake Validator ───────────────────────────────────────────────────

    def _validate_handshake(self):
        cap = self._vcap_var.get().strip()
        if not cap:
            messagebox.showerror("Missing", "Select a .cap file first.")
            return
        self.valid_result.set("⏳  Validating…")
        self._valid_lbl.configure(text_color=("#b45309", "#f59e0b"))

        def _check():
            out, err = run_cmd(["aircrack-ng", cap], timeout=30)
            combined = (out + err).lower()
            if re.search(r"\d+\s+handshake", combined):
                count = re.search(r"(\d+)\s+handshake", combined)
                n = count.group(1) if count else "?"
                self.after(0, self._set_valid_result,
                           f"✔  Valid — {n} handshake(s) found", "ok")
                self.after(0, self.log, f"Validator: {n} handshake(s) found in {cap}", "ok")
            else:
                self.after(0, self._set_valid_result,
                           "✘  No valid handshake found", "err")
                self.after(0, self.log, f"Validator: no handshake in {cap}", "warn")

        threading.Thread(target=_check, daemon=True).start()

    def _set_valid_result(self, msg, tag):
        self.valid_result.set(msg)
        colors = {"ok": ("#15803d","#22c55e"), "err": ("#dc2626","#ef4444"),
                  "warn": ("#b45309","#f59e0b")}
        self._valid_lbl.configure(text_color=colors.get(tag, ("gray50","gray50")))

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_html(self):
        if not self.networks:
            messagebox.showwarning("No Data", "Run a scan first.")
            return
        path = filedialog.asksaveasfilename(title="Save HTML Report",
                                             defaultextension=".html",
                                             filetypes=[("HTML","*.html"),("All","*.*")])
        if not path:
            return
        Path(path).write_text(self._generate_html(), encoding="utf-8")
        self.log(f"HTML report saved: {path}", "ok")
        webbrowser.open(f"file://{os.path.abspath(path)}")

    def _export_csv(self):
        if not self.networks:
            messagebox.showwarning("No Data", "Run a scan first.")
            return
        path = filedialog.asksaveasfilename(title="Save CSV",
                                             defaultextension=".csv",
                                             filetypes=[("CSV","*.csv"),("All","*.*")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["SSID","BSSID","Channel","Signal","Privacy","Cipher",
                        "Auth","Band","Clients","Vendor"])
            for n in self.networks.values():
                w.writerow([n["ssid"], n["bssid"], n["ch"], n["pwr"],
                            n["enc"], n["cipher"], n["auth"],
                            n["band"], n["clients"], oui_lookup(n["bssid"])])
        self.log(f"CSV saved: {path}", "ok")

    def _generate_html(self) -> str:
        ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n5g    = sum(1 for n in self.networks.values() if n["band"] == "5 GHz")
        n_open = sum(1 for n in self.networks.values() if n["enc_tag"] == "open")
        ec     = {"wpa3":"#22c55e","wpa2":"#38bdf8","wpa":"#f59e0b","wep":"#ef4444","open":"#94a3b8"}

        ap_rows = "".join(
            f"<tr><td>{n['ssid']}</td><td class='mono'>{n['bssid']}</td>"
            f"<td class='c'>{n['ch']}</td><td class='c'>{n['pwr']} dBm</td>"
            f"<td class='c' style='color:{ec.get(n[\"enc_tag\"],\"#94a3b8\")}'>{n['enc']}</td>"
            f"<td class='c'>{n['band']}</td><td class='c'>{n['clients']}</td>"
            f"<td>{oui_lookup(n['bssid'])}</td></tr>"
            for n in sorted(self.networks.values(), key=lambda x: int(x["pwr"] or 0))
        )
        cli_rows = "".join(
            f"<tr><td class='mono'>{c['mac']}</td><td class='mono'>{c['bssid']}</td>"
            f"<td>{c['ssid']}</td><td class='c'>{c['pwr']} dBm</td>"
            f"<td class='c'>{c['packets']}</td><td>{oui_lookup(c['mac'])}</td>"
            f"<td>{c['probes']}</td></tr>"
            for c in self.clients.values()
        )
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>AirGUI Report — {ts}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0b0b16;color:#e2e8f0;padding:40px}}
h1{{font-size:24px;color:#9d8ae8;margin-bottom:4px}}
.sub{{color:#5a5a80;font-size:12px;margin-bottom:28px}}
.stats{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:32px}}
.stat{{background:#1c1c38;border:1px solid #2d2d58;border-radius:12px;padding:16px 24px}}
.stat .n{{font-size:30px;font-weight:700;color:#9d8ae8}}
.stat .l{{font-size:11px;color:#8895aa;margin-top:2px}}
h2{{font-size:14px;color:#8895aa;text-transform:uppercase;letter-spacing:.08em;
    border-bottom:1px solid #2d2d58;padding-bottom:8px;margin:28px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:28px}}
th{{background:#1c1c38;color:#8895aa;text-align:left;padding:9px 12px;
    font-size:10px;text-transform:uppercase;letter-spacing:.05em}}
td{{padding:8px 12px;border-bottom:1px solid #13132a}}
tr:hover td{{background:#1a1a30}}
.mono{{font-family:'Consolas',monospace;font-size:11px}}
.c{{text-align:center}}
footer{{color:#2d2d58;font-size:11px;margin-top:32px;text-align:center}}
</style></head><body>
<h1>✦ AirGUI Scan Report</h1>
<div class="sub">Generated: {ts}</div>
<div class="stats">
  <div class="stat"><div class="n">{len(self.networks)}</div><div class="l">Networks</div></div>
  <div class="stat"><div class="n">{len(self.clients)}</div><div class="l">Clients</div></div>
  <div class="stat"><div class="n">{n5g}</div><div class="l">5 GHz APs</div></div>
  <div class="stat"><div class="n">{n_open}</div><div class="l">Open Networks</div></div>
</div>
<h2>Access Points ({len(self.networks)})</h2>
<table><tr><th>SSID</th><th>BSSID</th><th>CH</th><th>Signal</th>
<th>Encryption</th><th>Band</th><th>Clients</th><th>Vendor</th></tr>
{ap_rows}</table>
<h2>Clients ({len(self.clients)})</h2>
<table><tr><th>MAC</th><th>AP BSSID</th><th>SSID</th><th>Signal</th>
<th>Packets</th><th>Vendor</th><th>Probed SSIDs</th></tr>
{cli_rows}</table>
<footer>AirGUI · For authorized security testing only</footer>
</body></html>"""

    # ── Async Runner ──────────────────────────────────────────────────────────

    def _run_async(self, cmd):
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._run_async_proc(proc)
        except FileNotFoundError:
            self.after(0, self.log, f"{cmd[0]}: command not found", "err")
        except Exception as e:
            self.after(0, self.log, str(e), "err")

    def _run_async_proc(self, proc):
        for line in proc.stdout:
            self.after(0, self.log, line.rstrip())
        proc.wait()
        tag = "ok" if proc.returncode == 0 else "err"
        self.after(0, self.log, f"[exited: {proc.returncode}]", tag)

    # ── File Dialogs ──────────────────────────────────────────────────────────

    def _browse_cap(self):
        p = filedialog.askopenfilename(filetypes=[("Capture","*.cap *.pcap"),("All","*.*")])
        if p: self.cap_path.set(p)

    def _browse_wordlist(self):
        p = filedialog.askopenfilename(filetypes=[("Text","*.txt"),("All","*.*")])
        if p: self.wl_path.set(p)

    def _browse_vcap(self):
        p = filedialog.askopenfilename(filetypes=[("Capture","*.cap *.pcap"),("All","*.*")])
        if p: self._vcap_var.set(p)

    def _browse_pmkid_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".pcapng",
                                          filetypes=[("pcapng","*.pcapng"),("All","*.*")])
        if p: self.pmkid_out.set(p)

    def _browse_pmkid_hash(self):
        p = filedialog.asksaveasfilename(defaultextension=".hc22000",
                                          filetypes=[("hc22000","*.hc22000"),("All","*.*")])
        if p: self.pmkid_hash.set(p)

    # ── Terminal ──────────────────────────────────────────────────────────────

    def log(self, msg, tag=""):
        self.terminal.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.terminal.insert("end", f"[{ts}]  {msg}\n", tag)
        self.terminal.see("end")
        self.terminal.configure(state="disabled")

    def _clear_terminal(self):
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self._stop_scan()
        self._pmkid_stop()
        if self.mon_iface:
            if messagebox.askyesno("Exit", "Stop monitor mode before closing?"):
                self._stop_monitor()
        self.destroy()


if __name__ == "__main__":
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("[!] Not running as root — some features will fail.")
        print("[!] Use:  sudo python3 airgui.py")
    app = AirGUI()
    app.mainloop()
