import datetime
import decimal
import re
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
    cast,
)
from xml.dom.minidom import Document
from xml.dom.minidom import Element as XmlElement
from xml.dom.minidom import parseString
from xml.parsers.expat import ExpatError

from ._utils import (
    StreamType,
    deprecate_with_replacement,
    deprecation_with_replacement,
)
from .errors import PdfReadError
from .generic import ContentStream, PdfObject

RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XMP_NAMESPACE = "http://ns.adobe.com/xap/1.0/"
PDF_NAMESPACE = "http://ns.adobe.com/pdf/1.3/"
XMPMM_NAMESPACE = "http://ns.adobe.com/xap/1.0/mm/"
PDFX_NAMESPACE = "http://ns.adobe.com/pdfx/1.3/"

iso8601 = re.compile(
    """
        (?P<year>[0-9]{4})
        (-
            (?P<month>[0-9]{2})
            (-
                (?P<day>[0-9]+)
                (T
                    (?P<hour>[0-9]{2}):
                    (?P<minute>[0-9]{2})
                    (:(?P<second>[0-9]{2}(.[0-9]+)?))?
                    (?P<tzd>Z|[-+][0-9]{2}:[0-9]{2})
                )?
            )?
        )?
        """,
    re.VERBOSE,
)


K = TypeVar("K")


def _identity(value: K) -> K:
    return value


def _converter_date(value: str) -> datetime.datetime:
    matches = iso8601.match(value)
    if matches is None:
        raise ValueError(f"Invalid date format: {value}")
    year = int(matches.group("year"))
    month = int(matches.group("month") or "1")
    day = int(matches.group("day") or "1")
    hour = int(matches.group("hour") or "0")
    minute = int(matches.group("minute") or "0")
    second = decimal.Decimal(matches.group("second") or "0")
    seconds_dec = second.to_integral(decimal.ROUND_FLOOR)
    milliseconds_dec = (second - seconds_dec) * 1000000

    seconds = int(seconds_dec)
    milliseconds = int(milliseconds_dec)

    tzd = matches.group("tzd") or "Z"
    dt = datetime.datetime(year, month, day, hour, minute, seconds, milliseconds)
    if tzd != "Z":
        tzd_hours, tzd_minutes = (int(x) for x in tzd.split(":"))
        tzd_hours *= -1
        if tzd_hours < 0:
            tzd_minutes *= -1
        dt = dt + datetime.timedelta(hours=tzd_hours, minutes=tzd_minutes)
    return dt


def _getter_bag(
    namespace: str, name: str
) -> Callable[["XmpInformation"], Optional[List[str]]]:
    def get(self: "XmpInformation") -> Optional[List[str]]:
        cached = self.cache.get(namespace, {}).get(name)
        if cached:
            return cached
        retval = []
        for element in self.get_element("", namespace, name):
            bags = element.getElementsByTagNameNS(RDF_NAMESPACE, "Bag")
            if len(bags):
                for bag in bags:
                    for item in bag.getElementsByTagNameNS(RDF_NAMESPACE, "li"):
                        value = self._get_text(item)
                        retval.append(value)
        ns_cache = self.cache.setdefault(namespace, {})
        ns_cache[name] = retval
        return retval

    return get


def _getter_seq(
    namespace: str, name: str, converter: Callable[[Any], Any] = _identity
) -> Callable[["XmpInformation"], Optional[List[Any]]]:
    def get(self: "XmpInformation") -> Optional[List[Any]]:
        cached = self.cache.get(namespace, {}).get(name)
        if cached:
            return cached
        retval = []
        for element in self.get_element("", namespace, name):
            seqs = element.getElementsByTagNameNS(RDF_NAMESPACE, "Seq")
            if len(seqs):
                for seq in seqs:
                    for item in seq.getElementsByTagNameNS(RDF_NAMESPACE, "li"):
                        value = self._get_text(item)
                        value = converter(value)
                        retval.append(value)
            else:
                value = converter(self._get_text(element))
                retval.append(value)
        ns_cache = self.cache.setdefault(namespace, {})
        ns_cache[name] = retval
        return retval

    return get


def _getter_langalt(
    namespace: str, name: str
) -> Callable[["XmpInformation"], Optional[Dict[Any, Any]]]:
    def get(self: "XmpInformation") -> Optional[Dict[Any, Any]]:
        cached = self.cache.get(namespace, {}).get(name)
        if cached:
            return cached
        retval = {}
        for element in self.get_element("", namespace, name):
            alts = element.getElementsByTagNameNS(RDF_NAMESPACE, "Alt")
            if len(alts):
                for alt in alts:
                    for item in alt.getElementsByTagNameNS(RDF_NAMESPACE, "li"):
                        value = self._get_text(item)
                        retval[item.getAttribute("xml:lang")] = value
            else:
                retval["x-default"] = self._get_text(element)
        ns_cache = self.cache.setdefault(namespace, {})
        ns_cache[name] = retval
        return retval

    return get


def _getter_single(
    namespace: str, name: str, converter: Callable[[str], Any] = _identity
) -> Callable[["XmpInformation"], Optional[Any]]:
    def get(self: "XmpInformation") -> Optional[Any]:
        cached = self.cache.get(namespace, {}).get(name)
        if cached:
            return cached
        value = None
        for element in self.get_element("", namespace, name):
            if element.nodeType == element.ATTRIBUTE_NODE:
                value = element.nodeValue
            else:
                value = self._get_text(element)
            break
        if value is not None:
            value = converter(value)
        ns_cache = self.cache.setdefault(namespace, {})
        ns_cache[name] = value
        return value

    return get


class XmpInformation(PdfObject):
    def __init__(self, stream: ContentStream) -> None:
        self.stream = stream
        try:
            data = self.stream.get_data()
            doc_root: Document = parseString(data)
        except ExpatError as e:
            raise PdfReadError(f"XML in XmpInformation was invalid: {e}")
        self.rdf_root: XmlElement = doc_root.getElementsByTagNameNS(
            RDF_NAMESPACE, "RDF"
        )[0]
        self.cache: Dict[Any, Any] = {}

    @property
    def rdfRoot(self) -> XmlElement:
        deprecate_with_replacement("rdfRoot", "rdf_root", "4.0.0")
        return self.rdf_root

    def write_to_stream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        self.stream.write_to_stream(stream, encryption_key)

    def writeToStream(
        self, stream: StreamType, encryption_key: Union[None, str, bytes]
    ) -> None:
        deprecation_with_replacement("writeToStream", "write_to_stream", "3.0.0")
        self.write_to_stream(stream, encryption_key)

    def get_element(self, about_uri: str, namespace: str, name: str) -> Iterator[Any]:
        for desc in self.rdf_root.getElementsByTagNameNS(RDF_NAMESPACE, "Description"):
            if desc.getAttributeNS(RDF_NAMESPACE, "about") == about_uri:
                attr = desc.getAttributeNodeNS(namespace, name)
                if attr is not None:
                    yield attr
                yield from desc.getElementsByTagNameNS(namespace, name)

    def getElement(
        self, aboutUri: str, namespace: str, name: str
    ) -> Iterator[Any]:
        deprecation_with_replacement("getElement", "get_element", "3.0.0")
        return self.get_element(aboutUri, namespace, name)

    def get_nodes_in_namespace(self, about_uri: str, namespace: str) -> Iterator[Any]:
        for desc in self.rdf_root.getElementsByTagNameNS(RDF_NAMESPACE, "Description"):
            if desc.getAttributeNS(RDF_NAMESPACE, "about") == about_uri:
                for i in range(desc.attributes.length):
                    attr = desc.attributes.item(i)
                    if attr.namespaceURI == namespace:
                        yield attr
                for child in desc.childNodes:
                    if child.namespaceURI == namespace:
                        yield child

    def getNodesInNamespace(
        self, aboutUri: str, namespace: str
    ) -> Iterator[Any]:
        deprecation_with_replacement(
            "getNodesInNamespace", "get_nodes_in_namespace", "3.0.0"
        )
        return self.get_nodes_in_namespace(aboutUri, namespace)

    def _get_text(self, element: XmlElement) -> str:
        text = ""
        for child in element.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text += child.data
        return text

    dc_contributor = property(_getter_bag(DC_NAMESPACE, "contributor"))

    dc_coverage = property(_getter_single(DC_NAMESPACE, "coverage"))
    dc_creator = property(_getter_seq(DC_NAMESPACE, "creator"))
    dc_date = property(_getter_seq(DC_NAMESPACE, "date", _converter_date))
    dc_description = property(_getter_langalt(DC_NAMESPACE, "description"))
    dc_format = property(_getter_single(DC_NAMESPACE, "format"))
    dc_identifier = property(_getter_single(DC_NAMESPACE, "identifier"))
    dc_language = property(_getter_bag(DC_NAMESPACE, "language"))
    dc_publisher = property(_getter_bag(DC_NAMESPACE, "publisher"))
    dc_relation = property(_getter_bag(DC_NAMESPACE, "relation"))
    dc_rights = property(_getter_langalt(DC_NAMESPACE, "rights"))
    dc_source = property(_getter_single(DC_NAMESPACE, "source"))
    dc_subject = property(_getter_bag(DC_NAMESPACE, "subject"))
    dc_title = property(_getter_langalt(DC_NAMESPACE, "title"))
    dc_type = property(_getter_bag(DC_NAMESPACE, "type"))
    pdf_keywords = property(_getter_single(PDF_NAMESPACE, "Keywords"))
    pdf_pdfversion = property(_getter_single(PDF_NAMESPACE, "PDFVersion"))
    pdf_producer = property(_getter_single(PDF_NAMESPACE, "Producer"))
    xmp_create_date = property(
        _getter_single(XMP_NAMESPACE, "CreateDate", _converter_date)
    )

    @property
    def xmp_createDate(self) -> datetime.datetime:
        deprecate_with_replacement("xmp_createDate", "xmp_create_date", "4.0.0")
        return self.xmp_create_date

    @xmp_createDate.setter
    def xmp_createDate(self, value: datetime.datetime) -> None:
        deprecate_with_replacement("xmp_createDate", "xmp_create_date", "4.0.0")
        self.xmp_create_date = value

    xmp_modify_date = property(
        _getter_single(XMP_NAMESPACE, "ModifyDate", _converter_date)
    )

    @property
    def xmp_modifyDate(self) -> datetime.datetime:
        deprecate_with_replacement("xmp_modifyDate", "xmp_modify_date", "4.0.0")
        return self.xmp_modify_date

    @xmp_modifyDate.setter
    def xmp_modifyDate(self, value: datetime.datetime) -> None:
        deprecate_with_replacement("xmp_modifyDate", "xmp_modify_date", "4.0.0")
        self.xmp_modify_date = value

    xmp_metadata_date = property(
        _getter_single(XMP_NAMESPACE, "MetadataDate", _converter_date)
    )

    @property
    def xmp_metadataDate(self) -> datetime.datetime:
        deprecate_with_replacement("xmp_metadataDate", "xmp_metadata_date", "4.0.0")
        return self.xmp_metadata_date

    @xmp_metadataDate.setter
    def xmp_metadataDate(self, value: datetime.datetime) -> None:
        deprecate_with_replacement("xmp_metadataDate", "xmp_metadata_date", "4.0.0")
        self.xmp_metadata_date = value

    xmp_creator_tool = property(_getter_single(XMP_NAMESPACE, "CreatorTool"))

    @property
    def xmp_creatorTool(self) -> str:
        deprecation_with_replacement("xmp_creatorTool", "xmp_creator_tool", "3.0.0")
        return self.xmp_creator_tool

    @xmp_creatorTool.setter
    def xmp_creatorTool(self, value: str) -> None:
        deprecation_with_replacement("xmp_creatorTool", "xmp_creator_tool", "3.0.0")
        self.xmp_creator_tool = value

    xmpmm_document_id = property(_getter_single(XMPMM_NAMESPACE, "DocumentID"))

    @property
    def xmpmm_documentId(self) -> str:
        deprecation_with_replacement("xmpmm_documentId", "xmpmm_document_id", "3.0.0")
        return self.xmpmm_document_id

    @xmpmm_documentId.setter
    def xmpmm_documentId(self, value: str) -> None:
        deprecation_with_replacement("xmpmm_documentId", "xmpmm_document_id", "3.0.0")
        self.xmpmm_document_id = value

    xmpmm_instance_id = property(_getter_single(XMPMM_NAMESPACE, "InstanceID"))

    @property
    def xmpmm_instanceId(self) -> str:
        deprecation_with_replacement("xmpmm_instanceId", "xmpmm_instance_id", "3.0.0")
        return cast(str, self.xmpmm_instance_id)

    @xmpmm_instanceId.setter
    def xmpmm_instanceId(self, value: str) -> None:
        deprecation_with_replacement("xmpmm_instanceId", "xmpmm_instance_id", "3.0.0")
        self.xmpmm_instance_id = value

    @property
    def custom_properties(self) -> Dict[Any, Any]:
        if not hasattr(self, "_custom_properties"):
            self._custom_properties = {}
            for node in self.get_nodes_in_namespace("", PDFX_NAMESPACE):
                key = node.localName
                while True:
                    # see documentation about PDFX_NAMESPACE earlier in file
                    idx = key.find("\u2182")
                    if idx == -1:
                        break
                    key = (
                        key[:idx]
                        + chr(int(key[idx + 1 : idx + 5], base=16))
                        + key[idx + 5 :]
                    )
                if node.nodeType == node.ATTRIBUTE_NODE:
                    value = node.nodeValue
                else:
                    value = self._get_text(node)
                self._custom_properties[key] = value
        return self._custom_properties
