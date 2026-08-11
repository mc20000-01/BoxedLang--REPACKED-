"""
bxdebug.py - BoxedLANG step-through debugger + state explorer (Tkinter).

Two small windows:
  - Debug explorer: tps / current command / current args, plus live
    boxes and marks lists.
  - Step controls: start (auto-tick), pause, tick 1/5/10, set a custom
    tick rate, stop.

say/ask still go through the real terminal exactly like bx.py does -
this tool only adds a window for watching and driving execution, it
doesn't redirect input/output into the GUI itself. Because of that,
the GUI will visibly freeze while an `ask` is waiting on terminal
input - that's expected, not a bug: `input()` blocks the same thread
Tk's event loop runs on.

Usage: python bxdebug.py yourscript.bx
"""
import sys
import os
import argparse
import tkinter as tk

from bxastgen import make_ast, BoxedSyntaxError
from bxrunner import BoxedRunner

LIGHT = {"bg": "#f5f5f5", "fg": "#111111", "panel": "#ffffff", "btn": "#e6e6e6"}
DARK = {"bg": "#1e1e1e", "fg": "#eaeaea", "panel": "#2a2a2a", "btn": "#3a3a3a"}


class DebugApp:
    def __init__(self, ast_tree, marks, filename):
        self.ast = ast_tree
        self.marks = marks
        self.filename = filename
        self.runner = BoxedRunner(silent=False)
        self.runner.marks = marks
        self.runner.ast = ast_tree
        self.running = False
        self.tps = 5
        self.theme = LIGHT

        self.root = tk.Tk()
        self.root.title(f"BoxedLANG Debug - {filename}")
        self._build_explorer(self.root)

        self.ctrl = tk.Toplevel(self.root)
        self.ctrl.title("Step Controls")
        self._build_controls(self.ctrl)
        self.ctrl.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.apply_theme()
        self.refresh()

    # ---- explorer window ----
    def _build_explorer(self, root):
        self.explorer_widgets = [root]
        top = tk.Frame(root)
        top.pack(fill="x", padx=6, pady=6)

        self.tps_var = tk.StringVar(value="0")
        self.cmd_var = tk.StringVar(value="")
        self.args_var = tk.StringVar(value="")
        for label, var in (("tps", self.tps_var), ("cur cmd", self.cmd_var), ("cur args", self.args_var)):
            f = tk.Frame(top)
            f.pack(side="left", expand=True, fill="x", padx=3)
            tk.Label(f, text=label).pack()
            tk.Label(f, textvariable=var, relief="groove", width=16, anchor="w").pack(fill="x")

        panels = tk.Frame(root)
        panels.pack(fill="both", expand=True, padx=6, pady=6)

        self.boxes_list, self.boxes_count = self._make_panel(panels, "boxes")
        self.marks_list, self.marks_count = self._make_panel(panels, "marks")

        self.theme_btn = tk.Button(root, text="Toggle light/dark", command=self.toggle_theme)
        self.theme_btn.pack(pady=4)

        self.explorer_widgets.extend([top, panels])

    def _make_panel(self, parent, title):
        frame = tk.Frame(parent, bd=1, relief="solid")
        frame.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(frame, text=title, font=("", 10, "bold")).pack()
        lb = tk.Listbox(frame)
        lb.pack(fill="both", expand=True)
        count_var = tk.StringVar(value="+ length 0 =")
        tk.Label(frame, textvariable=count_var).pack()
        self.explorer_widgets.append(frame)
        return lb, count_var

    # ---- controls window ----
    def _build_controls(self, root):
        row = tk.Frame(root)
        row.pack(padx=6, pady=6)
        self.btn_start = tk.Button(row, text="\u25B6 Start", command=self.start, width=8)
        self.btn_pause = tk.Button(row, text="\u23F8 Pause", command=self.pause, width=8)
        self.btn_tick1 = tk.Button(row, text="Tick 1", command=lambda: self.tick_n(1), width=8)
        self.btn_tick5 = tk.Button(row, text="Tick 5", command=lambda: self.tick_n(5), width=8)
        self.btn_tick10 = tk.Button(row, text="Tick 10", command=lambda: self.tick_n(10), width=8)
        self.btn_stop = tk.Button(row, text="\u23F9 Stop", command=self.stop, width=8)
        for i, b in enumerate((self.btn_start, self.btn_pause, self.btn_tick1,
                                self.btn_tick5, self.btn_tick10, self.btn_stop)):
            b.grid(row=0, column=i, padx=2)

        row2 = tk.Frame(root)
        row2.pack(padx=6, pady=6)
        tk.Label(row2, text="ticks/sec:").pack(side="left")
        self.tps_entry = tk.Entry(row2, width=6)
        self.tps_entry.insert(0, str(self.tps))
        self.tps_entry.pack(side="left", padx=4)
        self.btn_set_tps = tk.Button(row2, text="Set", command=self.set_tps)
        self.btn_set_tps.pack(side="left")

        self.control_widgets = [root, row, row2, self.tps_entry,
                                 self.btn_start, self.btn_pause, self.btn_tick1,
                                 self.btn_tick5, self.btn_tick10, self.btn_stop, self.btn_set_tps]

    # ---- theme ----
    def toggle_theme(self):
        self.theme = DARK if self.theme is LIGHT else LIGHT
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        for w in [self.root, self.ctrl] + self.explorer_widgets + self.control_widgets:
            try:
                w.configure(bg=t["bg"])
            except tk.TclError:
                pass
        for w in (self.btn_start, self.btn_pause, self.btn_tick1, self.btn_tick5,
                  self.btn_tick10, self.btn_stop, self.btn_set_tps, self.theme_btn):
            try:
                w.configure(bg=t["btn"], fg=t["fg"])
            except tk.TclError:
                pass
        for lb in (self.boxes_list, self.marks_list):
            lb.configure(bg=t["panel"], fg=t["fg"])

    # ---- execution ----
    def set_tps(self):
        try:
            self.tps = max(1, int(self.tps_entry.get()))
        except ValueError:
            pass

    def start(self):
        if not self.running:
            self.running = True
            self._auto_tick()

    def pause(self):
        self.running = False

    def stop(self):
        self.running = False
        self.runner.line_index = len(self.ast)
        self.cmd_var.set("(stopped)")
        self.refresh()

    def _auto_tick(self):
        if not self.running:
            return
        if not self.tick_once():
            self.running = False
            return
        self.root.after(max(1, int(1000 / self.tps)), self._auto_tick)

    def tick_n(self, n):
        for _ in range(n):
            if not self.tick_once():
                break

    def tick_once(self):
        if self.runner.line_index >= len(self.ast):
            self.cmd_var.set("(done)")
            return False
        node = self.ast[self.runner.line_index]
        self.cmd_var.set(str(node.get('type', '?')))
        self.args_var.set(str({k: v for k, v in node.items() if k != 'type'}))
        try:
            result = self.runner.execute_node(node)
        except SystemExit:
            self.cmd_var.set("(exited)")
            self.refresh()
            return False
        except Exception as e:
            self.cmd_var.set(f"ERROR: {e}")
            self.refresh()
            return False
        if result != 'EXIT':
            self.runner.line_index += 1
        self.refresh()
        return self.runner.line_index < len(self.ast)

    def refresh(self):
        self.tps_var.set(str(self.tps))

        self.boxes_list.delete(0, "end")
        for k, v in self.runner.boxes.items():
            self.boxes_list.insert("end", f"{k} = {v}")
        self.boxes_count.set(f"+ length {len(self.runner.boxes)} =")

        self.marks_list.delete(0, "end")
        for k, v in self.marks.items():
            self.marks_list.insert("end", f"{k} = {v}")
        self.marks_count.set(f"+ length {len(self.marks)} =")

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="BoxedLANG step-through debugger (Tk)")
    parser.add_argument("file", help="path to the .bx source file")
    cli_args = parser.parse_args()

    filepath = os.path.expanduser(cli_args.file)
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    code = open(filepath, "r", encoding="utf-8").read()
    try:
        ast_tree, marks = make_ast(code, base_dir=os.path.dirname(os.path.abspath(filepath)))
    except BoxedSyntaxError as e:
        print(f"BoxedLANG syntax error: {e}")
        sys.exit(1)

    app = DebugApp(ast_tree, marks, os.path.basename(filepath))
    app.run()


if __name__ == "__main__":
    main()
