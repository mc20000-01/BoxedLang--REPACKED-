#!/usr/bin/env bash
# install.sh - installs the BoxedLANG toolkit (bx.py, bxastgen.py,
# bxrunner.py, transpilebx.py, bxdebug.py) to a real location, puts
# `bx`/`transpilebx`/`bxdebug` on your PATH, and installs syntax
# highlighting for micro and VS Code / Code-OSS / VSCodium if it
# detects you have them. Run this from the folder containing the
# files above (e.g. your REPACKED/ folder).
set -e

INSTALL_DIR="$HOME/.local/share/bxlang"
BIN_DIR="$HOME/.local/bin"

echo "=== Installing BoxedLANG core to $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
for f in bx.py bxastgen.py bxrunner.py transpilebx.py bxdebug.py; do
    if [ -f "$f" ]; then
        cp "$f" "$INSTALL_DIR/"
    else
        echo "  warning: $f not found here, skipping"
    fi
done
if [ -d apis ]; then
    cp -r apis "$INSTALL_DIR/"
fi

echo "=== Creating launchers in $BIN_DIR ==="
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/bx" << EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/bx.py" "\$@"
EOF

cat > "$BIN_DIR/transpilebx" << EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/transpilebx.py" "\$@"
EOF

cat > "$BIN_DIR/bxdebug" << EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/bxdebug.py" "\$@"
EOF

chmod +x "$BIN_DIR/bx" "$BIN_DIR/transpilebx" "$BIN_DIR/bxdebug"

echo "=== Checking PATH ==="
case ":$PATH:" in
    *":$BIN_DIR:"*)
        echo "  $BIN_DIR is already on PATH."
        ;;
    *)
        SHELL_RC=""
        case "$SHELL" in
            */zsh) SHELL_RC="$HOME/.zshrc" ;;
            */bash) SHELL_RC="$HOME/.bashrc" ;;
            *) SHELL_RC="$HOME/.profile" ;;
        esac
        if ! grep -q "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
            echo "" >> "$SHELL_RC"
            echo "# added by BoxedLANG install.sh" >> "$SHELL_RC"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_RC"
            echo "  added $BIN_DIR to PATH in $SHELL_RC (restart your shell, or run: source $SHELL_RC)"
        else
            echo "  $BIN_DIR already referenced in $SHELL_RC"
        fi
        ;;
esac

echo ""
echo "=== Editor support ==="

# --- micro ---
if command -v micro >/dev/null 2>&1 || [ -d "$HOME/.config/micro" ]; then
    echo "  micro detected - installing syntax + colorscheme"
    mkdir -p "$HOME/.config/micro/syntax" "$HOME/.config/micro/colorschemes"
    [ -f bx.yaml ] && cp bx.yaml "$HOME/.config/micro/syntax/bx.yaml"
    [ -f boxedlang.micro ] && cp boxedlang.micro "$HOME/.config/micro/colorschemes/boxedlang.micro"
    echo "    -> set colorscheme boxedlang (inside micro, or in settings.json) to see it"
else
    echo "  micro not detected, skipping"
fi

# --- VS Code / Code-OSS / VSCodium ---
VSCODE_EXT_DIR=""
if command -v code >/dev/null 2>&1 || [ -d "$HOME/.vscode" ]; then
    VSCODE_EXT_DIR="$HOME/.vscode/extensions/boxedlang-0.0.1"
elif command -v code-oss >/dev/null 2>&1 || [ -d "$HOME/.vscode-oss" ]; then
    VSCODE_EXT_DIR="$HOME/.vscode-oss/extensions/boxedlang-0.0.1"
elif command -v codium >/dev/null 2>&1 || [ -d "$HOME/.vscodium" ]; then
    VSCODE_EXT_DIR="$HOME/.vscodium/extensions/boxedlang-0.0.1"
fi

if [ -n "$VSCODE_EXT_DIR" ]; then
    echo "  VS Code-family editor detected - installing extension to $VSCODE_EXT_DIR"
    mkdir -p "$VSCODE_EXT_DIR/syntaxes"
    [ -f package.json ] && cp package.json "$VSCODE_EXT_DIR/"
    [ -f language-configuration.json ] && cp language-configuration.json "$VSCODE_EXT_DIR/"
    [ -f bx.tmLanguage.json ] && cp bx.tmLanguage.json "$VSCODE_EXT_DIR/syntaxes/"
    if [ -f boxedlang-vscode.tar.gz ]; then
        tar -xzf boxedlang-vscode.tar.gz -C "$VSCODE_EXT_DIR" --strip-components=1 2>/dev/null || true
    fi
    echo "    -> restart the editor, then open a .bx file"
else
    echo "  no VS Code-family editor detected, skipping"
fi

echo ""
echo "=== Done ==="
echo "Run 'bx yourscript.bx', 'transpilebx yourscript.bx -l python', or 'bxdebug yourscript.bx'."
echo "If 'bx' isn't found right away, restart your shell or run: source ~/.bashrc (or your shell's rc file)"
