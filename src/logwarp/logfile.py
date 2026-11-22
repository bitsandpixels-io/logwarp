# SPDX-FileCopyrightText: 2026 Lukasz Tuz <lukasz@bitsandpixels.io>
# SPDX-License-Identifier: BSD-3-Clause

"""Implements a representation of a log file that can be searched and analyzed
by other modules.

This module provides a class, `LogFile`, that represents a log file as a list
of `LogLine` objects. The `LogFile` objects are subscriptable and iterable,
allowing for using integers, slices, and lists as indices.
"""

import re
from collections import UserString
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import overload

import numpy as np
import scipy

from logwarp.errors import PatternGroupError
from logwarp.utils import SliceableArray, Vectorizer


class LogSignalProcessor:
    """Implements signal processing methods for log files."""

    @staticmethod
    def smooth(signal: np.ndarray, window_size: int = 10) -> np.ndarray:
        """Smooths a signal convolution with a rectangular window."""
        return np.convolve(signal, np.ones(window_size) / window_size, mode="valid")

    @staticmethod
    def tune_peak_detection(signal: np.ndarray) -> tuple[float, float]:
        """Tunes parameters for peak detection in a signal.

        Based on signals peak-to-peak value, calculates prominence and height
        for `scipy.signal.find_peaks()`

        Returns
        -------
        tuple[float, float]
            Tuple of prominence and height
        """
        ptp = np.ptp(signal)
        return 0.66 * ptp, 0.33 * ptp


class LogLine(UserString):
    """Representation of a single log line.

    Essentially, a string, but with extra read-only properties, common for log
    files:

    - line number; carries the number of the line in the original file.
      Immutable, even when file is split, filtered, or merged.
    - timestamp; optional. If there is a time stamp embedded in the log line
      and it is correctly identified, this property holds its value as datetime
    - level; optional, keeps information about log level of the line
    """

    _number: int
    _timestamp: datetime
    _level: str

    def __init__(self, line: str, /, n: int = -1):
        self._number = n
        super().__init__(line)

    @property
    def number(self):
        return self._number

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def level(self):
        return self._level


class LogFileSplit(dict):
    """Dict-like storage for split log file buckets. Guarantees existence of the
    'outliers' bucket."""

    OUTLIERS = "outliers"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self[LogFileSplit.OUTLIERS] = []


class LogFile:
    _content: list[str | LogLine]
    _vectorized: SliceableArray[float]
    _hashes: dict

    def __init__(self, log_file, **kwargs):
        """Main class for interacting with a log file.

        Implements indexing by integers (single line), slices, and lists (including
        non-contiguous ranges of lines).

        Parameters
        ----------
        log_file : str | Path | list | tuple
            Path to the log file to load (`str` or `Path`) or content of a log
            file in form of an iterable with strings.

        Keyword Arguments
        -----------------
        kwargs : Any
            Arguments passed directly to the `SliceableArray` constructor.

        Examples
        --------
        >>> log_file = LogFile(["Line 1", "Line 2", "Line 3", "Line 4"])
        >>> log_file[0]
        'Line 1'
        >>> log_file[1:3]  # Slice returns list of lists
        ['Line 2', 'Line 3']
        >>> log_file[[0, 2]]
        ['Line 1', 'Line 3']
        >>> log_file[::2]
        ['Line 1', 'Line 3']
        """
        if isinstance(log_file, (str, Path)):
            self._content = self.from_file(log_file)
        elif isinstance(log_file, (list, tuple)):
            self._content = self.from_list(log_file)
        else:
            raise TypeError(f"Don't know how to make a LogFile from {type(log_file)}")

        # Store intermittent results, traces, etc. here
        self._vectorized = SliceableArray([])
        self._hashes = {}

    def __getitem__(self, key):
        if isinstance(key, list):
            return [line for idx, line in enumerate(self) if idx in key]
        return self._content[key]

    def __setitem__(self, key, value):
        raise AttributeError("LogFile is read only")

    def __len__(self):
        return len(self._content)

    def from_file(self, log_file: str | Path):
        """Creates a LogFile object from a file path."""
        with open(log_file, "r", encoding="utf-8") as lf:
            return self.from_list(lf.readlines())  # type: ignore

    def from_list(self, lines: list[str] | list[LogLine]):
        """Creates a LogFile object from a list of lines."""

        def maybe_convert(line, n=-1):
            if isinstance(line, str):
                return LogLine(line.strip(), n=n)
            if isinstance(line, LogLine):
                return line
            return None

        _logfile = [
            converted
            for n, line in enumerate(lines)
            if (converted := maybe_convert(line, n=n))
        ]
        return _logfile

    @property
    def lines(self):
        return self._content

    def vectorize(
        self,
        tokenize: bool = True,
        parallel: bool = False,
        /,
        **kwargs,
    ) -> None:
        """Convert the log file into an array of floating-point numbers.

        Applies the vectorization mechanism to the log file and creates an array
        of numbers.

        Parameters
        ----------
        tokenize : bool, optional
            Flag controls if the log line should be split into tokens before
            vectorization, by default True
        parallel : bool, optional
            Flag controlling if the vectorization process is to be executed in
            parallel, using ProcessPoolExecutor. Defaults to False.

        Returns
        -------
        SliceableArray
            Instance of the `SliceableArray` class with the calculated vectors.

        Raises
        ------
        ValueError
            Requested an invalid (negative or zero) number of parallel workers.
        """
        if parallel:
            n_workers = kwargs.get("n_workers", 4)
            if n_workers <= 0:
                raise ValueError(f"Cannot split the data into {n_workers} pieces.")
            if n_workers == 1:
                batches = self._content

            split_size = len(self._content) // n_workers
            batches = [
                self._content[i * split_size : (i + 1) * split_size]
                for i in range(n_workers)
            ]

            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                results = pool.map(Vectorizer(tokenize), batches)

            scores = []
            for result in list(results):
                scores.extend(result)

        else:
            v = Vectorizer(tokenize)
            if tokenize:
                scores = [
                    [v._vectorize(token) for token in line.split(" ")] for line in self
                ]
            else:
                scores = [[v._vectorize(line)] for line in self]

        self._vectorized = SliceableArray(scores)

    def find_similar(
        self, index: int | slice, step: int = 0, q: float = 0.001
    ) -> list[int]:
        """Find log entries similar to the one at the given index.

        Parameters
        ----------
        index : int | slice
            Index of the log entry to compare. When using slice, it must be
            contiguous.
        step : int, optional
            How many rows to step over when iterating over the log file's lines.
            Defaults to 0, in which case, size of the reference chunk will be
            used.
        q : float, optional
            Value of quantile used to determine if a chunk is to be considered
            similar to the reference.

        Returns
        -------
        list[int]
            List of indices of similar log entries.

        Raises
        ------
        ValueError
            If the provided index is not contiguous - slice step is not 1.

        AttributeError
            When attempting to run similarity check on a log file which hasn't
            been vectorized yet. Normally shouldn't happen, as the vectorization
            is done automatically in the init.
        """

        # Slide through the entire scores array, line by line, comparing each
        # chunk to the reference. Skip comparing the chunk at `index`. Fun part:
        # we can do this in parallel!
        # Comparison extracted to a separate function to catch exceptions,
        # reporting the local variables from the list comprehension.
        if not self._vectorized:
            raise AttributeError(
                "LogFile has not been vectorized yet. Run vectorize() first."
            )

        if isinstance(index, slice) and index.step is not None and index.step > 1:
            raise ValueError("Only contiguous slices are supported.")

        if isinstance(index, slice) and (not index.start or not index.stop):
            raise ValueError("Can't calculate similarity to a slice without bounds.")

        if isinstance(index, int):
            index = slice(index, index + 1)
        chunk_len = index.stop - index.start

        # Vectorized reference chunk (the one we're looking for similar entries to)
        # At this point, index should be a slice regardless of the initial type.
        ref: SliceableArray = self._vectorized[index]
        if not ref:
            raise ValueError("Trying to compare to an empty array.")

        # Compute similarity scores between the reference and the rest of the
        # file.
        chunk_step = step if step > 0 else chunk_len

        # Assume it's "quick" mode whenever the step is greater than 1.
        quick = chunk_step != 1
        similarities = [
            chunk % ref
            for chunk in self._vectorized.chunks(chunk_len, stride=chunk_step)
        ]
        threshold = np.quantile(similarities, q, axis=0)

        similar_indices = [
            idx
            for idx, score in enumerate(similarities)
            # Don't compare with the reference chunk...
            if slice(idx, idx + chunk_len) != index
            # ...don't go out of bounds...
            and (
                (idx + 1) * chunk_len < len(self._vectorized)
                if quick
                else idx + chunk_len < len(self._vectorized)
            )
            and score[0] < threshold[0]
            and score[1] < threshold[1]
        ]
        return similar_indices

    def find_distinctive(
        self,
        **kwargs,
    ) -> "list[LogFile]":
        """Find log entries with prominent peaks.

        Method helps find relevant information in a noisy log file. It uses a
        median filter to reduce the noise (controlled by the `kernel_size`), and
        then finds peaks in the resulting signal (controlled by the `distance`,
        `prominence` and `height` parameters).

        Returns a list of log entries corresponding to the detected peaks, with
        added lines of context.

        If `prominence` or `height` is not provided, it will be automatically
        calculated based on the peak-to-peak range of the signal.

        Parameters
        ----------
        log_file : LogFile
            Log file to find peaks in.
        context_size : int, optional
            Context size adds additional lines around the detected peaks.
            Default is 5.
        kernel_size : int, optional
            Kernel size to use when de-noising the log file, by default 5.
        distance : int, optional
            Minimal distance between peaks, by default 10.
        prominence : float, optional
            Prominence to use when finding peaks. When not set, will be
            automatically determined from the signal's parameters. By default
            None.
        height : float, optional
            Minimal distance between peak and surrounding samples. When not set,
            will be automatically determined from the signal's parameters. By
            default None.
        fn : Callable, optional
            User-defined function for reducing the vectorized log file into a 1D
            series. Must follow signature `fn(data: SliceableArray) ->
            list[float] | SliceableArray`.
            If not provided, square root of sum will be used.

        Returns
        -------
        list[LogFile]
            List of detected peaks.
        """

        def rms(data):
            return [np.sqrt(np.sum(r)) for r in data]

        kernel_size: int = kwargs.get("kernel_size", 1)
        prominence: int = kwargs.get("prominence", None)
        distance: int = kwargs.get("distance", 1)
        height: float | None = kwargs.get("height", None)
        fn: Callable | None = kwargs.get("fn", rms)

        # Make sure the kernel_size is an odd number
        if kernel_size % 2 == 0:
            kernel_size += 1

        # Re-calculate scores without tokenization to create a 1D array
        # (that's why tokenize=False)
        reduced = fn(self._vectorized.data)
        normalized = np.abs(reduced - np.mean(reduced))
        # Clean up the noise from the signal.
        # TODO: Re-implement in numpy to avoid scipy dependency
        denoised = scipy.signal.medfilt(normalized, kernel_size=kernel_size)
        auto_params = LogSignalProcessor.tune_peak_detection(denoised)
        height = height if height is not None else auto_params[0]
        prominence = prominence if prominence is not None else auto_params[1]

        peaks = [
            int(peak)
            for peak in scipy.signal.find_peaks(
                denoised, prominence=prominence, distance=distance, height=height
            )[0]
        ]
        # return [self[i - context_size : i + context_size + 1] for i in peaks]
        return peaks

    @staticmethod
    def split_by(func):
        def wrapper(self, data, by, /, **kwargs):
            buckets = LogFileSplit()
            for line in data:
                bucket: str = func(self, line, by, **kwargs)
                if bucket not in buckets:
                    buckets[bucket] = []
                buckets[bucket].append(line)
            return buckets

        return wrapper

    @split_by
    def split_by_token(self, line, by: int, /, delimiter=" ") -> str:
        # Some lines might be shorter and not have the listed index
        try:
            bucket = line.split(delimiter)[by]
        except IndexError:
            bucket = LogFileSplit.OUTLIERS
        return bucket

    @split_by
    def split_by_pattern(self, line, by: re.Pattern) -> str:
        # default bucket for the unmatched strings
        m: re.Match = by.match(str(line))
        if m is None:
            bucket = LogFileSplit.OUTLIERS
        else:
            bucket = m.group(1)
        return bucket

    @split_by
    def split_by_index(self, line, by: tuple[int, int]) -> str:
        start, stop = by
        bucket = line[start:stop]
        if bucket == "":
            # Indexing with a slice won't raise exceptions, just return an empty string.
            bucket = LogFileSplit.OUTLIERS
        return bucket

    @overload
    def unravel(self, by: int) -> LogFileSplit: ...
    @overload
    def unravel(self, by: str) -> LogFileSplit: ...
    @overload
    def unravel(self, by: tuple[int, int]) -> LogFileSplit: ...
    def unravel(self, *args, **kwargs) -> LogFileSplit:
        """Splits an interleaved log file by unique values of the selected log
        file fragment.

        Assuming a log file is a semi-structured document, parts of each line
        may contain a set of unique values, for example: log severity
        information, thread ID, etc. `unravel()` groups the log file's lines
        into buckets, with each bucket representing on of the unique values from
        the set.

        Parameters
        ----------
        by : int | str | tuple[int, int]
            Definition of the log file field to split the file by.

            When the argument has type `int`, it is treated as index of the
            token (group of characters separated from others by a delimiter
            character).

            When the argument is string, it is treated as a regular expression
            pattern to match. The pattern must define exactly one match group.

            When the argument is a two-value tuple, it is interpreted as indices
            for the log line slice.

        Returns
        -------
        LogFileSplit
            `dict`-like object with keys storing the detected buckets and
            instances of `LogFile` as values.

        Raises
        ------
        ValueError
            Value of the `by` parameter is incorrect; pattern is invalid, or the
            tuple is not a two-value.
        PatternGroupError
            Supplied pattern string does not define exactly one match group.
        TypeError
            Type of the `by` parameter cannot be used to split the log file.
        """
        by = kwargs.get("by", args[0] if args else None)

        if isinstance(by, tuple):
            assert len(by) == 2, ValueError("Argument must be a two-value tuple")
            buckets = self.split_by_index(self._content, by)

        elif isinstance(by, str):
            try:
                pattern = re.compile(by)
            except re.PatternError as e:
                raise ValueError(f"Incorrect regular expression pattern: {e}") from e
            if pattern.groups != 1:
                raise PatternGroupError("The pattern must define exactly one group.")
            buckets = self.split_by_pattern(self._content, pattern)

        elif isinstance(by, int):
            buckets = self.split_by_token(self._content, by)
        else:
            raise TypeError(f"Can't split by {type(by)} with value {by}")

        for bucket, lines in buckets.items():
            # TODO: This probably is expensive in terms of extra memcpy operations
            # maybe convert in place?
            buckets[bucket] = LogFile(lines)
        return buckets

    def merge(self): ...
