# BoxedLang--REPACKED-

## Installing

### Linux / macOS
```bash
sudo -E bash install.sh
```
Installs the `bx`, `transpilebx`, and `bxdebug` CLI tools, plus syntax
highlighting for micro and VS Code / Code-OSS / VSCodium if detected.

To remove: `bash uninstall.sh`

### Windows
Double-click `windows\install.bat` (no admin rights needed — just
Python 3 from https://python.org/downloads, with "Add python.exe to
PATH" checked during its install).

This installs the CLI tools **and the BoxedLANG IDE**, with a Start
Menu entry, a desktop shortcut, `.bx` files set to open in the IDE,
and the VS Code / VSCodium extension if detected.

To remove: double-click `windows\uninstall.bat`.

Want a single click-through `Setup.exe` instead? Compile
`windows\BoxedLANG.iss` with [Inno Setup](https://jrsoftware.org/isdl.php) —
see `windows\README_WINDOWS.md` for details.
