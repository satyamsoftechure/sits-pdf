import re
from typing import Any, List, Tuple, Union

from .errors import ParseError

_INT_RE = r"(0|-?[1-9]\d*)"
PAGE_RANGE_RE = "^({int}|({int}?(:{int}?(:{int}?)?)))$".format(int=_INT_RE)


class PageRange:
    def __init__(self, arg: Union[slice, "PageRange", str]) -> None:
        if isinstance(arg, slice):
            self._slice = arg
            return

        if isinstance(arg, PageRange):
            self._slice = arg.to_slice()
            return

        m = isinstance(arg, str) and re.match(PAGE_RANGE_RE, arg)
        if not m:
            raise ParseError(arg)
        elif m.group(2):
            start = int(m.group(2))
            stop = start + 1 if start != -1 else None
            self._slice = slice(start, stop)
        else:
            self._slice = slice(*[int(g) if g else None for g in m.group(4, 6, 8)])

    @staticmethod
    def valid(input: Any) -> bool:
        return isinstance(input, (slice, PageRange)) or (
            isinstance(input, str) and bool(re.match(PAGE_RANGE_RE, input))
        )

    def to_slice(self) -> slice:
        return self._slice

    def __str__(self) -> str:
        s = self._slice
        indices: Union[Tuple[int, int], Tuple[int, int, int]]
        if s.step is None:
            if s.start is not None and s.stop == s.start + 1:
                return str(s.start)

            indices = s.start, s.stop
        else:
            indices = s.start, s.stop, s.step
        return ":".join("" if i is None else str(i) for i in indices)

    def __repr__(self) -> str:
        return "PageRange(" + repr(str(self)) + ")"

    def indices(self, n: int) -> Tuple[int, int, int]:
        return self._slice.indices(n)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PageRange):
            return False
        return self._slice == other._slice

    def __add__(self, other: "PageRange") -> "PageRange":
        if not isinstance(other, PageRange):
            raise TypeError(f"Can't add PageRange and {type(other)}")
        if self._slice.step is not None or other._slice.step is not None:
            raise ValueError("Can't add PageRange with stride")
        a = self._slice.start, self._slice.stop
        b = other._slice.start, other._slice.stop

        if a[0] > b[0]:
            a, b = b, a
        if b[0] > a[1]:
            raise ValueError("Can't add PageRanges with gap")
        return PageRange(slice(a[0], max(a[1], b[1])))


PAGE_RANGE_ALL = PageRange(":")


def parse_filename_page_ranges(
    args: List[Union[str, PageRange, None]]
) -> List[Tuple[str, PageRange]]:
    pairs: List[Tuple[str, PageRange]] = []
    pdf_filename = None
    did_page_range = False
    for arg in args + [None]:
        if PageRange.valid(arg):
            if not pdf_filename:
                raise ValueError(
                    "The first argument must be a filename, not a page range."
                )

            pairs.append((pdf_filename, PageRange(arg)))
            did_page_range = True
        else:
            if pdf_filename and not did_page_range:
                pairs.append((pdf_filename, PAGE_RANGE_ALL))

            pdf_filename = arg
            did_page_range = False
    return pairs


PageRangeSpec = Union[str, PageRange, Tuple[int, int], Tuple[int, int, int], List[int]]
