import os
import re
import struct
import zlib
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

from ._encryption import Encryption, PasswordType
from ._page import PageObject, _VirtualList
from ._utils import (
    StrByteType,
    StreamType,
    b_,
    deprecate_no_replacement,
    deprecation_no_replacement,
    deprecation_with_replacement,
    logger_warning,
    read_non_whitespace,
    read_previous_line,
    read_until_whitespace,
    skip_over_comment,
    skip_over_whitespace,
)
from .constants import CatalogAttributes as CA
from .constants import CatalogDictionary as CD
from .constants import CheckboxRadioButtonAttributes
from .constants import Core as CO
from .constants import DocumentInformationAttributes as DI
from .constants import FieldDictionaryAttributes, GoToActionArguments
from .constants import PageAttributes as PG
from .constants import PagesAttributes as PA
from .constants import TrailerKeys as TK
from .errors import (
    EmptyFileError,
    FileNotDecryptedError,
    PdfReadError,
    PdfStreamError,
    WrongPasswordError,
)
from .generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    Destination,
    DictionaryObject,
    EncodedStreamObject,
    Field,
    Fit,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    PdfObject,
    TextStringObject,
    TreeObject,
    read_object,
)
from ._types import OutlineType, PagemodeType
from .xmp import XmpInformation


def convert_to_int(d: bytes, size: int) -> Union[int, Tuple[Any, ...]]:
    if size > 8:
        raise PdfReadError("invalid size in convert_to_int")
    d = b"\x00\x00\x00\x00\x00\x00\x00\x00" + d
    d = d[-8:]
    return struct.unpack(">q", d)[0]


def convertToInt(
    d: bytes, size: int
) -> Union[int, Tuple[Any, ...]]:  # pragma: no cover
    deprecation_with_replacement("convertToInt", "convert_to_int")
    return convert_to_int(d, size)


class DocumentInformation(DictionaryObject):
    def __init__(self) -> None:
        DictionaryObject.__init__(self)

    def _get_text(self, key: str) -> Optional[str]:
        retval = self.get(key, None)
        if isinstance(retval, TextStringObject):
            return retval
        return None

    def getText(self, key: str) -> Optional[str]:
        deprecation_no_replacement("getText", "3.0.0")
        return self._get_text(key)

    @property
    def title(self) -> Optional[str]:
        return (
            self._get_text(DI.TITLE) or self.get(DI.TITLE).get_object()
            if self.get(DI.TITLE)
            else None
        )

    @property
    def title_raw(self) -> Optional[str]:
        return self.get(DI.TITLE)

    @property
    def author(self) -> Optional[str]:
        return self._get_text(DI.AUTHOR)

    @property
    def author_raw(self) -> Optional[str]:
        return self.get(DI.AUTHOR)

    @property
    def subject(self) -> Optional[str]:
        return self._get_text(DI.SUBJECT)

    @property
    def subject_raw(self) -> Optional[str]:
        return self.get(DI.SUBJECT)

    @property
    def creator(self) -> Optional[str]:
        return self._get_text(DI.CREATOR)

    @property
    def creator_raw(self) -> Optional[str]:
        return self.get(DI.CREATOR)

    @property
    def producer(self) -> Optional[str]:
        return self._get_text(DI.PRODUCER)

    @property
    def producer_raw(self) -> Optional[str]:
        return self.get(DI.PRODUCER)

    @property
    def creation_date(self) -> Optional[datetime]:
        text = self._get_text(DI.CREATION_DATE)
        if text is None:
            return None
        return datetime.strptime(text.replace("'", ""), "D:%Y%m%d%H%M%S%z")

    @property
    def creation_date_raw(self) -> Optional[str]:
        return self.get(DI.CREATION_DATE)

    @property
    def modification_date(self) -> Optional[datetime]:
        text = self._get_text(DI.MOD_DATE)
        if text is None:
            return None
        return datetime.strptime(text.replace("'", ""), "D:%Y%m%d%H%M%S%z")

    @property
    def modification_date_raw(self) -> Optional[str]:
        return self.get(DI.MOD_DATE)


class PdfReader:

    def __init__(
        self,
        stream: Union[StrByteType, Path],
        strict: bool = False,
        password: Union[None, str, bytes] = None,
    ) -> None:
        self.strict = strict
        self.flattened_pages: Optional[List[PageObject]] = None
        self.resolved_objects: Dict[Tuple[Any, Any], Optional[PdfObject]] = {}
        self.xref_index = 0
        self._page_id2num: Optional[Dict[Any, Any]] = None
        if hasattr(stream, "mode") and "b" not in stream.mode:
            logger_warning(
                "PdfReader stream/file object is not in binary mode. "
                "It may not be read correctly.",
                __name__,
            )
        if isinstance(stream, (str, Path)):
            with open(stream, "rb") as fh:
                stream = BytesIO(fh.read())
        self.read(stream)
        self.stream = stream

        self._override_encryption = False
        self._encryption: Optional[Encryption] = None
        if self.is_encrypted:
            self._override_encryption = True
            id_entry = self.trailer.get(TK.ID)
            id1_entry = id_entry[0].get_object().original_bytes if id_entry else b""
            encrypt_entry = cast(
                DictionaryObject, self.trailer[TK.ENCRYPT].get_object()
            )
            self._encryption = Encryption.read(encrypt_entry, id1_entry)
            pwd = password if password is not None else b""
            if (
                self._encryption.verify(pwd) == PasswordType.NOT_DECRYPTED
                and password is not None
            ):
                raise WrongPasswordError("Wrong password")
            self._override_encryption = False
        else:
            if password is not None:
                raise PdfReadError("Not encrypted file")

    @property
    def pdf_header(self) -> str:
        # TODO: Make this return a bytes object for consistency
        loc = self.stream.tell()
        self.stream.seek(0, 0)
        pdf_file_version = self.stream.read(8).decode("utf-8")
        self.stream.seek(loc, 0)
        return pdf_file_version

    @property
    def metadata(self) -> Optional[DocumentInformation]:
        if TK.INFO not in self.trailer:
            return None
        obj = self.trailer[TK.INFO]
        retval = DocumentInformation()
        if isinstance(obj, type(None)):
            raise PdfReadError(
                "trailer not found or does not point to document information directory"
            )
        retval.update(obj)
        return retval

    def getDocumentInfo(self) -> Optional[DocumentInformation]:
        deprecation_with_replacement("getDocumentInfo", "metadata", "3.0.0")
        return self.metadata

    @property
    def documentInfo(self) -> Optional[DocumentInformation]:
        deprecation_with_replacement("documentInfo", "metadata", "3.0.0")
        return self.metadata

    @property
    def xmp_metadata(self) -> Optional[XmpInformation]:
        try:
            self._override_encryption = True
            return self.trailer[TK.ROOT].xmp_metadata
        finally:
            self._override_encryption = False

    def getXmpMetadata(self) -> Optional[XmpInformation]:
        deprecation_with_replacement("getXmpMetadata", "xmp_metadata", "3.0.0")
        return self.xmp_metadata

    @property
    def xmpMetadata(self) -> Optional[XmpInformation]:
        deprecation_with_replacement("xmpMetadata", "xmp_metadata", "3.0.0")
        return self.xmp_metadata

    def _get_num_pages(self) -> int:
        if self.is_encrypted:
            return self.trailer[TK.ROOT]["/Pages"]["/Count"]
        else:
            if self.flattened_pages is None:
                self._flatten()
            return len(self.flattened_pages)

    def getNumPages(self) -> int:
        deprecation_with_replacement("reader.getNumPages", "len(reader.pages)", "3.0.0")
        return self._get_num_pages()

    @property
    def numPages(self) -> int:
        deprecation_with_replacement("reader.numPages", "len(reader.pages)", "3.0.0")
        return self._get_num_pages()

    def getPage(self, pageNumber: int) -> PageObject:
        deprecation_with_replacement(
            "reader.getPage(pageNumber)", "reader.pages[page_number]", "3.0.0"
        )
        return self._get_page(pageNumber)

    def _get_page(self, page_number: int) -> PageObject:
        if self.flattened_pages is None:
            self._flatten()
        assert self.flattened_pages is not None, "hint for mypy"
        return self.flattened_pages[page_number]

    @property
    def namedDestinations(self) -> Dict[str, Any]:
        deprecation_with_replacement("namedDestinations", "named_destinations", "3.0.0")
        return self.named_destinations

    @property
    def named_destinations(self) -> Dict[str, Any]:
        return self._get_named_destinations()

    def get_fields(
        self,
        tree: Optional[TreeObject] = None,
        retval: Optional[Dict[Any, Any]] = None,
        fileobj: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        field_attributes = FieldDictionaryAttributes.attributes_dict()
        field_attributes.update(CheckboxRadioButtonAttributes.attributes_dict())
        if retval is None:
            retval = {}
            catalog = cast(DictionaryObject, self.trailer[TK.ROOT])
            if CD.ACRO_FORM in catalog:
                tree = cast(Optional[TreeObject], catalog[CD.ACRO_FORM])
            else:
                return None
        if tree is None:
            return retval
        self._check_kids(tree, retval, fileobj)
        for attr in field_attributes:
            if attr in tree:
                self._build_field(tree, retval, fileobj, field_attributes)
                break

        if "/Fields" in tree:
            fields = cast(ArrayObject, tree["/Fields"])
            for f in fields:
                field = f.get_object()
                self._build_field(field, retval, fileobj, field_attributes)

        return retval

    def getFields(
        self,
        tree: Optional[TreeObject] = None,
        retval: Optional[Dict[Any, Any]] = None,
        fileobj: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        deprecation_with_replacement("getFields", "get_fields", "3.0.0")
        return self.get_fields(tree, retval, fileobj)

    def _build_field(
        self,
        field: Union[TreeObject, DictionaryObject],
        retval: Dict[Any, Any],
        fileobj: Any,
        field_attributes: Any,
    ) -> None:
        self._check_kids(field, retval, fileobj)
        try:
            key = field["/TM"]
        except KeyError:
            try:
                key = field["/T"]
            except KeyError:
                return
        if fileobj:
            self._write_field(fileobj, field, field_attributes)
            fileobj.write("\n")
        retval[key] = Field(field)

    def _check_kids(
        self, tree: Union[TreeObject, DictionaryObject], retval: Any, fileobj: Any
    ) -> None:
        if PA.KIDS in tree:
            for kid in tree[PA.KIDS]:
                self.get_fields(kid.get_object(), retval, fileobj)

    def _write_field(self, fileobj: Any, field: Any, field_attributes: Any) -> None:
        field_attributes_tuple = FieldDictionaryAttributes.attributes()
        field_attributes_tuple = (
            field_attributes_tuple + CheckboxRadioButtonAttributes.attributes()
        )

        for attr in field_attributes_tuple:
            if attr in (
                FieldDictionaryAttributes.Kids,
                FieldDictionaryAttributes.AA,
            ):
                continue
            attr_name = field_attributes[attr]
            try:
                if attr == FieldDictionaryAttributes.FT:
                    types = {
                        "/Btn": "Button",
                        "/Tx": "Text",
                        "/Ch": "Choice",
                        "/Sig": "Signature",
                    }
                    if field[attr] in types:
                        fileobj.write(attr_name + ": " + types[field[attr]] + "\n")
                elif attr == FieldDictionaryAttributes.Parent:
                    try:
                        name = field[attr][FieldDictionaryAttributes.TM]
                    except KeyError:
                        name = field[attr][FieldDictionaryAttributes.T]
                    fileobj.write(attr_name + ": " + name + "\n")
                else:
                    fileobj.write(attr_name + ": " + str(field[attr]) + "\n")
            except KeyError:
                pass

    def get_form_text_fields(self) -> Dict[str, Any]:
        formfields = self.get_fields()
        if formfields is None:
            return {}
        return {
            formfields[field]["/T"]: formfields[field].get("/V")
            for field in formfields
            if formfields[field].get("/FT") == "/Tx"
        }

    def getFormTextFields(self) -> Dict[str, Any]:
        deprecation_with_replacement(
            "getFormTextFields", "get_form_text_fields", "3.0.0"
        )
        return self.get_form_text_fields()

    def _get_named_destinations(
        self,
        tree: Union[TreeObject, None] = None,
        retval: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if retval is None:
            retval = {}
            catalog = cast(DictionaryObject, self.trailer[TK.ROOT])
            if CA.DESTS in catalog:
                tree = cast(TreeObject, catalog[CA.DESTS])
            elif CA.NAMES in catalog:
                names = cast(DictionaryObject, catalog[CA.NAMES])
                if CA.DESTS in names:
                    tree = cast(TreeObject, names[CA.DESTS])

        if tree is None:
            return retval

        if PA.KIDS in tree:
            for kid in cast(ArrayObject, tree[PA.KIDS]):
                self._get_named_destinations(kid.get_object(), retval)
        elif CA.NAMES in tree:
            names = cast(DictionaryObject, tree[CA.NAMES])
            for i in range(0, len(names), 2):
                key = cast(str, names[i].get_object())
                value = names[i + 1].get_object()
                if isinstance(value, DictionaryObject) and "/D" in value:
                    value = value["/D"]
                dest = self._build_destination(key, value)
                if dest is not None:
                    retval[key] = dest
        else:
            for k__, v__ in tree.items():
                val = v__.get_object()
                dest = self._build_destination(k__, val)
                if dest is not None:
                    retval[k__] = dest
        return retval

    def getNamedDestinations(
        self,
        tree: Union[TreeObject, None] = None,
        retval: Optional[Any] = None,
    ) -> Dict[str, Any]:
        deprecation_with_replacement(
            "getNamedDestinations", "named_destinations", "3.0.0"
        )
        return self._get_named_destinations(tree, retval)

    @property
    def outline(self) -> OutlineType:
        return self._get_outline()

    @property
    def outlines(self) -> OutlineType:
        deprecation_with_replacement("outlines", "outline", "3.0.0")
        return self.outline

    def _get_outline(
        self, node: Optional[DictionaryObject] = None, outline: Optional[Any] = None
    ) -> OutlineType:
        if outline is None:
            outline = []
            catalog = cast(DictionaryObject, self.trailer[TK.ROOT])
            if CO.OUTLINES in catalog:
                lines = cast(DictionaryObject, catalog[CO.OUTLINES])

                if isinstance(lines, NullObject):
                    return outline
                if lines is not None and "/First" in lines:
                    node = cast(DictionaryObject, lines["/First"])
            self._namedDests = self._get_named_destinations()

        if node is None:
            return outline
        while True:
            outline_obj = self._build_outline_item(node)
            if outline_obj:
                outline.append(outline_obj)

            # check for sub-outline
            if "/First" in node:
                sub_outline: List[Any] = []
                self._get_outline(cast(DictionaryObject, node["/First"]), sub_outline)
                if sub_outline:
                    outline.append(sub_outline)

            if "/Next" not in node:
                break
            node = cast(DictionaryObject, node["/Next"])

        return outline

    def getOutlines(
        self, node: Optional[DictionaryObject] = None, outline: Optional[Any] = None
    ) -> OutlineType:
        deprecation_with_replacement("getOutlines", "outline", "3.0.0")
        return self._get_outline(node, outline)

    @property
    def threads(self) -> Optional[ArrayObject]:
        catalog = cast(DictionaryObject, self.trailer[TK.ROOT])
        if CO.THREADS in catalog:
            return cast("ArrayObject", catalog[CO.THREADS])
        else:
            return None

    def _get_page_number_by_indirect(
        self, indirect_reference: Union[None, int, NullObject, IndirectObject]
    ) -> int:
        if self._page_id2num is None:
            self._page_id2num = {
                x.indirect_reference.idnum: i for i, x in enumerate(self.pages)
            }

        if indirect_reference is None or isinstance(indirect_reference, NullObject):
            return -1
        if isinstance(indirect_reference, int):
            idnum = indirect_reference
        else:
            idnum = indirect_reference.idnum
        assert self._page_id2num is not None, "hint for mypy"
        ret = self._page_id2num.get(idnum, -1)
        return ret

    def get_page_number(self, page: PageObject) -> int:
        return self._get_page_number_by_indirect(page.indirect_reference)

    def getPageNumber(self, page: PageObject) -> int:
        deprecation_with_replacement("getPageNumber", "get_page_number", "3.0.0")
        return self.get_page_number(page)

    def get_destination_page_number(self, destination: Destination) -> int:
        return self._get_page_number_by_indirect(destination.page)

    def getDestinationPageNumber(self, destination: Destination) -> int:
        deprecation_with_replacement(
            "getDestinationPageNumber", "get_destination_page_number", "3.0.0"
        )
        return self.get_destination_page_number(destination)

    def _build_destination(
        self,
        title: str,
        array: Optional[
            List[
                Union[NumberObject, IndirectObject, None, NullObject, DictionaryObject]
            ]
        ],
    ) -> Destination:
        page, typ = None, None
        if (
            isinstance(array, (NullObject, str))
            or (isinstance(array, ArrayObject) and len(array) == 0)
            or array is None
        ):

            page = NullObject()
            return Destination(title, page, Fit.fit())
        else:
            page, typ = array[0:2]
            array = array[2:]
            try:
                return Destination(title, page, Fit(fit_type=typ, fit_args=array))
            except PdfReadError:
                logger_warning(f"Unknown destination: {title} {array}", __name__)
                if self.strict:
                    raise
                tmp = self.pages[0].indirect_reference
                indirect_reference = NullObject() if tmp is None else tmp
                return Destination(title, indirect_reference, Fit.fit())

    def _build_outline_item(self, node: DictionaryObject) -> Optional[Destination]:
        dest, title, outline_item = None, None, None
        try:
            title = cast("str", node["/Title"])
        except KeyError:
            if self.strict:
                raise PdfReadError(f"Outline Entry Missing /Title attribute: {node!r}")
            title = ""

        if "/A" in node:
            action = cast(DictionaryObject, node["/A"])
            action_type = cast(NameObject, action[GoToActionArguments.S])
            if action_type == "/GoTo":
                dest = action[GoToActionArguments.D]
        elif "/Dest" in node:
            dest = node["/Dest"]
            if isinstance(dest, DictionaryObject) and "/D" in dest:
                dest = dest["/D"]

        if isinstance(dest, ArrayObject):
            outline_item = self._build_destination(title, dest)
        elif isinstance(dest, str):
            # TODO : keep named destination instead of replacing it ?
            try:
                outline_item = self._build_destination(
                    title, self._namedDests[dest].dest_array
                )
            except KeyError:
                outline_item = self._build_destination(title, None)
        elif dest is None:
            outline_item = self._build_destination(title, dest)
        else:
            if self.strict:
                raise PdfReadError(f"Unexpected destination {dest!r}")
            else:
                logger_warning(
                    f"Removed unexpected destination {dest!r} from destination",
                    __name__,
                )
            outline_item = self._build_destination(title, None)
        if outline_item:
            if "/C" in node:
                outline_item[NameObject("/C")] = ArrayObject(
                    FloatObject(c) for c in node["/C"]
                )
            if "/F" in node:
                outline_item[NameObject("/F")] = node["/F"]
            if "/Count" in node:
                outline_item[NameObject("/Count")] = node["/Count"]
        outline_item.node = node
        return outline_item

    @property
    def pages(self) -> List[PageObject]:
        return _VirtualList(self._get_num_pages, self._get_page)  # type: ignore

    @property
    def page_layout(self) -> Optional[str]:
        trailer = cast(DictionaryObject, self.trailer[TK.ROOT])
        if CD.PAGE_LAYOUT in trailer:
            return cast(NameObject, trailer[CD.PAGE_LAYOUT])
        return None

    def getPageLayout(self) -> Optional[str]:
        deprecation_with_replacement("getPageLayout", "page_layout", "3.0.0")
        return self.page_layout

    @property
    def pageLayout(self) -> Optional[str]:
        deprecation_with_replacement("pageLayout", "page_layout", "3.0.0")
        return self.page_layout

    @property
    def page_mode(self) -> Optional[PagemodeType]:
        try:
            return self.trailer[TK.ROOT]["/PageMode"]  # type: ignore
        except KeyError:
            return None

    def getPageMode(self) -> Optional[PagemodeType]:
        deprecation_with_replacement("getPageMode", "page_mode", "3.0.0")
        return self.page_mode

    @property
    def pageMode(self) -> Optional[PagemodeType]:
        deprecation_with_replacement("pageMode", "page_mode", "3.0.0")
        return self.page_mode

    def _flatten(
        self,
        pages: Union[None, DictionaryObject, PageObject] = None,
        inherit: Optional[Dict[str, Any]] = None,
        indirect_reference: Optional[IndirectObject] = None,
    ) -> None:
        inheritable_page_attributes = (
            NameObject(PG.RESOURCES),
            NameObject(PG.MEDIABOX),
            NameObject(PG.CROPBOX),
            NameObject(PG.ROTATE),
        )
        if inherit is None:
            inherit = {}
        if pages is None:
            catalog = self.trailer[TK.ROOT].get_object()
            pages = catalog["/Pages"].get_object()
            self.flattened_pages = []

        t = "/Pages"
        if PA.TYPE in pages:
            t = pages[PA.TYPE]

        if t == "/Pages":
            for attr in inheritable_page_attributes:
                if attr in pages:
                    inherit[attr] = pages[attr]
            for page in pages[PA.KIDS]:
                addt = {}
                if isinstance(page, IndirectObject):
                    addt["indirect_reference"] = page
                self._flatten(page.get_object(), inherit, **addt)
        elif t == "/Page":
            for attr_in, value in list(inherit.items()):
                if attr_in not in pages:
                    pages[attr_in] = value
            page_obj = PageObject(self, indirect_reference)
            page_obj.update(pages)

            # TODO: Could flattened_pages be None at this point?
            self.flattened_pages.append(page_obj)

    def _get_object_from_stream(
        self, indirect_reference: IndirectObject
    ) -> Union[int, PdfObject, str]:
        stmnum, idx = self.xref_objStm[indirect_reference.idnum]
        obj_stm: EncodedStreamObject = IndirectObject(stmnum, 0, self).get_object()
        assert cast(str, obj_stm["/Type"]) == "/ObjStm"
        assert idx < obj_stm["/N"]
        stream_data = BytesIO(b_(obj_stm.get_data()))
        for i in range(obj_stm["/N"]):
            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)
            objnum = NumberObject.read_from_stream(stream_data)
            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)
            offset = NumberObject.read_from_stream(stream_data)
            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)
            if objnum != indirect_reference.idnum:
                continue
            if self.strict and idx != i:
                raise PdfReadError("Object is in wrong index.")
            stream_data.seek(int(obj_stm["/First"] + offset), 0)
            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)

            try:
                obj = read_object(stream_data, self)
            except PdfStreamError as exc:
                logger_warning(
                    f"Invalid stream (index {i}) within object "
                    f"{indirect_reference.idnum} {indirect_reference.generation}: "
                    f"{exc}",
                    __name__,
                )

                if self.strict:
                    raise PdfReadError(f"Can't read object stream: {exc}")
                obj = NullObject()
            return obj

        if self.strict:
            raise PdfReadError("This is a fatal error in strict mode.")
        return NullObject()

    def _get_indirect_object(self, num: int, gen: int) -> Optional[PdfObject]:
        return IndirectObject(num, gen, self).get_object()

    def get_object(
        self, indirect_reference: Union[int, IndirectObject]
    ) -> Optional[PdfObject]:
        if isinstance(indirect_reference, int):
            indirect_reference = IndirectObject(indirect_reference, 0, self)
        retval = self.cache_get_indirect_object(
            indirect_reference.generation, indirect_reference.idnum
        )
        if retval is not None:
            return retval
        if (
            indirect_reference.generation == 0
            and indirect_reference.idnum in self.xref_objStm
        ):
            retval = self._get_object_from_stream(indirect_reference)
        elif (
            indirect_reference.generation in self.xref
            and indirect_reference.idnum in self.xref[indirect_reference.generation]
        ):
            if self.xref_free_entry.get(indirect_reference.generation, {}).get(
                indirect_reference.idnum, False
            ):
                return NullObject()
            start = self.xref[indirect_reference.generation][indirect_reference.idnum]
            self.stream.seek(start, 0)
            try:
                idnum, generation = self.read_object_header(self.stream)
            except Exception:
                if hasattr(self.stream, "getbuffer"):
                    buf = bytes(self.stream.getbuffer())  # type: ignore
                else:
                    p = self.stream.tell()
                    self.stream.seek(0, 0)
                    buf = self.stream.read(-1)
                    self.stream.seek(p, 0)
                m = re.search(
                    rf"\s{indirect_reference.idnum}\s+{indirect_reference.generation}\s+obj".encode(),
                    buf,
                )
                if m is not None:
                    logger_warning(
                        f"Object ID {indirect_reference.idnum},{indirect_reference.generation} ref repaired",
                        __name__,
                    )
                    self.xref[indirect_reference.generation][
                        indirect_reference.idnum
                    ] = (m.start(0) + 1)
                    self.stream.seek(m.start(0) + 1)
                    idnum, generation = self.read_object_header(self.stream)
                else:
                    idnum = -1
            if idnum != indirect_reference.idnum and self.xref_index:
                if self.strict:
                    raise PdfReadError(
                        f"Expected object ID ({indirect_reference.idnum} {indirect_reference.generation}) "
                        f"does not match actual ({idnum} {generation}); "
                        "xref table not zero-indexed."
                    )
            elif idnum != indirect_reference.idnum and self.strict:
                raise PdfReadError(
                    f"Expected object ID ({indirect_reference.idnum} "
                    f"{indirect_reference.generation}) does not match actual "
                    f"({idnum} {generation})."
                )
            if self.strict:
                assert generation == indirect_reference.generation
            retval = read_object(self.stream, self)
            if not self._override_encryption and self._encryption is not None:
                if not self._encryption.is_decrypted():
                    raise FileNotDecryptedError("File has not been decrypted")
                retval = cast(PdfObject, retval)
                retval = self._encryption.decrypt_object(
                    retval, indirect_reference.idnum, indirect_reference.generation
                )
        else:
            if hasattr(self.stream, "getbuffer"):
                buf = bytes(self.stream.getbuffer())
            else:
                p = self.stream.tell()
                self.stream.seek(0, 0)
                buf = self.stream.read(-1)
                self.stream.seek(p, 0)
            m = re.search(
                rf"\s{indirect_reference.idnum}\s+{indirect_reference.generation}\s+obj".encode(),
                buf,
            )
            if m is not None:
                logger_warning(
                    f"Object {indirect_reference.idnum} {indirect_reference.generation} found",
                    __name__,
                )
                if indirect_reference.generation not in self.xref:
                    self.xref[indirect_reference.generation] = {}
                self.xref[indirect_reference.generation][indirect_reference.idnum] = (
                    m.start(0) + 1
                )
                self.stream.seek(m.end(0) + 1)
                skip_over_whitespace(self.stream)
                self.stream.seek(-1, 1)
                retval = read_object(self.stream, self)
                if not self._override_encryption and self._encryption is not None:
                    if not self._encryption.is_decrypted():
                        raise FileNotDecryptedError("File has not been decrypted")
                    retval = cast(PdfObject, retval)
                    retval = self._encryption.decrypt_object(
                        retval, indirect_reference.idnum, indirect_reference.generation
                    )
            else:
                logger_warning(
                    f"Object {indirect_reference.idnum} {indirect_reference.generation} not defined.",
                    __name__,
                )
                if self.strict:
                    raise PdfReadError("Could not find object.")
        self.cache_indirect_object(
            indirect_reference.generation, indirect_reference.idnum, retval
        )
        return retval

    def getObject(self, indirectReference: IndirectObject) -> Optional[PdfObject]:
        """
        .. deprecated:: 1.28.0

            Use :meth:`get_object` instead.
        """
        deprecation_with_replacement("getObject", "get_object", "3.0.0")
        return self.get_object(indirectReference)

    def read_object_header(self, stream: StreamType) -> Tuple[int, int]:
        extra = False
        skip_over_comment(stream)
        extra |= skip_over_whitespace(stream)
        stream.seek(-1, 1)
        idnum = read_until_whitespace(stream)
        extra |= skip_over_whitespace(stream)
        stream.seek(-1, 1)
        generation = read_until_whitespace(stream)
        extra |= skip_over_whitespace(stream)
        stream.seek(-1, 1)
        _obj = stream.read(3)

        read_non_whitespace(stream)
        stream.seek(-1, 1)
        if extra and self.strict:
            logger_warning(
                f"Superfluous whitespace found in object header {idnum} {generation}",
                __name__,
            )
        return int(idnum), int(generation)

    def readObjectHeader(self, stream: StreamType) -> Tuple[int, int]:
        deprecation_with_replacement("readObjectHeader", "read_object_header", "3.0.0")
        return self.read_object_header(stream)

    def cache_get_indirect_object(
        self, generation: int, idnum: int
    ) -> Optional[PdfObject]:
        return self.resolved_objects.get((generation, idnum))

    def cacheGetIndirectObject(
        self, generation: int, idnum: int
    ) -> Optional[PdfObject]:
        deprecation_with_replacement(
            "cacheGetIndirectObject", "cache_get_indirect_object", "3.0.0"
        )
        return self.cache_get_indirect_object(generation, idnum)

    def cache_indirect_object(
        self, generation: int, idnum: int, obj: Optional[PdfObject]
    ) -> Optional[PdfObject]:
        if (generation, idnum) in self.resolved_objects:
            msg = f"Overwriting cache for {generation} {idnum}"
            if self.strict:
                raise PdfReadError(msg)
            logger_warning(msg, __name__)
        self.resolved_objects[(generation, idnum)] = obj
        if obj is not None:
            obj.indirect_reference = IndirectObject(idnum, generation, self)
        return obj

    def cacheIndirectObject(
        self, generation: int, idnum: int, obj: Optional[PdfObject]
    ) -> Optional[PdfObject]:
        deprecation_with_replacement("cacheIndirectObject", "cache_indirect_object")
        return self.cache_indirect_object(generation, idnum, obj)

    def read(self, stream: StreamType) -> None:
        self._basic_validation(stream)
        self._find_eof_marker(stream)
        startxref = self._find_startxref_pos(stream)
        xref_issue_nr = self._get_xref_issues(stream, startxref)
        if xref_issue_nr != 0:
            if self.strict and xref_issue_nr:
                raise PdfReadError("Broken xref table")
            logger_warning(f"incorrect startxref pointer({xref_issue_nr})", __name__)
        self._read_xref_tables_and_trailers(stream, startxref, xref_issue_nr)
        if self.xref_index and not self.strict:
            loc = stream.tell()
            for gen, xref_entry in self.xref.items():
                if gen == 65535:
                    continue
                xref_k = sorted(xref_entry.keys())
                for id in xref_k:
                    stream.seek(xref_entry[id], 0)
                    try:
                        pid, _pgen = self.read_object_header(stream)
                    except ValueError:
                        break
                    if pid == id - self.xref_index:
                        self.xref[gen][pid] = self.xref[gen][id]
                        del self.xref[gen][id]
            stream.seek(loc, 0)

    def _basic_validation(self, stream: StreamType) -> None:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            raise EmptyFileError("Cannot read an empty file")
        if self.strict:
            stream.seek(0, os.SEEK_SET)
            header_byte = stream.read(5)
            if header_byte != b"%PDF-":
                raise PdfReadError(
                    f"PDF starts with '{header_byte.decode('utf8')}', "
                    "but '%PDF-' expected"
                )
            stream.seek(0, os.SEEK_END)

    def _find_eof_marker(self, stream: StreamType) -> None:
        last_mb = 8
        line = b""
        while line[:5] != b"%%EOF":
            if stream.tell() < last_mb:
                raise PdfReadError("EOF marker not found")
            line = read_previous_line(stream)

    def _find_startxref_pos(self, stream: StreamType) -> int:
        line = read_previous_line(stream)
        try:
            startxref = int(line)
        except ValueError:
            if not line.startswith(b"startxref"):
                raise PdfReadError("startxref not found")
            startxref = int(line[9:].strip())
            logger_warning("startxref on same line as offset", __name__)
        else:
            line = read_previous_line(stream)
            if line[:9] != b"startxref":
                raise PdfReadError("startxref not found")
        return startxref

    def _read_standard_xref_table(self, stream: StreamType) -> None:
        ref = stream.read(4)
        if ref[:3] != b"ref":
            raise PdfReadError("xref table read error")
        read_non_whitespace(stream)
        stream.seek(-1, 1)
        firsttime = True
        while True:
            num = cast(int, read_object(stream, self))
            if firsttime and num != 0:
                self.xref_index = num
                if self.strict:
                    logger_warning(
                        "Xref table not zero-indexed. ID numbers for objects will be corrected.",
                        __name__,
                    )
            firsttime = False
            read_non_whitespace(stream)
            stream.seek(-1, 1)
            size = cast(int, read_object(stream, self))
            read_non_whitespace(stream)
            stream.seek(-1, 1)
            cnt = 0
            while cnt < size:
                line = stream.read(20)
                while line[0] in b"\x0D\x0A":
                    stream.seek(-20 + 1, 1)
                    line = stream.read(20)
                if line[-1] in b"0123456789t":
                    stream.seek(-1, 1)

                try:
                    offset_b, generation_b = line[:16].split(b" ")
                    entry_type_b = line[17:18]

                    offset, generation = int(offset_b), int(generation_b)
                except Exception:
                    if hasattr(stream, "getbuffer"):
                        buf = bytes(stream.getbuffer())
                    else:
                        p = stream.tell()
                        stream.seek(0, 0)
                        buf = stream.read(-1)
                        stream.seek(p)

                    f = re.search(f"{num}\\s+(\\d+)\\s+obj".encode(), buf)
                    if f is None:
                        logger_warning(
                            f"entry {num} in Xref table invalid; object not found",
                            __name__,
                        )
                        generation = 65535
                        offset = -1
                    else:
                        logger_warning(
                            f"entry {num} in Xref table invalid but object found",
                            __name__,
                        )
                        generation = int(f.group(1))
                        offset = f.start()

                if generation not in self.xref:
                    self.xref[generation] = {}
                    self.xref_free_entry[generation] = {}
                if num in self.xref[generation]:
                    pass
                else:
                    self.xref[generation][num] = offset
                    try:
                        self.xref_free_entry[generation][num] = entry_type_b == b"f"
                    except Exception:
                        pass
                    try:
                        self.xref_free_entry[65535][num] = entry_type_b == b"f"
                    except Exception:
                        pass
                cnt += 1
                num += 1
            read_non_whitespace(stream)
            stream.seek(-1, 1)
            trailertag = stream.read(7)
            if trailertag != b"trailer":
                stream.seek(-7, 1)
            else:
                break

    def _read_xref_tables_and_trailers(
        self, stream: StreamType, startxref: Optional[int], xref_issue_nr: int
    ) -> None:
        self.xref: Dict[int, Dict[Any, Any]] = {}
        self.xref_free_entry: Dict[int, Dict[Any, Any]] = {}
        self.xref_objStm: Dict[int, Tuple[Any, Any]] = {}
        self.trailer = DictionaryObject()
        while startxref is not None:
            stream.seek(startxref, 0)
            x = stream.read(1)
            if x in b"\r\n":
                x = stream.read(1)
            if x == b"x":
                startxref = self._read_xref(stream)
            elif xref_issue_nr:
                try:
                    self._rebuild_xref_table(stream)
                    break
                except Exception:
                    xref_issue_nr = 0
            elif x.isdigit():
                try:
                    xrefstream = self._read_pdf15_xref_stream(stream)
                except Exception as e:
                    if TK.ROOT in self.trailer:
                        logger_warning(
                            f"Previous trailer can not be read {e.args}",
                            __name__,
                        )
                        break
                    else:
                        raise PdfReadError(f"trailer can not be read {e.args}")
                trailer_keys = TK.ROOT, TK.ENCRYPT, TK.INFO, TK.ID
                for key in trailer_keys:
                    if key in xrefstream and key not in self.trailer:
                        self.trailer[NameObject(key)] = xrefstream.raw_get(key)
                if "/XRefStm" in xrefstream:
                    p = stream.tell()
                    stream.seek(cast(int, xrefstream["/XRefStm"]) + 1, 0)
                    self._read_pdf15_xref_stream(stream)
                    stream.seek(p, 0)
                if "/Prev" in xrefstream:
                    startxref = cast(int, xrefstream["/Prev"])
                else:
                    break
            else:
                startxref = self._read_xref_other_error(stream, startxref)

    def _read_xref(self, stream: StreamType) -> Optional[int]:
        self._read_standard_xref_table(stream)
        read_non_whitespace(stream)
        stream.seek(-1, 1)
        new_trailer = cast(Dict[str, Any], read_object(stream, self))
        for key, value in new_trailer.items():
            if key not in self.trailer:
                self.trailer[key] = value
        if "/XRefStm" in new_trailer:
            p = stream.tell()
            stream.seek(cast(int, new_trailer["/XRefStm"]) + 1, 0)
            try:
                self._read_pdf15_xref_stream(stream)
            except Exception:
                logger_warning(
                    f"XRef object at {new_trailer['/XRefStm']} can not be read, some object may be missing",
                    __name__,
                )
            stream.seek(p, 0)
        if "/Prev" in new_trailer:
            startxref = new_trailer["/Prev"]
            return startxref
        else:
            return None

    def _read_xref_other_error(
        self, stream: StreamType, startxref: int
    ) -> Optional[int]:
        if startxref == 0:
            if self.strict:
                raise PdfReadError(
                    "/Prev=0 in the trailer (try opening with strict=False)"
                )
            logger_warning(
                "/Prev=0 in the trailer - assuming there is no previous xref table",
                __name__,
            )
            return None
        stream.seek(-11, 1)
        tmp = stream.read(20)
        xref_loc = tmp.find(b"xref")
        if xref_loc != -1:
            startxref -= 10 - xref_loc
            return startxref
        stream.seek(startxref, 0)
        for look in range(5):
            if stream.read(1).isdigit():
                startxref += look
                return startxref
        if "/Root" in self.trailer and not self.strict:
            logger_warning("Invalid parent xref., rebuild xref", __name__)
            try:
                self._rebuild_xref_table(stream)
                return None
            except Exception:
                raise PdfReadError("can not rebuild xref")
        raise PdfReadError("Could not find xref table at specified location")

    def _read_pdf15_xref_stream(
        self, stream: StreamType
    ) -> Union[ContentStream, EncodedStreamObject, DecodedStreamObject]:
        stream.seek(-1, 1)
        idnum, generation = self.read_object_header(stream)
        xrefstream = cast(ContentStream, read_object(stream, self))
        assert cast(str, xrefstream["/Type"]) == "/XRef"
        self.cache_indirect_object(generation, idnum, xrefstream)
        stream_data = BytesIO(b_(xrefstream.get_data()))
        idx_pairs = xrefstream.get("/Index", [0, xrefstream.get("/Size")])
        entry_sizes = cast(Dict[Any, Any], xrefstream.get("/W"))
        assert len(entry_sizes) >= 3
        if self.strict and len(entry_sizes) > 3:
            raise PdfReadError(f"Too many entry sizes: {entry_sizes}")

        def get_entry(i: int) -> Union[int, Tuple[int, ...]]:
            if entry_sizes[i] > 0:
                d = stream_data.read(entry_sizes[i])
                return convert_to_int(d, entry_sizes[i])
            if i == 0:
                return 1
            else:
                return 0

        def used_before(num: int, generation: Union[int, Tuple[int, ...]]) -> bool:
            return num in self.xref.get(generation, []) or num in self.xref_objStm

        self._read_xref_subsections(idx_pairs, get_entry, used_before)
        return xrefstream

    @staticmethod
    def _get_xref_issues(stream: StreamType, startxref: int) -> int:
        """Return an int which indicates an issue. 0 means there is no issue."""
        stream.seek(startxref - 1, 0)
        line = stream.read(1)
        if line not in b"\r\n \t":
            return 1
        line = stream.read(4)
        if line != b"xref":
            line = b""
            while line in b"0123456789 \t":
                line = stream.read(1)
                if line == b"":
                    return 2
            line += stream.read(2)
            if line.lower() != b"obj":
                return 3
        return 0

    def _rebuild_xref_table(self, stream: StreamType) -> None:
        self.xref = {}
        stream.seek(0, 0)
        f_ = stream.read(-1)

        for m in re.finditer(rb"[\r\n \t][ \t]*(\d+)[ \t]+(\d+)[ \t]+obj", f_):
            idnum = int(m.group(1))
            generation = int(m.group(2))
            if generation not in self.xref:
                self.xref[generation] = {}
            self.xref[generation][idnum] = m.start(1)
        stream.seek(0, 0)
        for m in re.finditer(rb"[\r\n \t][ \t]*trailer[\r\n \t]*(<<)", f_):
            stream.seek(m.start(1), 0)
            new_trailer = cast(Dict[Any, Any], read_object(stream, self))
            for key, value in list(new_trailer.items()):
                self.trailer[key] = value

    def _read_xref_subsections(
        self,
        idx_pairs: List[int],
        get_entry: Callable[[int], Union[int, Tuple[int, ...]]],
        used_before: Callable[[int, Union[int, Tuple[int, ...]]], bool],
    ) -> None:
        last_end = 0
        for start, size in self._pairs(idx_pairs):
            assert start >= last_end
            last_end = start + size
            for num in range(start, start + size):
                xref_type = get_entry(0)
                if xref_type == 0:

                    next_free_object = get_entry(1)
                    next_generation = get_entry(2)
                elif xref_type == 1:
                    byte_offset = get_entry(1)
                    generation = get_entry(2)
                    if generation not in self.xref:
                        self.xref[generation] = {}
                    if not used_before(num, generation):
                        self.xref[generation][num] = byte_offset
                elif xref_type == 2:
                    objstr_num = get_entry(1)
                    obstr_idx = get_entry(2)
                    generation = 0
                    if not used_before(num, generation):
                        self.xref_objStm[num] = (objstr_num, obstr_idx)
                elif self.strict:
                    raise PdfReadError(f"Unknown xref type: {xref_type}")

    def _pairs(self, array: List[int]) -> Iterable[Tuple[int, int]]:
        i = 0
        while True:
            yield array[i], array[i + 1]
            i += 2
            if (i + 1) >= len(array):
                break

    def read_next_end_line(self, stream: StreamType, limit_offset: int = 0) -> bytes:
        deprecate_no_replacement("read_next_end_line", removed_in="4.0.0")
        line_parts = []
        while True:
            if stream.tell() == 0 or stream.tell() == limit_offset:
                raise PdfReadError("Could not read malformed PDF file")
            x = stream.read(1)
            if stream.tell() < 2:
                raise PdfReadError("EOL marker not found")
            stream.seek(-2, 1)
            if x in (b"\n", b"\r"):
                crlf = False
                while x in (b"\n", b"\r"):
                    x = stream.read(1)
                    if x in (b"\n", b"\r"):
                        stream.seek(-1, 1)
                        crlf = True
                    if stream.tell() < 2:
                        raise PdfReadError("EOL marker not found")
                    stream.seek(-2, 1)
                stream.seek(2 if crlf else 1, 1)
                break
            else:
                line_parts.append(x)
        line_parts.reverse()
        return b"".join(line_parts)

    def readNextEndLine(self, stream: StreamType, limit_offset: int = 0) -> bytes:
        deprecation_no_replacement("readNextEndLine", "3.0.0")
        return self.read_next_end_line(stream, limit_offset)

    def decrypt(self, password: Union[str, bytes]) -> PasswordType:
        if not self._encryption:
            raise PdfReadError("Not encrypted file")
        # TODO: raise Exception for wrong password
        return self._encryption.verify(password)

    def decode_permissions(self, permissions_code: int) -> Dict[str, bool]:
        permissions = {}
        permissions["print"] = permissions_code & (1 << 3 - 1) != 0
        permissions["modify"] = permissions_code & (1 << 4 - 1) != 0
        permissions["copy"] = permissions_code & (1 << 5 - 1) != 0
        permissions["annotations"] = permissions_code & (1 << 6 - 1) != 0
        permissions["forms"] = permissions_code & (1 << 9 - 1) != 0
        permissions["accessability"] = permissions_code & (1 << 10 - 1) != 0
        permissions["assemble"] = permissions_code & (1 << 11 - 1) != 0
        permissions["print_high_quality"] = permissions_code & (1 << 12 - 1) != 0
        return permissions

    @property
    def is_encrypted(self) -> bool:
        return TK.ENCRYPT in self.trailer

    def getIsEncrypted(self) -> bool:

        deprecation_with_replacement("getIsEncrypted", "is_encrypted", "3.0.0")
        return self.is_encrypted

    @property
    def isEncrypted(self) -> bool:
        deprecation_with_replacement("isEncrypted", "is_encrypted", "3.0.0")
        return self.is_encrypted

    @property
    def xfa(self) -> Optional[Dict[str, Any]]:
        tree: Optional[TreeObject] = None
        retval: Dict[str, Any] = {}
        catalog = cast(DictionaryObject, self.trailer[TK.ROOT])

        if "/AcroForm" not in catalog or not catalog["/AcroForm"]:
            return None

        tree = cast(TreeObject, catalog["/AcroForm"])

        if "/XFA" in tree:
            fields = cast(ArrayObject, tree["/XFA"])
            i = iter(fields)
            for f in i:
                tag = f
                f = next(i)
                if isinstance(f, IndirectObject):
                    field = cast(Optional[EncodedStreamObject], f.get_object())
                    if field:
                        es = zlib.decompress(field._data)
                        retval[tag] = es
        return retval


class PdfFileReader(PdfReader):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        deprecation_with_replacement("PdfFileReader", "PdfReader", "3.0.0")
        if "strict" not in kwargs and len(args) < 2:
            kwargs["strict"] = True
        super().__init__(*args, **kwargs)
