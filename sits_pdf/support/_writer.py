import codecs
import collections
import decimal
import logging
import random
import re
import struct
import time
import uuid
import warnings
from hashlib import md5
from io import BytesIO, FileIO, IOBase
from pathlib import Path
from types import TracebackType
from typing import (
    IO,
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Pattern,
    Tuple,
    Type,
    Union,
    cast,
)

from ._encryption import Encryption
from ._page import PageObject, _VirtualList
from ._reader import PdfReader
from ._security import _alg33, _alg34, _alg35
from ._utils import (
    StrByteType,
    StreamType,
    _get_max_pdf_version_header,
    b_,
    deprecate_with_replacement,
    deprecation_bookmark,
    deprecation_with_replacement,
    logger_warning,
)
from .constants import AnnotationDictionaryAttributes
from .constants import CatalogAttributes as CA
from .constants import CatalogDictionary
from .constants import Core as CO
from .constants import EncryptionDictAttributes as ED
from .constants import (
    FieldDictionaryAttributes,
    FieldFlag,
    FileSpecificationDictionaryEntries,
    GoToActionArguments,
    InteractiveFormDictEntries,
)
from .constants import PageAttributes as PG
from .constants import PagesAttributes as PA
from .constants import StreamAttributes as SA
from .constants import TrailerKeys as TK
from .constants import TypFitArguments, UserAccessPermissions
from .generic import (
    PAGE_FIT,
    AnnotationBuilder,
    ArrayObject,
    BooleanObject,
    ByteStringObject,
    ContentStream,
    DecodedStreamObject,
    Destination,
    DictionaryObject,
    Fit,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    PdfObject,
    RectangleObject,
    StreamObject,
    TextStringObject,
    TreeObject,
    create_string_object,
    hex_to_rgb,
)
from .pagerange import PageRange, PageRangeSpec
from ._types import (
    BorderArrayType,
    FitType,
    LayoutType,
    OutlineItemType,
    OutlineType,
    PagemodeType,
    ZoomArgType,
)

logger = logging.getLogger(__name__)


OPTIONAL_READ_WRITE_FIELD = FieldFlag(0)
ALL_DOCUMENT_PERMISSIONS = UserAccessPermissions((2**31 - 1) - 3)


class PdfWriter:
    def __init__(self, fileobj: StrByteType = "") -> None:
        self._header = b"%PDF-1.3"
        self._objects: List[PdfObject] = []
        self._idnum_hash: Dict[bytes, IndirectObject] = {}
        self._id_translated: Dict[int, Dict[int, int]] = {}
        pages = DictionaryObject()
        pages.update(
            {
                NameObject(PA.TYPE): NameObject("/Pages"),
                NameObject(PA.COUNT): NumberObject(0),
                NameObject(PA.KIDS): ArrayObject(),
            }
        )
        self._pages = self._add_object(pages)
        info = DictionaryObject()
        info.update(
            {
                NameObject("/Producer"): create_string_object(
                    codecs.BOM_UTF16_BE + "PyPDF2".encode("utf-16be")
                )
            }
        )
        self._info = self._add_object(info)
        self._root_object = DictionaryObject()
        self._root_object.update(
            {
                NameObject(PA.TYPE): NameObject(CO.CATALOG),
                NameObject(CO.PAGES): self._pages,
            }
        )
        self._root = self._add_object(self._root_object)
        self.fileobj = fileobj
        self.with_as_usage = False

    def __enter__(self) -> "PdfWriter":
        self.with_as_usage = True
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.fileobj:
            self.write(self.fileobj)

    @property
    def pdf_header(self) -> bytes:
        return self._header

    @pdf_header.setter
    def pdf_header(self, new_header: bytes) -> None:
        self._header = new_header

    def _add_object(self, obj: PdfObject) -> IndirectObject:
        if hasattr(obj, "indirect_reference") and obj.indirect_reference.pdf == self:
            return obj.indirect_reference
        self._objects.append(obj)
        obj.indirect_reference = IndirectObject(len(self._objects), 0, self)
        return obj.indirect_reference

    def get_object(
        self,
        indirect_reference: Union[None, int, IndirectObject] = None,
        ido: Optional[IndirectObject] = None,
    ) -> PdfObject:
        if ido is not None:
            if indirect_reference is not None:
                raise ValueError(
                    "Please only set 'indirect_reference'. The 'ido' argument is deprecated."
                )
            else:
                indirect_reference = ido
                warnings.warn(
                    "The parameter 'ido' is depreciated and will be removed in PyPDF2 4.0.0.",
                    DeprecationWarning,
                )
        assert indirect_reference is not None
        if isinstance(indirect_reference, int):
            return self._objects[indirect_reference - 1]
        if indirect_reference.pdf != self:
            raise ValueError("pdf must be self")
        return self._objects[indirect_reference.idnum - 1]

    def getObject(self, ido: Union[int, IndirectObject]) -> PdfObject:
        deprecation_with_replacement("getObject", "get_object", "3.0.0")
        return self.get_object(ido)

    def _add_page(
        self,
        page: PageObject,
        action: Callable[[Any, IndirectObject], None],
        excluded_keys: Iterable[str] = (),
    ) -> PageObject:
        assert cast(str, page[PA.TYPE]) == CO.PAGE
        page_org = page
        excluded_keys = list(excluded_keys)
        excluded_keys += [PA.PARENT, "/StructParents"]
        try:
            del self._id_translated[id(page_org.indirect_reference.pdf)][
                page_org.indirect_reference.idnum
            ]
        except Exception:
            pass
        page = cast("PageObject", page_org.clone(self, False, excluded_keys))
        if page_org.pdf is not None:
            other = page_org.pdf.pdf_header
            if isinstance(other, str):
                other = other.encode()
            self.pdf_header = _get_max_pdf_version_header(self.pdf_header, other)
        page[NameObject(PA.PARENT)] = self._pages
        pages = cast(DictionaryObject, self.get_object(self._pages))
        assert page.indirect_reference is not None
        action(pages[PA.KIDS], page.indirect_reference)
        page_count = cast(int, pages[PA.COUNT])
        pages[NameObject(PA.COUNT)] = NumberObject(page_count + 1)
        return page

    def set_need_appearances_writer(self) -> None:
        try:
            catalog = self._root_object
            if CatalogDictionary.ACRO_FORM not in catalog:
                self._root_object.update(
                    {
                        NameObject(CatalogDictionary.ACRO_FORM): IndirectObject(
                            len(self._objects), 0, self
                        )
                    }
                )

            need_appearances = NameObject(InteractiveFormDictEntries.NeedAppearances)
            self._root_object[CatalogDictionary.ACRO_FORM][need_appearances] = (
                BooleanObject(True)
            )
        except Exception as exc:
            logger.error("set_need_appearances_writer() catch : ", repr(exc))

    def add_page(
        self,
        page: PageObject,
        excluded_keys: Iterable[str] = (),
    ) -> PageObject:
        return self._add_page(page, list.append, excluded_keys)

    def addPage(
        self,
        page: PageObject,
        excluded_keys: Iterable[str] = (),
    ) -> PageObject:
        deprecation_with_replacement("addPage", "add_page", "3.0.0")
        return self.add_page(page, excluded_keys)

    def insert_page(
        self,
        page: PageObject,
        index: int = 0,
        excluded_keys: Iterable[str] = (),
    ) -> PageObject:
        return self._add_page(page, lambda l, p: l.insert(index, p))

    def insertPage(
        self,
        page: PageObject,
        index: int = 0,
        excluded_keys: Iterable[str] = (),
    ) -> PageObject:
        deprecation_with_replacement("insertPage", "insert_page", "3.0.0")
        return self.insert_page(page, index, excluded_keys)

    def get_page(
        self, page_number: Optional[int] = None, pageNumber: Optional[int] = None
    ) -> PageObject:
        if pageNumber is not None:
            if page_number is not None:
                raise ValueError("Please only use the page_number parameter")
            deprecate_with_replacement(
                "get_page(pageNumber)", "get_page(page_number)", "4.0.0"
            )
            page_number = pageNumber
        if page_number is None and pageNumber is None:
            raise ValueError("Please specify the page_number")
        pages = cast(Dict[str, Any], self.get_object(self._pages))
        # TODO: crude hack
        return cast(PageObject, pages[PA.KIDS][page_number].get_object())

    def getPage(self, pageNumber: int) -> PageObject:
        deprecation_with_replacement("getPage", "writer.pages[page_number]", "3.0.0")
        return self.get_page(pageNumber)

    def _get_num_pages(self) -> int:
        pages = cast(Dict[str, Any], self.get_object(self._pages))
        return int(pages[NameObject("/Count")])

    def getNumPages(self) -> int:
        deprecation_with_replacement("getNumPages", "len(writer.pages)", "3.0.0")
        return self._get_num_pages()

    @property
    def pages(self) -> List[PageObject]:
        return _VirtualList(self._get_num_pages, self.get_page)

    def add_blank_page(
        self, width: Optional[float] = None, height: Optional[float] = None
    ) -> PageObject:
        page = PageObject.create_blank_page(self, width, height)
        self.add_page(page)
        return page

    def addBlankPage(
        self, width: Optional[float] = None, height: Optional[float] = None
    ) -> PageObject:
        deprecation_with_replacement("addBlankPage", "add_blank_page", "3.0.0")
        return self.add_blank_page(width, height)

    def insert_blank_page(
        self,
        width: Optional[decimal.Decimal] = None,
        height: Optional[decimal.Decimal] = None,
        index: int = 0,
    ) -> PageObject:
        if width is None or height is None and (self._get_num_pages() - 1) >= index:
            oldpage = self.pages[index]
            width = oldpage.mediabox.width
            height = oldpage.mediabox.height
        page = PageObject.create_blank_page(self, width, height)
        self.insert_page(page, index)
        return page

    def insertBlankPage(
        self,
        width: Optional[decimal.Decimal] = None,
        height: Optional[decimal.Decimal] = None,
        index: int = 0,
    ) -> PageObject:
        deprecation_with_replacement("insertBlankPage", "insert_blank_page", "3.0.0")
        return self.insert_blank_page(width, height, index)

    @property
    def open_destination(
        self,
    ) -> Union[None, Destination, TextStringObject, ByteStringObject]:
        if "/OpenAction" not in self._root_object:
            return None
        oa = self._root_object["/OpenAction"]
        if isinstance(oa, (str, bytes)):
            return create_string_object(str(oa))
        elif isinstance(oa, ArrayObject):
            try:
                page, typ = oa[0:2]
                array = oa[2:]
                fit = Fit(typ, tuple(array))
                return Destination("OpenAction", page, fit)
            except Exception as exc:
                raise Exception(f"Invalid Destination {oa}: {exc}")
        else:
            return None

    @open_destination.setter
    def open_destination(self, dest: Union[None, str, Destination, PageObject]) -> None:
        if dest is None:
            try:
                del self._root_object["/OpenAction"]
            except KeyError:
                pass
        elif isinstance(dest, str):
            self._root_object[NameObject("/OpenAction")] = TextStringObject(dest)
        elif isinstance(dest, Destination):
            self._root_object[NameObject("/OpenAction")] = dest.dest_array
        elif isinstance(dest, PageObject):
            self._root_object[NameObject("/OpenAction")] = Destination(
                "Opening",
                (
                    dest.indirect_reference
                    if dest.indirect_reference is not None
                    else NullObject()
                ),
                PAGE_FIT,
            ).dest_array

    def add_js(self, javascript: str) -> None:
        if "/Names" not in self._root_object:
            self._root_object[NameObject(CA.NAMES)] = DictionaryObject()
        names = cast(DictionaryObject, self._root_object[CA.NAMES])
        if "/JavaScript" not in names:
            names[NameObject("/JavaScript")] = DictionaryObject(
                {NameObject("/Names"): ArrayObject()}
            )
        js_list = cast(
            ArrayObject, cast(DictionaryObject, names["/JavaScript"])["/Names"]
        )

        js = DictionaryObject()
        js.update(
            {
                NameObject(PA.TYPE): NameObject("/Action"),
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject(f"{javascript}"),
            }
        )
        js_list.append(create_string_object(str(uuid.uuid4())))
        js_list.append(self._add_object(js))

    def addJS(self, javascript: str) -> None:
        deprecation_with_replacement("addJS", "add_js", "3.0.0")
        return self.add_js(javascript)

    def add_attachment(self, filename: str, data: Union[str, bytes]) -> None:
        file_entry = DecodedStreamObject()
        file_entry.set_data(data)
        file_entry.update({NameObject(PA.TYPE): NameObject("/EmbeddedFile")})
        ef_entry = DictionaryObject()
        ef_entry.update({NameObject("/F"): file_entry})
        filespec = DictionaryObject()
        filespec.update(
            {
                NameObject(PA.TYPE): NameObject("/Filespec"),
                NameObject(FileSpecificationDictionaryEntries.F): create_string_object(
                    filename
                ),
                NameObject(FileSpecificationDictionaryEntries.EF): ef_entry,
            }
        )
        embedded_files_names_dictionary = DictionaryObject()
        embedded_files_names_dictionary.update(
            {
                NameObject(CA.NAMES): ArrayObject(
                    [create_string_object(filename), filespec]
                )
            }
        )
        embedded_files_dictionary = DictionaryObject()
        embedded_files_dictionary.update(
            {NameObject("/EmbeddedFiles"): embedded_files_names_dictionary}
        )
        self._root_object.update({NameObject(CA.NAMES): embedded_files_dictionary})

    def addAttachment(self, fname: str, fdata: Union[str, bytes]) -> None:
        deprecation_with_replacement("addAttachment", "add_attachment", "3.0.0")
        return self.add_attachment(fname, fdata)

    def append_pages_from_reader(
        self,
        reader: PdfReader,
        after_page_append: Optional[Callable[[PageObject], None]] = None,
    ) -> None:
        reader_num_pages = len(reader.pages)
        for reader_page_number in range(reader_num_pages):
            reader_page = reader.pages[reader_page_number]
            writer_page = self.add_page(reader_page)
            if callable(after_page_append):
                after_page_append(writer_page)

    def appendPagesFromReader(
        self,
        reader: PdfReader,
        after_page_append: Optional[Callable[[PageObject], None]] = None,
    ) -> None:
        deprecation_with_replacement(
            "appendPagesFromReader", "append_pages_from_reader", "3.0.0"
        )
        self.append_pages_from_reader(reader, after_page_append)

    def update_page_form_field_values(
        self,
        page: PageObject,
        fields: Dict[str, Any],
        flags: FieldFlag = OPTIONAL_READ_WRITE_FIELD,
    ) -> None:
        self.set_need_appearances_writer()
        if PG.ANNOTS not in page:
            logger_warning("No fields to update on this page", __name__)
            return
        for j in range(len(page[PG.ANNOTS])):
            writer_annot = page[PG.ANNOTS][j].get_object()
            writer_parent_annot = {}
            if PG.PARENT in writer_annot:
                writer_parent_annot = writer_annot[PG.PARENT]
            for field in fields:
                if writer_annot.get(FieldDictionaryAttributes.T) == field:
                    if writer_annot.get(FieldDictionaryAttributes.FT) == "/Btn":
                        writer_annot.update(
                            {
                                NameObject(
                                    AnnotationDictionaryAttributes.AS
                                ): NameObject(fields[field])
                            }
                        )
                    writer_annot.update(
                        {
                            NameObject(FieldDictionaryAttributes.V): TextStringObject(
                                fields[field]
                            )
                        }
                    )
                    if flags:
                        writer_annot.update(
                            {
                                NameObject(FieldDictionaryAttributes.Ff): NumberObject(
                                    flags
                                )
                            }
                        )
                elif writer_parent_annot.get(FieldDictionaryAttributes.T) == field:
                    writer_parent_annot.update(
                        {
                            NameObject(FieldDictionaryAttributes.V): TextStringObject(
                                fields[field]
                            )
                        }
                    )

    def updatePageFormFieldValues(
        self,
        page: PageObject,
        fields: Dict[str, Any],
        flags: FieldFlag = OPTIONAL_READ_WRITE_FIELD,
    ) -> None:
        deprecation_with_replacement(
            "updatePageFormFieldValues", "update_page_form_field_values", "3.0.0"
        )
        return self.update_page_form_field_values(page, fields, flags)

    def clone_reader_document_root(self, reader: PdfReader) -> None:
        self._root_object = cast(DictionaryObject, reader.trailer[TK.ROOT])

    def cloneReaderDocumentRoot(self, reader: PdfReader) -> None:
        deprecation_with_replacement(
            "cloneReaderDocumentRoot", "clone_reader_document_root", "3.0.0"
        )
        self.clone_reader_document_root(reader)

    def clone_document_from_reader(
        self,
        reader: PdfReader,
        after_page_append: Optional[Callable[[PageObject], None]] = None,
    ) -> None:
        # TODO : ppZZ may be limited because we do not copy all info...
        self.clone_reader_document_root(reader)
        self.append_pages_from_reader(reader, after_page_append)

    def cloneDocumentFromReader(
        self,
        reader: PdfReader,
        after_page_append: Optional[Callable[[PageObject], None]] = None,
    ) -> None:
        deprecation_with_replacement(
            "cloneDocumentFromReader", "clone_document_from_reader", "3.0.0"
        )
        self.clone_document_from_reader(reader, after_page_append)

    def encrypt(
        self,
        user_password: Optional[str] = None,
        owner_password: Optional[str] = None,
        use_128bit: bool = True,
        permissions_flag: UserAccessPermissions = ALL_DOCUMENT_PERMISSIONS,
        user_pwd: Optional[str] = None,
        owner_pwd: Optional[str] = None,
    ) -> None:
        if user_pwd is not None:
            if user_password is not None:
                raise ValueError(
                    "Please only set 'user_password'. "
                    "The 'user_pwd' argument is deprecated."
                )
            else:
                warnings.warn(
                    "Please use 'user_password' instead of 'user_pwd'. "
                    "The 'user_pwd' argument is deprecated and "
                    "will be removed in PyPDF2 4.0.0."
                )
                user_password = user_pwd
        if user_password is None:
            raise ValueError("user_password may not be None")

        if owner_pwd is not None:
            if owner_password is not None:
                raise ValueError(
                    "The argument owner_pwd of encrypt is deprecated. Use owner_password only."
                )
            else:
                old_term = "owner_pwd"
                new_term = "owner_password"
                warnings.warn(
                    message=(
                        f"{old_term} is deprecated as an argument and will be "
                        f"removed in PyPDF2 4.0.0. Use {new_term} instead"
                    ),
                    category=DeprecationWarning,
                )
                owner_password = owner_pwd

        if owner_password is None:
            owner_password = user_password
        if use_128bit:
            V = 2
            rev = 3
            keylen = int(128 / 8)
        else:
            V = 1
            rev = 2
            keylen = int(40 / 8)
        P = permissions_flag
        O = ByteStringObject(_alg33(owner_password, user_password, rev, keylen))[arg - type]  # type: ignore
        ID_1 = ByteStringObject(md5((repr(time.time())).encode("utf8")).digest())
        ID_2 = ByteStringObject(md5((repr(random.random())).encode("utf8")).digest())
        self._ID = ArrayObject((ID_1, ID_2))
        if rev == 2:
            U, key = _alg34(user_password, O, P, ID_1)
        else:
            assert rev == 3
            U, key = _alg35(user_password, rev, keylen, O, P, ID_1, False)[arg - type]  # type: ignore
        encrypt = DictionaryObject()
        encrypt[NameObject(SA.FILTER)] = NameObject("/Standard")
        encrypt[NameObject("/V")] = NumberObject(V)
        if V == 2:
            encrypt[NameObject(SA.LENGTH)] = NumberObject(keylen * 8)
        encrypt[NameObject(ED.R)] = NumberObject(rev)
        encrypt[NameObject(ED.O)] = ByteStringObject(O)
        encrypt[NameObject(ED.U)] = ByteStringObject(U)
        encrypt[NameObject(ED.P)] = NumberObject(P)
        self._encrypt = self._add_object(encrypt)
        self._encrypt_key = key

    def write_stream(self, stream: StreamType) -> None:
        if hasattr(stream, "mode") and "b" not in stream.mode:
            logger_warning(
                f"File <{stream.name}> to write to is not in binary mode. "
                "It may not be written to correctly.",
                __name__,
            )

        if not self._root:
            self._root = self._add_object(self._root_object)
        self._sweep_indirect_references(self._root)

        object_positions = self._write_header(stream)
        xref_location = self._write_xref_table(stream, object_positions)
        self._write_trailer(stream)
        stream.write(b_(f"\nstartxref\n{xref_location}\n%%EOF\n"))  # eof

    def write(self, stream: Union[Path, StrByteType]) -> Tuple[bool, IO]:
        my_file = False

        if stream == "":
            raise ValueError(f"Output(stream={stream}) is empty.")

        if isinstance(stream, (str, Path)):
            stream = FileIO(stream, "wb")
            self.with_as_usage = True  #
            my_file = True

        self.write_stream(stream)

        if self.with_as_usage:
            stream.close()

        return my_file, stream

    def _write_header(self, stream: StreamType) -> List[int]:
        object_positions = []
        stream.write(self.pdf_header + b"\n")
        stream.write(b"%\xE2\xE3\xCF\xD3\n")
        for i, obj in enumerate(self._objects):
            obj = self._objects[i]
            if obj is not None:
                idnum = i + 1
                object_positions.append(stream.tell())
                stream.write(b_(str(idnum)) + b" 0 obj\n")
                key = None
                if hasattr(self, "_encrypt") and idnum != self._encrypt.idnum:
                    pack1 = struct.pack("<i", i + 1)[:3]
                    pack2 = struct.pack("<i", 0)[:2]
                    key = self._encrypt_key + pack1 + pack2
                    assert len(key) == (len(self._encrypt_key) + 5)
                    md5_hash = md5(key).digest()
                    key = md5_hash[: min(16, len(self._encrypt_key) + 5)]
                obj.write_to_stream(stream, key)
                stream.write(b"\nendobj\n")
        return object_positions

    def _write_xref_table(self, stream: StreamType, object_positions: List[int]) -> int:
        xref_location = stream.tell()
        stream.write(b"xref\n")
        stream.write(b_(f"0 {len(self._objects) + 1}\n"))
        stream.write(b_(f"{0:0>10} {65535:0>5} f \n"))
        for offset in object_positions:
            stream.write(b_(f"{offset:0>10} {0:0>5} n \n"))
        return xref_location

    def _write_trailer(self, stream: StreamType) -> None:
        stream.write(b"trailer\n")
        trailer = DictionaryObject()
        trailer.update(
            {
                NameObject(TK.SIZE): NumberObject(len(self._objects) + 1),
                NameObject(TK.ROOT): self._root,
                NameObject(TK.INFO): self._info,
            }
        )
        if hasattr(self, "_ID"):
            trailer[NameObject(TK.ID)] = self._ID
        if hasattr(self, "_encrypt"):
            trailer[NameObject(TK.ENCRYPT)] = self._encrypt
        trailer.write_to_stream(stream, None)

    def add_metadata(self, infos: Dict[str, Any]) -> None:
        args = {}
        for key, value in list(infos.items()):
            args[NameObject(key)] = create_string_object(value)
        self.get_object(self._info).update(args)

    def addMetadata(self, infos: Dict[str, Any]) -> None:
        deprecation_with_replacement("addMetadata", "add_metadata", "3.0.0")
        self.add_metadata(infos)

    def _sweep_indirect_references(
        self,
        root: Union[
            ArrayObject,
            BooleanObject,
            DictionaryObject,
            FloatObject,
            IndirectObject,
            NameObject,
            PdfObject,
            NumberObject,
            TextStringObject,
            NullObject,
        ],
    ) -> None:
        stack: Deque[
            Tuple[
                Any,
                Optional[Any],
                Any,
                List[PdfObject],
            ]
        ] = collections.deque()
        discovered = []
        parent = None
        grant_parents: List[PdfObject] = []
        key_or_id = None
        stack.append((root, parent, key_or_id, grant_parents))

        while len(stack):
            data, parent, key_or_id, grant_parents = stack.pop()
            if isinstance(data, (ArrayObject, DictionaryObject)):
                for key, value in data.items():
                    stack.append(
                        (
                            value,
                            data,
                            key,
                            grant_parents + [parent] if parent is not None else [],
                        )
                    )
            elif isinstance(data, IndirectObject):
                if data.pdf != self:
                    data = self._resolve_indirect_object(data)

                    if str(data) not in discovered:
                        discovered.append(str(data))
                        stack.append((data.get_object(), None, None, []))
            if isinstance(parent, (DictionaryObject, ArrayObject)):
                if isinstance(data, StreamObject):
                    data = self._resolve_indirect_object(self._add_object(data))

                update_hashes = []
                if parent[key_or_id] != data:
                    update_hashes = [parent.hash_value()] + [
                        grant_parent.hash_value() for grant_parent in grant_parents
                    ]
                    parent[key_or_id] = data
                for old_hash in update_hashes:
                    indirect_reference = self._idnum_hash.pop(old_hash, None)

                    if indirect_reference is not None:
                        indirect_reference_obj = indirect_reference.get_object()

                        if indirect_reference_obj is not None:
                            self._idnum_hash[indirect_reference_obj.hash_value()] = (
                                indirect_reference
                            )

    def _resolve_indirect_object(self, data: IndirectObject) -> IndirectObject:
        if hasattr(data.pdf, "stream") and data.pdf.stream.closed:
            raise ValueError(f"I/O operation on closed file: {data.pdf.stream.name}")

        if data.pdf == self:
            return data
        real_obj = data.pdf.get_object(data)

        if real_obj is None:
            logger_warning(
                f"Unable to resolve [{data.__class__.__name__}: {data}], "
                "returning NullObject instead",
                __name__,
            )
            real_obj = NullObject()

        hash_value = real_obj.hash_value()
        if hash_value in self._idnum_hash:
            return self._idnum_hash[hash_value]

        if data.pdf == self:
            self._idnum_hash[hash_value] = IndirectObject(data.idnum, 0, self)
        else:
            self._idnum_hash[hash_value] = self._add_object(real_obj)

        return self._idnum_hash[hash_value]

    def get_reference(self, obj: PdfObject) -> IndirectObject:
        idnum = self._objects.index(obj) + 1
        ref = IndirectObject(idnum, 0, self)
        assert ref.get_object() == obj
        return ref

    def getReference(self, obj: PdfObject) -> IndirectObject:
        deprecation_with_replacement("getReference", "get_reference", "3.0.0")
        return self.get_reference(obj)

    def get_outline_root(self) -> TreeObject:
        if CO.OUTLINES in self._root_object:
            outline = cast(TreeObject, self._root_object[CO.OUTLINES])
            idnum = self._objects.index(outline) + 1
            outline_ref = IndirectObject(idnum, 0, self)
            assert outline_ref.get_object() == outline
        else:
            outline = TreeObject()
            outline.update({})
            outline_ref = self._add_object(outline)
            self._root_object[NameObject(CO.OUTLINES)] = outline_ref

        return outline

    def get_threads_root(self) -> ArrayObject:
        if CO.THREADS in self._root_object:
            threads = cast(ArrayObject, self._root_object[CO.THREADS])
        else:
            threads = ArrayObject()
            self._root_object[NameObject(CO.THREADS)] = threads
        return threads

    @property
    def threads(self) -> ArrayObject:
        return self.get_threads_root()

    def getOutlineRoot(self) -> TreeObject:
        deprecation_with_replacement("getOutlineRoot", "get_outline_root", "3.0.0")
        return self.get_outline_root()

    def get_named_dest_root(self) -> ArrayObject:
        if CA.NAMES in self._root_object and isinstance(
            self._root_object[CA.NAMES], DictionaryObject
        ):
            names = cast(DictionaryObject, self._root_object[CA.NAMES])
            names_ref = names.indirect_reference
            if CA.DESTS in names and isinstance(names[CA.DESTS], DictionaryObject):
                dests = cast(DictionaryObject, names[CA.DESTS])
                dests_ref = dests.indirect_reference
                if CA.NAMES in dests:
                    nd = cast(ArrayObject, dests[CA.NAMES])
                else:
                    nd = ArrayObject()
                    dests[NameObject(CA.NAMES)] = nd
            else:
                dests = DictionaryObject()
                dests_ref = self._add_object(dests)
                names[NameObject(CA.DESTS)] = dests_ref
                nd = ArrayObject()
                dests[NameObject(CA.NAMES)] = nd

        else:
            names = DictionaryObject()
            names_ref = self._add_object(names)
            self._root_object[NameObject(CA.NAMES)] = names_ref
            dests = DictionaryObject()
            dests_ref = self._add_object(dests)
            names[NameObject(CA.DESTS)] = dests_ref
            nd = ArrayObject()
            dests[NameObject(CA.NAMES)] = nd

        return nd

    def getNamedDestRoot(self) -> ArrayObject:
        deprecation_with_replacement("getNamedDestRoot", "get_named_dest_root", "3.0.0")
        return self.get_named_dest_root()

    def add_outline_item_destination(
        self,
        page_destination: Union[None, PageObject, TreeObject] = None,
        parent: Union[None, TreeObject, IndirectObject] = None,
        before: Union[None, TreeObject, IndirectObject] = None,
        dest: Union[None, PageObject, TreeObject] = None,
    ) -> IndirectObject:
        if page_destination is not None and dest is not None:
            raise ValueError(
                "The argument dest of add_outline_item_destination is deprecated. Use page_destination only."
            )
        if dest is not None:  # deprecated
            old_term = "dest"
            new_term = "page_destination"
            warnings.warn(
                message=(
                    f"{old_term} is deprecated as an argument and will be "
                    f"removed in PyPDF2 4.0.0. Use {new_term} instead"
                ),
                category=DeprecationWarning,
            )
            page_destination = dest
        if page_destination is None:
            raise ValueError("page_destination may not be None")

        if parent is None:
            parent = self.get_outline_root()

        parent = cast(TreeObject, parent.get_object())
        page_destination_ref = self._add_object(page_destination)
        if before is not None:
            before = before.indirect_reference
        parent.insert_child(page_destination_ref, before, self)

        return page_destination_ref

    def add_bookmark_destination(
        self,
        dest: Union[PageObject, TreeObject],
        parent: Union[None, TreeObject, IndirectObject] = None,
    ) -> IndirectObject:
        deprecation_with_replacement(
            "add_bookmark_destination", "add_outline_item_destination", "3.0.0"
        )
        return self.add_outline_item_destination(dest, parent)

    def addBookmarkDestination(
        self, dest: PageObject, parent: Optional[TreeObject] = None
    ) -> IndirectObject:
        deprecation_with_replacement(
            "addBookmarkDestination", "add_outline_item_destination", "3.0.0"
        )
        return self.add_outline_item_destination(dest, parent)

    @deprecation_bookmark(bookmark="outline_item")
    def add_outline_item_dict(
        self,
        outline_item: OutlineItemType,
        parent: Union[None, TreeObject, IndirectObject] = None,
        before: Union[None, TreeObject, IndirectObject] = None,
    ) -> IndirectObject:
        outline_item_object = TreeObject()
        for k, v in list(outline_item.items()):
            outline_item_object[NameObject(str(k))] = v
        outline_item_object.update(outline_item)

        if "/A" in outline_item:
            action = DictionaryObject()
            a_dict = cast(DictionaryObject, outline_item["/A"])
            for k, v in list(a_dict.items()):
                action[NameObject(str(k))] = v
            action_ref = self._add_object(action)
            outline_item_object[NameObject("/A")] = action_ref

        return self.add_outline_item_destination(outline_item_object, parent, before)

    @deprecation_bookmark(bookmark="outline_item")
    def add_bookmark_dict(
        self, outline_item: OutlineItemType, parent: Optional[TreeObject] = None
    ) -> IndirectObject:
        deprecation_with_replacement(
            "add_bookmark_dict", "add_outline_item_dict", "3.0.0"
        )
        return self.add_outline_item_dict(outline_item, parent)

    @deprecation_bookmark(bookmark="outline_item")
    def addBookmarkDict(
        self, outline_item: OutlineItemType, parent: Optional[TreeObject] = None
    ) -> IndirectObject:
        deprecation_with_replacement(
            "addBookmarkDict", "add_outline_item_dict", "3.0.0"
        )
        return self.add_outline_item_dict(outline_item, parent)

    def add_outline_item(
        self,
        title: str,
        page_number: Union[None, PageObject, IndirectObject, int],
        parent: Union[None, TreeObject, IndirectObject] = None,
        before: Union[None, TreeObject, IndirectObject] = None,
        color: Optional[Union[Tuple[float, float, float], str]] = None,
        bold: bool = False,
        italic: bool = False,
        fit: Fit = PAGE_FIT,
        pagenum: Optional[int] = None,
    ) -> IndirectObject:
        page_ref: Union[None, NullObject, IndirectObject, NumberObject]
        if isinstance(italic, Fit):
            if fit is not None and page_number is None:
                page_number = fit
            return self.add_outline_item(
                title, page_number, parent, None, before, color, bold, italic
            )
        if page_number is not None and pagenum is not None:
            raise ValueError(
                "The argument pagenum of add_outline_item is deprecated. Use page_number only."
            )
        if page_number is None:
            action_ref = None
        else:
            if isinstance(page_number, IndirectObject):
                page_ref = page_number
            elif isinstance(page_number, PageObject):
                page_ref = page_number.indirect_reference
            elif isinstance(page_number, int):
                try:
                    page_ref = self.pages[page_number].indirect_reference
                except IndexError:
                    page_ref = NumberObject(page_number)
            if page_ref is None:
                logger_warning(
                    f"can not find reference of page {page_number}",
                    __name__,
                )
                page_ref = NullObject()
            dest = Destination(
                NameObject("/" + title + " outline item"),
                page_ref,
                fit,
            )

            action_ref = self._add_object(
                DictionaryObject(
                    {
                        NameObject(GoToActionArguments.D): dest.dest_array,
                        NameObject(GoToActionArguments.S): NameObject("/GoTo"),
                    }
                )
            )
        outline_item = _create_outline_item(action_ref, title, color, italic, bold)

        if parent is None:
            parent = self.get_outline_root()
        return self.add_outline_item_destination(outline_item, parent, before)

    def add_bookmark(
        self,
        title: str,
        pagenum: int,
        parent: Union[None, TreeObject, IndirectObject] = None,
        color: Optional[Tuple[float, float, float]] = None,
        bold: bool = False,
        italic: bool = False,
        fit: FitType = "/Fit",
        *args: ZoomArgType,
    ) -> IndirectObject:
        deprecation_with_replacement("add_bookmark", "add_outline_item", "3.0.0")
        return self.add_outline_item(
            title,
            pagenum,
            parent,
            color,
            bold,
            italic,
            Fit(fit_type=fit, fit_args=args),
        )

    def addBookmark(
        self,
        title: str,
        pagenum: int,
        parent: Union[None, TreeObject, IndirectObject] = None,
        color: Optional[Tuple[float, float, float]] = None,
        bold: bool = False,
        italic: bool = False,
        fit: FitType = "/Fit",
        *args: ZoomArgType,
    ) -> IndirectObject:
        deprecation_with_replacement("addBookmark", "add_outline_item", "3.0.0")
        return self.add_outline_item(
            title,
            pagenum,
            parent,
            None,
            color,
            bold,
            italic,
            Fit(fit_type=fit, fit_args=args),
        )

    def add_outline(self) -> None:
        raise NotImplementedError(
            "This method is not yet implemented. Use :meth:`add_outline_item` instead."
        )

    def add_named_destination_array(
        self, title: TextStringObject, destination: Union[IndirectObject, ArrayObject]
    ) -> None:
        nd = self.get_named_dest_root()
        i = 0
        while i < len(nd):
            if title < nd[i]:
                nd.insert(i, destination)
                nd.insert(i, TextStringObject(title))
                return
            else:
                i += 2
        nd.extend([TextStringObject(title), destination])
        return

    def add_named_destination_object(
        self,
        page_destination: Optional[PdfObject] = None,
        dest: Optional[PdfObject] = None,
    ) -> IndirectObject:
        if page_destination is not None and dest is not None:
            raise ValueError(
                "The argument dest of add_named_destination_object is deprecated. Use page_destination only."
            )
        if dest is not None:  # deprecated
            old_term = "dest"
            new_term = "page_destination"
            warnings.warn(
                message=(
                    f"{old_term} is deprecated as an argument and will be "
                    f"removed in PyPDF2 4.0.0. Use {new_term} instead"
                ),
                category=DeprecationWarning,
            )
            page_destination = dest
        if page_destination is None:  # deprecated
            raise ValueError("page_destination may not be None")

        page_destination_ref = self._add_object(page_destination.dest_array)
        self.add_named_destination_array(
            cast("TextStringObject", page_destination["/Title"]), page_destination_ref
        )

        return page_destination_ref

    def addNamedDestinationObject(self, dest: Destination) -> IndirectObject:
        deprecation_with_replacement(
            "addNamedDestinationObject", "add_named_destination_object", "3.0.0"
        )
        return self.add_named_destination_object(dest)

    def add_named_destination(
        self,
        title: str,
        page_number: Optional[int] = None,
        pagenum: Optional[int] = None,  # deprecated
    ) -> IndirectObject:
        if page_number is not None and pagenum is not None:
            raise ValueError(
                "The argument pagenum of add_outline_item is deprecated. Use page_number only."
            )
        if pagenum is not None:
            old_term = "pagenum"
            new_term = "page_number"
            warnings.warn(
                message=(
                    f"{old_term} is deprecated as an argument and will be "
                    f"removed in PyPDF2 4.0.0. Use {new_term} instead"
                ),
                category=DeprecationWarning,
            )
            page_number = pagenum
        if page_number is None:
            raise ValueError("page_number may not be None")
        page_ref = self.get_object(self._pages)[PA.KIDS][page_number]
        dest = DictionaryObject()
        dest.update(
            {
                NameObject(GoToActionArguments.D): ArrayObject(
                    [page_ref, NameObject(TypFitArguments.FIT_H), NumberObject(826)]
                ),
                NameObject(GoToActionArguments.S): NameObject("/GoTo"),
            }
        )

        dest_ref = self._add_object(dest)
        nd = self.get_named_dest_root()
        if not isinstance(title, TextStringObject):
            title = TextStringObject(str(title))
        nd.extend([title, dest_ref])
        return dest_ref

    def addNamedDestination(self, title: str, pagenum: int) -> IndirectObject:
        deprecation_with_replacement(
            "addNamedDestination", "add_named_destination", "3.0.0"
        )
        return self.add_named_destination(title, pagenum)

    def remove_links(self) -> None:
        pg_dict = cast(DictionaryObject, self.get_object(self._pages))
        pages = cast(ArrayObject, pg_dict[PA.KIDS])
        for page in pages:
            page_ref = cast(DictionaryObject, self.get_object(page))
            if PG.ANNOTS in page_ref:
                del page_ref[PG.ANNOTS]

    def removeLinks(self) -> None:
        deprecation_with_replacement("removeLinks", "remove_links", "3.0.0")
        return self.remove_links()

    def remove_images(self, ignore_byte_string_object: bool = False) -> None:
        pg_dict = cast(DictionaryObject, self.get_object(self._pages))
        pages = cast(ArrayObject, pg_dict[PA.KIDS])
        jump_operators = (
            b"cm",
            b"w",
            b"J",
            b"j",
            b"M",
            b"d",
            b"ri",
            b"i",
            b"gs",
            b"W",
            b"b",
            b"s",
            b"S",
            b"f",
            b"F",
            b"n",
            b"m",
            b"l",
            b"c",
            b"v",
            b"y",
            b"h",
            b"B",
            b"Do",
            b"sh",
        )
        for page in pages:
            page_ref = cast(DictionaryObject, self.get_object(page))
            content = page_ref["/Contents"].get_object()
            if not isinstance(content, ContentStream):
                content = ContentStream(content, page_ref)

            _operations = []
            seq_graphics = False
            for operands, operator in content.operations:
                if operator in [b"Tj", b"'"]:
                    text = operands[0]
                    if ignore_byte_string_object and not isinstance(
                        text, TextStringObject
                    ):
                        operands[0] = TextStringObject()
                elif operator == b'"':
                    text = operands[2]
                    if ignore_byte_string_object and not isinstance(
                        text, TextStringObject
                    ):
                        operands[2] = TextStringObject()
                elif operator == b"TJ":
                    for i in range(len(operands[0])):
                        if ignore_byte_string_object and not isinstance(
                            operands[0][i], TextStringObject
                        ):
                            operands[0][i] = TextStringObject()

                if operator == b"q":
                    seq_graphics = True
                if operator == b"Q":
                    seq_graphics = False
                if seq_graphics and operator in jump_operators:
                    continue
                if operator == b"re":
                    continue
                _operations.append((operands, operator))

            content.operations = _operations
            page_ref.__setitem__(NameObject("/Contents"), content)

    def removeImages(self, ignoreByteStringObject: bool = False) -> None:
        deprecation_with_replacement("removeImages", "remove_images", "3.0.0")
        return self.remove_images(ignoreByteStringObject)

    def remove_text(self, ignore_byte_string_object: bool = False) -> None:
        pg_dict = cast(DictionaryObject, self.get_object(self._pages))
        pages = cast(List[IndirectObject], pg_dict[PA.KIDS])
        for page in pages:
            page_ref = cast(PageObject, self.get_object(page))
            content = page_ref["/Contents"].get_object()
            if not isinstance(content, ContentStream):
                content = ContentStream(content, page_ref)
            for operands, operator in content.operations:
                if operator in [b"Tj", b"'"]:
                    text = operands[0]
                    if not ignore_byte_string_object:
                        if isinstance(text, TextStringObject):
                            operands[0] = TextStringObject()
                    else:
                        if isinstance(text, (TextStringObject, ByteStringObject)):
                            operands[0] = TextStringObject()
                elif operator == b'"':
                    text = operands[2]
                    if not ignore_byte_string_object:
                        if isinstance(text, TextStringObject):
                            operands[2] = TextStringObject()
                    else:
                        if isinstance(text, (TextStringObject, ByteStringObject)):
                            operands[2] = TextStringObject()
                elif operator == b"TJ":
                    for i in range(len(operands[0])):
                        if not ignore_byte_string_object:
                            if isinstance(operands[0][i], TextStringObject):
                                operands[0][i] = TextStringObject()
                        else:
                            if isinstance(
                                operands[0][i], (TextStringObject, ByteStringObject)
                            ):
                                operands[0][i] = TextStringObject()

            page_ref.__setitem__(NameObject("/Contents"), content)

    def removeText(self, ignoreByteStringObject: bool = False) -> None:
        deprecation_with_replacement("removeText", "remove_text", "3.0.0")
        return self.remove_text(ignoreByteStringObject)

    def add_uri(
        self,
        page_number: int,
        uri: str,
        rect: RectangleObject,
        border: Optional[ArrayObject] = None,
        pagenum: Optional[int] = None,
    ) -> None:
        if pagenum is not None:
            warnings.warn(
                "The 'pagenum' argument of add_uri is deprecated and will be "
                "removed in PyPDF2 4.0.0. Use 'page_number' instead.",
                category=DeprecationWarning,
            )
            page_number = pagenum
        page_link = self.get_object(self._pages)[PA.KIDS][page_number]
        page_ref = cast(Dict[str, Any], self.get_object(page_link))

        border_arr: BorderArrayType
        if border is not None:
            border_arr = [NameObject(n) for n in border[:3]]
            if len(border) == 4:
                dash_pattern = ArrayObject([NameObject(n) for n in border[3]])
                border_arr.append(dash_pattern)
        else:
            border_arr = [NumberObject(2)] * 3

        if isinstance(rect, str):
            rect = NameObject(rect)
        elif isinstance(rect, RectangleObject):
            pass
        else:
            rect = RectangleObject(rect)

        lnk2 = DictionaryObject()
        lnk2.update(
            {
                NameObject("/S"): NameObject("/URI"),
                NameObject("/URI"): TextStringObject(uri),
            }
        )
        lnk = DictionaryObject()
        lnk.update(
            {
                NameObject(AnnotationDictionaryAttributes.Type): NameObject(PG.ANNOTS),
                NameObject(AnnotationDictionaryAttributes.Subtype): NameObject("/Link"),
                NameObject(AnnotationDictionaryAttributes.P): page_link,
                NameObject(AnnotationDictionaryAttributes.Rect): rect,
                NameObject("/H"): NameObject("/I"),
                NameObject(AnnotationDictionaryAttributes.Border): ArrayObject(
                    border_arr
                ),
                NameObject("/A"): lnk2,
            }
        )
        lnk_ref = self._add_object(lnk)

        if PG.ANNOTS in page_ref:
            page_ref[PG.ANNOTS].append(lnk_ref)
        else:
            page_ref[NameObject(PG.ANNOTS)] = ArrayObject([lnk_ref])

    def addURI(
        self,
        pagenum: int,
        uri: str,
        rect: RectangleObject,
        border: Optional[ArrayObject] = None,
    ) -> None:
        deprecation_with_replacement("addURI", "add_uri", "3.0.0")
        return self.add_uri(pagenum, uri, rect, border)

    def add_link(
        self,
        pagenum: int,
        page_destination: int,
        rect: RectangleObject,
        border: Optional[ArrayObject] = None,
        fit: FitType = "/Fit",
        *args: ZoomArgType,
    ) -> None:
        deprecation_with_replacement(
            "add_link", "add_annotation(AnnotationBuilder.link(...))"
        )

        if isinstance(rect, str):
            rect = rect.strip()[1:-1]
            rect = RectangleObject(
                [float(num) for num in rect.split(" ") if len(num) > 0]
            )
        elif isinstance(rect, RectangleObject):
            pass
        else:
            rect = RectangleObject(rect)

        annotation = AnnotationBuilder.link(
            rect=rect,
            border=border,
            target_page_index=page_destination,
            fit=Fit(fit_type=fit, fit_args=args),
        )
        return self.add_annotation(page_number=pagenum, annotation=annotation)

    def addLink(
        self,
        pagenum: int,
        page_destination: int,
        rect: RectangleObject,
        border: Optional[ArrayObject] = None,
        fit: FitType = "/Fit",
        *args: ZoomArgType,
    ) -> None:
        deprecate_with_replacement(
            "addLink", "add_annotation(AnnotationBuilder.link(...))", "4.0.0"
        )
        return self.add_link(pagenum, page_destination, rect, border, fit, *args)

    _valid_layouts = (
        "/NoLayout",
        "/SinglePage",
        "/OneColumn",
        "/TwoColumnLeft",
        "/TwoColumnRight",
        "/TwoPageLeft",
        "/TwoPageRight",
    )

    def _get_page_layout(self) -> Optional[LayoutType]:
        try:
            return cast(LayoutType, self._root_object["/PageLayout"])
        except KeyError:
            return None

    def getPageLayout(self) -> Optional[LayoutType]:
        deprecation_with_replacement("getPageLayout", "page_layout", "3.0.0")
        return self._get_page_layout()

    def _set_page_layout(self, layout: Union[NameObject, LayoutType]) -> None:
        if not isinstance(layout, NameObject):
            if layout not in self._valid_layouts:
                logger_warning(
                    f"Layout should be one of: {'', ''.join(self._valid_layouts)}",
                    __name__,
                )
            layout = NameObject(layout)
        self._root_object.update({NameObject("/PageLayout"): layout})

    def set_page_layout(self, layout: LayoutType) -> None:
        self._set_page_layout(layout)

    def setPageLayout(self, layout: LayoutType) -> None:
        deprecation_with_replacement(
            "writer.setPageLayout(val)", "writer.page_layout = val", "3.0.0"
        )
        return self._set_page_layout(layout)

    @property
    def page_layout(self) -> Optional[LayoutType]:
        return self._get_page_layout()

    @page_layout.setter
    def page_layout(self, layout: LayoutType) -> None:
        self._set_page_layout(layout)

    @property
    def pageLayout(self) -> Optional[LayoutType]:
        deprecation_with_replacement("pageLayout", "page_layout", "3.0.0")
        return self.page_layout

    @pageLayout.setter
    def pageLayout(self, layout: LayoutType) -> None:
        deprecation_with_replacement("pageLayout", "page_layout", "3.0.0")
        self.page_layout = layout

    _valid_modes = (
        "/UseNone",
        "/UseOutlines",
        "/UseThumbs",
        "/FullScreen",
        "/UseOC",
        "/UseAttachments",
    )

    def _get_page_mode(self) -> Optional[PagemodeType]:
        try:
            return cast(PagemodeType, self._root_object["/PageMode"])
        except KeyError:
            return None

    def getPageMode(self) -> Optional[PagemodeType]:
        deprecation_with_replacement("getPageMode", "page_mode", "3.0.0")
        return self._get_page_mode()

    def set_page_mode(self, mode: PagemodeType) -> None:
        if isinstance(mode, NameObject):
            mode_name: NameObject = mode
        else:
            if mode not in self._valid_modes:
                logger_warning(
                    f"Mode should be one of: {', '.join(self._valid_modes)}", __name__
                )
            mode_name = NameObject(mode)
        self._root_object.update({NameObject("/PageMode"): mode_name})

    def setPageMode(self, mode: PagemodeType) -> None:  # pragma: no cover
        deprecation_with_replacement(
            "writer.setPageMode(val)", "writer.page_mode = val", "3.0.0"
        )
        self.set_page_mode(mode)

    @property
    def page_mode(self) -> Optional[PagemodeType]:
        return self._get_page_mode()

    @page_mode.setter
    def page_mode(self, mode: PagemodeType) -> None:
        self.set_page_mode(mode)

    @property
    def pageMode(self) -> Optional[PagemodeType]:
        deprecation_with_replacement("pageMode", "page_mode", "3.0.0")
        return self.page_mode

    @pageMode.setter
    def pageMode(self, mode: PagemodeType) -> None:
        deprecation_with_replacement("pageMode", "page_mode", "3.0.0")
        self.page_mode = mode

    def add_annotation(self, page_number: int, annotation: Dict[str, Any]) -> None:
        to_add = cast(DictionaryObject, _pdf_objectify(annotation))
        to_add[NameObject("/P")] = self.get_object(self._pages)["/Kids"][page_number]
        page = self.pages[page_number]
        if page.annotations is None:
            page[NameObject("/Annots")] = ArrayObject()
        assert page.annotations is not None
        if to_add.get("/Subtype") == "/Link" and NameObject("/Dest") in to_add:
            tmp = cast(dict, to_add[NameObject("/Dest")])
            dest = Destination(
                NameObject("/LinkName"),
                tmp["target_page_index"],
                Fit(fit_type=tmp["fit"], fit_args=dict(tmp)["fit_args"]),
            )
            to_add[NameObject("/Dest")] = dest.dest_array

        ind_obj = self._add_object(to_add)

        page.annotations.append(ind_obj)

    def clean_page(self, page: Union[PageObject, IndirectObject]) -> PageObject:
        page = cast("PageObject", page.get_object())
        for a in page.get("/Annots", []):
            a_obj = a.get_object()
            d = a_obj.get("/Dest", None)
            act = a_obj.get("/A", None)
            if isinstance(d, NameObject):
                a_obj[NameObject("/Dest")] = TextStringObject(d)
            elif act is not None:
                act = act.get_object()
                d = act.get("/D", None)
                if isinstance(d, NameObject):
                    act[NameObject("/D")] = TextStringObject(d)
        return page

    def _create_stream(
        self, fileobj: Union[Path, StrByteType, PdfReader]
    ) -> Tuple[IOBase, Optional[Encryption]]:
        encryption_obj = None
        stream: IOBase
        if isinstance(fileobj, (str, Path)):
            with FileIO(fileobj, "rb") as f:
                stream = BytesIO(f.read())
        elif isinstance(fileobj, PdfReader):
            if fileobj._encryption:
                encryption_obj = fileobj._encryption
            orig_tell = fileobj.stream.tell()
            fileobj.stream.seek(0)
            stream = BytesIO(fileobj.stream.read())

            # reset the stream to its original location
            fileobj.stream.seek(orig_tell)
        elif hasattr(fileobj, "seek") and hasattr(fileobj, "read"):
            fileobj.seek(0)
            filecontent = fileobj.read()
            stream = BytesIO(filecontent)
        else:
            raise NotImplementedError(
                "PdfMerger.merge requires an object that PdfReader can parse. "
                "Typically, that is a Path or a string representing a Path, "
                "a file object, or an object implementing .seek and .read. "
                "Passing a PdfReader directly works as well."
            )
        return stream, encryption_obj

    def append(
        self,
        fileobj: Union[StrByteType, PdfReader, Path],
        outline_item: Union[
            str, None, PageRange, Tuple[int, int], Tuple[int, int, int], List[int]
        ] = None,
        pages: Union[
            None, PageRange, Tuple[int, int], Tuple[int, int, int], List[int]
        ] = None,
        import_outline: bool = True,
        excluded_fields: Optional[Union[List[str], Tuple[str, ...]]] = None,
    ) -> None:
        if excluded_fields is None:
            excluded_fields = ()
        if isinstance(outline_item, (tuple, list, PageRange)):
            if isinstance(pages, bool):
                if not isinstance(import_outline, bool):
                    excluded_fields = import_outline
                import_outline = pages
            pages = outline_item
            self.merge(None, fileobj, None, pages, import_outline, excluded_fields)
        else:  # if isinstance(outline_item,str):
            self.merge(
                None, fileobj, outline_item, pages, import_outline, excluded_fields
            )

    @deprecation_bookmark(bookmark="outline_item", import_bookmarks="import_outline")
    def merge(
        self,
        position: Optional[int],
        fileobj: Union[Path, StrByteType, PdfReader],
        outline_item: Optional[str] = None,
        pages: Optional[PageRangeSpec] = None,
        import_outline: bool = True,
        excluded_fields: Optional[Union[List[str], Tuple[str, ...]]] = (),
    ) -> None:
        if isinstance(fileobj, PdfReader):
            reader = fileobj
        else:
            stream, encryption_obj = self._create_stream(fileobj)
            # Create a new PdfReader instance using the stream
            # (either file or BytesIO or StringIO) created above
            reader = PdfReader(stream, strict=False)[arg - type]  # type: ignore

        if excluded_fields is None:
            excluded_fields = ()
        # Find the range of pages to merge.
        if pages is None:
            pages = list(range(0, len(reader.pages)))
        elif isinstance(pages, PageRange):
            pages = list(range(*pages.indices(len(reader.pages))))
        elif isinstance(pages, list):
            pass  # keep unchanged
        elif isinstance(pages, tuple) and len(pages) <= 3:
            pages = list(range(*pages))
        elif not isinstance(pages, tuple):
            raise TypeError(
                '"pages" must be a tuple of (start, stop[, step]) or a list'
            )

        srcpages = {}
        for i in pages:
            pg = reader.pages[i]
            assert pg.indirect_reference is not None
            if position is None:
                srcpages[pg.indirect_reference.idnum] = self.add_page(
                    pg, list(excluded_fields) + ["/B", "/Annots"]
                )
            else:
                srcpages[pg.indirect_reference.idnum] = self.insert_page(
                    pg, position, list(excluded_fields) + ["/B", "/Annots"]
                )
                position += 1
            srcpages[pg.indirect_reference.idnum].original_page = pg

        reader._namedDests = reader.named_destinations
        for dest in reader._namedDests.values():
            arr = dest.dest_array
            # try:
            if isinstance(dest["/Page"], NullObject):
                pass  # self.add_named_destination_array(dest["/Title"],arr)
            elif dest["/Page"].indirect_reference.idnum in srcpages:
                arr[NumberObject(0)] = srcpages[
                    dest["/Page"].indirect_reference.idnum
                ].indirect_reference
                self.add_named_destination_array(dest["/Title"], arr)
            # except Exception as e:
            #    logger_warning(f"can not insert {dest} : {e.msg}",__name__)

        outline_item_typ: TreeObject
        if outline_item is not None:
            outline_item_typ = cast(
                "TreeObject",
                self.add_outline_item(
                    TextStringObject(outline_item),
                    list(srcpages.values())[0].indirect_reference,
                    fit=PAGE_FIT,
                ).get_object(),
            )
        else:
            outline_item_typ = self.get_outline_root()

        _ro = cast("DictionaryObject", reader.trailer[TK.ROOT])
        if import_outline and CO.OUTLINES in _ro:
            outline = self._get_filtered_outline(
                _ro.get(CO.OUTLINES, None), srcpages, reader
            )
            self._insert_filtered_outline(
                outline, outline_item_typ, None
            )  # TODO : use before parameter

        if "/Annots" not in excluded_fields:
            for pag in srcpages.values():
                lst = self._insert_filtered_annotations(
                    pag.original_page.get("/Annots", ()), pag, srcpages, reader
                )
                if len(lst) > 0:
                    pag[NameObject("/Annots")] = lst
                self.clean_page(pag)

        if "/B" not in excluded_fields:
            self.add_filtered_articles("", srcpages, reader)

        return

    def _add_articles_thread(
        self,
        thread: DictionaryObject,
        pages: Dict[int, PageObject],
        reader: PdfReader,
    ) -> IndirectObject:
        nthread = thread.clone(self, force_duplicate=True, ignore_fields=("/F",))
        self.threads.append(nthread.indirect_reference)
        first_article = cast("DictionaryObject", thread["/F"])
        current_article: Optional[DictionaryObject] = first_article
        new_article: Optional[DictionaryObject] = None
        while current_article is not None:
            pag = self._get_cloned_page(
                cast("PageObject", current_article["/P"]), pages, reader
            )
            if pag is not None:
                if new_article is None:
                    new_article = cast(
                        "DictionaryObject",
                        self._add_object(DictionaryObject()).get_object(),
                    )
                    new_first = new_article
                    nthread[NameObject("/F")] = new_article.indirect_reference
                else:
                    new_article2 = cast(
                        "DictionaryObject",
                        self._add_object(
                            DictionaryObject(
                                {NameObject("/V"): new_article.indirect_reference}
                            )
                        ).get_object(),
                    )
                    new_article[NameObject("/N")] = new_article2.indirect_reference
                    new_article = new_article2
                new_article[NameObject("/P")] = pag
                new_article[NameObject("/T")] = nthread.indirect_reference
                new_article[NameObject("/R")] = current_article["/R"]
                pag_obj = cast("PageObject", pag.get_object())
                if "/B" not in pag_obj:
                    pag_obj[NameObject("/B")] = ArrayObject()
                cast("ArrayObject", pag_obj["/B"]).append(
                    new_article.indirect_reference
                )
            current_article = cast("DictionaryObject", current_article["/N"])
            if current_article == first_article:
                new_article[NameObject("/N")] = new_first.indirect_reference
                new_first[NameObject("/V")] = new_article.indirect_reference
                current_article = None
        assert nthread.indirect_reference is not None
        return nthread.indirect_reference

    def add_filtered_articles(
        self,
        fltr: Union[Pattern, str],
        pages: Dict[int, PageObject],
        reader: PdfReader,
    ) -> None:
        if isinstance(fltr, str):
            fltr = re.compile(fltr)
        elif not isinstance(fltr, Pattern):
            fltr = re.compile("")
        for p in pages.values():
            pp = p.original_page
            for a in pp.get("/B", ()):
                thr = a.get_object()["/T"]
                if thr.indirect_reference.idnum not in self._id_translated[
                    id(reader)
                ] and fltr.search(thr["/I"]["/Title"]):
                    self._add_articles_thread(thr, pages, reader)

    def _get_cloned_page(
        self,
        page: Union[None, int, IndirectObject, PageObject, NullObject],
        pages: Dict[int, PageObject],
        reader: PdfReader,
    ) -> Optional[IndirectObject]:
        if isinstance(page, NullObject):
            return None
        if isinstance(page, int):
            _i = reader.pages[page].indirect_reference
        elif isinstance(page, DictionaryObject) and page.get("/Type", "") == "/Page":
            _i = page.indirect_reference
        elif isinstance(page, IndirectObject):
            _i = page
        try:
            return pages[_i.idnum].indirect_reference
        except Exception:
            return None

    def _insert_filtered_annotations(
        self,
        annots: Union[IndirectObject, List[DictionaryObject]],
        page: PageObject,
        pages: Dict[int, PageObject],
        reader: PdfReader,
    ) -> List[Destination]:
        outlist = ArrayObject()
        if isinstance(annots, IndirectObject):
            annots = cast("List", annots.get_object())
        for an in annots:
            ano = cast("DictionaryObject", an.get_object())
            if (
                ano["/Subtype"] != "/Link"
                or "/A" not in ano
                or cast("DictionaryObject", ano["/A"])["/S"] != "/GoTo"
                or "/Dest" in ano
            ):
                if "/Dest" not in ano:
                    outlist.append(ano.clone(self).indirect_reference)
                else:
                    d = ano["/Dest"]
                    if isinstance(d, str):
                        if str(d) in self.get_named_dest_root():
                            outlist.append(ano.clone(self).indirect_reference)
                    else:
                        d = cast("ArrayObject", d)
                        p = self._get_cloned_page(d[0], pages, reader)
                        if p is not None:
                            anc = ano.clone(self, ignore_fields=("/Dest",))
                            anc[NameObject("/Dest")] = ArrayObject([p] + d[1:])
                            outlist.append(anc.indirect_reference)
            else:
                d = cast("DictionaryObject", ano["/A"])["/D"]
                if isinstance(d, str):
                    if str(d) in self.get_named_dest_root():
                        outlist.append(ano.clone(self).indirect_reference)
                else:
                    d = cast("ArrayObject", d)
                    p = self._get_cloned_page(d[0], pages, reader)
                    if p is not None:
                        anc = ano.clone(self, ignore_fields=("/D",))
                        anc = cast("DictionaryObject", anc)
                        cast("DictionaryObject", anc["/A"])[NameObject("/D")] = (
                            ArrayObject([p] + d[1:])
                        )
                        outlist.append(anc.indirect_reference)
        return outlist

    def _get_filtered_outline(
        self,
        node: Any,
        pages: Dict[int, PageObject],
        reader: PdfReader,
    ) -> List[Destination]:
        new_outline = []
        node = node.get_object()
        if node.get("/Type", "") == "/Outlines" or "/Title" not in node:
            node = node.get("/First", None)
            if node is not None:
                node = node.get_object()
                new_outline += self._get_filtered_outline(node, pages, reader)
        else:
            v: Union[None, IndirectObject, NullObject]
            while node is not None:
                node = node.get_object()
                o = cast("Destination", reader._build_outline_item(node))
                v = self._get_cloned_page(cast("PageObject", o["/Page"]), pages, reader)
                if v is None:
                    v = NullObject()
                o[NameObject("/Page")] = v
                if "/First" in node:
                    o.childs = self._get_filtered_outline(node["/First"], pages, reader)
                else:
                    o.childs = []
                if not isinstance(o["/Page"], NullObject) or len(o.childs) > 0:
                    new_outline.append(o)
                node = node.get("/Next", None)
        return new_outline

    def _clone_outline(self, dest: Destination) -> TreeObject:
        n_ol = TreeObject()
        self._add_object(n_ol)
        n_ol[NameObject("/Title")] = TextStringObject(dest["/Title"])
        if not isinstance(dest["/Page"], NullObject):
            if dest.node is not None and "/A" in dest.node:
                n_ol[NameObject("/A")] = dest.node["/A"].clone(self)
            else:
                n_ol[NameObject("/Dest")] = dest.dest_array
        # TODO: /SE
        if dest.node is not None:
            n_ol[NameObject("/F")] = NumberObject(dest.node.get("/F", 0))
            n_ol[NameObject("/C")] = ArrayObject(
                dest.node.get(
                    "/C", [FloatObject(0.0), FloatObject(0.0), FloatObject(0.0)]
                )
            )
        return n_ol

    def _insert_filtered_outline(
        self,
        outlines: List[Destination],
        parent: Union[TreeObject, IndirectObject],
        before: Union[None, TreeObject, IndirectObject] = None,
    ) -> None:
        for dest in outlines:
            # TODO  : can be improved to keep A and SE entries (ignored for the moment)
            if dest.get("/Type", "") == "/Outlines" or "/Title" not in dest:
                np = parent
            else:
                np = self._clone_outline(dest)
                cast(TreeObject, parent.get_object()).insert_child(np, before, self)
            self._insert_filtered_outline(dest.childs, np, None)

    def close(self) -> None:
        """To match the functions from Merger"""
        return

    def find_outline_item(
        self,
        outline_item: Dict[str, Any],
        root: Optional[OutlineType] = None,
    ) -> Optional[List[int]]:
        if root is None:
            o = self.get_outline_root()
        else:
            o = cast("TreeObject", root)

        i = 0
        while o is not None:
            if (
                o.indirect_reference == outline_item
                or o.get("/Title", None) == outline_item
            ):
                return [i]
            else:
                if "/First" in o:
                    res = self.find_outline_item(
                        outline_item, cast(OutlineType, o["/First"])
                    )
                    if res:
                        return ([i] if "/Title" in o else []) + res
            if "/Next" in o:
                i += 1
                o = cast(TreeObject, o["/Next"])
            else:
                return None

    @deprecation_bookmark(bookmark="outline_item")
    def find_bookmark(
        self,
        outline_item: Dict[str, Any],
        root: Optional[OutlineType] = None,
    ) -> Optional[List[int]]:
        return self.find_outline_item(outline_item, root)

    def reset_translation(
        self, reader: Union[None, PdfReader, IndirectObject] = None
    ) -> None:
        if reader is None:
            self._id_translated = {}
        elif isinstance(reader, PdfReader):
            try:
                del self._id_translated[id(reader)]
            except Exception:
                pass
        elif isinstance(reader, IndirectObject):
            try:
                del self._id_translated[id(reader.pdf)]
            except Exception:
                pass
        else:
            raise Exception("invalid parameter {reader}")


def _pdf_objectify(obj: Union[Dict[str, Any], str, int, List[Any]]) -> PdfObject:
    if isinstance(obj, PdfObject):
        return obj
    if isinstance(obj, dict):
        to_add = DictionaryObject()
        for key, value in obj.items():
            name_key = NameObject(key)
            casted_value = _pdf_objectify(value)
            to_add[name_key] = casted_value
        return to_add
    elif isinstance(obj, list):
        arr = ArrayObject()
        for el in obj:
            arr.append(_pdf_objectify(el))
        return arr
    elif isinstance(obj, str):
        if obj.startswith("/"):
            return NameObject(obj)
        else:
            return TextStringObject(obj)
    elif isinstance(obj, (int, float)):
        return FloatObject(obj)
    else:
        raise NotImplementedError(
            f"type(obj)={type(obj)} could not be casted to PdfObject"
        )


def _create_outline_item(
    action_ref: Union[None, IndirectObject],
    title: str,
    color: Union[Tuple[float, float, float], str, None],
    italic: bool,
    bold: bool,
) -> TreeObject:
    outline_item = TreeObject()
    if action_ref is not None:
        outline_item[NameObject("/A")] = action_ref
    outline_item.update(
        {
            NameObject("/Title"): create_string_object(title),
        }
    )
    if color:
        if isinstance(color, str):
            color = hex_to_rgb(color)
        prec = decimal.Decimal("1.00000")
        outline_item.update(
            {
                NameObject("/C"): ArrayObject(
                    [FloatObject(decimal.Decimal(c).quantize(prec)) for c in color]
                )
            }
        )
    if italic or bold:
        format_flag = 0
        if italic:
            format_flag += 1
        if bold:
            format_flag += 2
        outline_item.update({NameObject("/F"): NumberObject(format_flag)})
    return outline_item


class PdfFileWriter(PdfWriter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        deprecation_with_replacement("PdfFileWriter", "PdfWriter", "3.0.0")
        super().__init__(*args, **kwargs)
