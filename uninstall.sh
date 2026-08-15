#!/usr/bin/env bash
# uninstall.sh - removes everything BoxedLANG's install.sh put in place.
# Run from anywhere; it doesn't touch your .bx files or scripts.
set -e

INSTALL_DIR="$HOME/.local/share/bxlang"
BIN_DIR="$HOME/.local/bin"

echo "=== Removing BoxedLANG core from $INSTALL_DIR ==="
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  removed $INSTALL_DIR"
else
    echo "  $INSTALL_DIR not found, nothing to remove"
fi

echo "=== Removing launchers from $BIN_DIR ==="
for bin in bx transpilebx bxdebug; do
    if [ -f "$BIN_DIR/$bin" ]; then
        rm -f "$BIN_DIR/$bin"
        echo "  removed $BIN_DIR/$bin"
    fi
done

echo "=== Removing micro syntax/colorscheme ==="
[ -f "$HOME/.config/micro/syntax/bx.yaml" ] && \
    rm -f "$HOME/.config/micro/syntax/bx.yaml" && \
    echo "  removed bx.yaml from micro syntax"
[ -f "$HOME/.config/micro/colorschemes/boxedlang.micro" ] && \
    rm -f "$HOME/.config/micro/colorschemes/boxedlang.micro" && \
    echo "  removed boxedlang.micro from micro colorschemes"

echo "=== Removing VS Code / Code-OSS / VSCodium extension ==="
for ext_dir in \
    "$HOME/.vscode/extensions/boxedlang-0.0.1" \
    "$HOME/.vscode-oss/extensions/boxedlang-0.0.1" \
    "$HOME/.vscodium/extensions/boxedlang-0.0.1"; do
    if [ -d "$ext_dir" ]; then
        rm -rf "$ext_dir"
        echo "  removed $ext_dir"
    fi
done

echo "=== Cleaning PATH entry from shell rc ==="
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rc" ] && grep -q "bxlang" "$rc" 2>/dev/null; then
        # Remove the two lines install.sh added (comment + export)
        sed -i '/# added by BoxedLANG install.sh/d' "$rc"
        sed -i "/export PATH.*bxlang/d" "$rc"
        echo "  cleaned $rc"
    fi
done

echo ""
echo "=== Done ==="
echo "BoxedLANG has been uninstalled."
echo "Your .bx source files and any transpiled output are untouched."
