"""
IDE.py - BoxedLANG Visual Editor

A simple Tk-based editor for .bx files. Supports:
  - Syntax highlighting (keywords/operators/$vars/comments/pipes) using
    current BoxedLANG feature set (clear, return, import, ret-, etc.)
  - Light/dark theme toggle
  - Run (via bx.py), Debug (via bxdebug.py), Transpile (via transpilebx.py)
  - Open / Save / New
  - Live line numbers
  - Status bar

All tools are loaded from the same folder as this file, so keep
bx.py, bxastgen.py, bxrunner.py, transpilebx.py, bxdebug.py alongside it.
"""
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, ttk
import re
import sys
import os
import subprocess

# ---------------------------------------------------------------------------
# Path helpers - everything runs from the folder this file lives in
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
BX_PY          = os.path.join(HERE, "bx.py")
BXDEBUG_PY     = os.path.join(HERE, "bxdebug.py")
TRANSPILEBX_PY = os.path.join(HERE, "transpilebx.py")
PYTHON         = sys.executable

# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
LIGHT = {
    "bg":      "#f5f5f5",
    "editor":  "#ffffff",
    "fg":      "#1a1a1a",
    "gutter":  "#e0e0e0",
    "gutfg":   "#888888",
    "status":  "#e0e0e0",
    "btn":     "#e6e6e6",
    "btnfg":   "#111111",
    "sel":     "#b3d4fc",
    # syntax colours
    "kw":      "#1a7c32",   # keyword - green
    "op":      "#885361",   # operator - dusty rose
    "var":     "#00838a",   # $variable - teal
    "comment": "#8264a4",   # // comment - purple italic
    "pipe":    "#885361",   # | separator - same as operator
    "string":  "#7a97b2",   # plain text / strings - slate blue
    "ns_call": "#84b29c",   # namespace.func / import path - sage
}
DARK = {
    "bg":      "#1e1e1e",
    "editor":  "#252526",
    "fg":      "#eaeaea",
    "gutter":  "#2a2a2a",
    "gutfg":   "#555555",
    "status":  "#2a2a2a",
    "btn":     "#3a3a3a",
    "btnfg":   "#eaeaea",
    "sel":     "#264f78",
    "kw":      "#68d087",
    "op":      "#c06080",
    "var":     "#bcece1",
    "comment": "#9555b3",
    "pipe":    "#885361",
    "string":  "#9db0c8",
    "ns_call": "#84b29c",
}

# ---------------------------------------------------------------------------
# Syntax patterns (applied in order - later patterns win on overlap)
# ---------------------------------------------------------------------------
KEYWORDS = (
    "box|b", "say|s", "ask|a", "math|m", "test|t", "if|i",
    "jump|j", "jumpif|ji", "del|d", "wait|wt", "weigh|wh",
    "premark|mark|mk", "end|e", "clear|cls", "return|ret",
    "import|imp",
)

KW_PATTERN = re.compile(
    r"(?im)^[ \t]*("
    + "|".join(
        "|".join(re.escape(a) for a in kw.split("|"))
        for kw in KEYWORDS
    )
    + r")\b"
)

OP_PATTERN    = re.compile(r"==|!=|>=|<=|>|<|\+|-|\*|/|%(?=[^/])")
VAR_PATTERN   = re.compile(r"\$[A-Za-z_#?][A-Za-z0-9_#?-]*")
PIPE_PATTERN  = re.compile(r"\|")
COMMENT_PATTERN = re.compile(r"//.*$", re.MULTILINE)
# namespace.func calls and ret- prefixed box names
NS_PATTERN    = re.compile(r"\b[A-Za-z_][A-Za-z0-9_-]*\.[A-Za-z_][A-Za-z0-9_-]*\b")
RET_PATTERN   = re.compile(r"\bret-[A-Za-z0-9_]+")


class BxEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("BoxedLANG IDE")
        self.root.geometry("900x650")
        self.current_file = None
        self.theme = DARK
        self._after_id = None

        self._build_menu()
        self._build_toolbar()
        self._build_editor()
        self._build_status()
        self._apply_theme()
        self.highlight()

    # ------------------------------------------------------------------ UI --
    def _build_menu(self):
        mb = tk.Menu(self.root)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="New",   command=self.new_file,  accelerator="Ctrl+N")
        fm.add_command(label="Open",  command=self.open_file, accelerator="Ctrl+O")
        fm.add_command(label="Save",  command=self.save_file, accelerator="Ctrl+S")
        fm.add_command(label="Save As", command=self.save_as)
        fm.add_separator()
        fm.add_command(label="Quit",  command=self.root.quit)
        mb.add_cascade(label="File", menu=fm)

        vm = tk.Menu(mb, tearoff=0)
        vm.add_command(label="Toggle Light/Dark", command=self.toggle_theme, accelerator="Ctrl+T")
        mb.add_cascade(label="View", menu=vm)

        self.root.config(menu=mb)
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-t>", lambda e: self.toggle_theme())

    def _build_toolbar(self):
        self.toolbar = tk.Frame(self.root)
        self.toolbar.pack(side="top", fill="x", padx=4, pady=2)
        btns = [
            ("New",        self.new_file),
            ("Open",       self.open_file),
            ("Save",       self.save_file),
            ("|",          None),
            ("▶ Run",      self.run_code),
            ("🔬 Debug",   self.debug_code),
            ("⇄ Transpile", self.transpile_code),
            ("|",          None),
            ("🌙 Theme",   self.toggle_theme),
        ]
        self._toolbar_btns = []
        for label, cmd in btns:
            if label == "|":
                sep = tk.Label(self.toolbar, text=" | ")
                sep.pack(side="left")
                self._toolbar_btns.append(("sep", sep))
            else:
                b = tk.Button(self.toolbar, text=label, command=cmd,
                               relief="flat", padx=6, pady=2)
                b.pack(side="left", padx=1)
                self._toolbar_btns.append(("btn", b))

    def _build_editor(self):
        pane = tk.Frame(self.root)
        pane.pack(fill="both", expand=True)

        self.gutter = tk.Text(pane, width=4, state="disabled",
                               takefocus=0, cursor="arrow",
                               wrap="none", padx=4)
        self.gutter.pack(side="left", fill="y")

        self.editor = scrolledtext.ScrolledText(
            pane, wrap="none", undo=True,
            font=("Monospace", 11),
            selectbackground=self.theme["sel"],
            insertwidth=2,
        )
        self.editor.pack(side="left", fill="both", expand=True)

        self.editor.bind("<KeyRelease>", self._on_key)
        self.editor.bind("<Button-1>", self._update_status)
        self.editor.bind("<MouseWheel>", self._sync_gutter)

        # sync gutter scrolling
        self.editor.config(yscrollcommand=self._on_scroll)

        # tag configuration happens in _apply_theme
        self.editor.tag_config("comment", elide=False)

    def _build_status(self):
        self.status_var = tk.StringVar(value="Ready")
        self.status = tk.Label(self.root, textvariable=self.status_var,
                                anchor="w", padx=6)
        self.status.pack(side="bottom", fill="x")

    # ---------------------------------------------------------- Theming -----
    def toggle_theme(self):
        self.theme = LIGHT if self.theme is DARK else DARK
        self._apply_theme()
        self.highlight()

    def _apply_theme(self):
        t = self.theme
        self.root.config(bg=t["bg"])
        self.toolbar.config(bg=t["bg"])
        self.status.config(bg=t["status"], fg=t["fg"])
        self.gutter.config(bg=t["gutter"], fg=t["gutfg"],
                            disabledforeground=t["gutfg"])

        self.editor.config(bg=t["editor"], fg=t["fg"],
                            insertbackground=t["fg"],
                            selectbackground=t["sel"])

        for kind, w in self._toolbar_btns:
            if kind == "btn":
                w.config(bg=t["btn"], fg=t["btnfg"],
                          activebackground=t["sel"])
            else:
                w.config(bg=t["bg"], fg=t["fg"])

        # Syntax tag colours
        tag_defs = {
            "kw":      {"foreground": t["kw"],      "font": ("Monospace", 11, "bold")},
            "op":      {"foreground": t["op"]},
            "var":     {"foreground": t["var"]},
            "pipe":    {"foreground": t["pipe"]},
            "comment": {"foreground": t["comment"],  "font": ("Monospace", 11, "italic")},
            "ns":      {"foreground": t["ns_call"]},
            "ret":     {"foreground": t["ns_call"]},
        }
        for tag, opts in tag_defs.items():
            self.editor.tag_config(tag, **opts)

    # --------------------------------------------------------- Highlighting --
    def _on_key(self, event=None):
        self._update_status()
        self._update_gutter()
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(80, self.highlight)

    def _on_scroll(self, *args):
        self.editor.vbar.set(*args)
        self._sync_gutter()

    def _sync_gutter(self, event=None):
        self._update_gutter()

    def _update_gutter(self):
        self.gutter.config(state="normal")
        self.gutter.delete("1.0", "end")
        content = self.editor.get("1.0", "end-1c")
        n_lines = content.count("\n") + 1
        nums = "\n".join(str(i) for i in range(1, n_lines + 1))
        self.gutter.insert("1.0", nums)
        self.gutter.config(state="disabled")
        # sync scroll position
        try:
            self.gutter.yview_moveto(self.editor.yview()[0])
        except Exception:
            pass

    def highlight(self):
        content = self.editor.get("1.0", "end-1c")
        for tag in ("kw", "op", "var", "pipe", "comment", "ns", "ret"):
            self.editor.tag_remove(tag, "1.0", "end")

        def apply(pattern, tag):
            for m in pattern.finditer(content):
                start = f"1.0 + {m.start()} chars"
                end   = f"1.0 + {m.end()} chars"
                self.editor.tag_add(tag, start, end)

        apply(NS_PATTERN,   "ns")
        apply(RET_PATTERN,  "ret")
        apply(VAR_PATTERN,  "var")
        apply(PIPE_PATTERN, "pipe")
        apply(OP_PATTERN,   "op")
        apply(KW_PATTERN,   "kw")
        apply(COMMENT_PATTERN, "comment")

        # raise comment on top so it wins over keyword matches
        self.editor.tag_raise("comment")

    def _update_status(self, event=None):
        try:
            pos = self.editor.index("insert")
            line, col = pos.split(".")
            name = os.path.basename(self.current_file) if self.current_file else "untitled"
            self.status_var.set(f"  {name}  |  Ln {line}, Col {int(col)+1}")
        except Exception:
            pass

    # --------------------------------------------------------- File ops -----
    def new_file(self):
        if self._confirm_unsaved():
            self.editor.delete("1.0", "end")
            self.current_file = None
            self.root.title("BoxedLANG IDE - untitled")
            self.status_var.set("New file")

    def open_file(self):
        if not self._confirm_unsaved():
            return
        path = filedialog.askopenfilename(
            filetypes=[("BoxedLANG files", "*.bx"), ("All files", "*.*")])
        if path:
            self.editor.delete("1.0", "end")
            self.editor.insert("end", open(path, encoding="utf-8").read())
            self.current_file = path
            self.root.title(f"BoxedLANG IDE - {os.path.basename(path)}")
            self.highlight()
            self._update_gutter()
            self.status_var.set(f"Opened {path}")

    def save_file(self):
        if self.current_file:
            open(self.current_file, "w", encoding="utf-8").write(
                self.editor.get("1.0", "end-1c"))
            self.status_var.set(f"Saved {self.current_file}")
        else:
            self.save_as()

    def save_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".bx",
            filetypes=[("BoxedLANG files", "*.bx"), ("All files", "*.*")])
        if path:
            self.current_file = path
            self.save_file()
            self.root.title(f"BoxedLANG IDE - {os.path.basename(path)}")

    def _confirm_unsaved(self):
        return True  # could add dirty-tracking later

    # --------------------------------------------------------- Tools --------
    def _save_temp(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".bx", delete=False,
                                           mode="w", encoding="utf-8")
        tmp.write(self.editor.get("1.0", "end-1c"))
        tmp.close()
        return tmp.name

    def run_code(self):
        path = self.current_file or self._save_temp()
        if not self.current_file:
            self.save_file() if self.current_file else None
        # run in a new terminal window if possible, else a Tk output window
        try:
            subprocess.Popen(
                ["x-terminal-emulator", "-e",
                 f"{PYTHON} {BX_PY} {path}"])
        except FileNotFoundError:
            try:
                subprocess.Popen(
                    ["xterm", "-e", f"{PYTHON} {BX_PY} {path}"])
            except FileNotFoundError:
                self._run_in_window(path)

    def debug_code(self):
        path = self.current_file or self._save_temp()
        try:
            subprocess.Popen([PYTHON, BXDEBUG_PY, path])
        except Exception as e:
            messagebox.showerror("Debug Error", str(e))

    def transpile_code(self):
        if not self.current_file:
            messagebox.showinfo("Transpile",
                "Save your file first before transpiling.")
            return
        win = tk.Toplevel(self.root)
        win.title("Transpile")
        win.geometry("350x160")
        win.config(bg=self.theme["bg"])

        tk.Label(win, text="Target language(s):",
                  bg=self.theme["bg"], fg=self.theme["fg"]).pack(pady=(12, 2))
        lang_var = tk.StringVar(value="python")
        tk.Entry(win, textvariable=lang_var,
                  bg=self.theme["btn"], fg=self.theme["fg"]).pack(fill="x", padx=20)

        tk.Label(win, text="Output dir (blank = same folder):",
                  bg=self.theme["bg"], fg=self.theme["fg"]).pack(pady=(8, 2))
        out_var = tk.StringVar()
        tk.Entry(win, textvariable=out_var,
                  bg=self.theme["btn"], fg=self.theme["fg"]).pack(fill="x", padx=20)

        def do_transpile():
            langs = lang_var.get().split()
            cmd = [PYTHON, TRANSPILEBX_PY, self.current_file,
                   "-l"] + langs + ["-a"]
            if out_var.get().strip():
                cmd += ["-d", out_var.get().strip()]
            else:
                cmd += ["-d", os.path.dirname(self.current_file) or "."]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
                msg = (r.stdout + r.stderr).strip()
                messagebox.showinfo("Transpile result", msg or "Done.")
            except Exception as e:
                messagebox.showerror("Transpile Error", str(e))
            win.destroy()

        tk.Button(win, text="Transpile", command=do_transpile,
                   bg=self.theme["btn"], fg=self.theme["fg"]).pack(pady=10)

    def _run_in_window(self, path):
        win = tk.Toplevel(self.root)
        win.title("Run output")
        win.geometry("600x400")
        out = scrolledtext.ScrolledText(win, bg="#111", fg="#eee",
                                         font=("Monospace", 10))
        out.pack(fill="both", expand=True)
        try:
            r = subprocess.run([PYTHON, BX_PY, path, "-s"],
                                capture_output=True, text=True, timeout=10)
            out.insert("end", r.stdout + r.stderr)
        except subprocess.TimeoutExpired:
            out.insert("end", "[timed out after 10 s - scripts that need "
                               "user input must run in a real terminal]")
        except Exception as e:
            out.insert("end", str(e))


def main():
    root = tk.Tk()
    app = BxEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
