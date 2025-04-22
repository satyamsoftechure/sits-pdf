__author__ = "Satyam Shukla"

from typing import Dict, List, Union

from ._utils import StreamType, deprecate_with_replacement
from .constants import OutlineFontFlag
from ._annotations import AnnotationBuilder
from ._base import (
    BooleanObject,
    ByteStringObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    PdfObject,
    TextStringObject,
    encode_pdfdocencoding,
)
from ._data_structures import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    Destination,
    DictionaryObject,
    EncodedStreamObject,
    Field,
    StreamObject,
    TreeObject,
    read_object,
)
from ._fit import Fit
from ._outline import Bookmark, OutlineItem
from ._rectangle import RectangleObject
from .__utils import (
    create_string_object,
    decode_pdfdocencoding,
    hex_to_rgb,
    read_hex_string_from_stream,
    read_string_from_stream,
)


def readHexStringFromStream(
    stream: StreamType,
) -> Union["TextStringObject", "ByteStringObject"]:
    deprecate_with_replacement(
        "readHexStringFromStream", "read_hex_string_from_stream", "4.0.0"
    )
    return read_hex_string_from_stream(stream)


def readStringFromStream(
    stream: StreamType,
    forced_encoding: Union[None, str, List[str], Dict[int, str]] = None,
) -> Union["TextStringObject", "ByteStringObject"]:
    deprecate_with_replacement(
        "readStringFromStream", "read_string_from_stream", "4.0.0"
    )
    return read_string_from_stream(stream, forced_encoding)


def createStringObject(
    string: Union[str, bytes],
    forced_encoding: Union[None, str, List[str], Dict[int, str]] = None,
) -> Union[TextStringObject, ByteStringObject]:
    deprecate_with_replacement("createStringObject", "create_string_object", "4.0.0")
    return create_string_object(string, forced_encoding)


PAGE_FIT = Fit.fit()


__all__ = [
    "BooleanObject",
    "FloatObject",
    "NumberObject",
    "NameObject",
    "IndirectObject",
    "NullObject",
    "PdfObject",
    "TextStringObject",
    "ByteStringObject",
    "AnnotationBuilder",
    "Fit",
    "PAGE_FIT",
    "ArrayObject",
    "DictionaryObject",
    "TreeObject",
    "StreamObject",
    "DecodedStreamObject",
    "EncodedStreamObject",
    "ContentStream",
    "RectangleObject",
    "Field",
    "Destination",
    "OutlineItem",
    "OutlineFontFlag",
    "Bookmark",
    "read_object",
    "create_string_object",
    "encode_pdfdocencoding",
    "decode_pdfdocencoding",
    "hex_to_rgb",
    "read_hex_string_from_stream",
    "read_string_from_stream",
]
