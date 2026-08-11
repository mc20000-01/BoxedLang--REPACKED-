#!/usr/bin/env bash
set -e

# Run this from the same folder as boxedlang-vscode.tar.gz (e.g. ~/Downloads,
# or wherever you saved it).

EXT_DIR="$HOME/.vscode-oss/extensions/boxedlang-0.0.1"
SETTINGS_DIR="$HOME/.config/Code - OSS/User"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

echo "--- Installing extension to $EXT_DIR ---"
mkdir -p "$EXT_DIR"
tar -xzf boxedlang-vscode.tar.gz -C "$EXT_DIR" --strip-components=1

echo "--- Merging color overrides into $SETTINGS_FILE ---"
mkdir -p "$SETTINGS_DIR"
[ -f "$SETTINGS_FILE" ] || echo "{}" > "$SETTINGS_FILE"

python3 - "$SETTINGS_FILE" << 'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    settings = json.load(f)

new_rules = [
    {"scope": "source.bx", "settings": {"foreground": "#7a97b2"}},
    {"scope": "keyword.control.bx", "settings": {"foreground": "#84b29c"}},
    {"scope": "variable.parameter.bx", "settings": {"foreground": "#bcece1"}},
    {"scope": "punctuation.separator.pipe.bx", "settings": {"foreground": "#885361"}},
    {"scope": "comment.line.double-slash.bx", "settings": {"foreground": "#8264a4", "fontStyle": "italic"}},
]

tcc = settings.setdefault("editor.tokenColorCustomizations", {})
rules = tcc.setdefault("textMateRules", [])

scopes_to_add = {r["scope"] for r in new_rules}
rules = [r for r in rules if r.get("scope") not in scopes_to_add]
rules.extend(new_rules)
tcc["textMateRules"] = rules

with open(path, "w") as f:
    json.dump(settings, f, indent=4)

print("settings.json updated (existing settings preserved).")
PYEOF

echo "--- Done. Restart Code - OSS and open a .bx file. ---"
