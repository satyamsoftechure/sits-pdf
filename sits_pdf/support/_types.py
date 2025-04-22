from typing import List, Union

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

try:
    from typing import TypeAlias
except ImportError:
    from typing_extensions import TypeAlias

from ._base import NameObject, NullObject, NumberObject
from ._data_structures import ArrayObject, Destination
from ._outline import OutlineItem

BorderArrayType: TypeAlias = List[Union[NameObject, NumberObject, ArrayObject]]
OutlineItemType: TypeAlias = Union[OutlineItem, Destination]
FitType: TypeAlias = Literal[
    "/Fit", "/XYZ", "/FitH", "/FitV", "/FitR", "/FitB", "/FitBH", "/FitBV"
]
ZoomArgType: TypeAlias = Union[NumberObject, NullObject, float]
ZoomArgsType: TypeAlias = List[ZoomArgType]
OutlineType = List[Union[Destination, List[Union[Destination, List[Destination]]]]]

LayoutType: TypeAlias = Literal[
    "/NoLayout",
    "/SinglePage",
    "/OneColumn",
    "/TwoColumnLeft",
    "/TwoColumnRight",
    "/TwoPageLeft",
    "/TwoPageRight",
]
PagemodeType: TypeAlias = Literal[
    "/UseNone",
    "/UseOutlines",
    "/UseThumbs",
    "/FullScreen",
    "/UseOC",
    "/UseAttachments",
]
