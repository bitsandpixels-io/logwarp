# SPDX-FileCopyrightText: 2026 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the logwarp CLI (cli.py).

Coverage:
- Argument parsing helpers (_parse_split_by, _parse_similar_index)
- Output helpers (_format_lines, _write_text, _output_split, _output_lines)
- Parser construction (build_parser) — flag defaults, sub-commands, mutually
  exclusive args, --version
- Command handlers (cmd_split, cmd_find_similar, cmd_find_distinctive) via
  mocked LogFile calls so tests don't depend on the numeric analysis pipeline
- main() integration smoke-tests with a real tmp log file
"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import logwarp.cli as cli
from logwarp.cli import (
    _format_lines,
    _output_lines,
    _output_split,
    _parse_similar_index,
    _parse_split_by,
    _write_text,
    build_parser,
    cmd_find_distinctive,
    cmd_find_similar,
    cmd_split,
    main,
)
from logwarp.logfile import LogFile, LogFileSplit


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_LINES = [
    "2023-01-01 10:00:00 INFO: Starting program",
    "2023-01-01 11:00:00 INFO: Heartbeat",
    "2023-01-01 12:00:00 INFO: Heartbeat",
    "2023-01-01 12:59:02 ERROR: Something went wrong",
    "2023-01-01 13:00:00 INFO: Heartbeat",
    "2023-01-01 14:00:00 INFO: Heartbeat",
    "2023-01-01 14:32:12 WARNING: This is weird",
    "2023-01-01 15:00:00 INFO: Heartbeat",
    "2023-01-01 16:00:00 INFO: Heartbeat",
]


@pytest.fixture
def log_path(tmp_path):
    """Write SAMPLE_LINES to a temporary file and return its Path."""
    p = tmp_path / "test.log"
    p.write_text("\n".join(SAMPLE_LINES) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def parser():
    return build_parser()


# ===========================================================================
# _parse_split_by
# ===========================================================================


class TestParseSplitBy:
    def test_integer_string(self):
        assert _parse_split_by("5") == 5

    def test_zero(self):
        assert _parse_split_by("0") == 0

    def test_slice_notation(self):
        assert _parse_split_by("10:20") == (10, 20)

    def test_slice_zero_start(self):
        assert _parse_split_by("0:7") == (0, 7)

    def test_regex_pattern_returned_as_string(self):
        pattern = r"[\w\d :-]+(INFO|ERROR|WARNING)"
        result = _parse_split_by(pattern)
        assert result == pattern
        assert isinstance(result, str)

    def test_plain_word_returned_as_string(self):
        result = _parse_split_by("kernel")
        assert result == "kernel"
        assert isinstance(result, str)

    def test_negative_integer_returned_as_int(self):
        # Negative integers are still valid token indices in Python
        assert _parse_split_by("-1") == -1

    def test_partial_slice_not_matched(self):
        # "5:" is not a full N:M match → returned as string
        result = _parse_split_by("5:")
        assert isinstance(result, str)
        assert result == "5:"


# ===========================================================================
# _parse_similar_index
# ===========================================================================


class TestParseSimilarIndex:
    def test_single_integer(self):
        assert _parse_similar_index("5") == 5

    def test_zero(self):
        assert _parse_similar_index("0") == 0

    def test_range_produces_slice(self):
        result = _parse_similar_index("120,134")
        assert result == slice(120, 134)

    def test_range_with_spaces(self):
        result = _parse_similar_index("10 , 20")
        assert result == slice(10, 20)

    def test_invalid_integer_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Expected an integer"):
            _parse_similar_index("abc")

    def test_invalid_range_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Expected format: N,M"):
            _parse_similar_index("abc,def")


# ===========================================================================
# _format_lines
# ===========================================================================


class TestFormatLines:
    def test_list_of_strings(self):
        assert _format_lines(["a\n", "b\n"]) == "a\nb\n"

    def test_logfile_object(self):
        lf = LogFile(["hello", "world"])
        result = _format_lines(lf)
        assert "hello" in result
        assert "world" in result

    def test_empty_list(self):
        assert _format_lines([]) == ""


# ===========================================================================
# _write_text
# ===========================================================================


class TestWriteText:
    def test_creates_file_with_index(self, tmp_path):
        input_path = tmp_path / "myfile.log"
        input_path.touch()
        _write_text("hello", input_path, "split", 3)
        out = tmp_path / "myfile_logwarp_split_3.log"
        assert out.exists()
        assert out.read_text() == "hello"

    def test_creates_file_with_bucket_label(self, tmp_path):
        input_path = tmp_path / "myfile.log"
        input_path.touch()
        _write_text("content", input_path, "split", 0, bucket_label="INFO")
        out = tmp_path / "myfile_logwarp_split_INFO.log"
        assert out.exists()

    def test_bucket_label_sanitized(self, tmp_path):
        input_path = tmp_path / "myfile.log"
        input_path.touch()
        _write_text("content", input_path, "split", 0, bucket_label="INFO (extra)")
        # Parentheses should be replaced by underscores
        out = tmp_path / "myfile_logwarp_split_INFO__extra_.log"
        assert out.exists()

    def test_custom_suffix_overrides_extension(self, tmp_path):
        input_path = tmp_path / "myfile.log"
        input_path.touch()
        _write_text("{}", input_path, "split", 0, suffix=".json")
        out = tmp_path / "myfile_logwarp_split_0.json"
        assert out.exists()

    def test_no_input_path_prints_warning(self, capsys):
        _write_text("x", None, "split", 0)
        err = capsys.readouterr().err
        assert "WARNING" in err

    def test_file_without_extension(self, tmp_path):
        input_path = tmp_path / "myfile"
        input_path.touch()
        _write_text("data", input_path, "op", 1)
        out = tmp_path / "myfile_logwarp_op_1.log"
        assert out.exists()


# ===========================================================================
# _output_split
# ===========================================================================


def _make_split(buckets: dict) -> LogFileSplit:
    """Build a LogFileSplit from a plain dict {name: [lines]}."""
    split = LogFileSplit()
    for key, lines in buckets.items():
        split[key] = LogFile(lines) if lines else LogFile([])
    return split


class TestOutputSplit:
    def test_stdout_plain(self, capsys):
        split = _make_split({"INFO": ["line1", "line2"], "ERROR": ["err"]})
        _output_split(split, None, write=False, stdout=True, as_yaml=False, as_json=False)
        out = capsys.readouterr().out
        assert "INFO" in out
        assert "line1" in out

    def test_stdout_json(self, capsys):
        split = _make_split({"A": ["x"], "outliers": []})
        _output_split(split, None, write=False, stdout=True, as_yaml=False, as_json=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "A" in data
        assert data["A"] == ["x"]

    def test_default_prints_when_no_stdout_no_write(self, capsys):
        split = _make_split({"X": ["foo"]})
        _output_split(split, None, write=False, stdout=False, as_yaml=False, as_json=False)
        out = capsys.readouterr().out
        assert "foo" in out

    def test_write_creates_files(self, tmp_path, capsys):
        input_path = tmp_path / "file.log"
        input_path.touch()
        split = _make_split({"INFO": ["line1"], "outliers": []})
        _output_split(
            split, input_path, write=True, stdout=False, as_yaml=False, as_json=False
        )
        written = list(tmp_path.glob("file_logwarp_split_*.log"))
        assert len(written) >= 1

    def test_write_json_single_file(self, tmp_path, capsys):
        input_path = tmp_path / "file.log"
        input_path.touch()
        split = _make_split({"A": ["a1"]})
        _output_split(
            split, input_path, write=True, stdout=False, as_yaml=False, as_json=True
        )
        written = list(tmp_path.glob("file_logwarp_split_*.json"))
        assert len(written) == 1
        data = json.loads(written[0].read_text())
        assert "A" in data


# ===========================================================================
# _output_lines
# ===========================================================================


class TestOutputLines:
    def test_stdout_plain(self, capsys):
        _output_lines(
            ["line1\n", "line2\n"],
            None,
            write=False,
            stdout=True,
            as_yaml=False,
            as_json=False,
            operation="find_similar",
        )
        out = capsys.readouterr().out
        assert "line1" in out

    def test_stdout_json(self, capsys):
        _output_lines(
            ["a", "b"],
            None,
            write=False,
            stdout=True,
            as_yaml=False,
            as_json=True,
            operation="op",
        )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data == ["a", "b"]

    def test_default_prints_when_no_flags(self, capsys):
        _output_lines(
            ["hello"],
            None,
            write=False,
            stdout=False,
            as_yaml=False,
            as_json=False,
            operation="op",
        )
        out = capsys.readouterr().out
        assert "hello" in out

    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "file.log"
        p.touch()
        _output_lines(
            ["line\n"],
            p,
            write=True,
            stdout=False,
            as_yaml=False,
            as_json=False,
            operation="find_similar",
        )
        written = list(tmp_path.glob("file_logwarp_find_similar_*.log"))
        assert len(written) == 1


# ===========================================================================
# build_parser — structure and defaults
# ===========================================================================


class TestBuildParser:
    def test_split_defaults(self, parser):
        args = parser.parse_args(["split", "-i", "foo.log", "3"])
        assert args.command == "split"
        assert args.input == "foo.log"
        assert args.by == "3"
        assert args.write is False
        assert args.stdout is False
        assert args.yaml is False
        assert args.json is False
        assert args.func is cmd_split

    def test_split_all_flags(self, parser):
        args = parser.parse_args(["split", "-i", "foo.log", "-w", "-o", "-Y", "-j", "2"])
        assert args.write is True
        assert args.stdout is True
        assert args.yaml is True
        assert args.json is True

    def test_split_long_flags(self, parser):
        args = parser.parse_args(
            ["split", "--input", "foo.log", "--write", "--stdout", "--yaml", "--json", "2"]
        )
        assert args.write is True
        assert args.input == "foo.log"

    def test_find_similar_defaults(self, parser):
        args = parser.parse_args(["find", "-i", "foo.log", "similar", "5"])
        assert args.command == "find"
        assert args.what == "similar"
        assert args.index == "5"
        assert args.step is None
        assert args.q is None
        assert args.func is cmd_find_similar

    def test_find_similar_optional_args(self, parser):
        args = parser.parse_args(
            ["find", "-i", "foo.log", "similar", "5", "--step", "2", "--q", "0.01"]
        )
        assert args.step == 2
        assert args.q == pytest.approx(0.01)

    def test_find_similar_range_index(self, parser):
        args = parser.parse_args(["find", "-i", "foo.log", "similar", "120,134"])
        assert args.index == "120,134"

    def test_find_distinctive_defaults(self, parser):
        args = parser.parse_args(["find", "-i", "foo.log", "distinctive"])
        assert args.command == "find"
        assert args.what == "distinctive"
        assert args.height is None
        assert args.prominence is None
        assert args.distance is None
        assert args.kernel_size is None
        assert args.func is cmd_find_distinctive

    def test_find_distinctive_all_kwargs(self, parser):
        args = parser.parse_args(
            [
                "find", "-i", "foo.log", "distinctive",
                "--height", "1.5",
                "--prominence", "2.0",
                "--distance", "10",
                "--kernel-size", "5",
            ]
        )
        assert args.height == pytest.approx(1.5)
        assert args.prominence == pytest.approx(2.0)
        assert args.distance == 10
        assert args.kernel_size == 5

    def test_no_command_exits(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_find_no_subcommand_exits(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["find", "-i", "foo.log"])

    def test_version_exits(self, parser):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        assert exc.value.code == 0

    def test_split_slice_by(self, parser):
        args = parser.parse_args(["split", "-i", "foo.log", "10:20"])
        assert args.by == "10:20"

    def test_split_pattern_by(self, parser):
        pattern = r"[\w\d :-]+(INFO|ERROR)"
        args = parser.parse_args(["split", "-i", "foo.log", pattern])
        assert args.by == pattern


# ===========================================================================
# cmd_split — via mocked LogFile
# ===========================================================================


class TestCmdSplit:
    def _args(self, by, input_file, *, write=False, stdout=True, yaml=False, json=False):
        ns = argparse.Namespace(
            by=by,
            input=input_file,
            write=write,
            stdout=stdout,
            yaml=yaml,
            json=json,
        )
        return ns

    def test_no_input_exits(self, capsys):
        args = self._args("0", None)
        with pytest.raises(SystemExit):
            cmd_split(args)
        err = capsys.readouterr().err
        assert "required" in err.lower()

    def test_split_by_token(self, log_path, capsys):
        args = self._args("2", str(log_path))
        cmd_split(args)
        out = capsys.readouterr().out
        assert "INFO:" in out

    def test_split_by_slice(self, log_path, capsys):
        args = self._args("20:24", str(log_path))
        cmd_split(args)
        out = capsys.readouterr().out
        assert "INFO" in out

    def test_split_by_pattern(self, log_path, capsys):
        pattern = r"[\w\d :-]+(INFO|ERROR|WARNING)"
        args = self._args(pattern, str(log_path))
        cmd_split(args)
        out = capsys.readouterr().out
        assert "INFO" in out

    def test_split_json_output(self, log_path, capsys):
        args = self._args("2", str(log_path), json=True)
        cmd_split(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)
        assert "INFO:" in data

    def test_split_write_creates_files(self, log_path, tmp_path, capsys):
        args = self._args("2", str(log_path), write=True, stdout=False)
        cmd_split(args)
        written = list(log_path.parent.glob("test_logwarp_split_*.log"))
        assert len(written) >= 1


# ===========================================================================
# cmd_find_similar — via mocked LogFile
# ===========================================================================


class TestCmdFindSimilar:
    def _args(
        self, index, input_file, *, step=None, q=None,
        write=False, stdout=True, yaml=False, json=False,
    ):
        return argparse.Namespace(
            index=index,
            input=input_file,
            step=step,
            q=q,
            write=write,
            stdout=stdout,
            yaml=yaml,
            json=json,
        )

    def test_no_input_exits(self, capsys):
        args = self._args("0", None)
        with pytest.raises(SystemExit):
            cmd_find_similar(args)

    def test_similar_integer_index(self, log_path, capsys):
        args = self._args("1", str(log_path), q=1.0)
        cmd_find_similar(args)
        # Should produce output without crashing; content depends on vectorization
        capsys.readouterr()

    def test_similar_range_index(self, log_path, capsys):
        args = self._args("1,3", str(log_path), q=1.0, step=1)
        cmd_find_similar(args)
        capsys.readouterr()

    def test_similar_json_output(self, log_path, capsys):
        args = self._args("1", str(log_path), q=1.0, json=True)
        cmd_find_similar(args)
        out = capsys.readouterr().out
        # Result may be empty list; must be valid JSON
        data = json.loads(out)
        assert isinstance(data, list)

    def test_similar_kwargs_forwarded(self, log_path):
        """Verify step and q are forwarded to find_similar."""
        mock_logfile = MagicMock()
        mock_logfile.find_similar.return_value = []
        with patch("logwarp.cli.LogFile", return_value=mock_logfile):
            args = self._args("5", str(log_path), step=2, q=0.05)
            cmd_find_similar(args)
        mock_logfile.find_similar.assert_called_once_with(5, step=2, q=0.05)

    def test_similar_no_kwargs_when_none(self, log_path):
        """Verify step/q absent from kwargs when not provided."""
        mock_logfile = MagicMock()
        mock_logfile.find_similar.return_value = []
        with patch("logwarp.cli.LogFile", return_value=mock_logfile):
            args = self._args("5", str(log_path))
            cmd_find_similar(args)
        call_kwargs = mock_logfile.find_similar.call_args[1]
        assert "step" not in call_kwargs
        assert "q" not in call_kwargs


# ===========================================================================
# cmd_find_distinctive — via mocked LogFile
# ===========================================================================


class TestCmdFindDistinctive:
    def _args(
        self, input_file, *, height=None, prominence=None, distance=None,
        kernel_size=None, write=False, stdout=True, yaml=False, json=False,
    ):
        return argparse.Namespace(
            input=input_file,
            height=height,
            prominence=prominence,
            distance=distance,
            kernel_size=kernel_size,
            write=write,
            stdout=stdout,
            yaml=yaml,
            json=json,
        )

    def test_no_input_exits(self, capsys):
        args = self._args(None)
        with pytest.raises(SystemExit):
            cmd_find_distinctive(args)

    def test_distinctive_runs(self, log_path, capsys):
        args = self._args(str(log_path))
        cmd_find_distinctive(args)
        capsys.readouterr()

    def test_distinctive_with_explicit_params(self, log_path, capsys):
        args = self._args(str(log_path), height=0.01, prominence=0.01, distance=1, kernel_size=3)
        cmd_find_distinctive(args)
        capsys.readouterr()

    def test_distinctive_json_output(self, log_path, capsys):
        args = self._args(str(log_path), json=True)
        cmd_find_distinctive(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_kwargs_forwarded(self, log_path):
        """Verify all kwargs are forwarded to find_distinctive."""
        mock_logfile = MagicMock()
        mock_logfile.find_distinctive.return_value = []
        with patch("logwarp.cli.LogFile", return_value=mock_logfile):
            args = self._args(
                str(log_path),
                height=1.5, prominence=2.0, distance=10, kernel_size=5,
            )
            cmd_find_distinctive(args)
        mock_logfile.find_distinctive.assert_called_once_with(
            height=1.5, prominence=2.0, distance=10, kernel_size=5
        )

    def test_no_kwargs_when_none(self, log_path):
        """Verify absent kwargs when all params are None."""
        mock_logfile = MagicMock()
        mock_logfile.find_distinctive.return_value = []
        with patch("logwarp.cli.LogFile", return_value=mock_logfile):
            args = self._args(str(log_path))
            cmd_find_distinctive(args)
        call_kwargs = mock_logfile.find_distinctive.call_args[1]
        assert call_kwargs == {}


# ===========================================================================
# main() — integration smoke-tests
# ===========================================================================


class TestMain:
    def test_main_split(self, log_path, capsys):
        main(["split", "-i", str(log_path), "-o", "2"])
        out = capsys.readouterr().out
        assert "INFO:" in out

    def test_main_find_similar(self, log_path, capsys):
        main(["find", "-i", str(log_path), "similar", "-o", "1"])
        capsys.readouterr()

    def test_main_find_distinctive(self, log_path, capsys):
        main(["find", "-i", str(log_path), "distinctive", "-o"])
        capsys.readouterr()

    def test_main_no_args_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_main_split_write(self, log_path, capsys):
        main(["split", "-i", str(log_path), "-w", "2"])
        written = list(log_path.parent.glob("test_logwarp_split_*.log"))
        assert len(written) >= 1

    def test_main_find_distinctive_params(self, log_path, capsys):
        main(
            [
                "find", "-i", str(log_path),
                "distinctive", "-o",
                "--height", "0.01",
                "--prominence", "0.01",
                "--distance", "1",
                "--kernel-size", "3",
            ]
        )
        capsys.readouterr()


# ===========================================================================
# Common flags inherit correctly into find sub-commands
# ===========================================================================


class TestFindCommonFlagInheritance:
    """The ``find`` parent parser adds common flags; verify they reach handlers."""

    def test_find_similar_stdout_flag(self, parser):
        args = parser.parse_args(["find", "-o", "-i", "f.log", "similar", "5"])
        assert args.stdout is True

    def test_find_similar_write_flag(self, parser):
        args = parser.parse_args(["find", "-w", "-i", "f.log", "similar", "5"])
        assert args.write is True

    def test_find_similar_json_flag(self, parser):
        args = parser.parse_args(["find", "-j", "-i", "f.log", "similar", "5"])
        assert args.json is True

    def test_find_similar_yaml_flag(self, parser):
        args = parser.parse_args(["find", "-Y", "-i", "f.log", "similar", "5"])
        assert args.yaml is True

    def test_find_distinctive_stdout_flag(self, parser):
        args = parser.parse_args(["find", "-o", "-i", "f.log", "distinctive"])
        assert args.stdout is True
