# SPDX-FileCopyrightText: 2026 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause
import mmap
import re
import string
from collections import UserList
from collections.abc import Iterable
from copy import copy
from pathlib import Path
from typing import Any


def find_timestamps(line: str) -> list[str]:
    """Finds timestamps in a log line.

    Parameters
    ----------
    line : str
        Log line to search for timestamps.

    Returns
    -------
    list[str]
        List of timestamps found in the log line.
    """

    # Regex pattern to match timestamps in various formats
    timestamp_pattern = re.compile(
        r"\b(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?|"  # ISO 8601
        r"\b(?:\d{4}-\d{2}-\d{2}[ T]\d{6})|"  # Poorly formed ISO 8601
        r"\d{2}/\d{2}/\d{4}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?|"  # MM/DD/YYYY HH:MM:SS
        r"\d{4}/\d{2}/\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?|"  # YYYY/MM/DD HH:MM:SS
        r"\b\d{1,2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?|"  # DD Mon YYYY HH:MM:SS
        r"\b[A-Za-z]{3} \d{1,2} \d{2}:\d{2}:\d{2}(?:\.\d+)?(?: \d{4})?\b|"  # Mon DD HH:MM:SS [YYYY]
        r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b)"  # HH:MM:SS
        r"|\b\d+\.\d+\b"  # monotonic timestamps like 12345.6789
        r"|\b\d{8,}\b"  # long integers like 1696118400 (Unix timestamps)
    )
    return timestamp_pattern.findall(line)


class Vectorizer:
    def __init__(self, tokenize: bool):
        self.tokenize = tokenize

    def _vectorize(
        self,
        token: str,
    ) -> float:
        score = 0.0
        length = 0
        for s in token:
            s = str(s)
            length += 1
            if s in string.ascii_letters:
                score += 1
            elif s in string.digits:
                score += 2
            elif s in string.whitespace:
                score += 3
            elif s in string.punctuation:
                score += 4
            else:
                score += 5
        return score / length if length else 0.0

    def __call__(self, batch):
        if self.tokenize:
            return [
                [self._vectorize(token) for token in line.split(" ")] for line in batch
            ]
        return [[self._vectorize(line)] for line in batch]


class MmapList:
    _line_offsets: list[int]
    _f: Any
    _map: mmap.mmap

    def __init__(self, file_path: str | Path):
        with open(file_path, "r", encoding="utf-8") as f:
            fmap = mmap.mmap(
                f.fileno(), 0, access=mmap.ACCESS_READ, flags=mmap.MAP_SHARED
            )
            self._line_offsets = [0]
            while fmap.readline():
                self._line_offsets.append(fmap.tell())

            self._f = f
            self._map = fmap

    def __del__(self):
        if self._map:
            self._map.close()
        if self._f:
            self._f.close()

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.start, index.stop, index.step or 1
            self._map.seek(self._line_offsets[start])
            return [
                str(self._map.readline().decode()).strip()
                for _ in range(start, stop, step)
            ]
        else:
            start, stop, step = index, index + 1, 1
            self._map.seek(self._line_offsets[start])
            return str(self._map.readline().decode()).strip()

    def __setitem__(self, index, value):
        raise NotImplementedError("MmapList is read-only.")

    def __len__(self):
        return len(self._line_offsets)


def paddedzip(a: Iterable, b: Iterable):
    diff = len(a) - len(b)
    if diff == 0 or (len(a) == 0 and len(b) == 0):
        # Nothing to see here, move along
        return zip(a, b)
    try:
        # try to derive type of the iterable's items
        T = type(a[0])
    except KeyError:
        T = type(b[0])
    shorter, longer = (a, b) if diff < 0 else (b, a)
    shorter.extend([T()] * abs(diff))
    return zip(shorter, longer)


class SliceableArray(UserList):
    """List with additional generator to iterate over portions of the content,
    yielding chunks of the same size each iteration.

    Examples:
    ---------
    >>> arr = SliceableArray([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]])
    >>> arr[1]
    [4, 5, 6]
    >>> arr[1:3]
    [[4, 5, 6], [7, 8, 9]]
    >>> arr[[0, 2]]
    [[1, 2, 3], [7, 8, 9]]
    >>> for chunk in arr.chunks(2, 2):
    ...     print(chunk)
    ...
    [[1, 2, 3], [4, 5, 6]]
    [[7, 8, 9], [10, 11, 12]]
    """

    def __getitem__(self, i):
        if isinstance(i, list):
            return SliceableArray([line for idx, line in enumerate(self) if idx in i])
        if isinstance(i, int):
            return self.data[i]
        return SliceableArray(super().__getitem__(i))

    def __sub__(self, other) -> "SliceableArray":
        if not isinstance(other, SliceableArray):
            raise TypeError("Can only subtract two SliceableArray instances")
        return SliceableArray(
            [a - b for a, b in paddedzip(row_a, row_b)]
            for row_a, row_b in zip(self.data, other.data)
        )

    def __rsub__(self, other) -> "SliceableArray":
        if not isinstance(other, "SliceableArray"):
            raise TypeError("Can only subtract two SliceableArray instances")
        return SliceableArray(
            [b - a for a, b in paddedzip(row_a, row_b)]
            for row_a, row_b in zip(self.data, other.data)
        )

    def __mod__(self, other):
        return self.similarity(other)

    __rmod__ = __mod__

    @property
    def uniform(self) -> bool:
        """Returns `True` if the all rows of the array have the same length,
        `False` otherwise.
        """
        return all(len(i) == len(self[0]) for i in self if self)

    def max(self) -> float:
        def absmax(iter: Iterable):
            return max([abs(i) for i in iter])

        return max([absmax(row) for row in self.data])

    def copy(self) -> "SliceableArray":
        """Returns a copy of self."""
        return copy(self)

    def chunks(self, size: int = 1, stride: int = 1):
        """Generator which yields chunks of the array of the specified size.

        Parameters
        ----------
        size : int, optional
            Number of rows to yield at a time, by default 1
        stride : int, optional
            This parameter determines the size of the step to use when skipping
            rows. Defaults to 1.

        For example, when `stride` equals `size`:
        ```
        0 1 2 3 4 5 6 7 8
        |---|---|---|---|        # Skips `size` rows at a time, yielding chunks
        ```

        When `stride` == 1:

        ```
        0 1 2 3 4 5 6 7 8
        |---|
          |---|
            |---|                # Iterates row by row, yielding chunk for each
              |---|
        ```

        Yields
        ------
        list
            List of rows of the array.
        """
        if stride == 0:
            raise ValueError("I can't walk in place with stride 0.")
        _len = len(self)
        for i in range(0, _len, stride):
            # Using slices as index will return a 2D array
            _next = self[i : i + size]

            if i + size > _len:
                # Try to pad with values of the same type as the rest of the
                # array. Of course, it won't help us if the array holds mixed
                # types (which it shouldn't).
                T = type(_next.data[-1][0]) if len(_next.data[-1]) else float
                # Add extra rows to always return a chunk of the same shape
                # Make sure that we're adding a 2D array here, keeping the shape
                # of the array.
                rows = [[T()] * len(_next.data[-1])] * (size - len(_next))
                _next.extend(rows)

            yield _next

    def similarity(self, other: "SliceableArray") -> tuple[float, int]:
        """Calculates similarity of two `SliceableArray`s (which might be
        slices of a larger `SliceableArray`s themselves). The compared arrays
        must have the same shapes.

        The similarity is calculated as the maximum absolute difference between
        the values in the arrays. Additionally, the number of differing values
        between the arrays is also returned. Exact method of calculating the
        difference depends on the type of the data stored in the array.

        Example:
        >>> slice_a = SliceableArray([[1.0, 2.0, 3.0, 4.0]])
        >>> slice_b = SliceableArray([[1.0, 2.0, 4.0, 4.5]])
        >>> slice_a % slice_b
        (1.0, 2)
        >>> slice_b % slice_a
        (1.0, 2)

        In this example, `slice_a` and `slice_b` differ only in one position.
        The calculated difference of the values is [[0.0, 0.0, -1.0 -0.5]].

        The maximum absolute difference is 1.0, and the number of different
        values is 2.

        Parameters
        ----------
        other : SliceableArray
            Array to calculate similarity metric with.

        Returns
        -------
        tuple[float, int]
            Tuple with the comparison results:
            (maximum absolute difference, number of different values)

        Raises
        ------
        ValueError
            _description_
        """
        if not isinstance(other, SliceableArray):
            raise TypeError("Can only compare with another SliceableArray")

        assert len(self) == len(other), "Both arrays must have the same length"

        diff = other - self
        # When comparing two lines, np.nonzero() always returns a tuple,
        # even if with a single element.
        diff_max = diff.max()  # Easier to keep it here for debugging
        diff_count = sum([sum([1 for i in row if i != 0]) for row in diff.data])
        return diff_max, diff_count
