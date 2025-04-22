import math
import uuid
import warnings
from decimal import Decimal
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from ._cmap import build_char_map, unknown_char_map
from ._protocols import PdfReaderProtocol
from ._utils import (
    CompressedTransformationMatrix,
    File,
    TransformationMatrixType,
    deprecation_no_replacement,
    deprecation_with_replacement,
    logger_warning,
    matrix_multiply,
)
from .constants import AnnotationDictionaryAttributes as ADA
from .constants import ImageAttributes as IA
from .constants import PageAttributes as PG
from .constants import Ressources as RES
from .errors import PageSizeNotDefinedError
from .filters import _xobj_to_image
from .generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    EncodedStreamObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    RectangleObject,
    encode_pdfdocencoding,
)

CUSTOM_RTL_MIN: int = -1
CUSTOM_RTL_MAX: int = -1
CUSTOM_RTL_SPECIAL_CHARS: List[int] = []


def set_custom_rtl(
    _min: Union[str, int, None] = None,
    _max: Union[str, int, None] = None,
    specials: Union[str, List[int], None] = None,
) -> Tuple[int, int, List[int]]:
    global CUSTOM_RTL_MIN, CUSTOM_RTL_MAX, CUSTOM_RTL_SPECIAL_CHARS
    if isinstance(_min, int):
        CUSTOM_RTL_MIN = _min
    elif isinstance(_min, str):
        CUSTOM_RTL_MIN = ord(_min)
    if isinstance(_max, int):
        CUSTOM_RTL_MAX = _max
    elif isinstance(_max, str):
        CUSTOM_RTL_MAX = ord(_max)
    if isinstance(specials, str):
        CUSTOM_RTL_SPECIAL_CHARS = [ord(x) for x in specials]
    elif isinstance(specials, list):
        CUSTOM_RTL_SPECIAL_CHARS = specials
    return CUSTOM_RTL_MIN, CUSTOM_RTL_MAX, CUSTOM_RTL_SPECIAL_CHARS


def _get_rectangle(self: Any, name: str, defaults: Iterable[str]) -> RectangleObject:
    retval: Union[None, RectangleObject, IndirectObject] = self.get(name)
    if isinstance(retval, RectangleObject):
        return retval
    if retval is None:
        for d in defaults:
            retval = self.get(d)
            if retval is not None:
                break
    if isinstance(retval, IndirectObject):
        retval = self.pdf.get_object(retval)
    retval = RectangleObject(retval)
    _set_rectangle(self, name, retval)
    return retval


def getRectangle(
    self: Any, name: str, defaults: Iterable[str]
) -> RectangleObject:
    deprecation_no_replacement("getRectangle", "3.0.0")
    return _get_rectangle(self, name, defaults)


def _set_rectangle(self: Any, name: str, value: Union[RectangleObject, float]) -> None:
    name = NameObject(name)
    self[name] = value


def setRectangle(
    self: Any, name: str, value: Union[RectangleObject, float]
) -> None:
    deprecation_no_replacement("setRectangle", "3.0.0")
    _set_rectangle(self, name, value)


def _delete_rectangle(self: Any, name: str) -> None:
    del self[name]


def deleteRectangle(self: Any, name: str) -> None:
    deprecation_no_replacement("deleteRectangle", "3.0.0")
    del self[name]


def _create_rectangle_accessor(name: str, fallback: Iterable[str]) -> property:
    return property(
        lambda self: _get_rectangle(self, name, fallback),
        lambda self, value: _set_rectangle(self, name, value),
        lambda self: _delete_rectangle(self, name),
    )


def createRectangleAccessor(
    name: str, fallback: Iterable[str]
) -> property: 
    deprecation_no_replacement("createRectangleAccessor", "3.0.0")
    return _create_rectangle_accessor(name, fallback)


class Transformation:
    def __init__(self, ctm: CompressedTransformationMatrix = (1, 0, 0, 1, 0, 0)):
        self.ctm = ctm

    @property
    def matrix(self) -> TransformationMatrixType:
        return (
            (self.ctm[0], self.ctm[1], 0),
            (self.ctm[2], self.ctm[3], 0),
            (self.ctm[4], self.ctm[5], 1),
        )

    @staticmethod
    def compress(matrix: TransformationMatrixType) -> CompressedTransformationMatrix:
        return (
            matrix[0][0],
            matrix[0][1],
            matrix[1][0],
            matrix[1][1],
            matrix[2][0],
            matrix[2][1],
        )

    def translate(self, tx: float = 0, ty: float = 0) -> "Transformation":
        m = self.ctm
        return Transformation(ctm=(m[0], m[1], m[2], m[3], m[4] + tx, m[5] + ty))

    def scale(
        self, sx: Optional[float] = None, sy: Optional[float] = None
    ) -> "Transformation":

        if sx is None and sy is None:
            raise ValueError("Either sx or sy must be specified")
        if sx is None:
            sx = sy
        if sy is None:
            sy = sx
        assert sx is not None
        assert sy is not None
        op: TransformationMatrixType = ((sx, 0, 0), (0, sy, 0), (0, 0, 1))
        ctm = Transformation.compress(matrix_multiply(self.matrix, op))
        return Transformation(ctm)

    def rotate(self, rotation: float) -> "Transformation":
        rotation = math.radians(rotation)
        op: TransformationMatrixType = (
            (math.cos(rotation), math.sin(rotation), 0),
            (-math.sin(rotation), math.cos(rotation), 0),
            (0, 0, 1),
        )
        ctm = Transformation.compress(matrix_multiply(self.matrix, op))
        return Transformation(ctm)

    def __repr__(self) -> str:
        return f"Transformation(ctm={self.ctm})"

    def apply_on(
        self, pt: Union[Tuple[Decimal, Decimal], Tuple[float, float], List[float]]
    ) -> Union[Tuple[float, float], List[float]]:
        pt1 = (
            float(pt[0]) * self.ctm[0] + float(pt[1]) * self.ctm[2] + self.ctm[4],
            float(pt[0]) * self.ctm[1] + float(pt[1]) * self.ctm[3] + self.ctm[5],
        )
        return list(pt1) if isinstance(pt, list) else pt1


class PageObject(DictionaryObject):

    original_page: "PageObject"  # very local use in writer when appending

    def __init__(
        self,
        pdf: Optional[PdfReaderProtocol] = None,
        indirect_reference: Optional[IndirectObject] = None,
        indirect_ref: Optional[IndirectObject] = None,  # deprecated
    ) -> None:

        DictionaryObject.__init__(self)
        self.pdf: Optional[PdfReaderProtocol] = pdf
        if indirect_ref is not None:  # deprecated
            warnings.warn(
                (
                    "indirect_ref is deprecated and will be removed in "
                    "PyPDF2 4.0.0. Use indirect_reference instead of indirect_ref."
                ),
                DeprecationWarning,
            )
            if indirect_reference is not None:
                raise ValueError("Use indirect_reference instead of indirect_ref.")
            indirect_reference = indirect_ref
        self.indirect_reference = indirect_reference

    @property
    def indirect_ref(self) -> Optional[IndirectObject]:  # deprecated
        warnings.warn(
            (
                "indirect_ref is deprecated and will be removed in PyPDF2 4.0.0"
                "Use indirect_reference instead of indirect_ref."
            ),
            DeprecationWarning,
        )
        return self.indirect_reference

    @indirect_ref.setter
    def indirect_ref(self, value: Optional[IndirectObject]) -> None:  # deprecated
        self.indirect_reference = value

    def hash_value_data(self) -> bytes:
        data = super().hash_value_data()
        data += b"%d" % id(self)
        return data

    @property
    def user_unit(self) -> float:
        return self.get(PG.USER_UNIT, 1)

    @staticmethod
    def create_blank_page(
        pdf: Optional[Any] = None,  # PdfReader
        width: Union[float, Decimal, None] = None,
        height: Union[float, Decimal, None] = None,
    ) -> "PageObject":
        page = PageObject(pdf)

        # Creates a new page (cf PDF Reference  7.7.3.3)
        page.__setitem__(NameObject(PG.TYPE), NameObject("/Page"))
        page.__setitem__(NameObject(PG.PARENT), NullObject())
        page.__setitem__(NameObject(PG.RESOURCES), DictionaryObject())
        if width is None or height is None:
            if pdf is not None and len(pdf.pages) > 0:
                lastpage = pdf.pages[len(pdf.pages) - 1]
                width = lastpage.mediabox.width
                height = lastpage.mediabox.height
            else:
                raise PageSizeNotDefinedError
        page.__setitem__(
            NameObject(PG.MEDIABOX), RectangleObject((0, 0, width, height))
        )

        return page

    @staticmethod
    def createBlankPage(
        pdf: Optional[Any] = None,
        width: Union[float, Decimal, None] = None,
        height: Union[float, Decimal, None] = None,
    ) -> "PageObject":
        deprecation_with_replacement("createBlankPage", "create_blank_page", "3.0.0")
        return PageObject.create_blank_page(pdf, width, height)

    @property
    def images(self) -> List[File]:
        images_extracted: List[File] = []
        if RES.XOBJECT not in self[PG.RESOURCES]:  # type: ignore
            return images_extracted

        x_object = self[PG.RESOURCES][RES.XOBJECT].get_object()  # type: ignore
        for obj in x_object:
            if x_object[obj][IA.SUBTYPE] == "/Image":
                extension, byte_stream = _xobj_to_image(x_object[obj])
                if extension is not None:
                    filename = f"{obj[1:]}{extension}"
                    images_extracted.append(File(name=filename, data=byte_stream))
        return images_extracted

    @property
    def rotation(self) -> int:
        return int(self.get(PG.ROTATE, 0))

    @rotation.setter
    def rotation(self, r: Union[int, float]) -> None:
        self[NameObject(PG.ROTATE)] = NumberObject((((int(r) + 45) // 90) * 90) % 360)

    def transfer_rotation_to_content(self) -> None:
        r = -self.rotation
        self.rotation = 0
        mb = RectangleObject(self.mediabox)
        trsf = (
            Transformation()
            .translate(
                -float(mb.left + mb.width / 2), -float(mb.bottom + mb.height / 2)
            )
            .rotate(r)
        )
        pt1 = trsf.apply_on(mb.lower_left)
        pt2 = trsf.apply_on(mb.upper_right)
        trsf = trsf.translate(-min(pt1[0], pt2[0]), -min(pt1[1], pt2[1]))
        self.add_transformation(trsf, False)
        for b in ["/MediaBox", "/CropBox", "/BleedBox", "/TrimBox", "/ArtBox"]:
            if b in self:
                rr = RectangleObject(self[b])  # type: ignore
                pt1 = trsf.apply_on(rr.lower_left)
                pt2 = trsf.apply_on(rr.upper_right)
                self[NameObject(b)] = RectangleObject(
                    (
                        min(pt1[0], pt2[0]),
                        min(pt1[1], pt2[1]),
                        max(pt1[0], pt2[0]),
                        max(pt1[1], pt2[1]),
                    )
                )

    def rotate(self, angle: int) -> "PageObject":
        if angle % 90 != 0:
            raise ValueError("Rotation angle must be a multiple of 90")
        rotate_obj = self.get(PG.ROTATE, 0)
        current_angle = (
            rotate_obj if isinstance(rotate_obj, int) else rotate_obj.get_object()
        )
        self[NameObject(PG.ROTATE)] = NumberObject(current_angle + angle)
        return self

    def rotate_clockwise(self, angle: int) -> "PageObject":  # pragma: no cover
        deprecation_with_replacement("rotate_clockwise", "rotate", "3.0.0")
        return self.rotate(angle)

    def rotateClockwise(self, angle: int) -> "PageObject":
        deprecation_with_replacement("rotateClockwise", "rotate", "3.0.0")
        return self.rotate(angle)

    def rotateCounterClockwise(self, angle: int) -> "PageObject":
        deprecation_with_replacement("rotateCounterClockwise", "rotate", "3.0.0")
        return self.rotate(-angle)

    @staticmethod
    def _merge_resources(
        res1: DictionaryObject, res2: DictionaryObject, resource: Any
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        new_res = DictionaryObject()
        new_res.update(res1.get(resource, DictionaryObject()).get_object())
        page2res = cast(
            DictionaryObject, res2.get(resource, DictionaryObject()).get_object()
        )
        rename_res = {}
        for key in list(page2res.keys()):
            if key in new_res and new_res.raw_get(key) != page2res.raw_get(key):
                newname = NameObject(key + str(uuid.uuid4()))
                rename_res[key] = newname
                new_res[newname] = page2res[key]
            elif key not in new_res:
                new_res[key] = page2res.raw_get(key)
        return new_res, rename_res

    @staticmethod
    def _content_stream_rename(
        stream: ContentStream, rename: Dict[Any, Any], pdf: Any
    ) -> ContentStream:
        if not rename:
            return stream
        stream = ContentStream(stream, pdf)
        for operands, _operator in stream.operations:
            if isinstance(operands, list):
                for i in range(len(operands)):
                    op = operands[i]
                    if isinstance(op, NameObject):
                        operands[i] = rename.get(op, op)
            elif isinstance(operands, dict):
                for i in operands:
                    op = operands[i]
                    if isinstance(op, NameObject):
                        operands[i] = rename.get(op, op)
            else:
                raise KeyError(f"type of operands is {type(operands)}")
        return stream

    @staticmethod
    def _push_pop_gs(contents: Any, pdf: Any) -> ContentStream:
        stream = ContentStream(contents, pdf)
        stream.operations.insert(0, ([], "q"))
        stream.operations.append(([], "Q"))
        return stream

    @staticmethod
    def _add_transformation_matrix(
        contents: Any, pdf: Any, ctm: CompressedTransformationMatrix
    ) -> ContentStream:
        a, b, c, d, e, f = ctm
        contents = ContentStream(contents, pdf)
        contents.operations.insert(
            0,
            [
                [
                    FloatObject(a),
                    FloatObject(b),
                    FloatObject(c),
                    FloatObject(d),
                    FloatObject(e),
                    FloatObject(f),
                ],
                " cm",
            ],
        )
        return contents

    def get_contents(self) -> Optional[ContentStream]:
        if PG.CONTENTS in self:
            return self[PG.CONTENTS].get_object()
        else:
            return None

    def getContents(self) -> Optional[ContentStream]:
        deprecation_with_replacement("getContents", "get_contents", "3.0.0")
        return self.get_contents()

    def merge_page(self, page2: "PageObject", expand: bool = False) -> None:
        self._merge_page(page2, expand=expand)

    def mergePage(self, page2: "PageObject") -> None:
        """
        .. deprecated:: 1.28.0

            Use :meth:`merge_page` instead.
        """
        deprecation_with_replacement("mergePage", "merge_page", "3.0.0")
        return self.merge_page(page2)

    def _merge_page(
        self,
        page2: "PageObject",
        page2transformation: Optional[Callable[[Any], ContentStream]] = None,
        ctm: Optional[CompressedTransformationMatrix] = None,
        expand: bool = False,
    ) -> None:
        new_resources = DictionaryObject()
        rename = {}
        try:
            original_resources = cast(DictionaryObject, self[PG.RESOURCES].get_object())
        except KeyError:
            original_resources = DictionaryObject()
        try:
            page2resources = cast(DictionaryObject, page2[PG.RESOURCES].get_object())
        except KeyError:
            page2resources = DictionaryObject()
        new_annots = ArrayObject()

        for page in (self, page2):
            if PG.ANNOTS in page:
                annots = page[PG.ANNOTS]
                if isinstance(annots, ArrayObject):
                    for ref in annots:
                        new_annots.append(ref)

        for res in (
            RES.EXT_G_STATE,
            RES.FONT,
            RES.XOBJECT,
            RES.COLOR_SPACE,
            RES.PATTERN,
            RES.SHADING,
            RES.PROPERTIES,
        ):
            new, newrename = PageObject._merge_resources(
                original_resources, page2resources, res
            )
            if new:
                new_resources[NameObject(res)] = new
                rename.update(newrename)
        new_resources[NameObject(RES.PROC_SET)] = ArrayObject(
            frozenset(
                original_resources.get(RES.PROC_SET, ArrayObject()).get_object()
            ).union(
                frozenset(page2resources.get(RES.PROC_SET, ArrayObject()).get_object())
            )
        )

        new_content_array = ArrayObject()

        original_content = self.get_contents()
        if original_content is not None:
            new_content_array.append(
                PageObject._push_pop_gs(original_content, self.pdf)
            )

        page2content = page2.get_contents()
        if page2content is not None:
            page2content = ContentStream(page2content, self.pdf)
            rect = page2.trimbox
            page2content.operations.insert(
                0,
                (
                    map(
                        FloatObject,
                        [
                            rect.left,
                            rect.bottom,
                            rect.width,
                            rect.height,
                        ],
                    ),
                    "re",
                ),
            )
            page2content.operations.insert(1, ([], "W"))
            page2content.operations.insert(2, ([], "n"))
            if page2transformation is not None:
                page2content = page2transformation(page2content)
            page2content = PageObject._content_stream_rename(
                page2content, rename, self.pdf
            )
            page2content = PageObject._push_pop_gs(page2content, self.pdf)
            new_content_array.append(page2content)
        if expand:
            self._expand_mediabox(page2, ctm)

        self[NameObject(PG.CONTENTS)] = ContentStream(new_content_array, self.pdf)
        self[NameObject(PG.RESOURCES)] = new_resources
        self[NameObject(PG.ANNOTS)] = new_annots

    def _expand_mediabox(
        self, page2: "PageObject", ctm: Optional[CompressedTransformationMatrix]
    ) -> None:
        corners1 = (
            self.mediabox.left.as_numeric(),
            self.mediabox.bottom.as_numeric(),
            self.mediabox.right.as_numeric(),
            self.mediabox.top.as_numeric(),
        )
        corners2 = (
            page2.mediabox.left.as_numeric(),
            page2.mediabox.bottom.as_numeric(),
            page2.mediabox.left.as_numeric(),
            page2.mediabox.top.as_numeric(),
            page2.mediabox.right.as_numeric(),
            page2.mediabox.top.as_numeric(),
            page2.mediabox.right.as_numeric(),
            page2.mediabox.bottom.as_numeric(),
        )
        if ctm is not None:
            ctm = tuple(float(x) for x in ctm)
            new_x = tuple(
                ctm[0] * corners2[i] + ctm[2] * corners2[i + 1] + ctm[4]
                for i in range(0, 8, 2)
            )
            new_y = tuple(
                ctm[1] * corners2[i] + ctm[3] * corners2[i + 1] + ctm[5]
                for i in range(0, 8, 2)
            )
        else:
            new_x = corners2[0:8:2]
            new_y = corners2[1:8:2]
        lowerleft = (min(new_x), min(new_y))
        upperright = (max(new_x), max(new_y))
        lowerleft = (min(corners1[0], lowerleft[0]), min(corners1[1], lowerleft[1]))
        upperright = (
            max(corners1[2], upperright[0]),
            max(corners1[3], upperright[1]),
        )

        self.mediabox.lower_left = lowerleft
        self.mediabox.upper_right = upperright

    def mergeTransformedPage(
        self,
        page2: "PageObject",
        ctm: Union[CompressedTransformationMatrix, Transformation],
        expand: bool = False,
    ) -> None:
        deprecation_with_replacement(
            "page.mergeTransformedPage(page2, ctm)",
            "page2.add_transformation(ctm); page.merge_page(page2)",
            "3.0.0",
        )
        if isinstance(ctm, Transformation):
            ctm = ctm.ctm
        ctm = cast(CompressedTransformationMatrix, ctm)
        self._merge_page(
            page2,
            lambda page2Content: PageObject._add_transformation_matrix(
                page2Content, page2.pdf, ctm  # type: ignore[arg-type]
            ),
            ctm,
            expand,
        )

    def mergeScaledPage(
        self, page2: "PageObject", scale: float, expand: bool = False
    ) -> None:
        deprecation_with_replacement(
            "page.mergeScaledPage(page2, scale, expand)",
            "page2.add_transformation(Transformation().scale(scale)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().scale(scale, scale)
        self.mergeTransformedPage(page2, op, expand)

    def mergeRotatedPage(
        self, page2: "PageObject", rotation: float, expand: bool = False
    ) -> None:
        deprecation_with_replacement(
            "page.mergeRotatedPage(page2, rotation, expand)",
            "page2.add_transformation(Transformation().rotate(rotation)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().rotate(rotation)
        self.mergeTransformedPage(page2, op, expand)

    def mergeTranslatedPage(
        self, page2: "PageObject", tx: float, ty: float, expand: bool = False
    ) -> None:
        deprecation_with_replacement(
            "page.mergeTranslatedPage(page2, tx, ty, expand)",
            "page2.add_transformation(Transformation().translate(tx, ty)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().translate(tx, ty)
        self.mergeTransformedPage(page2, op, expand)

    def mergeRotatedTranslatedPage(
        self,
        page2: "PageObject",
        rotation: float,
        tx: float,
        ty: float,
        expand: bool = False,
    ) -> None:
        deprecation_with_replacement(
            "page.mergeRotatedTranslatedPage(page2, rotation, tx, ty, expand)",
            "page2.add_transformation(Transformation().rotate(rotation).translate(tx, ty)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().translate(-tx, -ty).rotate(rotation).translate(tx, ty)
        return self.mergeTransformedPage(page2, op, expand)

    def mergeRotatedScaledPage(
        self, page2: "PageObject", rotation: float, scale: float, expand: bool = False
    ) -> None:
        deprecation_with_replacement(
            "page.mergeRotatedScaledPage(page2, rotation, scale, expand)",
            "page2.add_transformation(Transformation().rotate(rotation).scale(scale)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().rotate(rotation).scale(scale, scale)
        self.mergeTransformedPage(page2, op, expand)

    def mergeScaledTranslatedPage(
        self,
        page2: "PageObject",
        scale: float,
        tx: float,
        ty: float,
        expand: bool = False,
    ) -> None:
        deprecation_with_replacement(
            "page.mergeScaledTranslatedPage(page2, scale, tx, ty, expand)",
            "page2.add_transformation(Transformation().scale(scale).translate(tx, ty)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().scale(scale, scale).translate(tx, ty)
        return self.mergeTransformedPage(page2, op, expand)

    def mergeRotatedScaledTranslatedPage(
        self,
        page2: "PageObject",
        rotation: float,
        scale: float,
        tx: float,
        ty: float,
        expand: bool = False,
    ) -> None:
        deprecation_with_replacement(
            "page.mergeRotatedScaledTranslatedPage(page2, rotation, tx, ty, expand)",
            "page2.add_transformation(Transformation().rotate(rotation).scale(scale)); page.merge_page(page2, expand)",
            "3.0.0",
        )
        op = Transformation().rotate(rotation).scale(scale, scale).translate(tx, ty)
        self.mergeTransformedPage(page2, op, expand)

    def add_transformation(
        self,
        ctm: Union[Transformation, CompressedTransformationMatrix],
        expand: bool = False,
    ) -> None:
        if isinstance(ctm, Transformation):
            ctm = ctm.ctm
        content = self.get_contents()
        if content is not None:
            content = PageObject._add_transformation_matrix(content, self.pdf, ctm)
            content = PageObject._push_pop_gs(content, self.pdf)
            self[NameObject(PG.CONTENTS)] = content
        if expand:
            corners = [
                self.mediabox.left.as_numeric(),
                self.mediabox.bottom.as_numeric(),
                self.mediabox.left.as_numeric(),
                self.mediabox.top.as_numeric(),
                self.mediabox.right.as_numeric(),
                self.mediabox.top.as_numeric(),
                self.mediabox.right.as_numeric(),
                self.mediabox.bottom.as_numeric(),
            ]

            ctm = tuple(float(x) for x in ctm)
            new_x = [
                ctm[0] * corners[i] + ctm[2] * corners[i + 1] + ctm[4]
                for i in range(0, 8, 2)
            ]
            new_y = [
                ctm[1] * corners[i] + ctm[3] * corners[i + 1] + ctm[5]
                for i in range(0, 8, 2)
            ]

            lowerleft = (min(new_x), min(new_y))
            upperright = (max(new_x), max(new_y))
            lowerleft = (min(corners[0], lowerleft[0]), min(corners[1], lowerleft[1]))
            upperright = (
                max(corners[2], upperright[0]),
                max(corners[3], upperright[1]),
            )

            self.mediabox.lower_left = lowerleft
            self.mediabox.upper_right = upperright

    def addTransformation(
        self, ctm: CompressedTransformationMatrix
    ) -> None:
        deprecation_with_replacement("addTransformation", "add_transformation", "3.0.0")
        self.add_transformation(ctm)

    def scale(self, sx: float, sy: float) -> None:
        self.add_transformation((sx, 0, 0, sy, 0, 0))
        self.cropbox = self.cropbox.scale(sx, sy)
        self.artbox = self.artbox.scale(sx, sy)
        self.bleedbox = self.bleedbox.scale(sx, sy)
        self.trimbox = self.trimbox.scale(sx, sy)
        self.mediabox = self.mediabox.scale(sx, sy)

        if PG.ANNOTS in self:
            annotations = self[PG.ANNOTS]
            if isinstance(annotations, ArrayObject):
                for annotation in annotations:
                    annotation_obj = annotation.get_object()
                    if ADA.Rect in annotation_obj:
                        rectangle = annotation_obj[ADA.Rect]
                        if isinstance(rectangle, ArrayObject):
                            rectangle[0] = FloatObject(float(rectangle[0]) * sx)
                            rectangle[1] = FloatObject(float(rectangle[1]) * sy)
                            rectangle[2] = FloatObject(float(rectangle[2]) * sx)
                            rectangle[3] = FloatObject(float(rectangle[3]) * sy)

        if PG.VP in self:
            viewport = self[PG.VP]
            if isinstance(viewport, ArrayObject):
                bbox = viewport[0]["/BBox"]
            else:
                bbox = viewport["/BBox"]
            scaled_bbox = RectangleObject(
                (
                    float(bbox[0]) * sx,
                    float(bbox[1]) * sy,
                    float(bbox[2]) * sx,
                    float(bbox[3]) * sy,
                )
            )
            if isinstance(viewport, ArrayObject):
                self[NameObject(PG.VP)][NumberObject(0)][
                    NameObject("/BBox")
                ] = scaled_bbox
            else:
                self[NameObject(PG.VP)][NameObject("/BBox")] = scaled_bbox
    def scale_by(self, factor: float) -> None:
        self.scale(factor, factor)

    def scaleBy(self, factor: float) -> None:
        deprecation_with_replacement("scaleBy", "scale_by", "3.0.0")
        self.scale(factor, factor)

    def scale_to(self, width: float, height: float) -> None:
        sx = width / float(self.mediabox.width)
        sy = height / float(self.mediabox.height)
        self.scale(sx, sy)

    def scaleTo(self, width: float, height: float) -> None:
        deprecation_with_replacement("scaleTo", "scale_to", "3.0.0")
        self.scale_to(width, height)

    def compress_content_streams(self) -> None:
        content = self.get_contents()
        if content is not None:
            if not isinstance(content, ContentStream):
                content = ContentStream(content, self.pdf)
            self[NameObject(PG.CONTENTS)] = content.flate_encode()

    def compressContentStreams(self) -> None:
        deprecation_with_replacement(
            "compressContentStreams", "compress_content_streams", "3.0.0"
        )
        self.compress_content_streams()

    def _debug_for_extract(self) -> str:
        out = ""
        for ope, op in ContentStream(
            self["/Contents"].get_object(), self.pdf, "bytes"
        ).operations:
            if op == b"TJ":
                s = [x for x in ope[0] if isinstance(x, str)]
            else:
                s = []
            out += op.decode("utf-8") + " " + "".join(s) + ope.__repr__() + "\n"
        out += "\n=============================\n"
        try:
            for fo in self[PG.RESOURCES]["/Font"]:  # type:ignore
                out += fo + "\n"
                out += self[PG.RESOURCES]["/Font"][fo].__repr__() + "\n"  # type:ignore
                try:
                    enc_repr = self[PG.RESOURCES]["/Font"][fo][  # type:ignore
                        "/Encoding"
                    ].__repr__()
                    out += enc_repr + "\n"
                except Exception:
                    pass
                try:
                    out += (
                        self[PG.RESOURCES]["/Font"][fo][  # type:ignore
                            "/ToUnicode"
                        ]
                        .get_data()
                        .decode()
                        + "\n"
                    )
                except Exception:
                    pass

        except KeyError:
            out += "No Font\n"
        return out

    def _extract_text(
        self,
        obj: Any,
        pdf: Any,
        orientations: Tuple[int, ...] = (0, 90, 180, 270),
        space_width: float = 200.0,
        content_key: Optional[str] = PG.CONTENTS,
        visitor_operand_before: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_operand_after: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_text: Optional[Callable[[Any, Any, Any, Any, Any], None]] = None,
    ) -> str:
        text: str = ""
        output: str = ""
        rtl_dir: bool = False
        cmaps: Dict[
            str,
            Tuple[
                str, float, Union[str, Dict[int, str]], Dict[str, str], DictionaryObject
            ],
        ] = {}
        try:
            objr = obj
            while NameObject(PG.RESOURCES) not in objr:
                objr = objr["/Parent"].get_object()
            resources_dict = cast(DictionaryObject, objr[PG.RESOURCES])
        except Exception:
            return ""
        if "/Font" in resources_dict:
            for f in cast(DictionaryObject, resources_dict["/Font"]):
                cmaps[f] = build_char_map(f, space_width, obj)
        cmap: Tuple[
            Union[str, Dict[int, str]], Dict[str, str], str, Optional[DictionaryObject]
        ] = (
            "charmap",
            {},
            "NotInitialized",
            None,
        )
        try:
            content = (
                obj[content_key].get_object() if isinstance(content_key, str) else obj
            )
            if not isinstance(content, ContentStream):
                content = ContentStream(content, pdf, "bytes")
        except KeyError:
            return ""
        cm_matrix: List[float] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        cm_stack = []
        tm_matrix: List[float] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        tm_prev: List[float] = [
            1.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
        ]  
        char_scale = 1.0
        space_scale = 1.0
        _space_width: float = 500.0  
        TL = 0.0
        font_size = 12.0  

        def mult(m: List[float], n: List[float]) -> List[float]:
            return [
                m[0] * n[0] + m[1] * n[2],
                m[0] * n[1] + m[1] * n[3],
                m[2] * n[0] + m[3] * n[2],
                m[2] * n[1] + m[3] * n[3],
                m[4] * n[0] + m[5] * n[2] + n[4],
                m[4] * n[1] + m[5] * n[3] + n[5],
            ]

        def orient(m: List[float]) -> int:
            if m[3] > 1e-6:
                return 0
            elif m[3] < -1e-6:
                return 180
            elif m[1] > 0:
                return 90
            else:
                return 270

        def current_spacewidth() -> float:
            return _space_width / 1000.0

        def process_operation(operator: bytes, operands: List) -> None:
            nonlocal cm_matrix, cm_stack, tm_matrix, tm_prev, output, text, char_scale, space_scale, _space_width, TL, font_size, cmap, orientations, rtl_dir, visitor_text
            global CUSTOM_RTL_MIN, CUSTOM_RTL_MAX, CUSTOM_RTL_SPECIAL_CHARS

            check_crlf_space: bool = False
            if operator == b"BT":
                tm_matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                output += text
                if visitor_text is not None:
                    visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                text = ""
                return None
            elif operator == b"ET":
                output += text
                if visitor_text is not None:
                    visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                text = ""
            elif operator == b"q":
                cm_stack.append(
                    (
                        cm_matrix,
                        cmap,
                        font_size,
                        char_scale,
                        space_scale,
                        _space_width,
                        TL,
                    )
                )
            elif operator == b"Q":
                try:
                    (
                        cm_matrix,
                        cmap,
                        font_size,
                        char_scale,
                        space_scale,
                        _space_width,
                        TL,
                    ) = cm_stack.pop()
                except Exception:
                    cm_matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            elif operator == b"cm":
                output += text
                if visitor_text is not None:
                    visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                text = ""
                cm_matrix = mult(
                    [
                        float(operands[0]),
                        float(operands[1]),
                        float(operands[2]),
                        float(operands[3]),
                        float(operands[4]),
                        float(operands[5]),
                    ],
                    cm_matrix,
                )
            elif operator == b"Tz":
                char_scale = float(operands[0]) / 100.0
            elif operator == b"Tw":
                space_scale = 1.0 + float(operands[0])
            elif operator == b"TL":
                TL = float(operands[0])
            elif operator == b"Tf":
                if text != "":
                    output += text
                    if visitor_text is not None:
                        visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                text = ""
                try:
                    charMapTuple = cmaps[operands[0]]
                    _space_width = charMapTuple[1]
                    cmap = (
                        charMapTuple[2],
                        charMapTuple[3],
                        operands[0],
                        charMapTuple[4],
                    )
                except KeyError:
                    _space_width = unknown_char_map[1]
                    cmap = (
                        unknown_char_map[2],
                        unknown_char_map[3],
                        "???" + operands[0],
                        None,
                    )
                try:
                    font_size = float(operands[1])
                except Exception:
                    pass
            elif operator == b"Td":
                check_crlf_space = True
                tx = float(operands[0])
                ty = float(operands[1])
                tm_matrix[4] += tx * tm_matrix[0] + ty * tm_matrix[2]
                tm_matrix[5] += tx * tm_matrix[1] + ty * tm_matrix[3]
            elif operator == b"Tm":
                check_crlf_space = True
                tm_matrix = [
                    float(operands[0]),
                    float(operands[1]),
                    float(operands[2]),
                    float(operands[3]),
                    float(operands[4]),
                    float(operands[5]),
                ]
            elif operator == b"T*":
                check_crlf_space = True
                tm_matrix[5] -= TL

            elif operator == b"Tj":
                check_crlf_space = True
                m = mult(tm_matrix, cm_matrix)
                orientation = orient(m)
                if orientation in orientations:
                    if isinstance(operands[0], str):
                        text += operands[0]
                    else:
                        t: str = ""
                        tt: bytes = (
                            encode_pdfdocencoding(operands[0])
                            if isinstance(operands[0], str)
                            else operands[0]
                        )
                        if isinstance(cmap[0], str):
                            try:
                                t = tt.decode(
                                    cmap[0], "surrogatepass"
                                )
                            except Exception:
                                t = tt.decode(
                                    "utf-16-be" if cmap[0] == "charmap" else "charmap",
                                    "surrogatepass",
                                )
                        else:
                            t = "".join(
                                [
                                    cmap[0][x] if x in cmap[0] else bytes((x,)).decode()
                                    for x in tt
                                ]
                            )
                        for x in "".join(
                            [cmap[1][x] if x in cmap[1] else x for x in t]
                        ):
                            xx = ord(x)
                            if (
                                (xx <= 0x2F)                       
                                or (0x3A <= xx and xx <= 0x40)     
                                or (0x2000 <= xx and xx <= 0x206F) 
                                or (0x20A0 <= xx and xx <= 0x21FF) 
                                or xx in CUSTOM_RTL_SPECIAL_CHARS   
                            ):
                                text = x + text if rtl_dir else text + x
                            elif (
                                (0x0590 <= xx and xx <= 0x08FF)
                                or (0xFB1D <= xx and xx <= 0xFDFF)
                                or (0xFE70 <= xx and xx <= 0xFEFF)
                                or (CUSTOM_RTL_MIN <= xx and xx <= CUSTOM_RTL_MAX)
                            ):
                                if not rtl_dir:
                                    rtl_dir = True
                                    output += text
                                    if visitor_text is not None:
                                        visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                                    text = ""
                                text = x + text
                            else:
                                if rtl_dir:
                                    rtl_dir = False
                                    output += text
                                    if visitor_text is not None:
                                        visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                                    text = ""
                                text = text + x
            else:
                return None
            if check_crlf_space:
                m = mult(tm_matrix, cm_matrix)
                orientation = orient(m)
                delta_x = m[4] - tm_prev[4]
                delta_y = m[5] - tm_prev[5]
                k = math.sqrt(abs(m[0] * m[3]) + abs(m[1] * m[2]))
                f = font_size * k
                tm_prev = m
                if orientation not in orientations:
                    return None
                try:
                    if orientation == 0:
                        if delta_y < -0.8 * f:
                            if (output + text)[-1] != "\n":
                                output += text + "\n"
                                if visitor_text is not None:
                                    visitor_text(
                                        text + "\n",
                                        cm_matrix,
                                        tm_matrix,
                                        cmap[3],
                                        font_size,
                                    )
                                text = ""
                        elif (
                            abs(delta_y) < f * 0.3
                            and abs(delta_x) > current_spacewidth() * f * 15
                        ):
                            if (output + text)[-1] != " ":
                                text += " "
                    elif orientation == 180:
                        if delta_y > 0.8 * f:
                            if (output + text)[-1] != "\n":
                                output += text + "\n"
                                if visitor_text is not None:
                                    visitor_text(
                                        text + "\n",
                                        cm_matrix,
                                        tm_matrix,
                                        cmap[3],
                                        font_size,
                                    )
                                text = ""
                        elif (
                            abs(delta_y) < f * 0.3
                            and abs(delta_x) > current_spacewidth() * f * 15
                        ):
                            if (output + text)[-1] != " ":
                                text += " "
                    elif orientation == 90:
                        if delta_x > 0.8 * f:
                            if (output + text)[-1] != "\n":
                                output += text + "\n"
                                if visitor_text is not None:
                                    visitor_text(
                                        text + "\n",
                                        cm_matrix,
                                        tm_matrix,
                                        cmap[3],
                                        font_size,
                                    )
                                text = ""
                        elif (
                            abs(delta_x) < f * 0.3
                            and abs(delta_y) > current_spacewidth() * f * 15
                        ):
                            if (output + text)[-1] != " ":
                                text += " "
                    elif orientation == 270:
                        if delta_x < -0.8 * f:
                            if (output + text)[-1] != "\n":
                                output += text + "\n"
                                if visitor_text is not None:
                                    visitor_text(
                                        text + "\n",
                                        cm_matrix,
                                        tm_matrix,
                                        cmap[3],
                                        font_size,
                                    )
                                text = ""
                        elif (
                            abs(delta_x) < f * 0.3
                            and abs(delta_y) > current_spacewidth() * f * 15
                        ):
                            if (output + text)[-1] != " ":
                                text += " "
                except Exception:
                    pass

        for operands, operator in content.operations:
            if visitor_operand_before is not None:
                visitor_operand_before(operator, operands, cm_matrix, tm_matrix)
            if operator == b"'":
                process_operation(b"T*", [])
                process_operation(b"Tj", operands)
            elif operator == b'"':
                process_operation(b"Tw", [operands[0]])
                process_operation(b"Tc", [operands[1]])
                process_operation(b"T*", [])
                process_operation(b"Tj", operands[2:])
            elif operator == b"TD":
                process_operation(b"TL", [-operands[1]])
                process_operation(b"Td", operands)
            elif operator == b"TJ":
                for op in operands[0]:
                    if isinstance(op, (str, bytes)):
                        process_operation(b"Tj", [op])
                    if isinstance(op, (int, float, NumberObject, FloatObject)):
                        if (
                            (abs(float(op)) >= _space_width)
                            and (len(text) > 0)
                            and (text[-1] != " ")
                        ):
                            process_operation(b"Tj", [" "])
            elif operator == b"Do":
                output += text
                if visitor_text is not None:
                    visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                try:
                    if output[-1] != "\n":
                        output += "\n"
                        if visitor_text is not None:
                            visitor_text("\n", cm_matrix, tm_matrix, cmap[3], font_size)
                except IndexError:
                    pass
                try:
                    xobj = resources_dict["/XObject"]
                    if xobj[operands[0]]["/Subtype"] != "/Image":
                        text = self.extract_xform_text(
                            xobj[operands[0]],
                            orientations,
                            space_width,
                            visitor_operand_before,
                            visitor_operand_after,
                            visitor_text,
                        )
                        output += text
                        if visitor_text is not None:
                            visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
                except Exception:
                    logger_warning(
                        f" impossible to decode XFormObject {operands[0]}",
                        __name__,
                    )
                finally:
                    text = ""
            else:
                process_operation(operator, operands)
            if visitor_operand_after is not None:
                visitor_operand_after(operator, operands, cm_matrix, tm_matrix)
        output += text
        if text != "" and visitor_text is not None:
            visitor_text(text, cm_matrix, tm_matrix, cmap[3], font_size)
        return output

    def extract_text(
        self,
        *args: Any,
        Tj_sep: str = None,
        TJ_sep: str = None,
        orientations: Union[int, Tuple[int, ...]] = (0, 90, 180, 270),
        space_width: float = 200.0,
        visitor_operand_before: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_operand_after: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_text: Optional[Callable[[Any, Any, Any, Any, Any], None]] = None,
    ) -> str:
        if len(args) >= 1:
            if isinstance(args[0], str):
                Tj_sep = args[0]
                if len(args) >= 2:
                    if isinstance(args[1], str):
                        TJ_sep = args[1]
                    else:
                        raise TypeError(f"Invalid positional parameter {args[1]}")
                if len(args) >= 3:
                    if isinstance(args[2], (tuple, int)):
                        orientations = args[2]
                    else:
                        raise TypeError(f"Invalid positional parameter {args[2]}")
                if len(args) >= 4:
                    if isinstance(args[3], (float, int)):
                        space_width = args[3]
                    else:
                        raise TypeError(f"Invalid positional parameter {args[3]}")
            elif isinstance(args[0], (tuple, int)):
                orientations = args[0]
                if len(args) >= 2:
                    if isinstance(args[1], (float, int)):
                        space_width = args[1]
                    else:
                        raise TypeError(f"Invalid positional parameter {args[1]}")
            else:
                raise TypeError(f"Invalid positional parameter {args[0]}")
        if Tj_sep is not None or TJ_sep is not None:
            warnings.warn(
                "parameters Tj_Sep, TJ_sep depreciated, and will be removed in PyPDF2 4.0.0.",
                DeprecationWarning,
            )

        if isinstance(orientations, int):
            orientations = (orientations,)

        return self._extract_text(
            self,
            self.pdf,
            orientations,
            space_width,
            PG.CONTENTS,
            visitor_operand_before,
            visitor_operand_after,
            visitor_text,
        )

    def extract_xform_text(
        self,
        xform: EncodedStreamObject,
        orientations: Tuple[int, ...] = (0, 90, 270, 360),
        space_width: float = 200.0,
        visitor_operand_before: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_operand_after: Optional[Callable[[Any, Any, Any, Any], None]] = None,
        visitor_text: Optional[Callable[[Any, Any, Any, Any, Any], None]] = None,
    ) -> str:
        return self._extract_text(
            xform,
            self.pdf,
            orientations,
            space_width,
            None,
            visitor_operand_before,
            visitor_operand_after,
            visitor_text,
        )

    def extractText(
        self, Tj_sep: str = "", TJ_sep: str = ""
    ) -> str:
        deprecation_with_replacement("extractText", "extract_text", "3.0.0")
        return self.extract_text()

    def _get_fonts(self) -> Tuple[Set[str], Set[str]]:
        obj = self.get_object()
        assert isinstance(obj, DictionaryObject)
        fonts, embedded = _get_fonts_walk(cast(DictionaryObject, obj[PG.RESOURCES]))
        unembedded = fonts - embedded
        return embedded, unembedded

    mediabox = _create_rectangle_accessor(PG.MEDIABOX, ())

    @property
    def mediaBox(self) -> RectangleObject:
        deprecation_with_replacement("mediaBox", "mediabox", "3.0.0")
        return self.mediabox

    @mediaBox.setter
    def mediaBox(self, value: RectangleObject) -> None:
        deprecation_with_replacement("mediaBox", "mediabox", "3.0.0")
        self.mediabox = value

    cropbox = _create_rectangle_accessor("/CropBox", (PG.MEDIABOX,))
    @property
    def cropBox(self) -> RectangleObject:
        deprecation_with_replacement("cropBox", "cropbox", "3.0.0")
        return self.cropbox

    @cropBox.setter
    def cropBox(self, value: RectangleObject) -> None:
        deprecation_with_replacement("cropBox", "cropbox", "3.0.0")
        self.cropbox = value

    bleedbox = _create_rectangle_accessor("/BleedBox", ("/CropBox", PG.MEDIABOX))
    @property
    def bleedBox(self) -> RectangleObject:
        deprecation_with_replacement("bleedBox", "bleedbox", "3.0.0")
        return self.bleedbox

    @bleedBox.setter
    def bleedBox(self, value: RectangleObject) -> None:
        deprecation_with_replacement("bleedBox", "bleedbox", "3.0.0")
        self.bleedbox = value

    trimbox = _create_rectangle_accessor("/TrimBox", ("/CropBox", PG.MEDIABOX))
    @property
    def trimBox(self) -> RectangleObject:
        deprecation_with_replacement("trimBox", "trimbox", "3.0.0")
        return self.trimbox

    @trimBox.setter
    def trimBox(self, value: RectangleObject) -> None:
        deprecation_with_replacement("trimBox", "trimbox", "3.0.0")
        self.trimbox = value

    artbox = _create_rectangle_accessor("/ArtBox", ("/CropBox", PG.MEDIABOX))
    @property
    def artBox(self) -> RectangleObject:
        deprecation_with_replacement("artBox", "artbox", "3.0.0")
        return self.artbox

    @artBox.setter
    def artBox(self, value: RectangleObject) -> None:  # pragma: no cover
        deprecation_with_replacement("artBox", "artbox", "3.0.0")
        self.artbox = value

    @property
    def annotations(self) -> Optional[ArrayObject]:
        if "/Annots" not in self:
            return None
        else:
            return cast(ArrayObject, self["/Annots"])

    @annotations.setter
    def annotations(self, value: Optional[ArrayObject]) -> None:
        if value is None:
            del self[NameObject("/Annots")]
        else:
            self[NameObject("/Annots")] = value


class _VirtualList:
    def __init__(
        self,
        length_function: Callable[[], int],
        get_function: Callable[[int], PageObject],
    ) -> None:
        self.length_function = length_function
        self.get_function = get_function
        self.current = -1

    def __len__(self) -> int:
        return self.length_function()

    def __getitem__(self, index: int) -> PageObject:
        if isinstance(index, slice):
            indices = range(*index.indices(len(self)))
            cls = type(self)
            return cls(indices.__len__, lambda idx: self[indices[idx]])  # type: ignore
        if not isinstance(index, int):
            raise TypeError("sequence indices must be integers")
        len_self = len(self)
        if index < 0:
            index = len_self + index
        if index < 0 or index >= len_self:
            raise IndexError("sequence index out of range")
        return self.get_function(index)

    def __iter__(self) -> Iterator[PageObject]:
        for i in range(len(self)):
            yield self[i]


def _get_fonts_walk(
    obj: DictionaryObject,
    fnt: Optional[Set[str]] = None,
    emb: Optional[Set[str]] = None,
) -> Tuple[Set[str], Set[str]]:
    if fnt is None:
        fnt = set()
    if emb is None:
        emb = set()
    if not hasattr(obj, "keys"):
        return set(), set()
    fontkeys = ("/FontFile", "/FontFile2", "/FontFile3")
    if "/BaseFont" in obj:
        fnt.add(cast(str, obj["/BaseFont"]))
    if "/FontName" in obj:
        if [x for x in fontkeys if x in obj]:
            emb.add(cast(str, obj["/FontName"]))

    for key in obj.keys():
        _get_fonts_walk(cast(DictionaryObject, obj[key]), fnt, emb)

    return fnt, emb
