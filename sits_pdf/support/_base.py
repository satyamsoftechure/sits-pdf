import codecs
import decimal
import hashlib
import re
from binascii import unhexlify
from typing import Any, Callable, List, Optional, Tuple, Union, cast

from ._codecs import _pdfdoc_encoding_rev
from ._protocols import PdfObjectProtocol, PdfWriterProtocol
from ._utils import (
    StreamType,
    b_,
    deprecation_with_replacement,
    hex_str,
    hexencode,
    logger_warning,
    read_non_whitespace,
    read_until_regex,
    str_,
)
from .errors import STREAM_TRUNCATED_PREMATURELY, PdfReadError, PdfStreamError

__author__ = "Satyam Shukla"

class PdfObject(PdfObjectProtocol):
    hash_func: Callable[..., "hashlib._Hash"] = hashlib.sha1
    indirect_reference: Optional["IndirectObject"]

    def hash_value_data(self) -> bytes:
        return ("%s" % self).encode()

    def hash_value(self) -> bytes:
        return (
            "%s:%s"
            % (
                self.__class__.__name__,
                self.hash_func(self.hash_value_data()).hexdigest(),
            )
        ).encode()

    def clone(
        self,
        pdf_dest: PdfWriterProtocol,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "PdfObject":
        raise Exception("clone PdfObject")

    def _reference_clone(
        self, clone: Any, pdf_dest: PdfWriterProtocol
    ) -> PdfObjectProtocol:
        try:
            if clone.indirect_reference.pdf == pdf_dest:
                return clone
        except Exception:
            pass
        if hasattr(self, "indirect_reference"):
            ind = self.indirect_reference
            i = len(pdf_dest._objects) + 1
            if ind is not None:
                if id(ind.pdf) not in pdf_dest._id_translated:
                    pdf_dest._id_translated[id(ind.pdf)] = {}
                if ind.idnum in pdf_dest._id_translated[id(ind.pdf)]:
                    obj = pdf_dest.get_object(
                        pdf_dest._id_translated[id(ind.pdf)][ind.idnum]
                    )
                    assert obj is not None
                    return obj
                pdf_dest._id_translated[id(ind.pdf)][ind.idnum] = i
            pdf_dest._objects.append(clone)
            clone.indirect_reference = IndirectObject(i, 0, pdf_dest)
        return clone

    def get_object(self) -> Optional["PdfObject"]:
        return self

    def getObject(self) -> Optional["PdfObject"]:
        deprecation_with_replacement("getObject", "get_object", "3.0.0")
        return self.get_object()

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        raise NotImplementedError


class NullObject(PdfObject):
    def clone(
        self,
        pdf_dest: PdfWriterProtocol,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "NullObject":
        return cast("NullObject", self._reference_clone(NullObject(), pdf_dest))

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        stream.write(b"null")

    @staticmethod
    def read_from_stream(stream: StreamType) -> "NullObject":
        nulltxt = stream.read(4)
        if nulltxt != b"null":
            raise PdfReadError("Could not read Null object")
        return NullObject()

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    def __repr__(self) -> str:
        return "NullObject"

    @staticmethod
    def readFromStream(stream: StreamType) -> "NullObject":
        deprecation_with_replacement("readFromStream", "read_from_stream", "3.0.0")
        return NullObject.read_from_stream(stream)


class BooleanObject(PdfObject):
    def __init__(self, value: Any) -> None:
        self.value = value

    def clone(
        self,
        pdf_dest: PdfWriterProtocol,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "BooleanObject":

        return cast(
            "BooleanObject", self._reference_clone(BooleanObject(self.value), pdf_dest)
        )

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, BooleanObject):
            return self.value == __o.value
        elif isinstance(__o, bool):
            return self.value == __o
        else:
            return False

    def __repr__(self) -> str:
        return "True" if self.value else "False"

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        if self.value:
            stream.write(b"true")
        else:
            stream.write(b"false")

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    @staticmethod
    def read_from_stream(stream: StreamType) -> "BooleanObject":
        word = stream.read(4)
        if word == b"true":
            return BooleanObject(True)
        elif word == b"fals":
            stream.read(1)
            return BooleanObject(False)
        else:
            raise PdfReadError("Could not read Boolean object")

    @staticmethod
    def readFromStream(stream: StreamType) -> "BooleanObject":  
        deprecation_with_replacement("readFromStream", "read_from_stream", "3.0.0")
        return BooleanObject.read_from_stream(stream)


class IndirectObject(PdfObject):
    def __init__(self, idnum: int, generation: int, pdf: Any) -> None:
        self.idnum = idnum
        self.generation = generation
        self.pdf = pdf

    def clone(
        self,
        pdf_dest: PdfWriterProtocol,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "IndirectObject":
        if self.pdf == pdf_dest and not force_duplicate:
            return self
        if id(self.pdf) not in pdf_dest._id_translated:
            pdf_dest._id_translated[id(self.pdf)] = {}

        if not force_duplicate and self.idnum in pdf_dest._id_translated[id(self.pdf)]:
            dup = pdf_dest.get_object(pdf_dest._id_translated[id(self.pdf)][self.idnum])
        else:
            obj = self.get_object()
            assert obj is not None
            dup = obj.clone(pdf_dest, force_duplicate, ignore_fields)
        assert dup is not None
        assert dup.indirect_reference is not None
        return dup.indirect_reference

    @property
    def indirect_reference(self) -> "IndirectObject":
        return self

    def get_object(self) -> Optional["PdfObject"]:
        obj = self.pdf.get_object(self)
        if obj is None:
            return None
        return obj.get_object()

    def __repr__(self) -> str:
        return f"IndirectObject({self.idnum!r}, {self.generation!r}, {id(self.pdf)})"

    def __eq__(self, other: Any) -> bool:
        return (
            other is not None
            and isinstance(other, IndirectObject)
            and self.idnum == other.idnum
            and self.generation == other.generation
            and self.pdf is other.pdf
        )

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        stream.write(b_(f"{self.idnum} {self.generation} R"))

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    @staticmethod
    def read_from_stream(stream: StreamType, pdf: Any) -> "IndirectObject": 
        idnum = b""
        while True:
            tok = stream.read(1)
            if not tok:
                raise PdfStreamError(STREAM_TRUNCATED_PREMATURELY)
            if tok.isspace():
                break
            idnum += tok
        generation = b""
        while True:
            tok = stream.read(1)
            if not tok:
                raise PdfStreamError(STREAM_TRUNCATED_PREMATURELY)
            if tok.isspace():
                if not generation:
                    continue
                break
            generation += tok
        r = read_non_whitespace(stream)
        if r != b"R":
            raise PdfReadError(
                f"Error reading indirect object reference at byte {hex_str(stream.tell())}"
            )
        return IndirectObject(int(idnum), int(generation), pdf)

    @staticmethod
    def readFromStream(
        stream: StreamType, pdf: Any 
    ) -> "IndirectObject":  
        deprecation_with_replacement("readFromStream", "read_from_stream", "3.0.0")
        return IndirectObject.read_from_stream(stream, pdf)


class FloatObject(decimal.Decimal, PdfObject):
    def __new__(
        cls, value: Union[str, Any] = "0", context: Optional[Any] = None
    ) -> "FloatObject":
        try:
            return decimal.Decimal.__new__(cls, str_(value), context)
        except Exception:
            logger_warning(f"FloatObject ({value}) invalid; use 0.0 instead", __name__)
            return decimal.Decimal.__new__(cls, "0.0")

    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "FloatObject":
        return cast("FloatObject", self._reference_clone(FloatObject(self), pdf_dest))

    def __repr__(self) -> str:
        if self == self.to_integral():
            return str(self.quantize(decimal.Decimal(1)))
        else:
            return f"{self:f}".rstrip("0")

    def as_numeric(self) -> float:
        return float(repr(self).encode("utf8"))

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        stream.write(repr(self).encode("utf8"))

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)


class NumberObject(int, PdfObject):
    NumberPattern = re.compile(b"[^+-.0-9]")

    def __new__(cls, value: Any) -> "NumberObject":
        try:
            return int.__new__(cls, int(value))
        except ValueError:
            logger_warning(f"NumberObject({value}) invalid; use 0 instead", __name__)
            return int.__new__(cls, 0)

    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "NumberObject":

        return cast("NumberObject", self._reference_clone(NumberObject(self), pdf_dest))

    def as_numeric(self) -> int:
        return int(repr(self).encode("utf8"))

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        stream.write(repr(self).encode("utf8"))

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    @staticmethod
    def read_from_stream(stream: StreamType) -> Union["NumberObject", "FloatObject"]:
        num = read_until_regex(stream, NumberObject.NumberPattern)
        if num.find(b".") != -1:
            return FloatObject(num)
        return NumberObject(num)

    @staticmethod
    def readFromStream(
        stream: StreamType,
    ) -> Union["NumberObject", "FloatObject"]:  
        deprecation_with_replacement("readFromStream", "read_from_stream", "3.0.0")
        return NumberObject.read_from_stream(stream)


class ByteStringObject(bytes, PdfObject):
    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "ByteStringObject":
        return cast(
            "ByteStringObject",
            self._reference_clone(ByteStringObject(bytes(self)), pdf_dest),
        )

    @property
    def original_bytes(self) -> bytes:
        return self

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        bytearr = self
        if encryption_key:
            from ._security import RC4_encrypt

            bytearr = RC4_encrypt(encryption_key, bytearr)
        stream.write(b"<")
        stream.write(hexencode(bytearr))
        stream.write(b">")

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)


class TextStringObject(str, PdfObject):
    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "TextStringObject":
        obj = TextStringObject(self)
        obj.autodetect_pdfdocencoding = self.autodetect_pdfdocencoding
        obj.autodetect_utf16 = self.autodetect_utf16
        return cast("TextStringObject", self._reference_clone(obj, pdf_dest))

    autodetect_pdfdocencoding = False
    autodetect_utf16 = False

    @property
    def original_bytes(self) -> bytes:
        return self.get_original_bytes()

    def get_original_bytes(self) -> bytes:
        if self.autodetect_utf16:
            return codecs.BOM_UTF16_BE + self.encode("utf-16be")
        elif self.autodetect_pdfdocencoding:
            return encode_pdfdocencoding(self)
        else:
            raise Exception("no information about original bytes")

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        try:
            bytearr = encode_pdfdocencoding(self)
        except UnicodeEncodeError:
            bytearr = codecs.BOM_UTF16_BE + self.encode("utf-16be")
        if encryption_key:
            from ._security import RC4_encrypt

            bytearr = RC4_encrypt(encryption_key, bytearr)
            obj = ByteStringObject(bytearr)
            obj.write_to_stream(stream, None)
        else:
            stream.write(b"(")
            for c in bytearr:
                if not chr(c).isalnum() and c != b" ":
                    stream.write(b_("\\%03o" % c))
                else:
                    stream.write(b_(chr(c)))
            stream.write(b")")

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)


class NameObject(str, PdfObject):
    delimiter_pattern = re.compile(rb"\s+|[\(\)<>\[\]{}/%]")
    surfix = b"/"
    renumber_table = {
        "#": b"#23",
        "(": b"#28",
        ")": b"#29",
        "/": b"#2F",
        **{chr(i): f"#{i:02X}".encode() for i in range(33)},
    }

    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> "NameObject":
        return cast("NameObject", self._reference_clone(NameObject(self), pdf_dest))

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        stream.write(self.renumber())  

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:  
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    def renumber(self) -> bytes:
        out = self[0].encode("utf-8")
        if out != b"/":
            logger_warning(f"Incorrect first char in NameObject:({self})", __name__)
        for c in self[1:]:
            if c > "~":
                for x in c.encode("utf-8"):
                    out += f"#{x:02X}".encode()
            else:
                try:
                    out += self.renumber_table[c]
                except KeyError:
                    out += c.encode("utf-8")
        return out

    @staticmethod
    def unnumber(sin: bytes) -> bytes:
        i = sin.find(b"#", 0)
        while i >= 0:
            try:
                sin = sin[:i] + unhexlify(sin[i + 1 : i + 3]) + sin[i + 3 :]
                i = sin.find(b"#", i + 1)
            except ValueError:
                i = i + 1
        return sin

    @staticmethod
    def read_from_stream(stream: StreamType, pdf: Any) -> "NameObject": 
        name = stream.read(1)
        if name != NameObject.surfix:
            raise PdfReadError("name read error")
        name += read_until_regex(stream, NameObject.delimiter_pattern, ignore_eof=True)
        try:
            name = NameObject.unnumber(name)
            for enc in ("utf-8", "gbk"):
                try:
                    ret = name.decode(enc)
                    return NameObject(ret)
                except Exception:
                    pass
            raise UnicodeDecodeError("", name, 0, 0, "Code Not Found")
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            if not pdf.strict:
                logger_warning(
                    f"Illegal character in Name Object ({repr(name)})", __name__
                )
                return NameObject(name.decode("charmap"))
            else:
                raise PdfReadError(
                    f"Illegal character in Name Object ({repr(name)})"
                ) from e

    @staticmethod
    def readFromStream(
        stream: StreamType, pdf: Any 
    ) -> "NameObject":  
        deprecation_with_replacement("readFromStream", "read_from_stream", "3.0.0")
        return NameObject.read_from_stream(stream, pdf)


def encode_pdfdocencoding(unicode_string: str) -> bytes:
    retval = b""
    for c in unicode_string:
        try:
            retval += b_(chr(_pdfdoc_encoding_rev[c]))
        except KeyError:
            raise UnicodeEncodeError(
                "pdfdocencoding", c, -1, -1, "does not exist in translation table"
            )
    return retval
