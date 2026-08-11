"""
bx.py - BoxedLANG CLI wrapper.

Ties together bxastgen (parsing) and bxrunner (execution). Handles the
tilde-patch (-p/-a) and silent (-s) flags, and is the thing you
actually run: `python bx.py yourscript.bx`.
"""
import sys
import argparse
import pathlib as file
import os.path

from bxastgen import make_ast, BoxedSyntaxError
from bxrunner import BoxedRunner


def main():
    parser = argparse.ArgumentParser(description="boxedLANG interpreter")
    parser.add_argument("file", nargs="?", help="path to the boxedLANG source file to run")
    parser.add_argument("-p", "--patch", action="store_true", help="patch tildes to spaces in memory for execution")
    parser.add_argument("-a", "--apply", action="store_true", help="write tilde patch back to the source file permanently")
    parser.add_argument("-s", "--silent", action="store_true", help="suppress system messages, warnings, and error details")
    parser.add_argument("--patch-dir", metavar="DIR",
                         help="recursively tilde-patch every .bx file under DIR in place, write the changes back, "
                              "and exit WITHOUT running anything")
    cli_args = parser.parse_args()

    if cli_args.patch_dir:
        root = os.path.expanduser(cli_args.patch_dir)
        if not os.path.isdir(root):
            if not cli_args.silent:
                print(f"Error: '{root}' is not a directory.")
            sys.exit(1)
        patched = 0
        for path in file.Path(root).rglob("*.bx"):
            text = path.read_text(encoding="utf-8")
            if "~" in text:
                path.write_text(text.replace("~", " "), encoding="utf-8")
                patched += 1
                if not cli_args.silent:
                    print(f"patched {path}")
        if not cli_args.silent:
            print(f"--- done: patched {patched} file(s) under {root} ---")
        sys.exit(0)

    if not cli_args.file:
        parser.error("the following arguments are required: file (unless using --patch-dir)")

    filepath = os.path.expanduser(cli_args.file)

    if not os.path.exists(filepath):
        if not cli_args.silent:
            print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    CODE = str(file.Path(filepath).read_text(encoding="utf-8"))

    if "~" in CODE:
        if cli_args.patch or cli_args.apply:
            if not cli_args.silent:
                print(f"--- Patching tildes (~) to spaces in {filepath} ---")
            CODE = CODE.replace("~", " ")
            if cli_args.apply:
                file.Path(filepath).write_text(CODE, encoding="utf-8")

    def warn(msg):
        if not cli_args.silent:
            print(f"warning: {msg}", file=sys.stderr)

    try:
        ast_tree, marks = make_ast(CODE, on_warning=warn, base_dir=os.path.dirname(os.path.abspath(filepath)))
    except BoxedSyntaxError as e:
        if not cli_args.silent:
            print(f"BoxedLANG syntax error: {e}", file=sys.stderr)
        sys.exit(1)

    runner = BoxedRunner(silent=cli_args.silent)
    runner.run(ast_tree, marks)


if __name__ == "__main__":
    main()
