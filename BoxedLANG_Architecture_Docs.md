# BoxedLANG - Architecture

## Core files
- `bxastgen.py` - parses .bx source into an AST + marks table. Handles
  `import` (merges another .bx file's AST in, namespaced), preemptive
  syntax validation (missing args, circular imports, mark collisions).
- `bxrunner.py` - the interpreter. Executes the AST directly via
  `execute_node()`, using Python 3.10+ `match`/`case` dispatch. Reports
  runtime errors with line/boxes/marks context unless `-s`/silent.
- `bx.py` - CLI: `bx script.bx` runs it. `-p`/`-a` tilde-patch,
  `-s` silent, `--patch-dir DIR` bulk-patches a folder without running.
- `transpilebx.py` - CLI: `transpilebx script.bx -l LANG` transpiles.
- `bxdebug.py` - Tk step-through debugger + live box/mark explorer.
  Drives `bxrunner.BoxedRunner.execute_node()` one call at a time.

## Language features
- Values/box refs: `$name` substitution, `\/` escapes the next char
  (commonly used to protect a literal `:` from the blanket strip).
- Control flow: `mark`/`premark` + `jump`/`jumpif` (goto-style).
- `import file.bx[|alias]` / `import name` (resolves to
  `~/.bx/packs/name/main.bx`) - merges another file's AST in.
  `namespace.func arg1|arg2` calls into an imported premark
  (args land in boxes `arg1`, `arg2`, ...; `return` pops back to the
  line after the call). A callee can hand a value back by setting a
  box named `ret-X` before returning - the caller sees it as `$X`.
- `clear` - clears the terminal (or, in Fractch, the print list).
- **BAPI (`api#func args`)**: parsed but currently disabled/commented
  out across `bxastgen.py`, `bxrunner.py`, and `transpilebx.py` - WIP,
  not ready yet. The design: `apis/<name>/main.<lang>.bapi` files hold
  native code blocks (`func(p1:p2:p3)&` ... code ... `&`) spliced
  directly into transpiled output, with the result landing in box
  `return`. Re-enable by uncommenting the marked blocks once the
  design is solid.

## Transpiler backends (`transpilebx.py -l <lang>`)
All seven mirror the interpreter's exact semantics via a `pc`-driven
dispatch loop (marks/jumps map to `pc` values) - none of them attempt
to recover structured control flow from arbitrary jumps.

- **python** - fully rewritten to use real native variables for any
  box name that's always assigned via a literal (non-`$`) target;
  only genuinely computed keys (`note-:$name`) fall back to a small
  residual dict. No `bxrunner` dependency in the output - standalone.
- **lua** - same native-variable design as python.
- **ruby, c, go, rust** - still the original dict/map-based design
  (every box lookup goes through a generic `resolve()`); not yet
  ported to the native-variable approach.
- **fractch** - targets the Fractch *text* format (not `.sb3` directly
  - packing is the real `fractch` CLI's job). Same native-variable
  design. `say` appends to a scrolling `print_output` list (with a
  `watch list` so it's visible on stage) instead of a single speech
  bubble. Custom blocks never use `return v;` (needs TurboWarp/
  MistWarp's extension and was causing load errors) - they set a
  shared `_ret` var and use bare `return;` instead, which is
  universally supported. `--tw-config` embeds a TurboWarp settings
  comment on the Stage. `--pack` shells out to the real `fractch` CLI
  via `~/.bx-temp` (cleared after) to produce an actual `.sb3`.

## CLI conveniences (`transpilebx.py`)
- `-l LANG [LANG ...]` - one or more targets in one run.
- `-a` - auto-name output as `<source>.<ext>`.
- `-d DIR` - output directory (required for multiple `-l` targets).
- `-ls`/`--list` - list available backends.
- `--test` - transpiles + runs each `-l` target in order so you can
  test interactively; reports how each exited (clean/`end`, Ctrl+C,
  or error) and copies the combined output to your clipboard if a
  clipboard tool is available.

## Known simplifications (documented, not bugs)
- Non-numeric `say`/`wait` durations default to `0` in every
  transpiled backend rather than erroring (the interpreter is
  stricter here, matching the original design).
- Fractch's dynamic-box lookup only special-cases the exact `$$name`
  double-indirection pattern the notes/files apps use - anything else
  dynamic gets flagged inline as `/* unsupported dynamic expr */`
  rather than silently emitting something wrong.
