"""
bxrunner.py - BoxedLANG runtime.

Executes an AST (as produced by bxastgen.make_ast) node-by-node. This
module is the shared execution engine used directly by bx.py, and its
resolve()/test_op()/math_op() helpers are reused by transpilebx.py so
generated code stays behaviorally identical to the real interpreter.

Error handling: any exception raised while executing a node is caught
in run(), and (unless silent=True) reported with the failing line
number, the raw AST node, and the current boxes/marks state - similar
in spirit to the old box_rs.py's "PY ERROR" dump, just without the
colorama dependency.
"""
import time
import sys
import re
import traceback


class BoxedRuntimeError(Exception):
    """Raised for a problem encountered while executing an AST node."""

    def __init__(self, message, line_no=None):
        self.line_no = line_no
        full = f"line {line_no}: {message}" if line_no is not None else message
        super().__init__(full)


class BoxedRunner:
    def __init__(self, silent=False):
        self.boxes = {}
        self.marks = {}
        self.ast = []
        self.line_index = 0
        self.silent = silent
        self.call_stack = []

    def resolve(self, val):
        if not isinstance(val, str):
            return val

        for _ in range(2):
            for box_name, box_val in sorted(self.boxes.items(), key=lambda x: len(x[0]), reverse=True):
                val = val.replace("$" + box_name, str(box_val))

        # \/ escapes the single character right after it (e.g. \/: keeps
        # a literal colon that would otherwise be stripped below).
        val = re.sub(r"\\/(.)", lambda m: "\x00" if m.group(1) == ":" else m.group(1), val)

        val = val.replace(":", "")
        val = val.replace("\x00", ":")

        return val

    def test_op(self, left, right, op):
        left = self.resolve(left)
        right = self.resolve(right)

        if op == "==": return left == right
        if op == "!=": return left != right

        try:
            l_num, r_num = float(left), float(right)
            if op == ">": return l_num > r_num
            if op == "<": return l_num < r_num
            if op == ">=": return l_num >= r_num
            if op == "<=": return l_num <= r_num
        except ValueError:
            pass
        return False

    def math_op(self, left, right, op):
        left_val = self.resolve(left)
        right_val = self.resolve(right)
        op = self.resolve(op)

        left_n = int(left_val) if left_val.strip('-').isnumeric() else 0
        right_n = int(right_val) if right_val.strip('-').isnumeric() else 0

        if op == "+": return left_n + right_n
        elif op == "-": return left_n - right_n
        elif op in ("*", "x"): return left_n * right_n
        elif op == "/": return left_n // right_n if right_n != 0 else 0
        elif op == "%": return left_n % right_n if right_n != 0 else 0
        return 0

    def run(self, ast, marks):
        self.ast = ast
        self.marks = marks
        self.line_index = 0

        try:
            while self.line_index < len(self.ast):
                node = self.ast[self.line_index]
                try:
                    result = self.execute_node(node)
                except Exception as e:
                    self._report_error(e, node)
                    sys.exit(1)

                if result == 'EXIT':
                    break

                self.line_index += 1
        except KeyboardInterrupt:
            print(" — stopped.")
            sys.exit(130)

    def _report_error(self, exc, node):
        if self.silent:
            return

        bar = "=" * 60
        print(f"\n{bar}", file=sys.stderr)
        print(f"BoxedLANG runtime error at line {self.line_index + 1}", file=sys.stderr)
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"  node  : {node}", file=sys.stderr)
        print(f"  boxes : {self.boxes}", file=sys.stderr)
        print(f"  marks : {self.marks}", file=sys.stderr)
        print(bar, file=sys.stderr)
        traceback.print_exc()
        print(bar, file=sys.stderr)

    def execute_node(self, node):
        match node:
            case {'type': 'Assign', 'target': target, 'value': value}:
                self.boxes[self.resolve(target)] = self.resolve(value)

            case {'type': 'Print', 'value': value, 'time': time_str}:
                print(self.resolve(value))
                time_val = int("0" + self.resolve(time_str).strip())
                if time_val > 0:
                    time.sleep(time_val)

            case {'type': 'Input', 'prompt': prompt_raw, 'target': target}:
                prompt = self.resolve(prompt_raw)
                suffix = self.boxes["prm"] if "prm" in self.boxes else "\n:> "
                user_in = input(prompt + suffix)
                self.boxes[self.resolve(target)] = user_in

            case {'type': 'Math', 'target': target, 'left': left, 'right': right, 'op': op}:
                self.boxes[self.resolve(target)] = str(self.math_op(left, right, op))

            case {'type': 'Test', 'target': target, 'left': left, 'right': right, 'op': op,
                  'true_val': true_val, 'false_val': false_val}:
                passed = self.test_op(left, right, op)
                resolved_target = self.resolve(target)
                self.boxes[resolved_target] = self.resolve(true_val if passed else false_val)

            case {'type': 'If', 'left': left, 'right': right, 'op': op, 'body': body}:
                if self.test_op(left, right, op):
                    return self.execute_node(body)

            case {'type': 'Jump', 'target': target_raw, 'mode': mode}:
                target = self.resolve(target_raw)
                if mode == "m":
                    self.line_index = self.marks.get(target, 0) - 1
                else:
                    self.line_index = int(target) - 2

            case {'type': 'JumpIf', 'left': left, 'right': right, 'op': op,
                  'target': target_raw, 'mode': mode}:
                if self.test_op(left, right, op):
                    target = self.resolve(target_raw)
                    if mode == "m":
                        self.line_index = self.marks.get(target, 0) - 1
                    else:
                        self.line_index = int(target) - 2

            case {'type': 'Delete', 'target': target_raw}:
                target = self.resolve(target_raw)
                if target in self.boxes:
                    del self.boxes[target]

            case {'type': 'End'}:
                sys.exit()

            case {'type': 'Clear'}:
                # ANSI clear screen + move cursor home. Works on any real
                # terminal (Linux/macOS terms, and modern Windows Terminal/
                # ConHost with VT processing on); a dumb pipe/non-tty target
                # just gets the raw escape bytes, which is harmless.
                sys.stdout.write("\x1b[2J\x1b[H")
                sys.stdout.flush()

            case {'type': 'Import'}:
                pass  # already merged into self.ast/self.marks at parse time

            case {'type': 'Call', 'namespace': namespace, 'func': func, 'args': args}:
                target_name = f"{namespace}.{func}"
                if target_name not in self.marks:
                    raise BoxedRuntimeError(
                        f"call to undefined '{target_name}' - is '{namespace}' imported, "
                        f"and does it define a premark called '{func}'?"
                    )
                for i, arg in enumerate(args, start=1):
                    self.boxes[f"arg{i}"] = self.resolve(arg)
                self.call_stack.append(self.line_index)
                self.line_index = self.marks[target_name] - 1

            case {'type': 'Return'}:
                if not self.call_stack:
                    raise BoxedRuntimeError("'return' with no active call (call stack is empty)")
                for key in list(self.boxes.keys()):
                    if key.startswith("ret-") and len(key) > 4:
                        self.boxes[key[4:]] = self.boxes[key]
                self.line_index = self.call_stack.pop()

            case {'type': 'BapiCall', 'api': api, 'func': func}:
                raise BoxedRuntimeError(
                    f"'{api}#{func}' is a bapi call - these only work when transpiling "
                    f"(see transpilebx.py --lang python/rust), not in the interpreter, since "
                    f"there's no way to run arbitrary native code from here"
                )

            case _:
                pass  # Mark, Unknown, and anything else: runtime no-op
