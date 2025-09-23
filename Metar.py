import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import tkinter as tk
import re
import json
import os


def load_config(filename: str) -> Dict[str, Any]:
    default_config = {
        "ICAO_GROUPS": [
            ["EPWA", "EPMO", "EPLL", "EPRA"],
            ["EPKK", "EPKT"],
            ["EPPO", "EPWR"],
            ["EPGD", "EPBY"],
            ["EPSC", "EPSY", "EPLB", "EPRZ"],
        ],
        "CAT_COLORS": {
            "VFR": "#0b4136", "SVFR": "#ffd600", "IFR": "#ff1744", "None": "#9e9e9e"
        },
        "FONT_FAMILY": "Consolas",
        "FONT_SIZE": 8
    }
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {**default_config, **config}
    except Exception:
        pass
    return default_config


config = load_config("config.json")

ICAO_GROUPS: List[List[str]] = config["ICAO_GROUPS"]
ALL_ICAOS = [icao for group in ICAO_GROUPS for icao in group]
CAT_COLORS = config["CAT_COLORS"]
FONT_FAMILY = config["FONT_FAMILY"]
FONT_SIZE = config["FONT_SIZE"]

METAR_BASE = "https://metar.vatsim.net"
ATIS_URL = "https://data.vatsim.net/v3/afv-atis-data.json"

WIND_REGEX = re.compile(r'^(?:VRB|[0-3]\d{2})\d{2,3}(?:G\d{2,3})?KT$')
QNH_Q_REGEX = re.compile(r'^Q\d{4}$')
Q_OR_A_REGEX = re.compile(r'^(?:Q|A)\d{4}$')
STAMP_REGEX = re.compile(r'^\d{6}Z$')

VIS_SM_REGEX = re.compile(r'^(P)?(\d+)(?:SM)$')
VIS_FRACT_SM_REGEX = re.compile(r'^(\d+)?\s?(\d)/(\d)SM$')

PLACEHOLDER = "(no data)"


def fetch_metars(icaos: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not icaos:
        return out
    try:
        url = f"{METAR_BASE}/" + ",".join(icaos) + "?format=text"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        for line in r.text.splitlines():
            s = line.strip()
            if not s:
                continue
            icao = s.split()[0]
            if icao in icaos:
                out[icao] = s
    except Exception:
        pass
    return out


def fetch_atis_codes(icaos: List[str]) -> Dict[str, str]:
    codes: Dict[str, str] = {}
    try:
        r = requests.get(ATIS_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        by_icao: Dict[str, List[Dict[str, Any]]] = {icao: [] for icao in icaos}
        for item in data:
            try:
                callsign = str(item.get("callsign", "")).upper()
                for icao in icaos:
                    if callsign.startswith(f"{icao}_"):
                        by_icao[icao].append(item)
            except Exception:
                continue

        def ts(item: Dict[str, Any]) -> float:
            ts_str = item.get("last_updated") or item.get("logon_time") or ""
            try:
                return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0

        for icao, items in by_icao.items():
            if not items:
                continue
            latest = max(items, key=ts)
            code = latest.get("atis_code")
            if isinstance(code, str) and len(code) == 1:
                codes[icao] = code
    except Exception:
        pass
    return codes


def parse_wind_qnh(metar_line: str, icao: str) -> Optional[Tuple[str, str]]:
    if not metar_line:
        return None
    parts = metar_line.split()
    if not parts or parts[0] != icao:
        return None
    space = parts[1:]
    wind = next((p for p in space if WIND_REGEX.match(p)), None)
    qnh = next((p for p in space if QNH_Q_REGEX.match(p)), None)
    return (wind, qnh) if wind and qnh else None


def parse_visibility_and_ceiling(metar_line: str, icao: str) -> Tuple[Optional[int], Optional[int]]:
    if not metar_line or not metar_line.startswith(icao):
        return (None, None)
    parts = metar_line.split()
    vis_m: Optional[int] = None
    ceiling_ft: Optional[int] = None

    if "CAVOK" in parts:
        return (10000, 5000)

    for p in parts:
        if p.isdigit() and len(p) in (4, 5):
            vis_m = int(p)
            break
        if p.endswith("SM"):
            m = VIS_SM_REGEX.match(p)
            if m:
                plus, whole = m.groups()
                miles = int(whole)
                if plus:
                    miles = max(miles, 6)
                vis_m = int(round(miles * 1609.34))
                break
        m2 = VIS_FRACT_SM_REGEX.match(p)
        if m2:
            whole, num, den = m2.groups()
            miles = (int(whole) if whole else 0) + (int(num) / int(den))
            vis_m = int(round(miles * 1609.34))
            break

    for p in parts:
        if p.startswith(("BKN", "OVC", "VV")) and len(p) >= 5 and p[3:6].isdigit():
            hft = int(p[3:6]) * 100
            ceiling_ft = hft if ceiling_ft is None else min(ceiling_ft, hft)

    if ceiling_ft is None:
        if not any(p.startswith(("BKN", "OVC", "VV")) for p in parts):
            ceiling_ft = 5000

    return (vis_m, ceiling_ft)


def classify_flight_category(vis_m: Optional[int], ceiling_ft: Optional[int]) -> Optional[str]:
    if vis_m is None or ceiling_ft is None:
        return None
    if vis_m >= 5000 and ceiling_ft >= 1500:
        return "VFR"
    if vis_m >= 1500 and ceiling_ft >= 600:
        return "SVFR"
    return "IFR"


def build_detail_text(metar_line: str, icao: str) -> str:
    if not metar_line or not metar_line.startswith(icao):
        return ""
    parts = metar_line.split()
    start = 1
    for i in range(1, len(parts)):
        if STAMP_REGEX.match(parts[i]):
            start = i + 1
            break
    body = parts[start:]
    filtered = [p for p in body if not WIND_REGEX.match(p) and not Q_OR_A_REGEX.match(p)]
    return " ".join(filtered).strip()


def seconds_to_next_slot(now_utc: datetime) -> int:
    m = now_utc.minute
    if m < 30:
        next_slot = now_utc.replace(minute=30, second=0, microsecond=0)
    else:
        next_slot = (now_utc + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(1, int((next_slot - now_utc).total_seconds()))


class MinimalMetarApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.resizable(False, False)

        self.metar_full: Dict[str, str] = {}
        self.summary: Dict[str, str] = {}
        self.detail_text: Dict[str, str] = {}
        self.category: Dict[str, Optional[str]] = {}
        self.atis_codes: Dict[str, str] = {}
        self.expanded: set[str] = set()

        self.row_dots: Dict[str, tk.Canvas] = {}
        self.row_main_labels: Dict[str, tk.Label] = {}
        self.row_detail_labels: Dict[str, tk.Label] = {}
        self.row_containers: Dict[str, tk.Frame] = {}

        self._create_airport_rows()

        self._start_win_x = self._start_win_y = self._drag_x = self._drag_y = 0
        self.bind("<Button-3>", self._start_move)
        self.bind("<B3-Motion>", self._on_move)
        self.unbind("<Button-1>")
        self.unbind("<B1-Motion>")
        self.bind("<Escape>", lambda e: self.destroy())

        self._initial_load()
        self._apply_all()

        self.schedule_next_metar_refresh()
        self.schedule_next_atis_refresh()

    def _create_airport_rows(self):
        for group in ICAO_GROUPS:
            for icao in group:
                container = tk.Frame(self, bg="black")
                container.pack(fill="x", padx=6)
                self.row_containers[icao] = container

                line = tk.Frame(container, bg="black", cursor="hand2")
                line.pack(fill="x")

                dot = tk.Canvas(line, width=12, height=12, bg="black", highlightthickness=0)
                dot.pack(side="left", padx=(0, 4))
                self.row_dots[icao] = dot

                main = tk.Label(
                    line, text=f"{icao} —",
                    font=(FONT_FAMILY, FONT_SIZE), fg="white", bg="black",
                    anchor="w", justify="left", padx=2
                )
                main.pack(side="left", fill="x", expand=True)
                self.row_main_labels[icao] = main

                def make_handler(ic=icao):
                    def handler(event, ic=ic):
                        self.toggle_detail(ic)
                        return "break"

                    return handler

                for w in (line, main, dot):
                    w.bind("<Button-1>", make_handler())
                    w.configure(cursor="hand2")

                detail = tk.Label(
                    container, text="",
                    font=(FONT_FAMILY, FONT_SIZE), fg="white", bg="black",
                    anchor="w", justify="left", padx=0
                )
                self.row_detail_labels[icao] = detail

            tk.Frame(self, height=10, bg="black").pack(fill="x")

    def _start_move(self, event):
        self._start_win_x, self._start_win_y = self.winfo_x(), self.winfo_y()
        self._drag_x, self._drag_y = event.x_root, event.y_root

    def _on_move(self, event):
        dx, dy = event.x_root - self._drag_x, event.y_root - self._drag_y
        self.geometry(f"+{self._start_win_x + dx}+{self._start_win_y + dy}")

    def _initial_load(self):
        metars = fetch_metars(ALL_ICAOS)
        atis = fetch_atis_codes(ALL_ICAOS)

        self.atis_codes = atis

        for icao in ALL_ICAOS:
            full = metars.get(icao, "")
            self.metar_full[icao] = full or ""

            cat = None
            if full:
                vis_m, ceiling_ft = parse_visibility_and_ceiling(full, icao)
                cat = classify_flight_category(vis_m, ceiling_ft)
            self.category[icao] = cat

            parts = parse_wind_qnh(full, icao) if full else None

            self._update_summary_and_details(icao, full, parts)

        if not metars:
            self.show_error()

    def _apply_all(self):
        for icao in ALL_ICAOS:
            self.row_main_labels[icao].config(text=self.summary.get(icao, f"{icao} —"))
            self._draw_dot(icao, self.category.get(icao))
            if icao in self.expanded:
                self.row_detail_labels[icao].config(text=self.detail_text[icao])
                self.row_detail_labels[icao].pack(fill="x")
            else:
                self.row_detail_labels[icao].pack_forget()
                self.row_detail_labels[icao].config(text="")

    def show_error(self):
        for icao in ALL_ICAOS:
            self.summary[icao] = f"{icao} (DATA ERROR)"
            self.detail_text[icao] = "(no data or connection error)"
        self._apply_all()

    def toggle_detail(self, icao: str):
        if icao in self.expanded:
            self.expanded.remove(icao)
        else:
            self.expanded.add(icao)
        self._apply_all()

    def _draw_dot(self, icao: str, category: Optional[str]):
        c = self.row_dots[icao]
        c.delete("all")
        color = CAT_COLORS.get(category, CAT_COLORS["None"])
        c.create_oval(1, 1, 11, 11, fill=color, outline=color)

    def _update_summary_and_details(self, icao, full_metar, parsed_metar):
        if parsed_metar:
            wind, qnh = parsed_metar
            atis_code = self.atis_codes.get(icao)
            self.summary[icao] = f"{icao} {wind} {qnh}" + (f" {atis_code}" if atis_code else "")
        else:
            self.summary[icao] = f"{icao} —"

        det = build_detail_text(full_metar, icao)
        self.detail_text[icao] = det if det else PLACEHOLDER

    def schedule_next_metar_refresh(self):
        delay = seconds_to_next_slot(datetime.utcnow())
        self.after(delay * 1000, self.refresh_metars_now)

    def refresh_metars_now(self):
        threading.Thread(target=self._refresh_metars_in_background, daemon=True).start()

    def _refresh_metars_in_background(self):
        metars = fetch_metars(ALL_ICAOS)

        if not metars:
            self.after(0, self.show_error)
            self.schedule_next_metar_refresh()
            return

        changed = False
        for icao in ALL_ICAOS:
            full_new = metars.get(icao)
            if full_new and self.metar_full.get(icao) != full_new:
                changed = True
                self.metar_full[icao] = full_new

                vis_m, ceiling_ft = parse_visibility_and_ceiling(full_new, icao)
                self.category[icao] = classify_flight_category(vis_m, ceiling_ft)

                parts = parse_wind_qnh(full_new, icao)
                self._update_summary_and_details(icao, full_new, parts)

        if changed:
            self.after(0, self._apply_all)
        self.schedule_next_metar_refresh()

    def schedule_next_atis_refresh(self):
        delay_seconds = 5 * 60
        self.after(delay_seconds * 1000, self.refresh_atis_now)

    def refresh_atis_now(self):
        threading.Thread(target=self._refresh_atis_in_background, daemon=True).start()

    def _refresh_atis_in_background(self):
        atis_data = fetch_atis_codes(ALL_ICAOS)

        if not atis_data:
            self.schedule_next_atis_refresh()
            return

        changed = False
        for icao in ALL_ICAOS:
            new_atis = atis_data.get(icao)
            if self.atis_codes.get(icao) != new_atis:
                changed = True
                self.atis_codes[icao] = new_atis

                full_metar = self.metar_full.get(icao)
                if full_metar:
                    parts = parse_wind_qnh(full_metar, icao)
                    self._update_summary_and_details(icao, full_metar, parts)

        if changed:
            self.after(0, self._apply_all)
        self.schedule_next_atis_refresh()


if __name__ == "__main__":
    MinimalMetarApp().mainloop()