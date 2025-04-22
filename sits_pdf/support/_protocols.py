from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Tuple, Union

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol
from ._utils import StrByteType

class PdfObjectProtocol(Protocol):
    indirect_reference: Any
    def clone(
        self,
        pdf_dest: Any,
        force_duplicate: bool = False,
        ignore_fields: Union[Tuple[str, ...], List[str], None] = (),
    ) -> Any:
        ...

    def _reference_clone(self, clone: Any, pdf_dest: Any) -> Any:
        ...

    def get_object(self) -> Optional["PdfObjectProtocol"]:
        ...


class PdfReaderProtocol(Protocol):
    @property
    def pdf_header(self) -> str:
        ...

    @property
    def strict(self) -> bool:
        ...

    @property
    def xref(self) -> Dict[int, Dict[int, Any]]:
        ...

    @property
    def pages(self) -> List[Any]:
        ...

    def get_object(self, indirect_reference: Any) -> Optional[PdfObjectProtocol]:
        ...


class PdfWriterProtocol(Protocol):
    _objects: List[Any]
    _id_translated: Dict[int, Dict[int, int]]

    def get_object(self, indirect_reference: Any) -> Optional[PdfObjectProtocol]:
        ...

    def write(self, stream: Union[Path, StrByteType]) -> Tuple[bool, IO]:
        ...
