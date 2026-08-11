"""
transpilebx.py - BoxedLANG transpiler.

Converts a .bx script into source code for another language. Backends
are looked up by name via --lang/-l, so adding support for a new
target language later is just: write one function with the same
signature as transpile_python() below, and add it to BACKENDS -
nothing else in this file needs to change.

Currently supported: python
"""
import sys
import re
import argparse
import pathlib as file
import os.path

from bxastgen import make_ast, BoxedSyntaxError


def _pyvar(box_name):
    """Box name -> a safe, collision-free Python identifier."""
    out = []
    for c in box_name:
        out.append(c if (c.isalnum() or c == "_") else "_")
    ident = "".join(out)
    if not ident or ident[0].isdigit():
        ident = "_" + ident
    return "bx_" + ident


def _clean_literal_py(s):
    """Compile-time \\/-escape + ':' strip for a value with NO $ refs at
    all - safe to fully precompute since there's no chance a runtime
    substitution could introduce a new colon that needs stripping."""
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "/" and i + 2 < len(s):
            c = s[i + 2]
            out.append("\x00" if c == ":" else c)
            i += 3
        else:
            out.append(s[i])
            i += 1
    joined = "".join(out).replace(":", "")
    return joined.replace("\x00", ":")


def _collect_static_box_names(ast_tree):
    """
    Box names that are EVERY TIME assigned via a literal (non-$) target
    somewhere in the program - these are safe to promote to real native
    variables. A box that's ever assigned through a computed/dynamic
    target (something like note-:$name) can't be - its actual key isn't
    known until runtime, so it stays in the small residual boxes dict.
    """
    names = set()

    def visit(node):
        if node['type'] in ('Assign', 'Math', 'Test', 'Input'):
            if "$" not in node['target']:
                names.add(node['target'])
        elif node['type'] == 'Call':
            for i in range(1, len(node['args']) + 1):
                names.add(f"arg{i}")
        elif node['type'] == 'If':
            visit(node['body'])

    for n in ast_tree:
        visit(n)
    return names


def _tokenize_value(value, static_names):
    """
    Splits a raw value/target string into either:
      ('literal', cleaned_str)     - no '$' at all, fully compile-time-known
      ('parts', [('text', s) | ('var', box_name), ...])
                                    - every $ref matches a known static name
      ('dynamic', value)           - at least one $ref doesn't match a
                                      known static name (a computed box,
                                      or the note/file $$-indirection trick)
    """
    if "$" not in value:
        return ("literal", _clean_literal_py(value))

    sorted_names = sorted(static_names, key=len, reverse=True)
    parts = []
    i, n = 0, len(value)
    while i < n:
        if value[i] == "$":
            matched = next((nm for nm in sorted_names if value.startswith("$" + nm, i)), None)
            if matched is None:
                return ("dynamic", value)
            parts.append(("var", matched))
            i += len(matched) + 1
            continue
        j = value.find("$", i)
        j = n if j == -1 else j
        parts.append(("text", value[i:j]))
        i = j
    return ("parts", parts)


def _fstring_body(parts):
    """('parts', [...]) -> the inside of an f"..." literal. Each var ref
    falls back to its own literal "$name" text if that box was never set
    (or was deleted) - matching the interpreter's resolve(), which only
    ever substitutes names that actually exist in self.boxes."""
    pieces = []
    for kind, val in parts:
        if kind == "text":
            pieces.append(val.replace("\\", "\\\\").replace('"', '\\"')
                             .replace("{", "{{").replace("}", "}}")
                             .replace("\n", "\\n"))
        else:
            var = _pyvar(val)
            pieces.append("{" + f"({var} if {var} is not None else '${val}')" + "}")
    return "".join(pieces)


def _value_expr(value, static_names):
    """The Python source EXPRESSION for a value/target string - a plain
    string literal, an f-string built from native variables, or (only
    for genuinely dynamic/computed refs) a call into the small residual
    resolver that also sees the static vars' current values."""
    kind, payload = _tokenize_value(value, static_names)
    if kind == "literal":
        return repr(payload)
    if kind == "parts":
        return f'_clean(f"{_fstring_body(payload)}")'
    return f"_resolve_dynamic({value!r}, boxes, _static_snapshot())"


def transpile_python(ast_tree, marks, source_name):
    """
    Generates a standalone, dependency-free Python script - no bxrunner
    import, no generic "boxes" dict driving everything. Box names that
    are always assigned through a literal target get promoted to real
    Python variables (e.g. box "login" -> the variable bx_login), which
    covers the large majority of a typical .bx script. Only box names
    that get created through a *computed* target (the note/file apps'
    note-:$name trick) live in a small residual `boxes` dict, since
    their actual key isn't knowable until runtime.

    Control flow is still a pc-driven dispatch loop mirroring marks/
    jumps 1:1 (recovering real loops/if-chains from arbitrary goto-style
    jumps is a much harder, separate problem - not attempted here).
    """
    static_names = _collect_static_box_names(ast_tree)
    has_prm = "prm" in static_names
    bapi_functions = []  # BAPI disabled for now (WIP) - stays empty, kept only so nothing below NameErrors

    def emit_jump(node, indent):
        target_expr = _value_expr(node['target'], static_names)
        return [
            f"{indent}_t = {target_expr}",
            f"{indent}pc = marks.get(_t, 0) if {node['mode']!r} == 'm' else int(_t) - 1",
            f"{indent}continue",
        ]

    def assign_box(target, value_expr, indent):
        """Emits an assignment to either a native var or the residual dict."""
        if "$" not in target:
            return [f"{indent}{_pyvar(target)} = {value_expr}"]
        key_expr = _value_expr(target, static_names)
        return [f"{indent}boxes[{key_expr}] = {value_expr}"]

    def emit_action(node, indent):
        """Returns (lines, always_continues)."""
        t = node['type']

        if t == 'Assign':
            return assign_box(node['target'], _value_expr(node['value'], static_names), indent), False

        elif t == 'Print':
            value_expr = _value_expr(node['value'], static_names)
            time_expr = _value_expr(node['time'], static_names)
            return [
                f"{indent}print({value_expr})",
                f"{indent}_tv = int('0' + ({time_expr}).strip())",
                f"{indent}if _tv > 0:",
                f"{indent}    time.sleep(_tv)",
            ], False

        elif t == 'Input':
            prompt_expr = _value_expr(node['prompt'], static_names)
            suffix_expr = "(bx_prm if bx_prm is not None else '\\n:> ')" if has_prm else "boxes.get('prm', '\\n:> ')"
            lines = [f"{indent}_suffix = {suffix_expr}"]
            lines.append(f"{indent}_line = input({prompt_expr} + _suffix)")
            lines.extend(assign_box(node['target'], "_line", indent))
            return lines, False

        elif t == 'Math':
            left_expr = _value_expr(node['left'], static_names)
            right_expr = _value_expr(node['right'], static_names)
            op_expr = _value_expr(node['op'], static_names)
            return assign_box(node['target'], f"str(_math({left_expr}, {right_expr}, {op_expr}))", indent), False

        elif t == 'Test':
            left_expr = _value_expr(node['left'], static_names)
            right_expr = _value_expr(node['right'], static_names)
            op_expr = _value_expr(node['op'], static_names)
            true_expr = _value_expr(node['true_val'], static_names)
            false_expr = _value_expr(node['false_val'], static_names)
            lines = [f"{indent}if _test({left_expr}, {right_expr}, {op_expr}):"]
            lines.extend(assign_box(node['target'], true_expr, indent + "    "))
            lines.append(f"{indent}else:")
            lines.extend(assign_box(node['target'], false_expr, indent + "    "))
            return lines, False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            left_expr = _value_expr(node['left'], static_names)
            right_expr = _value_expr(node['right'], static_names)
            op_expr = _value_expr(node['op'], static_names)
            lines = [f"{indent}if _test({left_expr}, {right_expr}, {op_expr}):"]
            lines.extend(emit_jump(node, indent + "    "))
            return lines, False

        elif t == 'If':
            left_expr = _value_expr(node['left'], static_names)
            right_expr = _value_expr(node['right'], static_names)
            op_expr = _value_expr(node['op'], static_names)
            lines = [f"{indent}if _test({left_expr}, {right_expr}, {op_expr}):"]
            body_lines, body_continues = emit_action(node['body'], indent + "    ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}    pc += 1")
                lines.append(f"{indent}    continue")
            return lines, False

        elif t == 'Wait':
            time_expr = _value_expr(node['time'], static_names)
            return [f"{indent}time.sleep(float({time_expr}))"], False

        elif t == 'Delete':
            # target is a value expression identifying WHICH box/var to
            # drop, e.g. `del $name` deletes whatever box name's value
            # currently points at - it does not touch the "name" var
            # itself. `del somelitteral` (no $) does reset that var.
            if "$" not in node['target']:
                return [f"{indent}{_pyvar(node['target'])} = None"], False
            key_expr = _value_expr(node['target'], static_names)
            return [f"{indent}boxes.pop({key_expr}, None)"], False

        elif t == 'Mark':
            return [f"{indent}pass  # mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}pass  # import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                lines.extend(assign_box(f"arg{i}", _value_expr(a, static_names), indent))
            lines.append(f"{indent}if {target!r} not in marks:")
            lines.append(
                f"{indent}    raise RuntimeError("
                f"\"call to undefined '{target}' - is '{node['namespace']}' imported, "
                f"and does it define a premark called '{node['func']}'?\")"
            )
            lines.append(f"{indent}_call_stack.append(pc + 1)")
            lines.append(f"{indent}pc = marks[{target!r}]")
            lines.append(f"{indent}continue")
            return lines, True

        elif t == 'Return':
            lines = []
            for name in sorted(static_names):
                if name.startswith("ret-") and len(name) > 4:
                    target_name = name[4:]
                    src_var = _pyvar(name)
                    if target_name in static_names:
                        lines.append(f"{indent}{_pyvar(target_name)} = {src_var}")
                    lines.append(f"{indent}boxes[{target_name!r}] = {src_var}")
            lines.append(f"{indent}for _k in list(boxes.keys()):")
            lines.append(f"{indent}    if _k.startswith('ret-') and len(_k) > 4: boxes[_k[4:]] = boxes[_k]")
            lines.append(f"{indent}if not _call_stack:")
            lines.append(f"{indent}    raise RuntimeError(\"'return' with no active call\")")
            lines.append(f"{indent}pc = _call_stack.pop()")
            lines.append(f"{indent}continue")
            return lines, True

        # BAPI disabled for now (WIP), see note above.
        # elif t == 'BapiCall':
        #     unique_name, spliced_src, decl_params = _splice_bapi_python(node['api'], node['func'], node['args'])
        #     if spliced_src not in bapi_functions:
        #         bapi_functions.append(spliced_src)
        #     arg_exprs = [f"_bapi_arg({_value_expr(a, static_names)})" for a in node['args']]
        #     lines = [f"{indent}_bapi_result = {unique_name}({', '.join(arg_exprs)})"]
        #     lines.append(f"{indent}boxes['return'] = str(_bapi_result)")
        #     return lines, False

        elif t == 'Clear':
            return [f"{indent}sys.stdout.write('\\x1b[2J\\x1b[H'); sys.stdout.flush()"], False

        elif t == 'End':
            return [f"{indent}sys.exit()"], True

        else:
            return [f"{indent}pass  # unhandled node type: {t}"], False

    # Pre-scan the whole program's generated body first, since whether
    # _resolve_dynamic/_static_snapshot are needed at all depends on
    # whether anything actually hit the 'dynamic' fallback path.
    body = []
    for i, node in enumerate(ast_tree):
        keyword = "if" if i == 0 else "elif"
        body.append(f"    {keyword} pc == {i}:")
        action_lines, always_continues = emit_action(node, "        ")
        body.extend(action_lines)
        if not always_continues:
            body.append("        pc += 1")
            body.append("        continue")
    body.append("    else:")
    body.append("        break")
    body_src = "\n".join(body)
    needs_dynamic = "_resolve_dynamic(" in body_src

    header = [
        f'"""Auto-generated by transpilebx.py --lang python from {source_name}. Do not edit by hand."""',
        "import sys",
        "import time",
        "import traceback",
        "",
        "boxes = {}  # only for computed/dynamic box names (e.g. note-:$name)",
        f"marks = {marks!r}",
        "_call_stack = []",
        "",
    ]

    header.append("# Box names that are always assigned via a literal target become")
    header.append("# plain variables here, initialized None (\"not set yet\"):")
    for name in sorted(static_names):
        header.append(f"{_pyvar(name)} = None")
    header.append("")

    header.append("def _clean(s):")
    header.append("    # \\/ escapes the char right after it (shields a literal ':'")
    header.append("    # through the blanket strip below).")
    header.append("    out = []")
    header.append("    i = 0")
    header.append("    while i < len(s):")
    header.append("        if s[i] == '\\\\' and i + 2 < len(s) and s[i + 1] == '/':")
    header.append("            c = s[i + 2]")
    header.append("            out.append('\\x00' if c == ':' else c)")
    header.append("            i += 3")
    header.append("        else:")
    header.append("            out.append(s[i])")
    header.append("            i += 1")
    header.append("    joined = ''.join(out).replace(':', '')")
    header.append("    return joined.replace('\\x00', ':')")
    header.append("")
    header.append("def _is_numeric(s):")
    header.append("    t = s[1:] if s.startswith('-') else s")
    header.append("    return t.isnumeric()")
    header.append("")
    header.append("def _math(left, right, op):")
    header.append("    l = int(left) if _is_numeric(left) else 0")
    header.append("    r = int(right) if _is_numeric(right) else 0")
    header.append("    if op == '+': return l + r")
    header.append("    if op == '-': return l - r")
    header.append("    if op in ('*', 'x'): return l * r")
    header.append("    if op == '/': return l // r if r != 0 else 0")
    header.append("    if op == '%': return l % r if r != 0 else 0")
    header.append("    return 0")
    header.append("")
    header.append("def _test(left, right, op):")
    header.append("    if op == '==': return left == right")
    header.append("    if op == '!=': return left != right")
    header.append("    try:")
    header.append("        l, r = float(left), float(right)")
    header.append("    except ValueError:")
    header.append("        return False")
    header.append("    if op == '>': return l > r")
    header.append("    if op == '<': return l < r")
    header.append("    if op == '>=': return l >= r")
    header.append("    if op == '<=': return l <= r")
    header.append("    return False")

    if needs_dynamic:
        header.append("")
        header.append("# Fallback for the rare $ref this script couldn't resolve at")
        header.append("# transpile time (the note/file apps' $$name double-lookup trick,")
        header.append("# where the box being read isn't known until runtime).")
        header.append("def _static_snapshot():")
        header.append("    d = {}")
        for name in sorted(static_names):
            header.append(f"    if {_pyvar(name)} is not None: d[{name!r}] = {_pyvar(name)}")
        header.append("    return d")
        header.append("")
        header.append("def _resolve_dynamic(val, boxes, extra):")
        header.append("    for _ in range(2):")
        header.append("        merged = {**boxes, **extra}")
        header.append("        for name, v in sorted(merged.items(), key=lambda kv: len(kv[0]), reverse=True):")
        header.append("            val = val.replace('$' + name, str(v))")
        header.append("    out = []")
        header.append("    i = 0")
        header.append("    while i < len(val):")
        header.append("        if val[i] == '\\\\' and i + 2 < len(val) and val[i + 1] == '/':")
        header.append("            c = val[i + 2]")
        header.append("            out.append('\\x00' if c == ':' else c)")
        header.append("            i += 3")
        header.append("        else:")
        header.append("            out.append(val[i])")
        header.append("            i += 1")
        header.append("    joined = ''.join(out).replace(':', '')")
        header.append("    return joined.replace('\\x00', ':')")

    # BAPI disabled for now (WIP) - bapi_functions stays empty, so this
    # was already inert; commented for clarity.
    # if bapi_functions:
    #     header.append("")
    #     header.append("def _bapi_arg(s):")
    #     header.append("    try:")
    #     header.append("        return int(s)")
    #     header.append("    except ValueError:")
    #     header.append("        return s")
    #     for fn_src in bapi_functions:
    #         header.append("")
    #         header.extend(fn_src.splitlines())

    header.append("")
    header.append("pc = 0")
    header.append(f"_END = {len(ast_tree)}")
    header.append("try:")
    header.append("    while True:")

    body_indented = "\n".join("    " + line if line else line for line in body)

    footer = [
        "except KeyboardInterrupt:",
        "    print(' — stopped.')",
        "    sys.exit(130)",
        "except SystemExit:",
        "    raise",
        "except Exception as e:",
        "    bar = '=' * 60",
        "    print(f'\\n{bar}', file=sys.stderr)",
        "    print(f'BoxedLANG (transpiled) runtime error at pc={pc}', file=sys.stderr)",
        "    print(f'  {type(e).__name__}: {e}', file=sys.stderr)",
        "    print(f'  boxes (dynamic only) : {boxes}', file=sys.stderr)",
        "    print(bar, file=sys.stderr)",
        "    traceback.print_exc()",
        "    print(bar, file=sys.stderr)",
        "    sys.exit(1)",
    ]

    return "\n".join(header) + "\n" + body_indented + "\n" + "\n".join(footer) + "\n"


def transpile_lua(ast_tree, marks, source_name):
    """
    Standalone Lua 5.3+. Same native-variable promotion as the Python
    backend: box names always assigned via a literal target become
    real Lua locals; only genuinely computed keys (note-:$name) live
    in a small residual `boxes` table.

    Lua has real goto/labels, but our jump targets are often runtime-
    computed ($vars), which no language here can goto to directly - so
    this still uses a pc-dispatch loop. Lua has no native 'continue',
    so goto+label simulates it.
    """
    static_names = _collect_static_box_names(ast_tree)
    has_prm = "prm" in static_names

    def lstr(s):
        out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + out + '"'

    def concat_expr(parts):
        pieces = []
        for kind, val in parts:
            if kind == "text":
                if val:
                    pieces.append(lstr(val))
            else:
                var = _pyvar(val)
                pieces.append(f"({var} ~= nil and {var} or {lstr('$' + val)})")
        return " .. ".join(pieces) if pieces else '""'

    def value_expr(value):
        kind, payload = _tokenize_value(value, static_names)
        if kind == "literal":
            return lstr(payload)
        if kind == "parts":
            return f"_clean({concat_expr(payload)})"
        return f"_resolve_dynamic({lstr(value)}, boxes, _static_snapshot())"

    def assign_box(target, value_expr_str, indent):
        if "$" not in target:
            return [f"{indent}{_pyvar(target)} = {value_expr_str}"]
        key_expr = value_expr(target)
        return [f"{indent}boxes[{key_expr}] = {value_expr_str}"]

    def emit_jump(node, indent):
        target_expr = value_expr(node['target'])
        return [
            f"{indent}local _t = {target_expr}",
            f"{indent}if {lstr(node['mode'])} == \"m\" then",
            f"{indent}  pc = marks[_t]",
            f"{indent}  if pc == nil then pc = 0 end",
            f"{indent}else",
            f"{indent}  pc = (tonumber(_t) or 1) - 1",
            f"{indent}end",
            f"{indent}goto continue",
        ]

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            return assign_box(node['target'], value_expr(node['value']), indent), False

        elif t == 'Print':
            return [
                f"{indent}print({value_expr(node['value'])})",
                f"{indent}local _tv = tonumber({value_expr(node['time'])}) or 0",
                f"{indent}if _tv > 0 then os.execute(\"sleep \" .. tostring(_tv)) end",
            ], False

        elif t == 'Input':
            suffix_expr = "(bx_prm ~= nil and bx_prm or \"\\n:> \")" if has_prm else "(boxes[\"prm\"] or \"\\n:> \")"
            lines = [
                f"{indent}io.write({value_expr(node['prompt'])})",
                f"{indent}io.write({suffix_expr})",
                f"{indent}io.flush()",
                f"{indent}local _line = io.read(\"*l\") or \"\"",
            ]
            lines.extend(assign_box(node['target'], "_line", indent))
            return lines, False

        elif t == 'Math':
            expr = f"tostring(_math({value_expr(node['left'])}, {value_expr(node['right'])}, {value_expr(node['op'])}))"
            return assign_box(node['target'], expr, indent), False

        elif t == 'Test':
            lines = [f"{indent}if _test({value_expr(node['left'])}, {value_expr(node['right'])}, {value_expr(node['op'])}) then"]
            lines.extend(assign_box(node['target'], value_expr(node['true_val']), indent + "  "))
            lines.append(f"{indent}else")
            lines.extend(assign_box(node['target'], value_expr(node['false_val']), indent + "  "))
            lines.append(f"{indent}end")
            return lines, False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            lines = [f"{indent}if _test({value_expr(node['left'])}, {value_expr(node['right'])}, {value_expr(node['op'])}) then"]
            lines.extend(emit_jump(node, indent + "  "))
            lines.append(f"{indent}end")
            return lines, False

        elif t == 'If':
            lines = [f"{indent}if _test({value_expr(node['left'])}, {value_expr(node['right'])}, {value_expr(node['op'])}) then"]
            body_lines, body_continues = emit_action(node['body'], indent + "  ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}  pc = pc + 1")
                lines.append(f"{indent}  goto continue")
            lines.append(f"{indent}end")
            return lines, False

        elif t == 'Wait':
            return [f"{indent}os.execute(\"sleep \" .. tostring(tonumber({value_expr(node['time'])}) or 0))"], False

        elif t == 'Delete':
            if "$" not in node['target']:
                return [f"{indent}{_pyvar(node['target'])} = nil"], False
            return [f"{indent}boxes[{value_expr(node['target'])}] = nil"], False

        elif t == 'Mark':
            return [f"{indent}-- mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}-- import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                lines.extend(assign_box(f"arg{i}", value_expr(a), indent))
            lines.append(f"{indent}local _m = marks[{lstr(target)}]")
            lines.append(f"{indent}if _m == nil then error(\"call to undefined '{target}' - is the module imported and does it define this premark?\") end")
            lines.append(f"{indent}table.insert(call_stack, pc + 1)")
            lines.append(f"{indent}pc = _m")
            lines.append(f"{indent}goto continue")
            return lines, True

        elif t == 'Return':
            lines = []
            for name in sorted(static_names):
                if name.startswith("ret-") and len(name) > 4:
                    target_name = name[4:]
                    src_var = _pyvar(name)
                    if target_name in static_names:
                        lines.append(f"{indent}{_pyvar(target_name)} = {src_var}")
                    lines.append(f'{indent}boxes["{target_name}"] = {src_var}')
            lines.append(f"{indent}for k, v in pairs(boxes) do")
            lines.append(f'{indent}  if k:sub(1, 4) == "ret-" and #k > 4 then boxes[k:sub(5)] = v end')
            lines.append(f"{indent}end")
            lines.append(f"{indent}if #call_stack == 0 then error(\"'return' with no active call\") end")
            lines.append(f"{indent}pc = call_stack[#call_stack]")
            lines.append(f"{indent}table.remove(call_stack)")
            lines.append(f"{indent}goto continue")
            return lines, True

        elif t == 'Clear':
            return [f"{indent}io.write(\"\\27[2J\\27[H\"); io.flush()"], False

        elif t == 'End':
            return [f"{indent}os.exit()"], True

        else:
            return [f"{indent}-- unhandled node type: {t}"], False

    marks_lines = ["local marks = {}"]
    for name, idx in marks.items():
        marks_lines.append(f"marks[{lstr(name)}] = {idx}")

    # Pre-scan the body first, since whether _resolve_dynamic/
    # _static_snapshot are needed at all depends on whether anything
    # actually hit the 'dynamic' fallback path.
    body = []
    for i, node in enumerate(ast_tree):
        keyword = "if" if i == 0 else "elseif"
        body.append(f"    {keyword} pc == {i} then")
        action_lines, always_continues = emit_action(node, "      ")
        body.extend(action_lines)
        if not always_continues:
            body.append("      pc = pc + 1")
            body.append("      goto continue")
    body.append("    end")
    body.append("    ::continue::")
    body_src = "\n".join(body)
    needs_dynamic = "_resolve_dynamic(" in body_src

    header = [
        f"-- Auto-generated by transpilebx.py --lang lua from {source_name}. Do not edit by hand.",
        "-- NOTE: sleeps use os.execute('sleep N') (Unix only). Non-numeric say/wait",
        "-- durations default to 0 rather than erroring (a deliberate simplification).",
        "local boxes = {}  -- only for computed/dynamic box names (e.g. note-:$name)",
        "local call_stack = {}",
        "",
    ] + marks_lines + [
        "",
        "-- Box names always assigned via a literal target become plain",
        "-- locals here, initialized nil (\"not set yet\"):",
    ]
    for name in sorted(static_names):
        header.append(f"local {_pyvar(name)} = nil")

    header += [
        "",
        "local function _clean(s)",
        "  -- \\/ escapes the char right after it (shields a literal ':'",
        "  -- through the blanket strip below).",
        "  s = s:gsub(\"\\\\/(.)\", function(c)",
        "    if c == \":\" then return \"\\0\" else return c end",
        "  end)",
        "  s = s:gsub(\":\", \"\")",
        "  s = s:gsub(\"\\0\", \":\")",
        "  return s",
        "end",
        "",
        "local function _test(left, right, op)",
        "  if op == \"==\" then return left == right end",
        "  if op == \"!=\" then return left ~= right end",
        "  local l = tonumber(left)",
        "  local r = tonumber(right)",
        "  if l == nil or r == nil then return false end",
        "  if op == \">\" then return l > r end",
        "  if op == \"<\" then return l < r end",
        "  if op == \">=\" then return l >= r end",
        "  if op == \"<=\" then return l <= r end",
        "  return false",
        "end",
        "",
        "local function _is_numeric(s)",
        "  local t = s:gsub(\"^%-\", \"\")",
        "  return t ~= \"\" and t:match(\"^%d+$\") ~= nil",
        "end",
        "",
        "local function _math(left, right, op)",
        "  local l = _is_numeric(left) and tonumber(left) or 0",
        "  local r = _is_numeric(right) and tonumber(right) or 0",
        "  if op == \"+\" then return l + r",
        "  elseif op == \"-\" then return l - r",
        "  elseif op == \"*\" or op == \"x\" then return l * r",
        "  elseif op == \"/\" then if r ~= 0 then return math.floor(l / r) else return 0 end",
        "  elseif op == \"%\" then if r ~= 0 then return l % r else return 0 end",
        "  end",
        "  return 0",
        "end",
    ]

    if needs_dynamic:
        header += [
            "",
            "-- Fallback for the rare $ref this script couldn't resolve at",
            "-- transpile time (the note/file apps' $$name double-lookup trick,",
            "-- where the box being read isn't known until runtime).",
            "local function _esc_pattern(s)",
            "  return (s:gsub(\"([%^%$%(%)%%%.%[%]%*%+%-%?])\", \"%%%1\"))",
            "end",
            "",
            "local function _static_snapshot()",
            "  local d = {}",
        ]
        for name in sorted(static_names):
            header.append(f"  if {_pyvar(name)} ~= nil then d[{lstr(name)}] = {_pyvar(name)} end")
        header += [
            "  return d",
            "end",
            "",
            "local function _resolve_dynamic(val, boxes, extra)",
            "  for _ = 1, 2 do",
            "    local merged = {}",
            "    for k, v in pairs(boxes) do merged[k] = v end",
            "    for k, v in pairs(extra) do merged[k] = v end",
            "    local keys = {}",
            "    for k in pairs(merged) do table.insert(keys, k) end",
            "    table.sort(keys, function(a, b) return #a > #b end)",
            "    for _, k in ipairs(keys) do",
            "      local repl = tostring(merged[k]):gsub(\"%%\", \"%%%%\")",
            "      val = val:gsub(\"%$\" .. _esc_pattern(k), repl)",
            "    end",
            "  end",
            "  return _clean(val)",
            "end",
        ]

    header += [
        "",
        "local pc = 0",
        f"local END = {len(ast_tree)}",
        "local ok, err = pcall(function()",
        "  while pc < END do",
    ]

    body.append("  end")
    body.append("end)")

    footer = [
        "if not ok then",
        "  local bar = string.rep(\"=\", 60)",
        "  io.stderr:write(\"\\n\" .. bar .. \"\\n\")",
        "  io.stderr:write(\"BoxedLANG (transpiled) runtime error at pc=\" .. tostring(pc) .. \"\\n\")",
        "  io.stderr:write(\"  \" .. tostring(err) .. \"\\n\")",
        "  io.stderr:write(bar .. \"\\n\")",
        "  os.exit(1)",
        "end",
    ]

    return "\n".join(header + body + footer) + "\n"


def transpile_ruby(ast_tree, marks, source_name):
    """Standalone Ruby. Ruby's String#gsub does literal replacement when
    given a String pattern (not a Regexp), so $var substitution needs no
    escaping - the cleanest of all six backends."""

    def rstr(s):
        out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + out + '"'

    def emit_jump(node, indent):
        return [
            f"{indent}_t = resolve({rstr(node['target'])})",
            f"{indent}pc = {rstr(node['mode'])} == \"m\" ? ($marks[_t] || 0) : (_t.to_i - 1)",
            f"{indent}next",
        ]

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            return [f"{indent}$boxes[resolve({rstr(node['target'])})] = resolve({rstr(node['value'])})"], False

        elif t == 'Print':
            return [
                f"{indent}puts resolve({rstr(node['value'])})",
                f"{indent}_tv = resolve({rstr(node['time'])}).to_i",
                f"{indent}sleep(_tv) if _tv > 0",
            ], False

        elif t == 'Input':
            return [
                f"{indent}_suffix = $boxes.key?(\"prm\") ? $boxes[\"prm\"] : \"\\n:> \"",
                f"{indent}print(resolve({rstr(node['prompt'])}) + _suffix)",
                f"{indent}$boxes[resolve({rstr(node['target'])})] = (STDIN.gets || \"\").chomp",
            ], False

        elif t == 'Math':
            return [
                f"{indent}$boxes[resolve({rstr(node['target'])})] = "
                f"math_op({rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])}).to_s"
            ], False

        elif t == 'Test':
            return [
                f"{indent}if test_op({rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])})",
                f"{indent}  $boxes[resolve({rstr(node['target'])})] = resolve({rstr(node['true_val'])})",
                f"{indent}else",
                f"{indent}  $boxes[resolve({rstr(node['target'])})] = resolve({rstr(node['false_val'])})",
                f"{indent}end",
            ], False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            lines = [f"{indent}if test_op({rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])})"]
            lines.extend(emit_jump(node, indent + "  "))
            lines.append(f"{indent}end")
            return lines, False

        elif t == 'If':
            lines = [f"{indent}if test_op({rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])})"]
            body_lines, body_continues = emit_action(node['body'], indent + "  ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}  pc += 1")
                lines.append(f"{indent}  next")
            lines.append(f"{indent}end")
            return lines, False

        elif t == 'Wait':
            return [f"{indent}sleep(resolve({rstr(node['time'])}).to_f)"], False

        elif t == 'Delete':
            return [f"{indent}$boxes.delete(resolve({rstr(node['target'])}))"], False

        elif t == 'Mark':
            return [f"{indent}# mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}# import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                lines.append(f"{indent}$boxes[\"arg{i}\"] = resolve({rstr(a)})")
            lines.append(f"{indent}raise \"call to undefined '{target}' - is the module imported and does it define this premark?\" unless $marks.key?({rstr(target)})")
            lines.append(f"{indent}$call_stack.push(pc + 1)")
            lines.append(f"{indent}pc = $marks[{rstr(target)}]")
            lines.append(f"{indent}next")
            return lines, True

        elif t == 'Return':
            return [
                f'{indent}$boxes.keys.each {{ |k| $boxes[k[4..]] = $boxes[k] if k.start_with?("ret-") && k.length > 4 }}',
                f"{indent}raise \"'return' with no active call\" if $call_stack.empty?",
                f"{indent}pc = $call_stack.pop()",
                f"{indent}next",
            ], True

        elif t == 'Clear':
            return [f"{indent}print \"\\e[2J\\e[H\"; $stdout.flush"], False

        elif t == 'End':
            return [f"{indent}exit(0)"], True

        else:
            return [f"{indent}# unhandled node type: {t}"], False

    header = [
        f"# Auto-generated by transpilebx.py --lang ruby from {source_name}. Do not edit by hand.",
        "# NOTE: non-numeric say/wait durations default to 0 rather than erroring",
        "# (a deliberate simplification).",
        "STDOUT.sync = true",
        "$boxes = {}",
        "$call_stack = []",
        "$marks = {" + ", ".join(f"{rstr(name)} => {idx}" for name, idx in marks.items()) + "}",
        "",
        "def resolve(val)",
        "  2.times do",
        "    $boxes.keys.sort_by { |k| -k.length }.each do |k|",
        "      val = val.gsub(\"$#{k}\", $boxes[k])",
        "    end",
        "  end",
        "  val = val.gsub(/\\\\\\/(.)/) { $~[1] == ':' ? \"\\x00\" : $~[1] }",
        "  val = val.gsub(':', '')",
        "  val = val.gsub(\"\\x00\", ':')",
        "  val",
        "end",
        "",
        "def test_op(left, right, op)",
        "  left = resolve(left)",
        "  right = resolve(right)",
        "  case op",
        "  when \"==\" then left == right",
        "  when \"!=\" then left != right",
        "  else",
        "    begin",
        "      l = Float(left); r = Float(right)",
        "      case op",
        "      when \">\" then l > r",
        "      when \"<\" then l < r",
        "      when \">=\" then l >= r",
        "      when \"<=\" then l <= r",
        "      else false",
        "      end",
        "    rescue ArgumentError, TypeError",
        "      false",
        "    end",
        "  end",
        "end",
        "",
        "def is_numeric(s)",
        "  t = s.sub(/\\A-/, '')",
        "  !t.empty? && t =~ /\\A\\d+\\z/",
        "end",
        "",
        "def math_op(left, right, op)",
        "  lv = resolve(left)",
        "  rv = resolve(right)",
        "  op = resolve(op)",
        "  l = is_numeric(lv) ? lv.to_i : 0",
        "  r = is_numeric(rv) ? rv.to_i : 0",
        "  case op",
        "  when \"+\" then l + r",
        "  when \"-\" then l - r",
        "  when \"*\", \"x\" then l * r",
        "  when \"/\" then r != 0 ? l / r : 0",
        "  when \"%\" then r != 0 ? l % r : 0",
        "  else 0",
        "  end",
        "end",
        "",
        "pc = 0",
        f"_END = {len(ast_tree)}",
        "begin",
        "  loop do",
        "    break if pc >= _END",
        "    case pc",
    ]

    body = []
    for i, node in enumerate(ast_tree):
        body.append(f"    when {i}")
        action_lines, always_continues = emit_action(node, "      ")
        body.extend(action_lines)
        if not always_continues:
            body.append("      pc += 1")
            body.append("      next")
    body.append("    else")
    body.append("      break")
    body.append("    end")
    body.append("  end")

    footer = [
        "rescue Interrupt",
        "  puts \" — stopped.\"",
        "  exit(130)",
        "rescue SystemExit",
        "  raise",
        "rescue => e",
        "  bar = \"=\" * 60",
        "  STDERR.puts \"\\n#{bar}\"",
        "  STDERR.puts \"BoxedLANG (transpiled) runtime error at pc=#{pc}\"",
        "  STDERR.puts \"  #{e.class}: #{e.message}\"",
        "  STDERR.puts \"  boxes : #{$boxes}\"",
        "  STDERR.puts \"  marks : #{$marks}\"",
        "  STDERR.puts bar",
        "  STDERR.puts e.backtrace.join(\"\\n\") if e.backtrace",
        "  STDERR.puts bar",
        "  exit(1)",
        "end",
    ]

    return "\n".join(header + body + footer) + "\n"


def transpile_c(ast_tree, marks, source_name):
    """
    Standalone C99. No built-in hashmap/dynamic strings in C, so this
    uses a fixed-size linear-scan box table (MAX_BOXES entries, up to
    VAL_LEN chars each) - fine for normal-sized .bx scripts, but a real
    limitation for huge ones. No exceptions in C, so runtime errors are
    handled by defensive bounds/parse checks rather than a catch-all.
    """
    MAX_BOXES = 512
    KEY_LEN = 128
    VAL_LEN = 8192

    def cstr(s):
        out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + out + '"'

    def emit_jump(node, indent):
        return [
            f'{indent}resolve(_t, {cstr(node["target"])});',
            f'{indent}if (strcmp({cstr(node["mode"])}, "m") == 0) {{',
            f'{indent}    pc = mark_get(_t);',
            f'{indent}    if (pc < 0) pc = 0;',
            f'{indent}}} else {{',
            f'{indent}    pc = atoi(_t) - 1;',
            f'{indent}}}',
            f'{indent}goto cont;',
        ]

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            return [
                f'{indent}{{',
                f'{indent}    char _k[KEY_LEN], _v[VAL_LEN];',
                f'{indent}    resolve(_k, {cstr(node["target"])});',
                f'{indent}    resolve(_v, {cstr(node["value"])});',
                f'{indent}    box_set(_k, _v);',
                f'{indent}}}',
            ], False

        elif t == 'Print':
            return [
                f'{indent}{{',
                f'{indent}    char _v[VAL_LEN], _tvbuf[VAL_LEN];',
                f'{indent}    resolve(_v, {cstr(node["value"])});',
                f'{indent}    printf("%s\\n", _v);',
                f'{indent}    resolve(_tvbuf, {cstr(node["time"])});',
                f'{indent}    int _tv = safe_atoi(_tvbuf);',
                f'{indent}    if (_tv > 0) sleep((unsigned int)_tv);',
                f'{indent}}}',
            ], False

        elif t == 'Input':
            return [
                f'{indent}{{',
                f'{indent}    char _prompt[VAL_LEN], _k[KEY_LEN], _line[VAL_LEN], _suffix[VAL_LEN];',
                f'{indent}    resolve(_prompt, {cstr(node["prompt"])});',
                f'{indent}    if (!box_get(_suffix, "prm")) strcpy(_suffix, "\\n:> ");',
                f'{indent}    printf("%s%s", _prompt, _suffix);',
                f'{indent}    fflush(stdout);',
                f'{indent}    if (fgets(_line, sizeof(_line), stdin) == NULL) _line[0] = \'\\0\';',
                f'{indent}    _line[strcspn(_line, "\\r\\n")] = \'\\0\';',
                f'{indent}    resolve(_k, {cstr(node["target"])});',
                f'{indent}    box_set(_k, _line);',
                f'{indent}}}',
            ], False

        elif t == 'Math':
            return [
                f'{indent}{{',
                f'{indent}    char _k[KEY_LEN], _v[VAL_LEN];',
                f'{indent}    resolve(_k, {cstr(node["target"])});',
                f'{indent}    snprintf(_v, sizeof(_v), "%d", math_op({cstr(node["left"])}, {cstr(node["right"])}, {cstr(node["op"])}));',
                f'{indent}    box_set(_k, _v);',
                f'{indent}}}',
            ], False

        elif t == 'Test':
            return [
                f'{indent}{{',
                f'{indent}    char _k[KEY_LEN], _v[VAL_LEN];',
                f'{indent}    resolve(_k, {cstr(node["target"])});',
                f'{indent}    if (test_op({cstr(node["left"])}, {cstr(node["right"])}, {cstr(node["op"])})) {{',
                f'{indent}        resolve(_v, {cstr(node["true_val"])});',
                f'{indent}    }} else {{',
                f'{indent}        resolve(_v, {cstr(node["false_val"])});',
                f'{indent}    }}',
                f'{indent}    box_set(_k, _v);',
                f'{indent}}}',
            ], False

        elif t == 'Jump':
            lines = [f'{indent}{{ char _t[VAL_LEN];']
            lines.extend(emit_jump(node, indent + "    "))
            lines.append(f'{indent}}}')
            return lines, True

        elif t == 'JumpIf':
            lines = [
                f'{indent}if (test_op({cstr(node["left"])}, {cstr(node["right"])}, {cstr(node["op"])})) {{',
                f'{indent}    char _t[VAL_LEN];',
            ]
            lines.extend(emit_jump(node, indent + "    "))
            lines.append(f'{indent}}}')
            return lines, False

        elif t == 'If':
            lines = [f'{indent}if (test_op({cstr(node["left"])}, {cstr(node["right"])}, {cstr(node["op"])})) {{']
            body_lines, body_continues = emit_action(node['body'], indent + "    ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f'{indent}    pc++;')
                lines.append(f'{indent}    goto cont;')
            lines.append(f'{indent}}}')
            return lines, False

        elif t == 'Wait':
            return [
                f'{indent}{{',
                f'{indent}    char _v[VAL_LEN];',
                f'{indent}    resolve(_v, {cstr(node["time"])});',
                f'{indent}    double _tv = atof(_v);',
                f'{indent}    if (_tv > 0) {{',
                f'{indent}        struct timespec _ts;',
                f'{indent}        _ts.tv_sec = (time_t)_tv;',
                f'{indent}        _ts.tv_nsec = (long)((_tv - (double)(time_t)_tv) * 1e9);',
                f'{indent}        nanosleep(&_ts, NULL);',
                f'{indent}    }}',
                f'{indent}}}',
            ], False

        elif t == 'Delete':
            return [
                f'{indent}{{',
                f'{indent}    char _k[KEY_LEN];',
                f'{indent}    resolve(_k, {cstr(node["target"])});',
                f'{indent}    box_del(_k);',
                f'{indent}}}',
            ], False

        elif t == 'Mark':
            return [f'{indent}/* mark: {node["name"]} */'], False

        elif t == 'Import':
            return [f'{indent}/* import already merged: {node.get("alias") or node["path"]} */'], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = [f'{indent}{{']
            lines.append(f'{indent}    char _k[KEY_LEN], _v[VAL_LEN];')
            for i, a in enumerate(node['args'], start=1):
                lines.append(f'{indent}    resolve(_v, {cstr(a)});')
                lines.append(f'{indent}    box_set("arg{i}", _v);')
            lines.append(f'{indent}    int _m = mark_get({cstr(target)});')
            lines.append(f'{indent}    if (_m < 0) {{')
            lines.append(f'{indent}        fprintf(stderr, "BoxedLANG (transpiled C) error: call to undefined \'{target}\' - '
                         f'is the module imported and does it define this premark?\\n");')
            lines.append(f'{indent}        exit(1);')
            lines.append(f'{indent}    }}')
            lines.append(f'{indent}    if (call_sp >= MAX_CALL_DEPTH) {{')
            lines.append(f'{indent}        fprintf(stderr, "BoxedLANG (transpiled C) error: call stack overflow\\n");')
            lines.append(f'{indent}        exit(1);')
            lines.append(f'{indent}    }}')
            lines.append(f'{indent}    call_stack[call_sp++] = pc + 1;')
            lines.append(f'{indent}    pc = _m;')
            lines.append(f'{indent}}}')
            lines.append(f'{indent}goto cont;')
            return lines, True

        elif t == 'Return':
            return [
                f'{indent}export_ret_boxes();',
                f'{indent}if (call_sp <= 0) {{',
                f'{indent}    fprintf(stderr, "BoxedLANG (transpiled C) error: \'return\' with no active call\\n");',
                f'{indent}    exit(1);',
                f'{indent}}}',
                f'{indent}pc = call_stack[--call_sp];',
                f'{indent}goto cont;',
            ], True

        elif t == 'Clear':
            return [f'{indent}printf("\\x1b[2J\\x1b[H"); fflush(stdout);'], False

        elif t == 'End':
            return [f'{indent}exit(0);'], True

        else:
            return [f'{indent}/* unhandled node type: {t} */'], False

    runtime = f'''/* Auto-generated by transpilebx.py --lang c from {source_name}. Do not edit by hand. */
/* NOTE: fixed-size box table (MAX_BOXES={MAX_BOXES}, VAL_LEN={VAL_LEN}) - fine for
   normal .bx scripts, a real limit for huge ones. No exceptions in C: parse/
   bounds issues are handled defensively (default to 0 / empty) rather than
   via a catch-all error report like the other backends. POSIX only (sleep/
   usleep) - not portable to native Windows without changes. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <ctype.h>
#include <time.h>

#define MAX_BOXES {MAX_BOXES}
#define KEY_LEN {KEY_LEN}
#define VAL_LEN {VAL_LEN}
#define MAX_CALL_DEPTH 256

static char box_keys[MAX_BOXES][KEY_LEN];
static char box_vals[MAX_BOXES][VAL_LEN];
static int box_count = 0;
static int call_stack[MAX_CALL_DEPTH];
static int call_sp = 0;

static int box_find(const char *key) {{
    for (int i = 0; i < box_count; i++) {{
        if (strcmp(box_keys[i], key) == 0) return i;
    }}
    return -1;
}}

static void die_too_long(const char *what, size_t needed, size_t limit) {{
    fprintf(stderr,
        "BoxedLANG (transpiled C) error: %s is %zu chars, over the %zu limit "
        "(raise KEY_LEN/VAL_LEN at the top of this generated file and recompile "
        "rather than silently truncating).\\n",
        what, needed, limit - 1);
    exit(1);
}}

static void box_set(const char *key, const char *val) {{
    if (strlen(key) >= KEY_LEN) die_too_long("a box key", strlen(key), KEY_LEN);
    if (strlen(val) >= VAL_LEN) die_too_long("a box value", strlen(val), VAL_LEN);
    int i = box_find(key);
    if (i < 0) {{
        if (box_count >= MAX_BOXES) {{
            fprintf(stderr, "BoxedLANG (transpiled C) error: too many boxes (max %d)\\n", MAX_BOXES);
            exit(1);
        }}
        i = box_count++;
        strcpy(box_keys[i], key);
    }}
    strcpy(box_vals[i], val);
}}

/* Returns 1 and copies into out if found, 0 otherwise. */
static int box_get(char *out, const char *key) {{
    int i = box_find(key);
    if (i < 0) {{ out[0] = '\\0'; return 0; }}
    strcpy(out, box_vals[i]);
    return 1;
}}

static void box_del(const char *key) {{
    int i = box_find(key);
    if (i < 0) return;
    for (int j = i; j < box_count - 1; j++) {{
        strcpy(box_keys[j], box_keys[j + 1]);
        strcpy(box_vals[j], box_vals[j + 1]);
    }}
    box_count--;
}}

/* On return, any box named ret-X gets exported as a plain box X, so a
   callee can hand a value back to its caller by convention. Snapshot
   the count first since box_set() below can append new entries. */
static void export_ret_boxes(void) {{
    int original_count = box_count;
    for (int i = 0; i < original_count; i++) {{
        if (strncmp(box_keys[i], "ret-", 4) == 0 && strlen(box_keys[i]) > 4) {{
            box_set(box_keys[i] + 4, box_vals[i]);
        }}
    }}
}}

/* In-place literal substring replace (find is never itself modified).
   Crashes with a clear message rather than silently truncating if the
   result would overflow bufsz - raise VAL_LEN and recompile instead. */
static void str_replace_all(char *buf, size_t bufsz, const char *find, const char *repl) {{
    char tmp[VAL_LEN];
    size_t fl = strlen(find);
    if (fl == 0) return;
    char *src = buf;
    char *dst = tmp;
    char *limit = tmp + bufsz - 1;
    while (*src) {{
        if (strncmp(src, find, fl) == 0) {{
            size_t rl = strlen(repl);
            if (dst + rl > limit) die_too_long("a resolved value", (size_t)(dst - tmp) + rl, bufsz);
            memcpy(dst, repl, rl);
            dst += rl; src += fl;
        }} else {{
            if (dst + 1 > limit) die_too_long("a resolved value", (size_t)(dst - tmp) + 1, bufsz);
            *dst++ = *src++;
        }}
    }}
    *dst = '\\0';
    strcpy(buf, tmp);
}}

static void resolve(char *out, const char *val) {{
    if (strlen(val) >= VAL_LEN) die_too_long("a value being resolved", strlen(val), VAL_LEN);
    strcpy(out, val);

    for (int pass = 0; pass < 2; pass++) {{
        /* sort box indices by key length descending (simple insertion sort) */
        int order[MAX_BOXES];
        for (int i = 0; i < box_count; i++) order[i] = i;
        for (int i = 1; i < box_count; i++) {{
            int cur = order[i], j = i - 1;
            while (j >= 0 && strlen(box_keys[order[j]]) < strlen(box_keys[cur])) {{
                order[j + 1] = order[j]; j--;
            }}
            order[j + 1] = cur;
        }}
        for (int oi = 0; oi < box_count; oi++) {{
            int i = order[oi];
            char pat[KEY_LEN + 1];
            snprintf(pat, sizeof(pat), "$%s", box_keys[i]);
            str_replace_all(out, VAL_LEN, pat, box_vals[i]);
        }}
    }}

    /* \\/ escapes the character right after it (shields a literal ':'
       through the blanket strip below). */
    {{
        char tmp[VAL_LEN];
        char *src = out, *dst = tmp;
        size_t remaining = sizeof(tmp) - 1;
        while (*src && remaining > 0) {{
            if (src[0] == '\\\\' && src[1] == '/' && src[2] != '\\0') {{
                char c = src[2];
                *dst++ = (c == ':') ? '\\x01' : c;
                remaining--;
                src += 3;
            }} else {{
                *dst++ = *src++;
                remaining--;
            }}
        }}
        *dst = '\\0';
        strncpy(out, tmp, VAL_LEN - 1);
        out[VAL_LEN - 1] = '\\0';
    }}
    {{
        char tmp[VAL_LEN];
        char *src = out, *dst = tmp;
        while (*src) {{
            if (*src == ':') {{ src++; continue; }}
            if (*src == '\\x01') {{ *dst++ = ':'; src++; continue; }}
            *dst++ = *src++;
        }}
        *dst = '\\0';
        strncpy(out, tmp, VAL_LEN - 1);
        out[VAL_LEN - 1] = '\\0';
    }}
}}

static int test_op(const char *left_raw, const char *right_raw, const char *op) {{
    char left[VAL_LEN], right[VAL_LEN];
    resolve(left, left_raw);
    resolve(right, right_raw);
    if (strcmp(op, "==") == 0) return strcmp(left, right) == 0;
    if (strcmp(op, "!=") == 0) return strcmp(left, right) != 0;
    char *endl, *endr;
    double l = strtod(left, &endl);
    double r = strtod(right, &endr);
    if (endl == left || endr == right) return 0;
    if (strcmp(op, ">") == 0) return l > r;
    if (strcmp(op, "<") == 0) return l < r;
    if (strcmp(op, ">=") == 0) return l >= r;
    if (strcmp(op, "<=") == 0) return l <= r;
    return 0;
}}

static int safe_atoi(const char *s) {{
    char *end;
    long v = strtol(s, &end, 10);
    if (end == s) return 0;
    return (int)v;
}}

static int is_numeric(const char *s) {{
    if (*s == '-') s++;
    if (*s == '\\0') return 0;
    while (*s) {{ if (!isdigit((unsigned char)*s)) return 0; s++; }}
    return 1;
}}

static int math_op(const char *left_raw, const char *right_raw, const char *op_raw) {{
    char left[VAL_LEN], right[VAL_LEN], op[VAL_LEN];
    resolve(left, left_raw);
    resolve(right, right_raw);
    resolve(op, op_raw);
    int l = is_numeric(left) ? atoi(left) : 0;
    int r = is_numeric(right) ? atoi(right) : 0;
    if (strcmp(op, "+") == 0) return l + r;
    if (strcmp(op, "-") == 0) return l - r;
    if (strcmp(op, "*") == 0 || strcmp(op, "x") == 0) return l * r;
    if (strcmp(op, "/") == 0) return r != 0 ? l / r : 0;
    if (strcmp(op, "%") == 0) return r != 0 ? l % r : 0;
    return 0;
}}

static int mark_get(const char *name) {{
'''
    mark_lookup_lines = []
    for name, idx in marks.items():
        mark_lookup_lines.append(f'    if (strcmp(name, {cstr(name)}) == 0) return {idx};')
    runtime += "\n".join(mark_lookup_lines)
    runtime += '''
    return -1;
}

int main(void) {
    int pc = 0;
'''
    runtime += f'    const int END = {len(ast_tree)};\n'
    runtime += '    while (pc < END) {\n        switch (pc) {\n'

    body = []
    for i, node in enumerate(ast_tree):
        body.append(f'        case {i}: {{')
        action_lines, always_continues = emit_action(node, "            ")
        body.extend(action_lines)
        if not always_continues:
            body.append("            pc++;")
            body.append("            goto cont;")
        body.append("        }")
    body.append("        default:")
    body.append("            goto done;")
    body.append("        }")
    body.append("        cont: ;")
    body.append("    }")
    body.append("done:")
    body.append("    return 0;")
    body.append("}")

    return runtime + "\n".join(body) + "\n"


def transpile_go(ast_tree, marks, source_name):
    """
    Standalone Go. Uses native map[string]string for boxes,
    strings.ReplaceAll for literal substitution (no escaping needed),
    and panic/recover for the same style of error report as the other
    backends.
    """

    def gstr(s):
        out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + out + '"'

    def emit_jump(node, indent):
        return [
            f"{indent}_t := resolve({gstr(node['target'])})",
            f"{indent}if {gstr(node['mode'])} == \"m\" {{",
            f"{indent}    if v, ok := marks[_t]; ok {{ pc = v }} else {{ pc = 0 }}",
            f"{indent}}} else {{",
            f"{indent}    n, _ := strconv.Atoi(_t)",
            f"{indent}    pc = n - 1",
            f"{indent}}}",
            f"{indent}continue",
        ]

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            return [f"{indent}boxes[resolve({gstr(node['target'])})] = resolve({gstr(node['value'])})"], False

        elif t == 'Print':
            return [
                f"{indent}fmt.Println(resolve({gstr(node['value'])}))",
                f"{indent}_tv, _ := strconv.Atoi(strings.TrimSpace(resolve({gstr(node['time'])})))",
                f"{indent}if _tv > 0 {{ time.Sleep(time.Duration(_tv) * time.Second) }}",
            ], False

        elif t == 'Input':
            return [
                f"{indent}_suffix := \"\\n:> \"",
                f"{indent}if v, ok := boxes[\"prm\"]; ok {{ _suffix = v }}",
                f"{indent}fmt.Print(resolve({gstr(node['prompt'])}) + _suffix)",
                f"{indent}_line, _ := stdinReader.ReadString('\\n')",
                f"{indent}_line = strings.TrimRight(_line, \"\\r\\n\")",
                f"{indent}boxes[resolve({gstr(node['target'])})] = _line",
            ], False

        elif t == 'Math':
            return [
                f"{indent}boxes[resolve({gstr(node['target'])})] = "
                f"strconv.Itoa(mathOp({gstr(node['left'])}, {gstr(node['right'])}, {gstr(node['op'])}))"
            ], False

        elif t == 'Test':
            return [
                f"{indent}if testOp({gstr(node['left'])}, {gstr(node['right'])}, {gstr(node['op'])}) {{",
                f"{indent}    boxes[resolve({gstr(node['target'])})] = resolve({gstr(node['true_val'])})",
                f"{indent}}} else {{",
                f"{indent}    boxes[resolve({gstr(node['target'])})] = resolve({gstr(node['false_val'])})",
                f"{indent}}}",
            ], False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            lines = [f"{indent}if testOp({gstr(node['left'])}, {gstr(node['right'])}, {gstr(node['op'])}) {{"]
            lines.extend(emit_jump(node, indent + "    "))
            lines.append(f"{indent}}}")
            return lines, False

        elif t == 'If':
            lines = [f"{indent}if testOp({gstr(node['left'])}, {gstr(node['right'])}, {gstr(node['op'])}) {{"]
            body_lines, body_continues = emit_action(node['body'], indent + "    ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}    pc++")
                lines.append(f"{indent}    continue")
            lines.append(f"{indent}}}")
            return lines, False

        elif t == 'Wait':
            return [
                f"{indent}_tv, _ := strconv.ParseFloat(resolve({gstr(node['time'])}), 64)",
                f"{indent}if _tv > 0 {{ time.Sleep(time.Duration(_tv * float64(time.Second))) }}",
            ], False

        elif t == 'Delete':
            return [f"{indent}delete(boxes, resolve({gstr(node['target'])}))"], False

        elif t == 'Mark':
            return [f"{indent}_ = 0 // mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}_ = 0 // import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                lines.append(f"{indent}boxes[\"arg{i}\"] = resolve({gstr(a)})")
            lines.append(f"{indent}_m, _ok := marks[{gstr(target)}]")
            lines.append(f"{indent}if !_ok {{ panic(\"call to undefined '{target}' - is the module imported and does it define this premark?\") }}")
            lines.append(f"{indent}callStack = append(callStack, pc+1)")
            lines.append(f"{indent}pc = _m")
            lines.append(f"{indent}continue")
            return lines, True

        elif t == 'Return':
            return [
                f"{indent}for k, v := range boxes {{",
                f'{indent}    if strings.HasPrefix(k, "ret-") && len(k) > 4 {{ boxes[k[4:]] = v }}',
                f"{indent}}}",
                f"{indent}if len(callStack) == 0 {{ panic(\"'return' with no active call\") }}",
                f"{indent}pc = callStack[len(callStack)-1]",
                f"{indent}callStack = callStack[:len(callStack)-1]",
                f"{indent}continue",
            ], True

        elif t == 'Clear':
            return [f"{indent}fmt.Print(\"\\x1b[2J\\x1b[H\")"], False

        elif t == 'End':
            return [f"{indent}os.Exit(0)"], True

        else:
            return [f"{indent}_ = 0 // unhandled node type: {t}"], False

    marks_lines = []
    for name, idx in marks.items():
        marks_lines.append(f"    {gstr(name)}: {idx},")

    header = [
        f"// Auto-generated by transpilebx.py --lang go from {source_name}. Do not edit by hand.",
        "// NOTE: non-numeric say/wait durations default to 0 rather than erroring",
        "// (a deliberate simplification).",
        "package main",
        "",
        "import (",
        '    "bufio"',
        '    "fmt"',
        '    "os"',
        '    "sort"',
        '    "strconv"',
        '    "strings"',
        '    "time"',
        ")",
        "",
        "var boxes = map[string]string{}",
        "var marks = map[string]int{",
    ] + marks_lines + [
        "}",
        "var pc = 0",
        "var callStack []int",
        "var stdinReader = bufio.NewReader(os.Stdin)",
        "",
        "func resolve(val string) string {",
        "    for i := 0; i < 2; i++ {",
        "        keys := make([]string, 0, len(boxes))",
        "        for k := range boxes {",
        "            keys = append(keys, k)",
        "        }",
        "        sort.Slice(keys, func(a, b int) bool { return len(keys[a]) > len(keys[b]) })",
        "        for _, k := range keys {",
        "            val = strings.ReplaceAll(val, \"$\"+k, boxes[k])",
        "        }",
        "    }",
        "    // \\\\/ escapes the character right after it (shields a literal ':'",
        "    // through the blanket strip below). Index is advanced explicitly",
        "    // (no implicit for-loop increment) so the 1-vs-3-rune skip per",
        "    // branch stays unambiguous.",
        "    var b strings.Builder",
        "    r := []rune(val)",
        "    i := 0",
        "    for i < len(r) {",
        "        if r[i] == '\\\\' && i+2 < len(r) && r[i+1] == '/' {",
        "            c := r[i+2]",
        "            if c == ':' {",
        "                b.WriteRune('\\x00')",
        "            } else {",
        "                b.WriteRune(c)",
        "            }",
        "            i += 3",
        "        } else {",
        "            b.WriteRune(r[i])",
        "            i++",
        "        }",
        "    }",
        "    val = b.String()",
        "    val = strings.ReplaceAll(val, \":\", \"\")",
        "    val = strings.ReplaceAll(val, \"\\x00\", \":\")",
        "    return val",
        "}",
        "",
        "func testOp(leftRaw, rightRaw, op string) bool {",
        "    left := resolve(leftRaw)",
        "    right := resolve(rightRaw)",
        "    switch op {",
        "    case \"==\":",
        "        return left == right",
        "    case \"!=\":",
        "        return left != right",
        "    }",
        "    l, errL := strconv.ParseFloat(left, 64)",
        "    r, errR := strconv.ParseFloat(right, 64)",
        "    if errL != nil || errR != nil {",
        "        return false",
        "    }",
        "    switch op {",
        "    case \">\":",
        "        return l > r",
        "    case \"<\":",
        "        return l < r",
        "    case \">=\":",
        "        return l >= r",
        "    case \"<=\":",
        "        return l <= r",
        "    }",
        "    return false",
        "}",
        "",
        "func isNumeric(s string) bool {",
        "    t := strings.TrimPrefix(s, \"-\")",
        "    if t == \"\" {",
        "        return false",
        "    }",
        "    for _, c := range t {",
        "        if c < '0' || c > '9' {",
        "            return false",
        "        }",
        "    }",
        "    return true",
        "}",
        "",
        "func mathOp(leftRaw, rightRaw, opRaw string) int {",
        "    lv := resolve(leftRaw)",
        "    rv := resolve(rightRaw)",
        "    op := resolve(opRaw)",
        "    l := 0",
        "    if isNumeric(lv) { l, _ = strconv.Atoi(lv) }",
        "    r := 0",
        "    if isNumeric(rv) { r, _ = strconv.Atoi(rv) }",
        "    switch op {",
        "    case \"+\":",
        "        return l + r",
        "    case \"-\":",
        "        return l - r",
        "    case \"*\", \"x\":",
        "        return l * r",
        "    case \"/\":",
        "        if r != 0 { return l / r }",
        "        return 0",
        "    case \"%\":",
        "        if r != 0 { return l % r }",
        "        return 0",
        "    }",
        "    return 0",
        "}",
        "",
        "func run() {",
        f"    const END = {len(ast_tree)}",
        "    for pc < END {",
        "        switch pc {",
    ]

    body = []
    for i, node in enumerate(ast_tree):
        body.append(f"        case {i}:")
        action_lines, always_continues = emit_action(node, "            ")
        body.extend(action_lines)
        if not always_continues:
            body.append("            pc++")
            body.append("            continue")
    body.append("        default:")
    body.append("            return")
    body.append("        }")
    body.append("    }")
    body.append("}")

    footer = [
        "func main() {",
        "    defer func() {",
        "        if r := recover(); r != nil {",
        "            bar := strings.Repeat(\"=\", 60)",
        "            fmt.Fprintln(os.Stderr, \"\\n\"+bar)",
        "            fmt.Fprintf(os.Stderr, \"BoxedLANG (transpiled) runtime error at pc=%d\\n\", pc)",
        "            fmt.Fprintf(os.Stderr, \"  panic: %v\\n\", r)",
        "            fmt.Fprintf(os.Stderr, \"  boxes : %v\\n\", boxes)",
        "            fmt.Fprintf(os.Stderr, \"  marks : %v\\n\", marks)",
        "            fmt.Fprintln(os.Stderr, bar)",
        "            os.Exit(1)",
        "        }",
        "    }()",
        "    run()",
        "}",
    ]

    return "\n".join(header + body + footer) + "\n"


def transpile_rust(ast_tree, marks, source_name):
    """
    Standalone Rust (2021 edition, no external crates). Boxes live in a
    RefCell<HashMap<String,String>> and pc in a Cell<i64> so the
    catch_unwind closure below can mutate them through shared refs
    without fighting the borrow checker. Every helper resolves values
    into owned Strings *before* taking any mutable borrow, to avoid
    overlapping-borrow panics in the generated code.

    NOTE: I could not compile-test this backend directly (no rustc in
    my sandbox) - if `cargo build`/`rustc` reports an error, paste it
    back and I'll fix it fast.
    """

    def rstr(s):
        out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + out + '"'

    bapi_functions = []  # BAPI disabled for now (WIP) - stays empty, kept only so nothing below NameErrors

    def emit_jump(node, indent):
        return [
            f"{indent}let _t = resolve(&boxes.borrow(), {rstr(node['target'])});",
            f"{indent}if {rstr(node['mode'])} == \"m\" {{",
            f"{indent}    pc.set(*marks.get(&_t).unwrap_or(&0));",
            f"{indent}}} else {{",
            f"{indent}    pc.set(_t.parse::<i64>().unwrap_or(1) - 1);",
            f"{indent}}}",
            f"{indent}continue;",
        ]

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            return [
                f"{indent}let _k = resolve(&boxes.borrow(), {rstr(node['target'])});",
                f"{indent}let _v = resolve(&boxes.borrow(), {rstr(node['value'])});",
                f"{indent}boxes.borrow_mut().insert(_k, _v);",
            ], False

        elif t == 'Print':
            return [
                f"{indent}let _v = resolve(&boxes.borrow(), {rstr(node['value'])});",
                f"{indent}println!(\"{{}}\", _v);",
                f"{indent}let _tv_s = resolve(&boxes.borrow(), {rstr(node['time'])});",
                f"{indent}let _tv: i64 = _tv_s.trim().parse().unwrap_or(0);",
                f"{indent}if _tv > 0 {{ std::thread::sleep(std::time::Duration::from_secs(_tv as u64)); }}",
            ], False

        elif t == 'Input':
            return [
                f"{indent}let _suffix = boxes.borrow().get(\"prm\").cloned().unwrap_or_else(|| \"\\n:> \".to_string());",
                f"{indent}let _prompt = resolve(&boxes.borrow(), {rstr(node['prompt'])});",
                f"{indent}print!(\"{{}}{{}}\", _prompt, _suffix);",
                f"{indent}use std::io::Write;",
                f"{indent}std::io::stdout().flush().ok();",
                f"{indent}let mut _line = String::new();",
                f"{indent}std::io::stdin().read_line(&mut _line).ok();",
                f"{indent}let _line = _line.trim_end_matches(['\\n', '\\r']).to_string();",
                f"{indent}let _k = resolve(&boxes.borrow(), {rstr(node['target'])});",
                f"{indent}boxes.borrow_mut().insert(_k, _line);",
            ], False

        elif t == 'Math':
            return [
                f"{indent}let _k = resolve(&boxes.borrow(), {rstr(node['target'])});",
                f"{indent}let _v = math_op(&boxes.borrow(), {rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])}).to_string();",
                f"{indent}boxes.borrow_mut().insert(_k, _v);",
            ], False

        elif t == 'Test':
            return [
                f"{indent}let _passed = test_op(&boxes.borrow(), {rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])});",
                f"{indent}let _k = resolve(&boxes.borrow(), {rstr(node['target'])});",
                f"{indent}let _v = if _passed {{ resolve(&boxes.borrow(), {rstr(node['true_val'])}) }} else {{ resolve(&boxes.borrow(), {rstr(node['false_val'])}) }};",
                f"{indent}boxes.borrow_mut().insert(_k, _v);",
            ], False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            lines = [f"{indent}if test_op(&boxes.borrow(), {rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])}) {{"]
            lines.extend(emit_jump(node, indent + "    "))
            lines.append(f"{indent}}}")
            return lines, False

        elif t == 'If':
            lines = [f"{indent}if test_op(&boxes.borrow(), {rstr(node['left'])}, {rstr(node['right'])}, {rstr(node['op'])}) {{"]
            body_lines, body_continues = emit_action(node['body'], indent + "    ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}    pc.set(pc.get() + 1);")
                lines.append(f"{indent}    continue;")
            lines.append(f"{indent}}}")
            return lines, False

        elif t == 'Wait':
            return [
                f"{indent}let _v = resolve(&boxes.borrow(), {rstr(node['time'])});",
                f"{indent}let _tv: f64 = _v.parse().unwrap_or(0.0);",
                f"{indent}if _tv > 0.0 {{ std::thread::sleep(std::time::Duration::from_secs_f64(_tv)); }}",
            ], False

        elif t == 'Delete':
            return [
                f"{indent}let _k = resolve(&boxes.borrow(), {rstr(node['target'])});",
                f"{indent}boxes.borrow_mut().remove(&_k);",
            ], False

        elif t == 'Mark':
            return [f"{indent}// mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}// import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                lines.append(f"{indent}let _argv{i} = resolve(&boxes.borrow(), {rstr(a)});")
                lines.append(f"{indent}boxes.borrow_mut().insert(\"arg{i}\".to_string(), _argv{i});")
            lines.append(
                f"{indent}let _m = *marks.get({rstr(target)}).unwrap_or_else(|| "
                f"panic!(\"call to undefined '{target}' - is the module imported and does it define this premark?\"));"
            )
            lines.append(f"{indent}call_stack.borrow_mut().push(pc.get() + 1);")
            lines.append(f"{indent}pc.set(_m);")
            lines.append(f"{indent}continue;")
            return lines, True

        elif t == 'Return':
            return [
                f"{indent}let _ret_pairs: Vec<(String, String)> = boxes.borrow().iter()",
                f'{indent}    .filter(|(k, _)| k.starts_with("ret-") && k.len() > 4)',
                f"{indent}    .map(|(k, v)| (k[4..].to_string(), v.clone()))",
                f"{indent}    .collect();",
                f"{indent}for (k, v) in _ret_pairs {{ boxes.borrow_mut().insert(k, v); }}",
                f"{indent}match call_stack.borrow_mut().pop() {{",
                f"{indent}    Some(v) => pc.set(v),",
                f"{indent}    None => panic!(\"'return' with no active call\"),",
                f"{indent}}}",
                f"{indent}continue;",
            ], True

        # BAPI disabled for now (WIP), see note above.
        # elif t == 'BapiCall':
        #     unique_name, spliced_src, decl_params = _splice_bapi_rust(node['api'], node['func'])
        #     if spliced_src not in bapi_functions:
        #         bapi_functions.append(spliced_src)
        #     lines = []
        #     arg_vars = []
        #     for i, a in enumerate(node['args'], start=1):
        #         var = f"_bapi_arg{i}"
        #         lines.append(f"{indent}let _bapi_raw{i} = resolve(&boxes.borrow(), {rstr(a)});")
        #         lines.append(f"{indent}let {var}: i32 = _bapi_raw{i}.parse().unwrap_or(0);")
        #         arg_vars.append(var)
        #     lines.append(f"{indent}let _bapi_result = {unique_name}({', '.join(arg_vars)});")
        #     lines.append(f'{indent}boxes.borrow_mut().insert("return".to_string(), _bapi_result.to_string());')
        #     return lines, False

        elif t == 'Clear':
            return [
                f"{indent}print!(\"\\x1b[2J\\x1b[H\");",
                f"{indent}use std::io::Write as _;",
                f"{indent}std::io::stdout().flush().ok();",
            ], False

        elif t == 'End':
            return [f"{indent}std::process::exit(0);"], True

        else:
            return [f"{indent}// unhandled node type: {t}"], False

    marks_lines = []
    for name, idx in marks.items():
        marks_lines.append(f"    m.insert({rstr(name)}.to_string(), {idx}i64);")

    header = [
        f"// Auto-generated by transpilebx.py --lang rust from {source_name}. Do not edit by hand.",
        "// NOTE: non-numeric say/wait durations default to 0 rather than erroring",
        "// (a deliberate simplification). Not compile-tested in a live sandbox -",
        "// paste back any rustc/cargo error and it'll get fixed quickly.",
        "use std::cell::{Cell, RefCell};",
        "use std::collections::HashMap;",
        "",
        "fn resolve(boxes: &HashMap<String, String>, val: &str) -> String {",
        "    let mut val = val.to_string();",
        "    for _ in 0..2 {",
        "        let mut keys: Vec<&String> = boxes.keys().collect();",
        "        keys.sort_by(|a, b| b.len().cmp(&a.len()));",
        "        for k in keys {",
        "            let pat = format!(\"${}\", k);",
        "            val = val.replace(&pat, &boxes[k]);",
        "        }",
        "    }",
        "    // \\/ escapes the character right after it (shields a literal ':'",
        "    // through the blanket strip below).",
        "    let chars: Vec<char> = val.chars().collect();",
        "    let mut out = String::new();",
        "    let mut i = 0;",
        "    while i < chars.len() {",
        "        if chars[i] == '\\\\' && i + 1 < chars.len() && chars[i + 1] == '/' && i + 2 < chars.len() {",
        "            let c = chars[i + 2];",
        "            out.push(if c == ':' { '\\u{0}' } else { c });",
        "            i += 3;",
        "        } else {",
        "            out.push(chars[i]);",
        "            i += 1;",
        "        }",
        "    }",
        "    let out: String = out.chars().filter(|&c| c != ':').collect();",
        "    out.replace('\\u{0}', \":\")",
        "}",
        "",
        "fn test_op(boxes: &HashMap<String, String>, left: &str, right: &str, op: &str) -> bool {",
        "    let left = resolve(boxes, left);",
        "    let right = resolve(boxes, right);",
        "    match op {",
        "        \"==\" => left == right,",
        "        \"!=\" => left != right,",
        "        _ => {",
        "            let l: Result<f64, _> = left.parse();",
        "            let r: Result<f64, _> = right.parse();",
        "            if let (Ok(l), Ok(r)) = (l, r) {",
        "                match op {",
        "                    \">\" => l > r,",
        "                    \"<\" => l < r,",
        "                    \">=\" => l >= r,",
        "                    \"<=\" => l <= r,",
        "                    _ => false,",
        "                }",
        "            } else {",
        "                false",
        "            }",
        "        }",
        "    }",
        "}",
        "",
        "fn is_numeric(s: &str) -> bool {",
        "    let t = s.strip_prefix('-').unwrap_or(s);",
        "    !t.is_empty() && t.chars().all(|c| c.is_ascii_digit())",
        "}",
        "",
        "fn math_op(boxes: &HashMap<String, String>, left: &str, right: &str, op: &str) -> i64 {",
        "    let lv = resolve(boxes, left);",
        "    let rv = resolve(boxes, right);",
        "    let op = resolve(boxes, op);",
        "    let l: i64 = if is_numeric(&lv) { lv.parse().unwrap_or(0) } else { 0 };",
        "    let r: i64 = if is_numeric(&rv) { rv.parse().unwrap_or(0) } else { 0 };",
        "    match op.as_str() {",
        "        \"+\" => l + r,",
        "        \"-\" => l - r,",
        "        \"*\" | \"x\" => l * r,",
        "        \"/\" => if r != 0 { l / r } else { 0 },",
        "        \"%\" => if r != 0 { l % r } else { 0 },",
        "        _ => 0,",
        "    }",
        "}",
        "",
        "fn main() {",
        "    let boxes: RefCell<HashMap<String, String>> = RefCell::new(HashMap::new());",
        "    let marks: HashMap<String, i64> = {",
        "        let mut m = HashMap::new();",
    ] + marks_lines + [
        "        m",
        "    };",
        "    let pc = Cell::new(0i64);",
        "    let call_stack: RefCell<Vec<i64>> = RefCell::new(Vec::new());",
        f"    const END: i64 = {len(ast_tree)};",
        "",
        "    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {",
        "        loop {",
        "            let cur = pc.get();",
        "            if cur < 0 || cur >= END { break; }",
        "            match cur {",
    ]

    body = []
    for i, node in enumerate(ast_tree):
        body.append(f"                {i} => {{")
        action_lines, always_continues = emit_action(node, "                    ")
        body.extend(action_lines)
        if not always_continues:
            body.append("                    pc.set(pc.get() + 1);")
            body.append("                    continue;")
        body.append("                }")
    body.append("                _ => break,")
    body.append("            }")
    body.append("        }")
    body.append("    }));")

    footer = [
        "    if let Err(e) = result {",
        "        let msg = if let Some(s) = e.downcast_ref::<&str>() {",
        "            s.to_string()",
        "        } else if let Some(s) = e.downcast_ref::<String>() {",
        "            s.clone()",
        "        } else {",
        "            \"unknown panic\".to_string()",
        "        };",
        "        let bar = \"=\".repeat(60);",
        "        eprintln!(\"\\n{}\", bar);",
        "        eprintln!(\"BoxedLANG (transpiled) runtime error at pc={}\", pc.get());",
        "        eprintln!(\"  panic: {}\", msg);",
        "        eprintln!(\"  boxes : {:?}\", boxes.borrow());",
        "        eprintln!(\"  marks : {:?}\", marks);",
        "        eprintln!(\"{}\", bar);",
        "        std::process::exit(1);",
        "    }",
        "}",
    ]

    # BAPI disabled for now (WIP) - bapi_functions stays empty, so this
    # block never actually did anything anyway; commented for clarity.
    # if bapi_functions:
    #     insert_at = header.index("fn main() {")
    #     bapi_lines = []
    #     for fn_src in bapi_functions:
    #         bapi_lines.append("")
    #         bapi_lines.extend(fn_src.splitlines())
    #     for offset, line in enumerate(bapi_lines):
    #         header.insert(insert_at + offset, line)

    return "\n".join(header + body + footer) + "\n"


_BLANK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
    'viewBox="0 0 100 100">\n'
    '  <rect x="4" y="4" width="92" height="92" fill="#4C97FF" '
    'stroke="#3373CC" stroke-width="4"/>\n'
    '</svg>\n'
)

_TW_CONFIG_TEXT = (
    'Configuration for https://turbowarp.org/\n'
    "You can move, resize, and minimize this comment, but don't edit it by hand. "
    'This comment can be deleted to remove the stored settings.\n'
    '{"framerate":60,"runtimeOptions":{"maxClones":Infinity,"miscLimits":false,'
    '"fencing":false},"interpolation":true,"hq":true} // _twconfig_'
)


def transpile_fractch(ast_tree, marks, source_name, tw_config=False):
    """
    Targets the Fractch text format (see docs/syntax.md), NOT .sb3
    directly - packing that is the actual `fractch` CLI's job, same as
    it's designed for. Returns a dict of relative_path -> text/asset
    content representing a whole project folder (a sprite named after
    the source file, plus a minimal Stage), not a single file - the
    caller in main() writes this out as a directory tree.

    IMPORTANT: custom blocks here never use `return v;` (a value) - that
    needs TurboWarp/MistWarp's extended semantics and was causing load
    errors even in MistWarp. Every custom block instead sets a shared
    `_ret` variable and does a bare `return;` (which just means "stop
    this script" and is universally supported, no extension needed).
    Every call site that needs a value calls the block as a plain
    statement first, then reads `_ret` afterward - never inline.

    Same native-variable design as Python/Lua otherwise: box names
    always assigned via a literal target become real Fractch
    variables. NO native dict/map exists in Fractch, so the residual
    store for genuinely computed keys (note-:$name) is two parallel
    lists searched linearly - and the trickiest case in practice (the
    notes/files apps' `$$name` double-lookup) is handled as a
    specifically-recognized pattern rather than a fully general
    recursive substitution engine. Anything falling outside that
    pattern is flagged inline as unsupported rather than silently
    emitting something wrong.

    pc/jump/mark still uses the same dispatch-loop trick as every other
    backend (a `forever` loop switching on a pc variable) since Scratch
    has no goto and jump targets are often runtime-computed. Call/
    Return use an explicit call-stack list for the same reason, rather
    than real nested custom blocks.
    """
    static_names = _collect_static_box_names(ast_tree)
    has_prm = "prm" in static_names

    def fstr(s):
        out = (s.replace("\\", "\\\\").replace('"', '\\"')
                 .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))
        return '"' + out + '"'

    def concat_expr(parts):
        pieces = []
        for kind, val in parts:
            if kind == "text":
                if val:
                    pieces.append(fstr(val))
            else:
                pieces.append(_pyvar(val))
        return " ++ ".join(pieces) if pieces else '""'

    _dyn_double_re = re.compile(r"^\$\$([A-Za-z0-9_#?-]+)$")

    def value_expr(value, temp, indent):
        """
        Returns (setup_lines, final_ref) - final_ref is a plain
        expression (literal / native var / one of the _rN temps) ready
        to drop straight into the surrounding statement. setup_lines
        (already indented) must be emitted immediately before that
        statement, since final_ref may depend on them.
        """
        kind, payload = _tokenize_value(value, static_names)
        if kind == "literal":
            return [], fstr(payload)
        if kind == "parts":
            return [f"{indent}@clean({concat_expr(payload)});", f"{indent}{temp} = _ret;"], temp
        m = _dyn_double_re.match(value)
        if m and m.group(1) in static_names:
            return [f"{indent}@dyn_get({_pyvar(m.group(1))});", f"{indent}{temp} = _ret;"], temp
        return [], f'"/* unsupported dynamic expr, see note in header: {value} */"'

    def assign_box(target, value_ref, indent, temp="_r2"):
        if "$" not in target:
            return [f"{indent}{_pyvar(target)} = {value_ref};"]
        setup, key_ref = value_expr(target, temp, indent)
        lines = list(setup)
        lines.append(f"{indent}@dyn_set({key_ref}, {value_ref});")
        return lines

    def emit_jump(node, indent):
        setup, target_ref = value_expr(node['target'], "_r1", indent)
        lines = list(setup)
        lines.append(f"{indent}_t = {target_ref};")
        if node['mode'] == "m":
            lines.append(f"{indent}@mark_get(_t);")
            lines.append(f"{indent}pc = _ret;")
        else:
            lines.append(f"{indent}pc = round(_t) - 1;")
        return lines

    def emit_test(left, right, op, indent, temp="_r4"):
        """Returns (setup_lines, bool_condition_expr) for `if <cond> {`."""
        setup_l, left_ref = value_expr(left, "_r1", indent)
        setup_r, right_ref = value_expr(right, "_r2", indent)
        setup_o, op_ref = value_expr(op, "_r3", indent)
        lines = setup_l + setup_r + setup_o
        lines.append(f"{indent}@test({left_ref}, {right_ref}, {op_ref});")
        lines.append(f"{indent}{temp} = _ret;")
        return lines, f'{temp} == "true"'

    def emit_action(node, indent):
        t = node['type']

        if t == 'Assign':
            setup, val_ref = value_expr(node['value'], "_r1", indent)
            lines = list(setup)
            lines.extend(assign_box(node['target'], val_ref, indent))
            return lines, False

        elif t == 'Print':
            setup_v, val_ref = value_expr(node['value'], "_r1", indent)
            setup_t, time_ref = value_expr(node['time'], "_r2", indent)
            lines = setup_v + [f"{indent}append(print_output, {val_ref});"] + setup_t
            lines.append(f"{indent}_tv = round({time_ref});")
            lines.append(f"{indent}if _tv > 0 {{ wait _tv secs; }}")
            return lines, False

        elif t == 'Input':
            setup, prompt_ref = value_expr(node['prompt'], "_r1", indent)
            lines = list(setup)
            lines.append(f"{indent}@input_suffix();")
            lines.append(f"{indent}_r2 = _ret;")
            lines.append(f"{indent}append(print_output, {prompt_ref} ++ _r2);")
            lines.append(f"{indent}ask {prompt_ref} ++ _r2;")
            lines.append(f"{indent}_line = sensing.answer();")
            lines.append(f"{indent}append(print_output, _line);")
            lines.extend(assign_box(node['target'], "_line", indent))
            return lines, False

        elif t == 'Math':
            setup_l, left_ref = value_expr(node['left'], "_r1", indent)
            setup_r, right_ref = value_expr(node['right'], "_r2", indent)
            setup_o, op_ref = value_expr(node['op'], "_r3", indent)
            lines = setup_l + setup_r + setup_o
            lines.append(f"{indent}@math({left_ref}, {right_ref}, {op_ref});")
            lines.append(f"{indent}_r5 = (_ret ++ \"\");")
            lines.extend(assign_box(node['target'], "_r5", indent))
            return lines, False

        elif t == 'Test':
            setup, cond = emit_test(node['left'], node['right'], node['op'], indent)
            lines = list(setup)
            lines.append(f"{indent}if {cond} {{")
            setup_true, true_ref = value_expr(node['true_val'], "_r5", indent + "  ")
            lines.extend(setup_true)
            lines.extend(assign_box(node['target'], true_ref, indent + "  "))
            lines.append(f"{indent}}} else {{")
            setup_false, false_ref = value_expr(node['false_val'], "_r5", indent + "  ")
            lines.extend(setup_false)
            lines.extend(assign_box(node['target'], false_ref, indent + "  "))
            lines.append(f"{indent}}}")
            return lines, False

        elif t == 'Jump':
            return emit_jump(node, indent), True

        elif t == 'JumpIf':
            setup, cond = emit_test(node['left'], node['right'], node['op'], indent)
            lines = list(setup)
            lines.append(f"{indent}if {cond} {{")
            lines.extend(emit_jump(node, indent + "  "))
            lines.append(f"{indent}}} else {{")
            lines.append(f"{indent}  pc = pc + 1;")
            lines.append(f"{indent}}}")
            return lines, True

        elif t == 'If':
            setup, cond = emit_test(node['left'], node['right'], node['op'], indent)
            lines = list(setup)
            lines.append(f"{indent}if {cond} {{")
            body_lines, body_continues = emit_action(node['body'], indent + "  ")
            lines.extend(body_lines)
            if not body_continues:
                lines.append(f"{indent}  pc = pc + 1;")
            lines.append(f"{indent}}} else {{")
            lines.append(f"{indent}  pc = pc + 1;")
            lines.append(f"{indent}}}")
            return lines, True

        elif t == 'Wait':
            setup, time_ref = value_expr(node['time'], "_r1", indent)
            return setup + [f"{indent}wait {time_ref} secs;"], False

        elif t == 'Delete':
            if "$" not in node['target']:
                return [f"{indent}{_pyvar(node['target'])} = \"\";"], False
            setup, target_ref = value_expr(node['target'], "_r1", indent)
            return setup + [f"{indent}@dyn_del({target_ref});"], False

        elif t == 'Mark':
            return [f"{indent}// mark: {node['name']}"], False

        elif t == 'Import':
            return [f"{indent}// import already merged: {node.get('alias') or node['path']}"], False

        elif t == 'Call':
            target = f"{node['namespace']}.{node['func']}"
            lines = []
            for i, a in enumerate(node['args'], start=1):
                setup, val_ref = value_expr(a, "_r1", indent)
                lines.extend(setup)
                lines.extend(assign_box(f"arg{i}", val_ref, indent))
            lines.append(f"{indent}@mark_get_checked({fstr(target)});")
            lines.append(f"{indent}_m = _ret;")
            lines.append(f"{indent}append(call_stack, pc + 1);")
            lines.append(f"{indent}pc = _m;")
            return lines, True

        elif t == 'Return':
            lines = []
            for name in sorted(static_names):
                if name.startswith("ret-") and len(name) > 4:
                    target_name = name[4:]
                    src_var = _pyvar(name)
                    if target_name in static_names:
                        lines.append(f"{indent}{_pyvar(target_name)} = {src_var};")
                    lines.append(f"{indent}@dyn_set({fstr(target_name)}, {src_var});")
            lines.append(f"{indent}@export_rets();")
            lines += [
                f"{indent}_n = call_stack.length;",
                f"{indent}if _n == 0 {{",
                f"{indent}  append(print_output, \"'return' with no active call\");",
                f"{indent}  stop all;",
                f"{indent}}} else {{",
                f"{indent}  pc = item(call_stack, _n);",
                f"{indent}  delete(call_stack, _n);",
                f"{indent}}}",
            ]
            return lines, True

        elif t == 'Clear':
            return [f"{indent}clear(print_output);"], False

        elif t == 'End':
            return [f"{indent}return;"], True

        else:
            return [f"{indent}// unhandled node type: {t}"], False

    body = []
    for i, node in enumerate(ast_tree):
        keyword = "if" if i == 0 else "else if"
        body.append(f"    {keyword} pc == {i} {{")
        action_lines, always_continues = emit_action(node, "      ")
        body.extend(action_lines)
        if not always_continues:
            body.append("      pc = pc + 1;")
        body.append(f"    }}")
    body_src = "\n".join(body)

    lines = [
        f"// Auto-generated by transpilebx.py --lang fractch from {source_name}. Do not edit by hand.",
        "// NOT an .sb3 - pack this project folder with the real `fractch` CLI",
        "// (see docs/cli.md), e.g.: fractch pack project.sb3 .",
        "//",
        "// Custom blocks never `return v;` - only bare `return;` (stop this",
        "// script), which needs no extension. Values come back via the shared",
        "// _ret variable instead: call the block as a plain statement, then",
        "// read _ret right after.",
        "//",
        "// Known simplifications vs the interpreter, since Fractch has no dict",
        "// and I have no way to run this through a real Scratch/TurboWarp",
        "// runtime to verify it: box names always assigned via a literal target",
        "// become real variables; a genuinely computed box name (note-:$name)",
        "// lives in a small linear key/value list pair instead; the notes/file",
        "// apps' `$$name` double-lookup is handled as a specifically-recognized",
        "// pattern, not a fully general recursive substitution - anything else",
        "// dynamic gets flagged inline as `/* unsupported dynamic expr */`",
        "// rather than silently emitting something wrong.",
        "",
        f'costume "costume1" file "assets/costume1.svg" center 50,50;',
        "",
        "var pc = 0;",
        "var call_stack = [];",
        "var _ret = \"\";",
        "var print_output = [];",
        "watch list \"print_output\" at 10,10 size 300x200;",
    ]
    for name in sorted(static_names):
        lines.append(f'var {_pyvar(name)} = "";')

    lines += [
        "",
        "def @clean(s) {",
        "  // \\/ escapes the char right after it; unescaped ':' gets",
        "  // stripped. Single pass: shielded chars go straight through,",
        "  // never hitting the bare-':' check below.",
        "  local result = \"\";",
        "  local i = 1;",
        "  local n = length(s);",
        "  while i <= n {",
        "    if s.letter(i) == \"\\\\\" && i + 2 <= n && s.letter(i + 1) == \"/\" {",
        "      result = result ++ s.letter(i + 2);",
        "      i = i + 3;",
        "    } else if s.letter(i) == \":\" {",
        "      i = i + 1;",
        "    } else {",
        "      result = result ++ s.letter(i);",
        "      i = i + 1;",
        "    }",
        "  }",
        "  _ret = result;",
        "  return;",
        "}",
        "",
        "def @is_numeric(s) {",
        "  local n = length(s);",
        "  if n == 0 { _ret = \"false\"; return; }",
        "  local start = 1;",
        "  if s.letter(1) == \"-\" { start = 2; }",
        "  if start > n { _ret = \"false\"; return; }",
        "  local i = start;",
        "  while i <= n {",
        "    if !(s.letter(i) >= \"0\" && s.letter(i) <= \"9\") { _ret = \"false\"; return; }",
        "    i = i + 1;",
        "  }",
        "  _ret = \"true\";",
        "  return;",
        "}",
        "",
        "def @math(l, r, op) {",
        "  local ln = 0;",
        "  local rn = 0;",
        "  @is_numeric(l);",
        "  if _ret == \"true\" { ln = l; }",
        "  @is_numeric(r);",
        "  if _ret == \"true\" { rn = r; }",
        "  if op == \"+\" { _ret = ln + rn; return; }",
        "  if op == \"-\" { _ret = ln - rn; return; }",
        "  if op == \"*\" || op == \"x\" { _ret = ln * rn; return; }",
        "  if op == \"/\" { if rn != 0 { _ret = floor(ln / rn); } else { _ret = 0; } return; }",
        "  if op == \"%\" { if rn != 0 { _ret = ln % rn; } else { _ret = 0; } return; }",
        "  _ret = 0;",
        "  return;",
        "}",
        "",
        "def @test(l, r, op) {",
        "  if op == \"==\" { _ret = (l == r); return; }",
        "  if op == \"!=\" { _ret = (l != r); return; }",
        "  if op == \">\" { _ret = (l > r); return; }",
        "  if op == \"<\" { _ret = (l < r); return; }",
        "  if op == \">=\" { _ret = (l >= r); return; }",
        "  if op == \"<=\" { _ret = (l <= r); return; }",
        "  _ret = \"false\";",
        "  return;",
        "}",
        "",
        "def @input_suffix() {",
    ]
    if has_prm:
        lines.append(f'  if {_pyvar("prm")} != "" {{ _ret = {_pyvar("prm")}; return; }}')
    else:
        lines.append('  @dyn_get("prm");')
        lines.append('  if _ret != "" { return; }')
    lines += [
        '  _ret = "\\n:> ";',
        "  return;",
        "}",
    ]

    mark_lines = ["def @mark_get(name) {"]
    for name, idx in marks.items():
        mark_lines.append(f'  if name == {fstr(name)} {{ _ret = {idx}; return; }}')
    mark_lines += ["  _ret = 0;", "  return;", "}", "",
                   "def @mark_get_checked(name) {"]
    for name, idx in marks.items():
        mark_lines.append(f'  if name == {fstr(name)} {{ _ret = {idx}; return; }}')
    mark_lines += [
        '  say "call to undefined \'" ++ name ++ "\'";',
        "  stop all;",
        "  _ret = 0;",
        "  return;",
        "}",
    ]
    lines += [""] + mark_lines
    lines += [
        "",
        "var dyn_keys = [];",
        "var dyn_vals = [];",
        "",
        "def @dyn_find(key) {",
        "  local n = dyn_keys.length;",
        "  local i = 1;",
        "  while i <= n {",
        "    if item(dyn_keys, i) == key { _ret = i; return; }",
        "    i = i + 1;",
        "  }",
        "  _ret = 0;",
        "  return;",
        "}",
        "",
        "def @dyn_get(key) {",
        "  @dyn_find(key);",
        "  local i = _ret;",
        "  if i == 0 { _ret = \"\"; return; }",
        "  _ret = item(dyn_vals, i);",
        "  return;",
        "}",
        "",
        "def @dyn_set(key, val) {",
        "  @dyn_find(key);",
        "  local i = _ret;",
        "  if i == 0 {",
        "    append(dyn_keys, key);",
        "    append(dyn_vals, val);",
        "  } else {",
        "    replace(dyn_vals, i, val);",
        "  }",
        "}",
        "",
        "def @dyn_del(key) {",
        "  @dyn_find(key);",
        "  local i = _ret;",
        "  if i > 0 {",
        "    delete(dyn_keys, i);",
        "    delete(dyn_vals, i);",
        "  }",
        "}",
        "",
        "// On return, any dynamically-stored box named ret-X gets exported",
        "// as plain box X, so a callee can hand a value back by convention.",
        "def @export_rets() {",
        "  local n = dyn_keys.length;",
        "  local i = 1;",
        "  while i <= n {",
        "    local k = item(dyn_keys, i);",
        "    if length(k) > 4 && k.letter(1) == \"r\" && k.letter(2) == \"e\" && k.letter(3) == \"t\" && k.letter(4) == \"-\" {",
        "      local suffix = \"\";",
        "      local j = 5;",
        "      while j <= length(k) {",
        "        suffix = suffix ++ k.letter(j);",
        "        j = j + 1;",
        "      }",
        "      @dyn_set(suffix, item(dyn_vals, i));",
        "    }",
        "    i = i + 1;",
        "  }",
        "}",
    ]

    lines += [
        "",
        "when flag {",
        "  local _line = \"\";",
        "  local _tv = 0;",
        "  local _t = \"\";",
        "  local _n = 0;",
        "  local _m = 0;",
        "  local _r1 = \"\";",
        "  local _r2 = \"\";",
        "  local _r3 = \"\";",
        "  local _r4 = \"\";",
        "  local _r5 = \"\";",
        "  pc = 0;",
        "  forever {",
    ]
    lines.extend(body)
    lines += [
        "  }",
        "}",
    ]

    fractch_src = "\n".join(lines) + "\n"

    files = {
        f"{source_name}/main.fractch": fractch_src,
        f"{source_name}/assets/costume1.svg": _BLANK_SVG,
        "Stage/assets/backdrop1.svg": _BLANK_SVG,
    }

    stage_lines = [f"// Auto-generated by transpilebx.py --lang fractch from {source_name}."]
    stage_lines.append('costume "backdrop1" file "assets/backdrop1.svg" center 50,50;')
    if tw_config:
        stage_lines.append("")
        stage_lines.append(f'comment {fstr(_TW_CONFIG_TEXT)} at 0,0 size 350x200;')
    files["Stage/main.fractch"] = "\n".join(stage_lines) + "\n"

    return files


# BAPI: disabled for now (WIP, more work needed before re-enabling).
# def _load_bapi_func(api_name, lang_ext, func_name, apis_dir="apis"):
#     """
#     Loads apis/<api_name>/main.<lang_ext>.bapi and returns (params, body)
#     for the named function block, or None if the file or that function
#     isn't found. Block format:
#         funcname(param1:param2:param3)&
#         <raw native code>
#         &
#     """
#     path = os.path.join(apis_dir, api_name, f"main.{lang_ext}.bapi")
#     if not os.path.exists(path):
#         return None
#     lines = open(path, "r", encoding="utf-8").read().splitlines()
#     header_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)&\s*$")
#     i = 0
#     while i < len(lines):
#         m = header_re.match(lines[i].strip())
#         if not m:
#             i += 1
#             continue
#         name, params_str = m.group(1), m.group(2)
#         params = [p.strip() for p in params_str.split(":") if p.strip()]
#         body_lines = []
#         i += 1
#         while i < len(lines) and lines[i].strip() != "&":
#             body_lines.append(lines[i])
#             i += 1
#         if name == func_name:
#             return params, "\n".join(body_lines)
#         i += 1  # skip the closing '&'
#     return None
#
#
# class BapiError(Exception):
#     """Raised at transpile time when a BapiCall can't be resolved."""
#
#
# def _splice_bapi_python(api, func, params):
#     """Loads apis/<api>/main.py.bapi's <func> block and renames/re-signatures
#     it into a unique top-level function. Returns (unique_name, spliced_src)
#     or raises BapiError if no matching .bapi function exists."""
#     loaded = _load_bapi_func(api, "py", func)
#     if loaded is None:
#         raise BapiError(f"no function '{func}' found in apis/{api}/main.py.bapi (or that file doesn't exist)")
#     decl_params, body = loaded
#     if params != decl_params:
#         pass  # positional binding is by call-site order, not name matching - fine either way
#     unique_name = f"bapi_{api}_{func}"
#     new_src, n = re.subn(r"def\s+\w+\s*\([^)]*\)", f"def {unique_name}({', '.join(decl_params)})", body, count=1)
#     if n == 0:
#         indented = "\n".join("    " + l for l in body.splitlines())
#         new_src = f"def {unique_name}({', '.join(decl_params)}):\n{indented}"
#     return unique_name, new_src, decl_params
#
#
# def _splice_bapi_rust(api, func):
#     """Same idea as _splice_bapi_python, but for apis/<api>/main.rs.bapi.
#     Params are typed i32 (matching the reference example, which does
#     integer arithmetic) - the only convention I have to go on so far."""
#     loaded = _load_bapi_func(api, "rs", func)
#     if loaded is None:
#         raise BapiError(f"no function '{func}' found in apis/{api}/main.rs.bapi (or that file doesn't exist)")
#     decl_params, body = loaded
#     unique_name = f"bapi_{api}_{func}"
#     typed = ", ".join(f"{p}: i32" for p in decl_params)
#     new_src, n = re.subn(r"fn\s+\w+\s*\([^)]*\)", f"fn {unique_name}({typed})", body, count=1)
#     if n == 0:
#         new_src = f"fn {unique_name}({typed}) -> i32 {{\n{body}\n}}"
#     return unique_name, new_src, decl_params


BACKENDS = {
    "python": transpile_python,
    "lua": transpile_lua,
    "ruby": transpile_ruby,
    "c": transpile_c,
    "go": transpile_go,
    "rust": transpile_rust,
    "fractch": transpile_fractch,
}

FRACTCH_LANGS = {"fractch"}  # backends that return a folder tree, not a single file's text


EXTENSIONS = {
    "python": "py",
    "lua": "lua",
    "ruby": "rb",
    "c": "c",
    "go": "go",
    "rust": "rs",
    "fractch": "fractch",  # produces a whole project folder, not one file - see FRACTCH_LANGS handling in main()
}


def _prepare_run(lang, path, workdir):
    """Returns (cmd_list, error_message). error_message is None on success."""
    import subprocess

    if lang == "python":
        return ["python3", path], None
    if lang == "lua":
        return ["lua", path], None
    if lang == "ruby":
        return ["ruby", path], None
    if lang == "go":
        return ["go", "run", path], None
    if lang == "c":
        binpath = os.path.join(workdir, "test_bin_c")
        try:
            r = subprocess.run(["gcc", "-std=c99", "-o", binpath, path], capture_output=True, text=True)
        except FileNotFoundError:
            return None, "`gcc` isn't on your PATH - install it and try again"
        if r.returncode != 0:
            return None, f"gcc failed:\n{r.stderr}"
        return [binpath], None
    if lang == "rust":
        # --crate-name avoids rustc choking on the dot in a filename like os.bx
        binpath = os.path.join(workdir, "test_bin_rs")
        try:
            r = subprocess.run(["rustc", "--crate-name", "bx_test", path, "-o", binpath], capture_output=True, text=True)
        except FileNotFoundError:
            return None, "`rustc` isn't on your PATH - install it and try again"
        if r.returncode != 0:
            return None, f"rustc failed:\n{r.stderr}"
        return [binpath], None
    return None, (f"--test doesn't know how to run '{lang}' directly (fractch produces a project "
                   f"folder/.sb3, not a runnable program - test that one in TurboWarp instead)")


def _copy_to_clipboard(text):
    import subprocess
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"],
                ["wl-copy"], ["pbcopy"]):
        try:
            p = subprocess.run(cmd, input=text, text=True, capture_output=True)
            if p.returncode == 0:
                print(f"\n(full combined output copied to clipboard via {cmd[0]})")
                return
        except FileNotFoundError:
            continue
    print("\n(no clipboard tool found - tried xclip/xsel/wl-copy/pbcopy - output wasn't copied, "
          "but it's all printed above)")


def _run_test_suite(ast_tree, marks, source_base, langs):
    """
    Transpiles+runs each requested language in turn so you can interact
    with each one exactly like running it manually. After each exits,
    reports how it ended (clean/`end`, Ctrl+C, or an error - including
    whatever debug/boxes-and-marks dump a backend already prints on
    error, since that's just part of the captured output). Combined
    output across every language gets copied to the clipboard at the
    end if a clipboard tool is available.
    """
    import subprocess
    import tempfile
    import shutil

    combined = []
    workdir = tempfile.mkdtemp(prefix="bx-test-")
    try:
        for lang in langs:
            print(f"\n{'=' * 60}\n>>> Testing {lang}\n{'=' * 60}")
            combined.append(f"\n===== {lang} =====\n")

            if lang in FRACTCH_LANGS:
                msg = f"(skipping {lang} - not directly runnable; test the .sb3 in TurboWarp instead)"
                print(msg)
                combined.append(msg + "\n")
                continue

            backend = BACKENDS[lang]
            # BAPI disabled for now - was: try/except BapiError around this call.
            output_code = backend(ast_tree, marks, source_base)
            src_path = os.path.join(workdir, f"test.{EXTENSIONS[lang]}")
            file.Path(src_path).write_text(output_code, encoding="utf-8")

            cmd, err = _prepare_run(lang, src_path, workdir)
            if err:
                print(f"could not run {lang}: {err}")
                combined.append(f"could not run: {err}\n")
                continue

            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=None, bufsize=1, universal_newlines=True)
            except FileNotFoundError:
                msg = f"could not run {lang}: `{cmd[0]}` isn't on your PATH - install it and try again"
                print(msg)
                combined.append(msg + "\n")
                continue

            captured = []
            try:
                for line in proc.stdout:
                    print(line, end="")
                    captured.append(line)
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                print(f"\n[harness] you interrupted the {lang} run with Ctrl+C")
                combined.append("".join(captured))
                combined.append(f"\n[harness] you (the tester) interrupted this run with Ctrl+C\n")
                continue

            combined.append("".join(captured))
            code = proc.returncode
            if code == 130:
                note = f"[{lang}] exited via Ctrl+C inside the script itself (SIGINT, code 130)"
            elif code == 0:
                note = f"[{lang}] ended normally (exit code 0)"
            else:
                note = f"[{lang}] exited with code {code} (see any error/debug dump in the output above)"
            print(f"\n{note}")
            combined.append(f"\n[harness] {note}\n")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    _copy_to_clipboard("".join(combined))


def main():
    parser = argparse.ArgumentParser(description="BoxedLANG transpiler")
    parser.add_argument("file", nargs="?", help="path to the .bx source file to transpile")
    parser.add_argument("-l", "--lang", nargs="+", default=["python"], metavar="LANG",
                         help=f"one or more target languages (default: python). available: {', '.join(BACKENDS)}")
    parser.add_argument("-o", "--output", help="output file path - only valid with exactly one -l target and without -a")
    parser.add_argument("-d", "--outdir", help="output directory (a single -o file doesn't make sense once you can ask "
                                                "for several languages at once, so multi-target output goes to a directory instead)")
    parser.add_argument("-a", "--auto-name", action="store_true",
                         help="auto-name each output as <source>.<lang-ext> (e.g. os.bx.py, os.bx.lua)")
    parser.add_argument("-ls", "--list", action="store_true", help="list available target languages and exit")
    parser.add_argument("--tw-config", action="store_true",
                         help="(fractch only) embed a TurboWarp settings comment on the Stage")
    parser.add_argument("--pack", action="store_true",
                         help="(fractch only) also pack into a real .sb3 via the `fractch` CLI - "
                              "writes scratch files to ~/.bx-temp, packs, then clears that folder")
    parser.add_argument("--test", action="store_true",
                         help="transpile+run each -l target in order so you can test them interactively; "
                              "reports how each one exited (clean/end, Ctrl+C, or error) and copies the "
                              "full combined output to your clipboard if a clipboard tool is available")
    cli_args = parser.parse_args()

    if cli_args.list:
        print("Available target languages:")
        for name in BACKENDS:
            print(f"  - {name} (.{EXTENSIONS[name]})")
        sys.exit(0)

    if not cli_args.file:
        parser.error("the following arguments are required: file")

    langs = cli_args.lang
    unknown = [l for l in langs if l not in BACKENDS]
    if unknown:
        print(f"Unknown target language(s): {', '.join(unknown)}. Available: {', '.join(BACKENDS)}", file=sys.stderr)
        sys.exit(1)

    if cli_args.output and (len(langs) > 1 or cli_args.auto_name):
        parser.error("-o/--output only works with a single -l target and without -a (use -d for multiple)")

    if cli_args.output and any(l in FRACTCH_LANGS for l in langs):
        parser.error("-o/--output doesn't apply to fractch - it produces a project folder, use -d")

    filepath = os.path.expanduser(cli_args.file)
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        sys.exit(1)

    CODE = str(file.Path(filepath).read_text(encoding="utf-8"))

    try:
        ast_tree, marks = make_ast(CODE, on_warning=lambda msg: print(f"warning: {msg}", file=sys.stderr),
                                    base_dir=os.path.dirname(os.path.abspath(filepath)))
    except BoxedSyntaxError as e:
        print(f"BoxedLANG syntax error: {e}", file=sys.stderr)
        sys.exit(1)

    source_base = os.path.basename(filepath)

    if cli_args.test:
        _run_test_suite(ast_tree, marks, source_base, langs)
        sys.exit(0)

    outdir = os.path.expanduser(cli_args.outdir) if cli_args.outdir else None
    if outdir:
        file.Path(outdir).mkdir(parents=True, exist_ok=True)

    for lang in langs:
        backend = BACKENDS[lang]

        if lang in FRACTCH_LANGS:
            file_tree = backend(ast_tree, marks, source_base, tw_config=cli_args.tw_config)

            if cli_args.pack:
                import subprocess
                import shutil

                temp_root = os.path.expanduser("~/.bx-temp")
                if os.path.exists(temp_root):
                    shutil.rmtree(temp_root, ignore_errors=True)
                file.Path(temp_root).mkdir(parents=True, exist_ok=True)

                for rel_path, content in file_tree.items():
                    full_path = file.Path(temp_root) / rel_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")

                sb3_name = f"{source_base}.sb3"
                out_sb3 = os.path.abspath(os.path.join(outdir, sb3_name) if outdir else sb3_name)

                try:
                    result = subprocess.run(
                        ["fractch", out_sb3, "from", temp_root],
                        capture_output=True, text=True,
                    )
                    if result.stdout:
                        print(result.stdout, end="")
                    if result.stderr:
                        print(result.stderr, file=sys.stderr, end="")
                    if result.returncode == 0:
                        print(f"packed {out_sb3}")
                    else:
                        print(f"fractch exited with code {result.returncode} - see output above", file=sys.stderr)
                except FileNotFoundError:
                    print("Error: the `fractch` CLI isn't on your PATH - install it, or drop --pack "
                          "to just get the project folder instead.", file=sys.stderr)
                finally:
                    shutil.rmtree(temp_root, ignore_errors=True)
            else:
                project_root = outdir or f"{source_base}_fractch_project"
                file.Path(project_root).mkdir(parents=True, exist_ok=True)
                for rel_path, content in file_tree.items():
                    full_path = file.Path(project_root) / rel_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                print(f"wrote fractch project to {project_root}/ "
                      f"(pack it yourself with: fractch {source_base}.sb3 from {project_root}, "
                      f"or rerun with --pack to have this do it for you)")
            continue

        # BAPI disabled for now - was: try/except BapiError around this call.
        output_code = backend(ast_tree, marks, source_base)

        if cli_args.output:
            out_path = cli_args.output
        elif cli_args.auto_name or len(langs) > 1:
            name = f"{source_base}.{EXTENSIONS[lang]}"
            out_path = os.path.join(outdir, name) if outdir else name
        elif outdir:
            name = f"{os.path.splitext(source_base)[0]}.{EXTENSIONS[lang]}"
            out_path = os.path.join(outdir, name)
        else:
            out_path = None

        if out_path:
            file.Path(out_path).write_text(output_code, encoding="utf-8")
            print(f"wrote {out_path}")
        else:
            print(output_code, end="")


if __name__ == "__main__":
    main()
