__author__ = "Satyam Shukla"

import functools
import logging
import warnings
from codecs import getencoder
from dataclasses import dataclass
from io import DEFAULT_BUFFER_SIZE
from os import SEEK_CUR
from typing import (
    IO,
    Any,
    Callable,
    Dict,
    Optional,
    Pattern,
    Tuple,
    Union,
    overload,
)

try:
    from typing import TypeAlias
except ImportError:
    from typing_extensions import TypeAlias

from .support.errors import (
    STREAM_TRUNCATED_PREMATURELY,
    DeprecationError,
    PdfStreamError,
)

TransformationMatrixType: TypeAlias = Tuple[
    Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]
]
CompressedTransformationMatrix: TypeAlias = Tuple[
    float, float, float, float, float, float
]

StreamType = IO
StrByteType = Union[str, StreamType]

DEPR_MSG_NO_REPLACEMENT = "{} is deprecated and will be removed in PyPDF2 {}."
DEPR_MSG_NO_REPLACEMENT_HAPPENED = "{} is deprecated and was removed in PyPDF2 {}."
DEPR_MSG = "{} is deprecated and will be removed in PyPDF2 3.0.0. Use {} instead."
DEPR_MSG_HAPPENED = "{} is deprecated and was removed in PyPDF2 {}. Use {} instead."


def _get_max_pdf_version_header(header1: bytes, header2: bytes) -> bytes:
    versions = (
        b"%PDF-1.3",
        b"%PDF-1.4",
        b"%PDF-1.5",
        b"%PDF-1.6",
        b"%PDF-1.7",
        b"%PDF-2.0",
    )
    pdf_header_indices = []
    if header1 in versions:
        pdf_header_indices.append(versions.index(header1))
    if header2 in versions:
        pdf_header_indices.append(versions.index(header2))
    if len(pdf_header_indices) == 0:
        raise ValueError(f"neither {header1!r} nor {header2!r} are proper headers")
    return versions[max(pdf_header_indices)]


def read_until_whitespace(stream: StreamType, maxchars: Optional[int] = None) -> bytes:
    txt = b""
    while True:
        tok = stream.read(1)
        if tok.isspace() or not tok:
            break
        txt += tok
        if len(txt) == maxchars:
            break
    return txt


def read_non_whitespace(stream: StreamType) -> bytes:
    tok = stream.read(1)
    while tok in WHITESPACES:
        tok = stream.read(1)
    return tok


def skip_over_whitespace(stream: StreamType) -> bool:
    tok = WHITESPACES[0]
    cnt = 0
    while tok in WHITESPACES:
        tok = stream.read(1)
        cnt += 1
    return cnt > 1


def skip_over_comment(stream: StreamType) -> None:
    tok = stream.read(1)
    stream.seek(-1, 1)
    if tok == b"%":
        while tok not in (b"\n", b"\r"):
            tok = stream.read(1)


def read_until_regex(
    stream: StreamType, regex: Pattern[bytes], ignore_eof: bool = False
) -> bytes:
    name = b""
    while True:
        tok = stream.read(16)
        if not tok:
            if ignore_eof:
                return name
            raise PdfStreamError(STREAM_TRUNCATED_PREMATURELY)
        m = regex.search(tok)
        if m is not None:
            name += tok[: m.start()]
            stream.seek(m.start() - len(tok), 1)
            break
        name += tok
    return name


def read_block_backwards(stream: StreamType, to_read: int) -> bytes:
    if stream.tell() < to_read:
        raise PdfStreamError("Could not read malformed PDF file")
    stream.seek(-to_read, SEEK_CUR)
    read = stream.read(to_read)
    stream.seek(-to_read, SEEK_CUR)
    return read


def read_previous_line(stream: StreamType) -> bytes:
    line_content = []
    found_crlf = False
    if stream.tell() == 0:
        raise PdfStreamError(STREAM_TRUNCATED_PREMATURELY)
    while True:
        to_read = min(DEFAULT_BUFFER_SIZE, stream.tell())
        if to_read == 0:
            break
        block = read_block_backwards(stream, to_read)
        idx = len(block) - 1
        if not found_crlf:
            while idx >= 0 and block[idx] not in b"\r\n":
                idx -= 1
            if idx >= 0:
                found_crlf = True
        if found_crlf:
            line_content.append(block[idx + 1 :])
            while idx >= 0 and block[idx] in b"\r\n":
                idx -= 1
        else:
            line_content.append(block)
        if idx >= 0:
            stream.seek(idx + 1, SEEK_CUR)
            break
    return b"".join(line_content[::-1])


def matrix_multiply(
    a: TransformationMatrixType, b: TransformationMatrixType
) -> TransformationMatrixType:
    return tuple(
        tuple(sum(float(i) * float(j) for i, j in zip(row, col)) for col in zip(*b))
        for row in a
    )


def mark_location(stream: StreamType) -> None:
    radius = 5000
    stream.seek(-radius, 1)
    with open("PyPDF2_pdfLocation.txt", "wb") as output_fh:
        output_fh.write(stream.read(radius))
        output_fh.write(b"HERE")
        output_fh.write(stream.read(radius))
    stream.seek(-radius, 1)


B_CACHE: Dict[Union[str, bytes], bytes] = {}


def b_(s: Union[str, bytes]) -> bytes:
    bc = B_CACHE
    if s in bc:
        return bc[s]
    if isinstance(s, bytes):
        return s
    try:
        r = s.encode("latin-1")
        if len(s) < 2:
            bc[s] = r
        return r
    except Exception:
        r = s.encode("utf-8")
        if len(s) < 2:
            bc[s] = r
        return r


@overload
def str_(b: str) -> str: ...


@overload
def str_(b: bytes) -> str: ...


def str_(b: Union[str, bytes]) -> str:
    if isinstance(b, bytes):
        return b.decode("latin-1")
    else:
        return b


@overload
def ord_(b: str) -> int: ...


@overload
def ord_(b: bytes) -> bytes: ...


@overload
def ord_(b: int) -> int: ...


def ord_(b: Union[int, str, bytes]) -> Union[int, bytes]:
    if isinstance(b, str):
        return ord(b)
    return b


def hexencode(b: bytes) -> bytes:

    coder = getencoder("hex_codec")
    coded = coder(b)
    return coded[0]


def hex_str(num: int) -> str:
    return hex(num).replace("L", "")


WHITESPACES = (b" ", b"\n", b"\r", b"\t", b"\x00")


def paeth_predictor(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    dist_left = abs(p - left)
    dist_up = abs(p - up)
    dist_up_left = abs(p - up_left)

    if dist_left <= dist_up and dist_left <= dist_up_left:
        return left
    elif dist_up <= dist_up_left:
        return up
    else:
        return up_left


def deprecate(msg: str, stacklevel: int = 3) -> None:
    warnings.warn(msg, DeprecationWarning, stacklevel=stacklevel)


def deprecation(msg: str) -> None:
    raise DeprecationError(msg)


def deprecate_with_replacement(
    old_name: str, new_name: str, removed_in: str = "3.0.0"
) -> None:
    deprecate(DEPR_MSG.format(old_name, new_name, removed_in), 4)


def deprecation_with_replacement(
    old_name: str, new_name: str, removed_in: str = "3.0.0"
) -> None:
    deprecation(DEPR_MSG_HAPPENED.format(old_name, removed_in, new_name))


def deprecate_no_replacement(name: str, removed_in: str = "3.0.0") -> None:
    deprecate(DEPR_MSG_NO_REPLACEMENT.format(name, removed_in), 4)


def deprecation_no_replacement(name: str, removed_in: str = "3.0.0") -> None:
    deprecation(DEPR_MSG_NO_REPLACEMENT_HAPPENED.format(name, removed_in))


def logger_warning(msg: str, src: str) -> None:
    logging.getLogger(src).warning(msg)


def deprecation_bookmark(**aliases: str) -> Callable:
    def decoration(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            rename_kwargs(func.__name__, kwargs, aliases, fail=True)
            return func(*args, **kwargs)

        return wrapper

    return decoration


def rename_kwargs(
    func_name: str, kwargs: Dict[str, Any], aliases: Dict[str, str], fail: bool = False
):

    for old_term, new_term in aliases.items():
        if old_term in kwargs:
            if fail:
                raise DeprecationError(
                    f"{old_term} is deprecated as an argument. Use {new_term} instead"
                )
            if new_term in kwargs:
                raise TypeError(
                    f"{func_name} received both {old_term} and {new_term} as an argument. "
                    f"{old_term} is deprecated. Use {new_term} instead."
                )
            kwargs[new_term] = kwargs.pop(old_term)
            warnings.warn(
                message=(
                    f"{old_term} is deprecated as an argument. Use {new_term} instead"
                ),
                category=DeprecationWarning,
            )


def _human_readable_bytes(bytes: int) -> str:
    if bytes < 10**3:
        return f"{bytes} Byte"
    elif bytes < 10**6:
        return f"{bytes / 10**3:.1f} kB"
    elif bytes < 10**9:
        return f"{bytes / 10**6:.1f} MB"
    else:
        return f"{bytes / 10**9:.1f} GB"


@dataclass
class File:
    name: str
    data: bytes

    def __str__(self) -> str:
        return f"File(name={self.name}, data: {_human_readable_bytes(len(self.data))})"

    def __repr__(self) -> str:
        return f"File(name={self.name}, data: {_human_readable_bytes(len(self.data))}, hash: {hash(self.data)})"
