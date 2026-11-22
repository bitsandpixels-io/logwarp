# SPDX-FileCopyrightText: 2026 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause

"""Command line interface for Logwarp.

CLI is organized using sub-parsers. First parameter after the invocation of the
tool is a command word, followed by its specific parameters. Main commands are:

    split <by>: splitting log file's contents into separate streams
          <by>: determines how to split the file. Values follow the API definition
                for `LogFile.unravel()`

    find <what>: lookup operations in the log file
         <what>: `similar` - execute similarity search in the file
                 `distinctive` - execute search for distinctive lines.
         Both sub-parameters accept keyword arguments matching their respective
         API. For example:

            find distinctive --height=2 --prominence=3
            find similar 5          # find lines similar to line number 5
            find similar 120,134    # find lines (chunks) similar to lines 120-134

    Common options:
        -w, --write  : results of the operations will be stored into files,
                       with naming scheme: <original_file_name>_logwrap_<operation>_<index>.<original_file_extension>
        -o, --stdout : results will be printed to stdout
        -Y, --yaml   : results will be formatted as YAML
        -j, --json   : results will be formatted as JSON
        -i <file>    : path to the input file

    Examples:

        logwarp split -i path/to/file.log 5   # splits by fifth token in log line
        logwarp split -i path/to/file.log 10:20
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from logwarp import __version__
from logwarp.logfile import LogFile

# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------


def _parse_split_by(value: str):
    """Parse the ``by`` argument for the ``split`` command.

    Accepted forms:
    - integer  → token index (e.g. ``5``)
    - ``N:M``  → character-index slice converted to a two-value tuple
    - anything else → treated as a regex pattern string
    """
    # Integer token index
    try:
        return int(value)
    except ValueError:
        pass

    # Slice notation  N:M  → tuple (N, M)
    m = re.fullmatch(r"(\d+):(\d+)", value)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Fall through: treat as regex pattern
    return value


def _parse_similar_index(value: str):
    """Parse the ``index`` argument for ``find similar``.

    Accepted forms:
    - single integer  → int
    - ``N,M``         → slice(N, M)
    """
    if "," in value:
        parts = value.split(",", 1)
        try:
            return slice(int(parts[0].strip()), int(parts[1].strip()))
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid index range '{value}'. Expected format: N,M"
            )
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid index '{value}'. Expected an integer or N,M range."
        )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _format_lines(lines) -> str:
    """Return a plain-text representation of a list of lines."""
    if hasattr(lines, "lines"):
        # LogFile object
        return "".join(str(line) for line in lines.lines)
    return "".join(str(line) for line in lines)


def _output_split(
    split_result,
    input_path: Path | None,
    *,
    write: bool,
    stdout: bool,
    as_yaml: bool,
    as_json: bool,
    operation: str = "split",
):
    """Write / print the result of a split (unravel) operation."""
    if as_json or as_yaml:
        data = {
            bucket: (
                [str(line) for line in logfile.lines]
                if hasattr(logfile, "lines")
                else [str(line) for line in logfile]
            )
            for bucket, logfile in split_result.items()
        }
        if as_json:
            text = json.dumps(data, indent=2)
        else:
            if not _YAML_AVAILABLE:
                print(
                    "ERROR: PyYAML is not installed. Install it with: pip install pyyaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            text = yaml.dump(data, allow_unicode=True)

        if stdout:
            print(text)
        if write:
            _write_text(
                text, input_path, operation, 0, suffix=".json" if as_json else ".yaml"
            )
        if not stdout and not write:
            print(text)
        return

    for idx, (bucket, logfile) in enumerate(split_result.items()):
        text = _format_lines(logfile)
        label = f"=== Bucket: {bucket} ===\n"
        if stdout:
            print(label + text)
        if write and input_path:
            _write_text(text, input_path, operation, idx, bucket_label=bucket)
    if not stdout and not write:
        for bucket, logfile in split_result.items():
            print(f"=== Bucket: {bucket} ===")
            print(_format_lines(logfile))


def _output_lines(
    lines,
    input_path: Path | None,
    *,
    write: bool,
    stdout: bool,
    as_yaml: bool,
    as_json: bool,
    operation: str,
    index: int = 0,
):
    """Write / print a list of lines."""
    str_lines = (
        [str(line) for line in lines]
        if not isinstance(lines, list)
        else [str(l) for l in lines]
    )

    if as_json or as_yaml:
        if as_json:
            text = json.dumps(str_lines, indent=2)
        else:
            if not _YAML_AVAILABLE:
                print(
                    "ERROR: PyYAML is not installed. Install it with: pip install pyyaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            text = yaml.dump(str_lines, allow_unicode=True)
    else:
        text = "".join(str_lines)

    if stdout:
        print(text)
    if write and input_path:
        _write_text(text, input_path, operation, index)
    if not stdout and not write:
        print(text)


def _write_text(
    text: str,
    input_path: Path | None,
    operation: str,
    index: int,
    suffix: str | None = None,
    bucket_label: str | None = None,
):
    """Write output text to a file following the naming scheme."""
    if input_path is None:
        print("WARNING: No input file path; cannot write output file.", file=sys.stderr)
        return

    stem = input_path.stem
    ext = suffix if suffix else input_path.suffix or ".log"
    if bucket_label:
        # Sanitize bucket label for use in a filename
        safe_label = re.sub(r"[^\w\-.]", "_", str(bucket_label))
        out_name = f"{stem}_logwarp_{operation}_{safe_label}{ext}"
    else:
        out_name = f"{stem}_logwarp_{operation}_{index}{ext}"
    out_path = input_path.parent / out_name
    out_path.write_text(text, encoding="utf-8")
    print(f"Written: {out_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_split(args):
    """Handle the ``split`` command."""
    by = _parse_split_by(args.by)

    input_path = Path(args.input) if args.input else None
    if input_path is None:
        print("ERROR: -i / --input is required for the split command.", file=sys.stderr)
        sys.exit(1)

    logfile = LogFile(input_path)
    result = logfile.unravel(by)

    _output_split(
        result,
        input_path,
        write=args.write,
        stdout=args.stdout,
        as_yaml=args.yaml,
        as_json=args.json,
        operation="split",
    )


def cmd_find_similar(args):
    """Handle the ``find similar`` sub-command."""
    index = _parse_similar_index(args.index)

    input_path = Path(args.input) if args.input else None
    if input_path is None:
        print("ERROR: -i / --input is required.", file=sys.stderr)
        sys.exit(1)

    logfile = LogFile(input_path)
    logfile.vectorize()

    kwargs = {}
    if args.step is not None:
        kwargs["step"] = args.step
    if args.q is not None:
        kwargs["q"] = args.q

    similar_indices = logfile.find_similar(index, **kwargs)
    lines = [logfile[i] for i in similar_indices]

    _output_lines(
        lines,
        input_path,
        write=args.write,
        stdout=args.stdout,
        as_yaml=args.yaml,
        as_json=args.json,
        operation="find_similar",
    )


def cmd_find_distinctive(args):
    """Handle the ``find distinctive`` sub-command."""
    input_path = Path(args.input) if args.input else None
    if input_path is None:
        print("ERROR: -i / --input is required.", file=sys.stderr)
        sys.exit(1)

    logfile = LogFile(input_path)
    logfile.vectorize()

    kwargs = {}
    if args.height is not None:
        kwargs["height"] = args.height
    if args.prominence is not None:
        kwargs["prominence"] = args.prominence
    if args.distance is not None:
        kwargs["distance"] = args.distance
    if args.kernel_size is not None:
        kwargs["kernel_size"] = args.kernel_size

    peak_indices = logfile.find_distinctive(**kwargs)
    lines = [logfile[i] for i in peak_indices]

    _output_lines(
        lines,
        input_path,
        write=args.write,
        stdout=args.stdout,
        as_yaml=args.yaml,
        as_json=args.json,
        operation="find_distinctive",
    )


def _add_common_args(parser: argparse.ArgumentParser, suppress_defaults: bool = False):
    """Add common output / input arguments to a parser."""
    def_none = argparse.SUPPRESS if suppress_defaults else None
    def_false = argparse.SUPPRESS if suppress_defaults else False

    parser.add_argument(
        "-i",
        "--input",
        metavar="FILE",
        default=def_none,
        help="Path to the input log file.",
    )
    parser.add_argument(
        "-w",
        "--write",
        action="store_true",
        default=def_false,
        help=(
            "Write results to files using the naming scheme: "
            "<original_file>_logwarp_<operation>_<index>.<ext>"
        ),
    )
    parser.add_argument(
        "-o",
        "--stdout",
        action="store_true",
        default=def_false,
        help="Print results to stdout.",
    )
    parser.add_argument(
        "-Y",
        "--yaml",
        action="store_true",
        default=def_false,
        help="Format output as YAML.",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=def_false,
        help="Format output as JSON.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="logwarp",
        description="Logwarp — log processor and analyzer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  logwarp split -i path/to/file.log 5\n"
            "  logwarp split -i path/to/file.log 10:20\n"
            "  logwarp find similar -i path/to/file.log 5\n"
            "  logwarp find similar -i path/to/file.log 120,134\n"
            "  logwarp find distinctive -i path/to/file.log --height=2 --prominence=3\n"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    _add_common_args(parser, suppress_defaults=False)

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ------------------------------------------------------------------
    # split
    # ------------------------------------------------------------------
    split_parser = subparsers.add_parser(
        "split",
        help="Split log file into separate streams.",
        description=(
            "Split a log file's contents into separate streams based on a "
            "field selector. The <by> argument follows the LogFile.unravel() API:\n\n"
            "  integer       — token index (space-delimited)\n"
            "  N:M           — character-slice range\n"
            "  regex pattern — regular expression with exactly one capture group"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_args(split_parser, suppress_defaults=True)
    split_parser.add_argument(
        "by",
        metavar="<by>",
        help=(
            "How to split the file: an integer (token index), N:M (char slice), "
            "or a regex pattern with one capture group."
        ),
    )
    split_parser.set_defaults(func=cmd_split)

    # ------------------------------------------------------------------
    # find
    # ------------------------------------------------------------------
    find_parser = subparsers.add_parser(
        "find",
        help="Lookup operations in the log file.",
    )
    _add_common_args(find_parser, suppress_defaults=True)
    find_subparsers = find_parser.add_subparsers(dest="what", metavar="WHAT")
    find_subparsers.required = True

    # find similar
    similar_parser = find_subparsers.add_parser(
        "similar",
        help="Find log lines similar to a reference line or chunk.",
        description=(
            "Find log entries similar to the entry at the given index.\n\n"
            "Index formats:\n"
            "  5        — single line (line number 5)\n"
            "  120,134  — chunk spanning lines 120 to 134"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_args(similar_parser, suppress_defaults=True)
    similar_parser.add_argument(
        "index",
        metavar="INDEX",
        help="Reference line index (integer) or range (N,M).",
    )
    similar_parser.add_argument(
        "--step",
        type=int,
        default=None,
        metavar="N",
        help="Step size when sliding over the log file (default: chunk size).",
    )
    similar_parser.add_argument(
        "--q",
        type=float,
        default=None,
        metavar="Q",
        help="Quantile threshold for similarity (default: 0.001).",
    )
    similar_parser.set_defaults(func=cmd_find_similar)

    # find distinctive
    distinctive_parser = find_subparsers.add_parser(
        "distinctive",
        help="Find distinctive (peak) log lines.",
        description=(
            "Find log entries with prominent peaks using signal processing. "
            "Automatically tunes prominence and height when not provided."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_args(distinctive_parser, suppress_defaults=True)
    distinctive_parser.add_argument(
        "--height",
        type=float,
        default=None,
        metavar="H",
        help="Minimum peak height (auto-tuned when omitted).",
    )
    distinctive_parser.add_argument(
        "--prominence",
        type=float,
        default=None,
        metavar="P",
        help="Minimum peak prominence (auto-tuned when omitted).",
    )
    distinctive_parser.add_argument(
        "--distance",
        type=int,
        default=None,
        metavar="D",
        help="Minimum distance between peaks (default: 1).",
    )
    distinctive_parser.add_argument(
        "--kernel-size",
        dest="kernel_size",
        type=int,
        default=None,
        metavar="K",
        help="Median filter kernel size for de-noising (default: 1).",
    )
    distinctive_parser.set_defaults(func=cmd_find_distinctive)

    return parser


def main(argv=None):
    """Main entry point for the logwarp CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Propagate common flags from the ``find`` parent parser down to its
    # sub-command namespace (argparse does not do this automatically for
    # nested sub-parsers).
    if args.command == "find" and hasattr(args, "func"):
        # common flags already present on args; nothing extra needed.
        pass

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)
