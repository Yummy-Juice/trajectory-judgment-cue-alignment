"""Run the published scenarios in the Windows G*Power 3.1 application.

Uses standard Windows control messages, without screenshots or GUI-coordinate
automation. The native G*Power protocol and every input/output field are saved.
G*Power is a separate, freely available application, not bundled here.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from ctypes import wintypes

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "outputs" / "power_analysis"


class GPower:
    def __init__(self, executable: Path, attach_pid: int | None = None):
        if os.name != "nt":
            raise RuntimeError("G*Power automation requires Windows.")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        self.user.SendMessageW.restype = ctypes.c_ssize_t
        self.user.PostMessageW.argtypes = self.user.SendMessageW.argtypes
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        self.user.GetDlgCtrlID.argtypes = [wintypes.HWND]
        self.user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                               wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]
        self.user.EnumChildWindows.argtypes = [wintypes.HWND, self.callback_type,
                                              wintypes.LPARAM]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                           ctypes.c_int]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                       ctypes.POINTER(wintypes.DWORD)]
        self.owned_process = None
        if attach_pid is None:
            if not executable.is_file():
                raise FileNotFoundError(executable)
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = 0
            self.owned_process = subprocess.Popen(
                [str(executable)], cwd=executable.parent, startupinfo=info)
            self.pid = self.owned_process.pid
        else:
            self.pid = attach_pid
        deadline = time.monotonic() + 15
        self.main = None
        while time.monotonic() < deadline:
            matches = [h for h in self.windows()
                       if self.process_id(h) == self.pid
                       and self.text(h).startswith("G*Power 3.1")]
            if matches:
                self.main = matches[0]
                break
            time.sleep(.05)
        if not self.main:
            raise RuntimeError(f"G*Power main window unavailable, PID {self.pid}")
        self.version_title = self.text(self.main)
        if "3.1.9.7" not in self.version_title:
            raise RuntimeError(f"Expected 3.1.9.7, found {self.version_title}")
        self.children = self.windows(self.main)
        self.selectors = {
            cid: next(h for h in self.children
                      if self.class_name(h) == "ComboBox" and self.cid(h) == cid)
            for cid in [1000, 1001, 1002]}
        self.parameters = self.user.GetParent(next(
            h for h in self.children if self.class_name(h) == "Edit"
            and self.cid(h) == 1020))
        self.protocol = next(h for h in self.children
                             if self.class_name(h).upper() == "RICHEDIT50W")

    def message(self, h, msg, w=0, l=0):
        return self.user.SendMessageW(h, msg, w, l)

    def windows(self, parent=None):
        result = []
        @self.callback_type
        def collect(h, _):
            result.append(h)
            return True
        if parent:
            self.user.EnumChildWindows(parent, collect, 0)
        else:
            self.user.EnumWindows(collect, 0)
        return result

    def process_id(self, h):
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(h, ctypes.byref(pid))
        return pid.value

    def cid(self, h):
        return self.user.GetDlgCtrlID(h)

    def class_name(self, h):
        buf = ctypes.create_unicode_buffer(256)
        self.user.GetClassNameW(h, buf, len(buf))
        return buf.value

    def text(self, h):
        n = self.message(h, 14)
        buf = ctypes.create_unicode_buffer(n + 1)
        self.message(h, 13, n + 1, ctypes.addressof(buf))
        return buf.value

    def displayed(self, h):
        # The main application is intentionally hidden; inspect child styles.
        while h and h != self.main:
            if not self.user.GetWindowLongW(h, -16) & 0x10000000:
                return False
            h = self.user.GetParent(h)
        return True

    def combo_values(self, h):
        values = []
        for i in range(self.message(h, 0x146)):
            buf = ctypes.create_unicode_buffer(1024)
            self.message(h, 0x148, i, ctypes.addressof(buf))
            values.append(buf.value)
        return values

    def choose(self, h, value, prefix=False):
        values = self.combo_values(h)
        matches = [i for i, v in enumerate(values)
                   if (v.startswith(value) if prefix else v == value)]
        if len(matches) != 1:
            raise ValueError(f"Selection {value!r} not unique among {values!r}")
        self.message(h, 0x14E, matches[0])
        self.message(self.user.GetParent(h), 0x111,
                     (1 << 16) | self.cid(h), h)

    def set_text(self, h, value):
        buf = ctypes.create_unicode_buffer(str(value))
        self.message(h, 12, 0, ctypes.addressof(buf))
        self.message(self.user.GetParent(h), 0x111,
                     (0x200 << 16) | self.cid(h), h)

    def controls(self, outputs=False):
        result = {}
        for h in self.windows(self.parameters):
            cid = self.cid(h)
            start = 1060 if outputs else 1004
            if self.class_name(h) != "Static" or not start <= cid < start + 11:
                continue
            if not self.displayed(h):
                continue
            index = cid - start
            ids = [1050 + index] if outputs else [1020 + index, 1040 + index]
            candidates = [c for c in self.windows(self.parameters)
                          if self.cid(c) in ids and self.displayed(c)
                          and self.class_name(c) in ("Edit", "ComboBox")]
            if len(candidates) != 1:
                raise RuntimeError(f"Cannot resolve value control for {self.text(h)}")
            result[self.text(h)] = candidates[0]
        return result

    def calculate(self, job):
        self.choose(self.selectors[1000], job["family"])
        self.choose(self.selectors[1001], job["test"])
        self.choose(self.selectors[1002], job["mode"], prefix=True)
        for label, value in job["inputs"].items():
            fields = self.controls()
            if label in fields and self.class_name(fields[label]) == "ComboBox":
                self.choose(fields[label], str(value))
        fields = self.controls()
        if set(fields) != set(job["inputs"]):
            raise RuntimeError(f"{job['id']}: input labels differ: "
                               f"GUI={list(fields)}, plan={list(job['inputs'])}")
        for label, h in fields.items():
            if self.class_name(h) == "Edit":
                self.set_text(h, job["inputs"][label])
        entered = {label: self.text(h) for label, h in self.controls().items()}
        old_protocol = self.text(self.protocol)
        buttons = [h for h in self.windows(self.main)
                   if self.class_name(h) == "Button" and self.text(h) == "Calculate"
                   and self.displayed(h)]
        if len(buttons) != 1:
            raise RuntimeError("Cannot identify the active Calculate control")
        self.user.PostMessageW(buttons[0], 0xF5, 0, 0)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            new_protocol = self.text(self.protocol)
            if len(new_protocol) > len(old_protocol):
                output = {label: self.text(h)
                          for label, h in self.controls(outputs=True).items()}
                if any(value in ("", "?") for value in output.values()):
                    raise RuntimeError(f"Incomplete G*Power output: {output}")
                native = new_protocol[len(old_protocol):].replace(
                    "\r\r\n", "\n").replace("\r\n", "\n")
                expected_option = {
                    "signed-rank": "A.R.E. method",
                    "correlation": "exact distribution",
                    "correlation-sensitivity": "exact distribution",
                    "logistic-reference": "Demidenko (2007) with var corr",
                }.get(job["group"])
                if expected_option and expected_option not in native:
                    raise RuntimeError(
                        f"{job['id']}: in G*Power Options select {expected_option!r}, "
                        "then resume. The current result has not been accepted.")
                return {"scenario": job, "software": self.version_title,
                        "entered_inputs": entered, "outputs": output,
                        "native_protocol": native}
            time.sleep(.02)
        raise TimeoutError(f"No completed protocol for {job['id']}; preserve session PID {self.pid}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpower-exe", required=True, type=Path)
    parser.add_argument("--scenarios", type=Path, default=HERE / "scenarios.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--attach-pid", type=int, help="Reuse a dedicated existing G*Power process")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--export-protocol", action="store_true",
                        help="Also export the native protocols as a separate text file")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    jobs = json.loads(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
    ids = [j["id"] for j in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("Scenario identifiers must be unique")
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "gpower_results.jsonl"
    completed = {}
    if checkpoint.exists():
        if not args.resume:
            raise FileExistsError("Results already exist. Use --resume or a new --output directory.")
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            key = record["scenario"]["id"]
            if key in completed:
                raise ValueError(f"Duplicate completed scenario {key}")
            completed[key] = record
        for job in jobs:
            if job["id"] in completed and completed[job["id"]]["scenario"] != job:
                raise ValueError(f"Changed specification for {job['id']}; select a new output directory")
        if set(completed) - set(ids):
            raise ValueError("Checkpoint contains scenarios outside the current plan")
    pending = [j for j in jobs if j["id"] not in completed]
    app = None
    if pending:
        app = GPower(args.gpower_exe.resolve(), args.attach_pid)
        print(f"G*Power PID {app.pid}; {len(pending)} pending scenarios", flush=True)
        with checkpoint.open("a", encoding="utf-8", newline="\n") as stream:
            for i, job in enumerate(pending, 1):
                record = app.calculate(job)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                completed[job["id"]] = record
                if i == 1 or i % 25 == 0 or i == len(pending):
                    print(f"Completed {i}/{len(pending)}: {job['id']}", flush=True)
    if args.export_protocol:
        protocol = "G*Power 3.1.9.7 native calculation protocols\n\n"
        for job in jobs:
            record = completed[job["id"]]
            protocol += f"Scenario ID: {job['id']}\n" + record["native_protocol"] + "\n"
        (args.output / "gpower_protocol.txt").write_text(protocol, encoding="utf-8")
    manifest = {
        "software": "G*Power 3.1.9.7", "execution": "Native Windows application control messages",
        "expected_scenarios": len(jobs), "completed_scenarios": len(completed),
        "scenario_ids_complete_and_unique": set(completed) == set(ids),
        "status": "completed", "calculation_role": "Design sensitivity and sample-size evaluation",
        "gpower_gui_analysis_types": ["A priori", "Sensitivity"],
        "unit": "Defined per scenario; participant count for participant-level tests",
    }
    (args.output / "gpower_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    if app is not None and app.owned_process is not None:
        app.user.PostMessageW(app.main, 0x10, 0, 0)


if __name__ == "__main__":
    main()
