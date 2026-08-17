# BoxedLANG on Windows

Two ways to install, pick one:

## Option A — just run it (no extra tools needed)

1. Make sure **Python 3** is installed from https://python.org/downloads
   - On the first install screen, check **"Add python.exe to PATH"**
   - tkinter is included by default — don't uncheck it in the optional
     features screen.
2. Double-click **`windows\install.bat`**.

That's it. This installs:
- The BoxedLANG CLI (`bx`, `transpilebx`, `bxdebug`) to your PATH
- **The BoxedLANG IDE**, with a Start Menu entry ("BoxedLANG" folder)
  and a Desktop shortcut
- `.bx` files now open in the IDE by double-click
- The VS Code / VSCodium syntax-highlighting extension, if you have
  either installed

No admin rights are needed — everything installs under your user
account (`%LOCALAPPDATA%\BoxedLANG`).

Open a **new** terminal window afterwards so `bx` is picked up on PATH.

To remove everything later, run `windows\uninstall.bat`, or use the
"Uninstall BoxedLANG" shortcut it adds to the Start Menu.

## Option B — build a proper Setup.exe wizard

If you'd rather hand people a single click-through installer (with an
uninstall entry in "Apps & Features"), `windows\BoxedLANG.iss` is an
[Inno Setup](https://jrsoftware.org/isdl.php) script that packages the
same install — CLI + IDE + shortcuts + file association — into a
signed-looking `BoxedLANG-Setup.exe`.

1. Install Inno Setup (free).
2. Open `windows\BoxedLANG.iss` in the Inno Setup Compiler, or run:
   ```
   ISCC.exe windows\BoxedLANG.iss
   ```
3. The finished installer is written to `windows\Output\BoxedLANG-Setup.exe`.

This is provided as source only — building the actual `.exe` requires
running the Inno Setup compiler on a Windows machine (or under Wine),
which isn't something that can be produced in this chat.

## What gets installed either way

| Item | Location |
|---|---|
| Core scripts + IDE | `%LOCALAPPDATA%\BoxedLANG\` (Option A) or `Program Files\BoxedLANG\` (Option B) |
| `bx` / `transpilebx` / `bxdebug` | added to your user `PATH` |
| BoxedLANG IDE shortcut | Start Menu → BoxedLANG, and optionally Desktop |
| `.bx` file association | opens in the IDE |
| VS Code / VSCodium extension | syntax highlighting for `.bx` files |
