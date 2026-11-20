# SPDX-FileCopyrightText: 2025 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause

import pytest

from logwarp.utils import (
    MmapList,
    SliceableArray,
    Vectorizer,
    find_timestamps,
    paddedzip,
)


def get_timestamps_data():
    return [
        ("2023-10-01 12:34:56", ["2023-10-01 12:34:56"]),
        ("2023-10-01T12:34:56Z", ["2023-10-01T12:34:56Z"]),
        ("Dec 10 07:07:45", ["Dec 10 07:07:45"]),
        ("2023-10-01 12:34:56.789+00:00", ["2023-10-01 12:34:56.789+00:00"]),
        ("10/01/2023 12:34:56", ["10/01/2023 12:34:56"]),
        ("2023/10/01 12:34:56", ["2023/10/01 12:34:56"]),
        ("01 Oct 2023 12:34:56", ["01 Oct 2023 12:34:56"]),
        ("Oct 01 12:34:56 2023", ["Oct 01 12:34:56 2023"]),
        ("12:34:56", ["12:34:56"]),
        ("12345.6789", ["12345.6789"]),
        ("1696118400", ["1696118400"]),
        (
            "Error occurred at 2023-10-01 12:34:56 in the system",
            ["2023-10-01 12:34:56"],
        ),
        (
            "Multiple timestamps: 2023-10-01 12:34:56 and 10/01/2023 12:34:56",
            ["2023-10-01 12:34:56", "10/01/2023 12:34:56"],
        ),
        ("No timestamp here", []),
        (
            "Random text 12345.6789 more text 1696118400 end",
            ["12345.6789", "1696118400"],
        ),
        ("20250910T153000", []),
        ("2023-10-01 12:34:56.789123", ["2023-10-01 12:34:56.789123"]),
        (
            "2023-10-01 12:34:56, another 2023-10-01 12:34:56",
            ["2023-10-01 12:34:56", "2023-10-01 12:34:56"],
        ),
        ("2023-10-01 123456", ["2023-10-01 123456"]),
    ]


def get_str_data():
    return [
        ["systemd[1]:", "Stopped", "target", "Bluetooth", "Support."],
        [
            "kernel:",
            "usb,1-1.1:",
            "reset",
            "full-speed",
            "USB",
            "device",
            "number",
            "6",
            "using",
            "xhci_hcd",
        ],
        ["systemd[1]:", "Reached", "target", "Bluetooth", "Support."],
        ["kernel:", "Bluetooth:", "hci0:", "command", "0xfc61", "tx", "timeout"],
        [
            "kernel:",
            "Bluetooth:",
            "hci0:",
            "RTL:",
            "Failed",
            "to",
            "generate",
            "devcoredump",
        ],
        ["kernel:", "Bluetooth:", "hci0:", "Resetting", "usb", "device."],
        [
            "kernel:",
            "Bluetooth:",
            "hci0:",
            "RTL:",
            "RTL:",
            "Read",
            "reg16",
            "failed",
            "(-110)",
        ],
    ]


def get_numeric_data():
    return [
        [1.0, 2.0, 3.0, 4.0],
        [3.0, 2.0],
        [2.1, 3.2, 1.1],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [0.1234, 123.0, 4],
        [1.2, 4.4, 544.32, 123, 123132, 130],
    ]


# ============================================================================
# Fixtures (Stateless: each returns fresh copies)
# ============================================================================


@pytest.fixture
def str_data():
    return get_str_data()


@pytest.fixture
def numeric_data():
    return get_numeric_data()


@pytest.fixture
def str_array():
    return SliceableArray(get_str_data())


@pytest.fixture
def float_array():
    return SliceableArray(get_numeric_data())


@pytest.fixture
def one_dim_array():
    return []


@pytest.fixture
def three_dim_array():
    return [[[]]]


@pytest.fixture
def single_string():
    return "lorem ipsum"


# ============================================================================
# find_timestamps Tests
# ============================================================================


@pytest.mark.parametrize("line, expected", get_timestamps_data())
def test_find_timestamps(line, expected):
    """Verify that find_timestamps identifies timestamps in various formats."""
    assert find_timestamps(line) == expected


# ============================================================================
# Vectorizer Tests
# ============================================================================


def test_vectorizer_character_types():
    """Verify _vectorize calculates scores for letters, digits, whitespace, punctuation, unicode."""
    v = Vectorizer(tokenize=True)
    # Empty token
    assert v._vectorize("") == 0.0

    # ASCII letters: score += 1
    assert v._vectorize("abc") == 1.0

    # Digits: score += 2
    assert v._vectorize("123") == 2.0

    # Whitespace: score += 3
    assert v._vectorize(" \t") == 3.0

    # Punctuation: score += 4
    assert v._vectorize("!?:") == 4.0

    # Other / Unicode: score += 5
    assert v._vectorize("ą€") == 5.0

    # Compound token: 1 (letter) + 2 (digit) + 3 (space) + 4 (punct) + 5 (unicode) = 15 / 5 = 3.0
    assert v._vectorize("a1 !ą") == 3.0


def test_vectorizer_call_tokenize_true():
    """Verify Vectorizer __call__ when tokenize is True."""
    v = Vectorizer(tokenize=True)
    batch = ["a 1", "b 2"]
    res = v(batch)
    assert res == [[1.0, 2.0], [1.0, 2.0]]


def test_vectorizer_call_tokenize_false():
    """Verify Vectorizer __call__ when tokenize is False."""
    v = Vectorizer(tokenize=False)
    batch = ["a 1", "b 2"]
    res = v(batch)
    # 'a' (1) + ' ' (3) + '1' (2) = 6 / 3 = 2.0
    assert res == [[2.0], [2.0]]


# ============================================================================
# MmapList Tests
# ============================================================================


def test_mmap_list_init_str_and_len(tmp_path):
    """Verify MmapList initialization from string path and its length."""
    fpath = tmp_path / "test.log"
    fpath.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    ml = MmapList(str(fpath))
    assert len(ml) == 4
    assert ml[0] == "line 1"
    assert ml[1] == "line 2"
    assert ml[2] == "line 3"


def test_mmap_list_init_path(tmp_path):
    """Verify MmapList initialization from Path object."""
    fpath = tmp_path / "test_path.log"
    fpath.write_text("first\nsecond\n", encoding="utf-8")

    ml = MmapList(fpath)
    assert ml[0] == "first"
    assert ml[1] == "second"


def test_mmap_list_slice(tmp_path):
    """Verify MmapList slice indexing with default and explicit step."""
    fpath = tmp_path / "test_slice.log"
    fpath.write_text("line 0\nline 1\nline 2\nline 3\n", encoding="utf-8")

    ml = MmapList(fpath)
    assert ml[0:2] == ["line 0", "line 1"]
    assert ml[1:3:1] == ["line 1", "line 2"]


def test_mmap_list_setitem(tmp_path):
    """Verify MmapList __setitem__ raises NotImplementedError."""
    fpath = tmp_path / "test_readonly.log"
    fpath.write_text("read only\n", encoding="utf-8")

    ml = MmapList(fpath)
    with pytest.raises(NotImplementedError, match="MmapList is read-only"):
        ml[0] = "forbidden"


def test_mmap_list_del(tmp_path):
    """Verify MmapList cleanup on __del__ and handling None handles."""
    fpath = tmp_path / "test_del.log"
    fpath.write_text("del test\n", encoding="utf-8")

    ml = MmapList(fpath)
    ml.__del__()
    assert ml._map.closed

    # Direct invocation when _map and _f are None
    ml._map = None
    ml._f = None
    ml.__del__()


# ============================================================================
# SliceableArray Tests
# ============================================================================


def test_sliceable_array_uniform():
    """Verify uniform property for empty, uniform, and non-uniform arrays."""
    assert SliceableArray([]).uniform is True
    assert SliceableArray([[1, 2], [3, 4]]).uniform is True
    assert SliceableArray([[1, 2], [3]]).uniform is False


def test_sliceable_array_copy():
    """Verify copy returns an equal but distinct SliceableArray instance."""
    sa = SliceableArray([[1.0, 2.0]])
    cp = sa.copy()
    assert cp == sa
    assert cp is not sa


def test_sliceable_array_extend():
    """Verify extend appends elements and updates shape."""
    sa = SliceableArray([[1, 2]])
    sa.extend([[3, 4], [5, 6]])
    assert len(sa) == 3


def test_getitem(str_array, str_data):
    """Verify indexing by non-contiguous list, slice, and single index."""
    non_contiguous = str_array[[1, 2, 4]]
    assert non_contiguous == [str_data[1], str_data[2], str_data[4]]
    assert isinstance(non_contiguous, SliceableArray), (
        "Getting a non-contiguous list-indexed fragment of a SliceableArray should yield a SliceableArray."
        f"Got: {type(non_contiguous)}"
    )
    assert non_contiguous != str_array

    contiguous = str_array[1:3]
    assert contiguous == str_data[1:3]
    assert isinstance(contiguous, SliceableArray), (
        f"Getting a contiguous slice of a SliceableArray should yield a SliceableArray. Got: {type(contiguous)}"
    )

    row = str_array[0]
    assert row == str_data[0]
    assert isinstance(row, list), (
        "Getting a single row from SliceableArray should yield a list instance. "
        f"Got: {type(row)}"
    )


def test_chunks(float_array: SliceableArray, numeric_data):
    """Verify chunks iteration with non-zero step and padding."""
    chunk_size = 3
    chunk_step = 2
    for idx, chunk in enumerate(float_array.chunks(chunk_size, stride=chunk_step)):
        start = idx * chunk_step
        stop = start + chunk_size
        if stop < len(numeric_data):
            assert chunk == numeric_data[start:stop]
        else:
            maxlen = max(len(r) for r in numeric_data)
            pad_row = [0.0] * maxlen
            pad_array = [pad_row] * (len(numeric_data) - start - 1)
            assert chunk == (numeric_data[start:] + pad_array)


def test_chunks_negative_size(float_array: SliceableArray, numeric_data):
    """Verify chunks iteration with non-zero step and padding."""
    chunk_size = -4
    chunk_step = 2
    for idx, chunk in enumerate(float_array.chunks(chunk_size, stride=chunk_step)):
        start = idx * chunk_step
        stop = start + chunk_size
        if stop < len(numeric_data):
            assert chunk == numeric_data[start:stop]
        else:
            maxlen = max(len(r) for r in numeric_data)
            pad_row = [0.0] * maxlen
            pad_array = [pad_row] * (len(numeric_data) - start - 1)
            assert chunk == (numeric_data[start:] + pad_array)


def test_chunks_step_zero(float_array: SliceableArray, numeric_data):
    """Verify chunks iteration with chunk_step=0 (skips size rows)."""
    with pytest.raises(ValueError):
        for c in float_array.chunks(size=2, stride=0):
            print(c)


def test_similarities():
    """Verify similarity calculation between numeric SliceableArrays."""
    self_arr = SliceableArray([[1.5, 2.2, 3.1, 4.67, 5.32, 6.33, 7.11, 9.32]])
    other = SliceableArray([[1.5, 2.2, 3.1, 1.67, 4.32, 6.33, 7.11, 9.32]])
    with pytest.raises(TypeError, match="Can only compare with another SliceableArray"):
        _ = self_arr % [[1, 2, 3]]

    assert self_arr % self_arr == (0.0, 0)
    assert self_arr % other == (3.0, 2)
    assert other % self_arr == (3.0, 2)
    assert self_arr.__rmod__(other) == (3.0, 2)


def test_paddedzip():
    a = [1, 2, 3]
    b = [1, 2, 3, 4]
    z = list(paddedzip(a, b))
    assert z == [(1, 1), (2, 2), (3, 3), (0, 4)]
    assert [] == list(paddedzip([], []))
    assert [(1, 1), (2, 2), (3, 3)] == list(paddedzip([1, 2, 3], [1, 2, 3]))


def test_similarity_errors():
    """Verify similarity error handling for non-uniform shape and non-numeric dtype."""
    sa1 = SliceableArray([[1.0, 2.0]])
    sa2 = SliceableArray([[1.0, 2.0, 3.0]])
    assert sa1 % sa2 == (3.0, 1)
    # Similarity calculation needs to account for different lengths of compared
    # arrays. Pad the shorter arrays with zeros so the difference shows up in
    # the score.
    assert sa2 % sa1 == (3.0, 1)

    sa_str = SliceableArray([["a", "b"]])
    with pytest.raises(TypeError):
        _ = sa_str % sa_str
