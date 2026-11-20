# SPDX-FileCopyrightText: 2025 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause

import pytest

from logwarp.errors import PatternGroupError
from logwarp.logfile import LogFile, LogFileSplit
from logwarp.utils import SliceableArray


def get_sample_log_lines():
    return [
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
def sample_log_lines():
    """Returns a fresh list of sample log lines."""
    return get_sample_log_lines()


@pytest.fixture
def log_file():
    """Returns a fresh LogFile object."""
    return LogFile(get_sample_log_lines())


# ============================================================================
# LogFile Initialization & Indexing Tests
# ============================================================================


def test_log_file_init(log_file, sample_log_lines):
    """Verify that the LogFile object is initialized correctly."""
    for i, line in enumerate(sample_log_lines):
        assert log_file[i] == line


def test_log_file_len(log_file, sample_log_lines):
    """Verify that the LogFile object has the correct length."""
    assert len(log_file) == len(sample_log_lines)


def test_log_file_getitem_by_int(log_file, sample_log_lines):
    """Verify that the LogFile object can be indexed by integer."""
    assert log_file[0] == sample_log_lines[0]


def test_log_file_getitem_by_slice(log_file, sample_log_lines):
    """Verify that the LogFile object can be indexed by slice."""
    # Standard Python slicing
    assert log_file[1:3] == sample_log_lines[1:3]

    # Modified step parameter
    assert log_file[::2] == sample_log_lines[::2]


def test_log_file_iter(log_file, sample_log_lines):
    """Verify that iterating over a LogFile yields lines."""
    for idx, line in enumerate(log_file):
        assert line == sample_log_lines[idx]


def test_log_file_getitem_list(log_file, sample_log_lines):
    """Verify that a list of integers can be used to index the LogFile object."""
    assert log_file[[0, 2]] == [sample_log_lines[0], sample_log_lines[2]]


def test_log_file_init_from_file_str(tmp_path, sample_log_lines):
    """Verify initializing LogFile from a string file path."""
    log_path = tmp_path / "test.log"
    log_path.write_text("\n".join(sample_log_lines) + "\n", encoding="utf-8")

    lf = LogFile(str(log_path))
    assert lf._content == sample_log_lines


def test_log_file_init_from_file_path(tmp_path, sample_log_lines):
    """Verify initializing LogFile from a Path object."""
    log_path = tmp_path / "test_path.log"
    log_path.write_text("\n".join(sample_log_lines) + "\n", encoding="utf-8")

    lf = LogFile(log_path)
    assert lf._content == sample_log_lines


def test_log_file_init_from_tuple(sample_log_lines):
    """Verify initializing LogFile from a tuple."""
    lf = LogFile(tuple(sample_log_lines))
    assert lf._content == sample_log_lines


def test_log_file_init_invalid_type():
    """Verify TypeError when initializing LogFile with unsupported type."""
    with pytest.raises(TypeError, match="Don't know how to make a LogFile from"):
        LogFile(12345)


def test_log_file_from_list_filters_non_strings(log_file):
    """Verify from_list strips strings and ignores non-string elements."""
    result = log_file.from_list([" line 1 \n", 42, None, "line 2\t"])
    assert result == ["line 1", "line 2"]


# ============================================================================
# find_similar Tests
# ============================================================================


def test_find_similar_not_vectorized(log_file):
    """Verify AttributeError when find_similar is called before vectorize."""
    with pytest.raises(AttributeError, match="LogFile has not been vectorized yet"):
        log_file.find_similar(0)


def test_find_similar_non_contiguous_slice(log_file):
    """Verify ValueError when a non-contiguous slice is used."""
    log_file.vectorize()
    with pytest.raises(ValueError, match="Only contiguous slices are supported"):
        log_file.find_similar(slice(0, 4, 2))


def test_find_similar_int_index():
    """Verify find_similar using an integer index."""
    lines = [
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
    lf = LogFile(lines)
    lf.vectorize()
    similar = lf.find_similar(1, q=1.0)
    assert isinstance(similar, list)
    assert 1 not in similar


def test_find_similar_slice_step_options():
    """Verify find_similar with contiguous slices and various step settings."""
    lines = [
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
    lf = LogFile(lines)
    lf.vectorize()

    # step=1 (not quick mode)
    res_step1 = lf.find_similar(slice(1, 3), step=1, q=1.0)
    assert isinstance(res_step1, list)

    # step=0 (defaults to chunk_len, quick mode if chunk_len > 1)
    res_step0 = lf.find_similar(slice(1, 3), step=0, q=1.0)
    assert isinstance(res_step0, list)

    # step=-1 (default, defaults to chunk_len)
    res_default = lf.find_similar(slice(1, 3), step=-1, q=1.0)
    assert res_default == res_step0

    # step=2 (quick mode)
    res_step2 = lf.find_similar(slice(1, 3), step=2, q=1.0)
    assert isinstance(res_step2, list)


# ============================================================================
# find_prominent Tests
# ============================================================================


def test_find_prominent_auto_params():
    """Verify find_prominent with automatic peak detection parameter tuning."""
    lines = ["short"] * 10 + ["super long message " * 5] * 5 + ["short"] * 10
    lf = LogFile(lines)
    lf.vectorize()
    peaks = lf.find_distinctive(kernel_size=3, distance=1)
    assert isinstance(peaks, list)
    assert len(peaks) > 0


def test_find_prominent_explicit_params_and_even_kernel():
    """Verify find_prominent with even kernel_size and explicit prominence/height."""
    lines = ["short"] * 10 + ["super long message " * 5] * 5 + ["short"] * 10
    lf = LogFile(lines)
    lf.vectorize()

    # kernel_size=4 is even, will trigger kernel_size += 1
    peaks = lf.find_distinctive(kernel_size=4, prominence=0.01, height=0.01, distance=1)
    assert isinstance(peaks, list)


# ============================================================================
# vectorize Tests
# ============================================================================


def test_log_file_vectorize_sequential(log_file):
    """Verify sequential vectorization with tokenize=True and tokenize=False."""
    log_file.vectorize(True, False)
    assert isinstance(log_file._vectorized, SliceableArray)
    assert len(log_file._vectorized) == len(log_file)

    log_file.vectorize(False, False)
    assert len(log_file._vectorized) == len(log_file)


def test_log_file_vectorize_parallel():
    """Verify parallel vectorization with tokenize=True and tokenize=False."""
    lines = [f"2023-01-01 1{i}:00:00 INFO: Message {i}" for i in range(8)]
    lf = LogFile(lines)

    # Parallel with default n_workers (4)
    lf.vectorize(True, True)
    assert len(lf._vectorized) == 8

    # Parallel with custom n_workers (2) and tokenize=False
    lf.vectorize(False, True, n_workers=2)
    assert len(lf._vectorized) == 8


def test_split_by_index(log_file):
    """Verify log file is correctly split by using fixed string offsets."""
    # Assuming the log file looks like this:
    # "2023-01-01 10:00:00 INFO: Starting program",
    # "2023-01-01 11:00:00 INFO: Heartbeat",
    # "2023-01-01 12:00:00 INFO: Heartbeat",
    # "2023-01-01 12:59:02 ERROR: Something went wrong",
    # "2023-01-01 13:00:00 INFO: Heartbeat",
    # "2023-01-01 14:00:00 INFO: Heartbeat",
    # "2023-01-01 14:32:12 WARNING: This is weird",
    # "2023-01-01 15:00:00 INFO: Heartbeat",
    # "2023-01-01 16:00:00 INFO: Heartbeat",

    # Splitting always returns +1 split bucket: outliers
    split: LogFileSplit = log_file.unravel((20, 24))
    assert len(split) == 4
    assert len(split["INFO"]) == 7
    assert len(split["ERRO"]) == 1
    assert len(split["WARN"]) == 1


def test_split_by_token(log_file):
    """Verify log file is correctly split by using selected token."""
    # Splitting by token at index 2, log severity
    split = log_file.unravel(2)
    assert len(split) == 4
    assert len(split["INFO:"]) == 7
    assert len(split["ERROR:"]) == 1
    assert len(split["WARNING:"]) == 1


def test_split_by_pattern(log_file):
    """Verify log file is correctly split by using regular expression."""
    # That's some lazy regexp writing right there...
    pattern = r"[\w\d :-]+(INFO|ERROR|WARNING)"
    split = log_file.unravel(pattern)
    assert len(split) == 4
    assert len(split["INFO"]) == 7
    assert len(split["ERROR"]) == 1
    assert len(split["WARNING"]) == 1


def test_split_by_invalid_params(log_file):
    """Verify exception is raised when using invalid type of parameter."""
    with pytest.raises(TypeError):
        log_file.unravel(slice(1, 3))
        log_file.unravel()


def test_split_invalid_patterns(log_file):
    """Verify exceptions are raised when using incorrectly defined regular expression."""
    with pytest.raises(ValueError):
        pattern = r"[\w\\d :-]+((INFO|ERROR|WARNING)"
        log_file.unravel(pattern)
    with pytest.raises(PatternGroupError):
        pattern = r"[\w\d :-]+INFO|ERROR|WARNING"
        log_file.unravel(pattern)


def test_split_outliers():
    """Verify that lines which failed to split at a token are added as outliers."""
    log_file = LogFile(
        [
            "2023-01-01 10:00:00 INFO: Starting program",
            "2023-01-01 11:00:00 INFO: Heartbeat",
        ]
    )
    split = log_file.unravel(4)
    # Splitting by token index 4, but the second line goes only up to 3.
    # Failed split goes to outliers
    assert [log_file[1]] == split["outliers"].lines

    split = log_file.unravel((35, 42))
    assert [log_file[1]] == split["outliers"].lines

    pattern = r"[\w\d :-]+(ERROR)"
    split = log_file.unravel(pattern)
    assert log_file.lines == split["outliers"].lines
