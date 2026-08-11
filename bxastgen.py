"""
bxastgen.py - BoxedLANG AST generator.

Turns raw BoxedLANG source text into a flat list of AST node dicts
(one per source line) plus a `marks` dict mapping mark names to their
index in that list. This module does no execution - it's purely the
parsing/validation stage, shared by the interpreter (bxrunner.py) and
the transpiler (transpilebx.py).

Preemptive validation: each command is checked for the minimum number
of arguments it needs as soon as it's parsed, so a malformed script
fails HERE with a clear BoxedSyntaxError (naming the line, the
command, and what was expected) instead of surfacing as a raw
IndexError deep inside the runner or transpiler later on.
"""


class BoxedSyntaxError(Exception):
    """Raised for a malformed BoxedLANG source line, caught at parse time."""

    def __init__(self, message, line_no=None, line_text=None):
        self.line_no = line_no
        self.line_text = line_text
        full = f"line {line_no}: {message}" if line_no is not None else message
        if line_text is not None:
            full += f"\n    {line_text.strip()}"
        super().__init__(full)


def _require(args, n, cmd, line_no, line_text, usage):
    if len(args) < n:
        raise BoxedSyntaxError(
            f"'{cmd}' needs {n} argument{'s' if n != 1 else ''} ({usage}), got {len(args)}",
            line_no, line_text,
        )


def parse_condition(args, start_idx, cmd, line_no, line_text):
    """
    Helper function to safely extract left, right, and op variables
    whether they are formatted as left|op|right or left|right|op.
    """
    if len(args) <= start_idx + 2:
        raise BoxedSyntaxError(
            f"'{cmd}' needs a left|op|right (or left|right|op) condition "
            f"starting at argument {start_idx}, got {max(0, len(args) - start_idx)} value(s)",
            line_no, line_text,
        )
    if args[start_idx + 1] in ("==", "!=", ">", "<", ">=", "<="):
        return args[start_idx], args[start_idx + 2], args[start_idx + 1], args[start_idx + 3:]
    else:
        return args[start_idx], args[start_idx + 1], args[start_idx + 2], args[start_idx + 3:]


def parse_command(cmd, args, line_no=None, line_text=None):
    """
    Recursively turns a command and its arguments into a structured AST node.
    Raises BoxedSyntaxError if the command doesn't have enough arguments.
    """
    cmd = cmd.lower()

    # [Assign]: box x|y
    if cmd in ("box", "b"):
        _require(args, 1, cmd, line_no, line_text, "target|value")
        return {'type': 'Assign', 'target': args[0], 'value': args[1] if len(args) > 1 else ""}

    # [Print]: say text|time
    elif cmd in ("say", "s"):
        return {'type': 'Print', 'value': args[0] if len(args) > 0 else "", 'time': args[1] if len(args) > 1 else "0"}

    # [Input]: ask prompt
    elif cmd in ("ask", "a"):
        prompt = args[0] if len(args) > 0 else ""
        target = prompt.split()[-1] if prompt else "ans"
        return {'type': 'Input', 'prompt': prompt, 'target': target}

    # [Math]: math target|left|right|op
    elif cmd in ("math", "m"):
        _require(args, 4, cmd, line_no, line_text, "target|left|right|op")
        return {'type': 'Math', 'target': args[0], 'left': args[1], 'right': args[2], 'op': args[3]}

    # [Test/Ternary]: test target|left|...
    elif cmd in ("test", "t"):
        _require(args, 1, cmd, line_no, line_text, "target|left|op|right|[true]|[false]")
        target = args[0]
        left, right, op, remainder = parse_condition(args, 1, cmd, line_no, line_text)
        return {
            'type': 'Test', 'target': target,
            'left': left, 'right': right, 'op': op,
            'true_val': remainder[0] if len(remainder) > 0 else "1",
            'false_val': remainder[1] if len(remainder) > 1 else "0"
        }

    # [Control Flow]: jump / jumpif
    elif cmd in ("jump", "j"):
        _require(args, 1, cmd, line_no, line_text, "target|[mode]")
        return {'type': 'Jump', 'target': args[0], 'mode': args[1] if len(args) > 1 else "l"}

    elif cmd in ("jumpif", "ji"):
        left, right, op, remainder = parse_condition(args, 0, cmd, line_no, line_text)
        if len(remainder) < 1:
            raise BoxedSyntaxError(f"'{cmd}' needs a jump target after the condition", line_no, line_text)
        return {
            'type': 'JumpIf', 'left': left, 'right': right, 'op': op,
            'target': remainder[0], 'mode': remainder[1] if len(remainder) > 1 else "l"
        }

    # [If Statement]: if condition|cmd|args...
    elif cmd in ("if", "i"):
        left, right, op, remainder = parse_condition(args, 0, cmd, line_no, line_text)
        if len(remainder) < 1:
            raise BoxedSyntaxError(f"'{cmd}' needs a command to run after the condition", line_no, line_text)
        sub_cmd = remainder[0]
        sub_args = remainder[1:]
        nested_ast = parse_command(sub_cmd, sub_args, line_no, line_text)

        return {
            'type': 'If', 'left': left, 'right': right, 'op': op,
            'body': nested_ast
        }

    # [Utility]: wait, del, weigh
    elif cmd in ("wait", "wt"):
        _require(args, 1, cmd, line_no, line_text, "time")
        return {'type': 'Wait', 'time': args[0]}
    elif cmd in ("del", "d"):
        _require(args, 1, cmd, line_no, line_text, "target")
        return {'type': 'Delete', 'target': args[0]}
    elif cmd in ("weigh", "wh"):
        _require(args, 2, cmd, line_no, line_text, "source|target")
        return {'type': 'Weigh', 'target': args[1], 'source': args[0]}

    # [Marks]: premark / mark
    elif cmd in ("premark", "mark", "mk"):
        _require(args, 1, cmd, line_no, line_text, "name")
        return {'type': 'Mark', 'name': args[0]}

    elif cmd in ("end", "e"):
        return {'type': 'End'}

    # [Clear]: clear the screen/output
    elif cmd in ("clear", "cls"):
        return {'type': 'Clear'}

    # [Return]: return from a namespace.func call back to the caller
    elif cmd in ("return", "ret"):
        return {'type': 'Return'}

    # [Import]: import a .bx file as a namespace (see make_ast for the
    # actual file loading/merging - this node itself is a runtime no-op)
    elif cmd in ("import", "imp"):
        _require(args, 1, cmd, line_no, line_text, "path|[alias]")
        return {'type': 'Import', 'path': args[0], 'alias': args[1] if len(args) > 1 else None}

    # [Call]: namespace.func arg1|arg2|... - calls into an imported
    # module's premark, positional args land in boxes arg1, arg2, ...
    if "." in cmd:
        namespace, _, func = cmd.partition(".")
        if not namespace or not func:
            raise BoxedSyntaxError(f"'{cmd}' looks like a namespaced call but is missing the namespace or function name", line_no, line_text)
        return {'type': 'Call', 'namespace': namespace, 'func': func, 'args': list(args)}

    # [BapiCall]: apiname#func arg1|arg2|... - calls a native function
    # spliced in from apis/<apiname>/main.<lang>.bapi at transpile time
    # (see transpilebx.py). Sets box "return" to whatever it returns.
    # Only meaningful when transpiling; the interpreter can't run
    # arbitrary native code, so it errors clearly instead.
    if "#" in cmd:
        api, _, func = cmd.partition("#")
        if not api or not func:
            raise BoxedSyntaxError(f"'{cmd}' looks like a bapi call but is missing the api name or function name", line_no, line_text)
        return {'type': 'BapiCall', 'api': api, 'func': func, 'args': list(args)}

    return {'type': 'Unknown', 'cmd': cmd, 'args': args}


def _resolve_import_path(raw_path, importing_dir):
    """
    Path resolution rules for `import`:
      - bare filename ending in .bx (no slashes)  -> next to the importing file
      - starts with ~ or contains a slash          -> used as-is (expanduser'd,
                                                       relative paths are relative
                                                       to the importing file's dir)
      - a bare name with no .bx and no slash       -> package convention:
                                                       ~/.bx/packs/<name>/main.bx
    Returns (absolute_path, default_alias).
    """
    import os

    if raw_path.endswith(".bx") and "/" not in raw_path and "\\" not in raw_path:
        abspath = os.path.join(importing_dir, raw_path)
        alias = raw_path[:-3]
    elif raw_path.startswith("~") or "/" in raw_path or "\\" in raw_path:
        expanded = os.path.expanduser(raw_path)
        abspath = expanded if os.path.isabs(expanded) else os.path.join(importing_dir, expanded)
        stem = os.path.splitext(os.path.basename(abspath))[0]
        alias = stem if stem != "main" else os.path.basename(os.path.dirname(abspath))
    else:
        abspath = os.path.expanduser(f"~/.bx/packs/{raw_path}/main.bx")
        alias = raw_path

    return os.path.normpath(abspath), alias


def _merge_marks(target_marks, new_marks, alias, offset, line_no, line_text):
    """
    Merges an imported module's marks into the importing program's mark
    table, offsetting every index and registering each mark under BOTH:
      - "<alias>.<name>"  (for cross-module namespace.func calls)
      - "<name>"          (bare, so the imported module's OWN internal
                            jumps - written before it knew it'd be
                            imported - still resolve)
    A bare-name collision (two modules, or a module and the main
    program, both using the same mark name) can't be safely
    disambiguated in a flat mark table, so it's a hard error naming
    both sides rather than a silent misresolution.
    """
    for name, idx in new_marks.items():
        global_idx = idx + offset
        namespaced = f"{alias}.{name}"

        if namespaced in target_marks:
            raise BoxedSyntaxError(
                f"import alias '{alias}' collides with an existing mark/import of the same name ('{namespaced}')",
                line_no, line_text,
            )
        target_marks[namespaced] = global_idx

        if name not in target_marks:
            target_marks[name] = global_idx
        else:
            raise BoxedSyntaxError(
                f"mark '{name}' from imported '{alias}' collides with an existing bare mark of the same name - "
                f"rename one of them (bare mark names must stay unique across the whole program, including "
                f"everything it imports, so internal jumps inside the imported file keep resolving)",
                line_no, line_text,
            )


def make_ast(code, on_warning=None, base_dir=None, _importing_stack=None):
    """
    Reads the full script, calculates marks ahead of time, and builds
    the AST list.

    :param code: raw BoxedLANG source text
    :param on_warning: optional callback(message) for non-fatal issues
                        (e.g. an unrecognized command). Pass None to
                        silence warnings entirely.
    :param base_dir: directory the source was loaded from, used to
                      resolve bare `import foo.bx` paths. Defaults to
                      the current working directory for a top-level
                      call (i.e. when code isn't itself an import).
    :param _importing_stack: internal - resolved paths currently being
                              imported, for circular-import detection.
                              Don't pass this yourself.
    :raises BoxedSyntaxError: on a malformed line (missing arguments,
                               a circular import, or a mark collision)
    """
    import os

    if base_dir is None:
        base_dir = os.getcwd()
    if _importing_stack is None:
        _importing_stack = []

    ast = []
    marks = {}
    pending_imports = []  # list of (alias, imported_ast, imported_marks)
    lines = code.strip().splitlines()

    for index, raw_line in enumerate(lines):
        line_no = index + 1
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        line = line.split("//")[0].strip()
        parts = line.split(" ", 1)
        cmd = parts[0]
        args = parts[1].split("|") if len(parts) > 1 else []

        if cmd in ("premark", "mark", "mk"):
            if not args:
                raise BoxedSyntaxError(f"'{cmd}' needs a name", line_no, raw_line)
            marks[args[0]] = len(ast)

        node = parse_command(cmd, args, line_no, raw_line)

        if node['type'] == 'Unknown' and on_warning is not None:
            on_warning(f"line {line_no}: unrecognized command '{cmd}', ignoring\n    {raw_line.strip()}")

        if node['type'] == 'Import':
            abspath, default_alias = _resolve_import_path(node['path'], base_dir)
            alias = (node['alias'] or default_alias).lower()

            if abspath in _importing_stack:
                cycle = " -> ".join(_importing_stack + [abspath])
                raise BoxedSyntaxError(f"circular import: {cycle}", line_no, raw_line)

            if not os.path.exists(abspath):
                raise BoxedSyntaxError(f"import target not found: {abspath}", line_no, raw_line)

            imported_code = open(abspath, "r", encoding="utf-8").read()
            imported_ast, imported_marks = make_ast(
                imported_code,
                on_warning=on_warning,
                base_dir=os.path.dirname(abspath),
                _importing_stack=_importing_stack + [abspath],
            )
            pending_imports.append((alias, imported_ast, imported_marks))

        ast.append(node)

    # Safety terminator: without this, a main file that just runs off
    # its own end (no explicit `end`) would fall straight through into
    # whatever gets appended below from imports, executing someone
    # else's module top-to-bottom by accident. Imported modules only
    # get in via an explicit namespace.func call/jump.
    if pending_imports:
        ast.append({'type': 'End'})

    for alias, imported_ast, imported_marks in pending_imports:
        offset = len(ast)
        _merge_marks(marks, imported_marks, alias, offset, None, None)
        ast.extend(imported_ast)

    return ast, marks
