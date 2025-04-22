from typing import Any, Optional, Tuple, Union

class Fit:
    def __init__(
        self, fit_type: str, fit_args: Tuple[Union[None, float, Any], ...] = tuple()
    ):
        from ._base import FloatObject, NameObject, NullObject

        self.fit_type = NameObject(fit_type)
        self.fit_args = [
            NullObject() if a is None or isinstance(a, NullObject) else FloatObject(a)
            for a in fit_args
        ]

    @classmethod
    def xyz(
        cls,
        left: Optional[float] = None,
        top: Optional[float] = None,
        zoom: Optional[float] = None,
    ) -> "Fit":
        return Fit(fit_type="/XYZ", fit_args=(left, top, zoom))

    @classmethod
    def fit(cls) -> "Fit":
        return Fit(fit_type="/Fit")

    @classmethod
    def fit_horizontally(cls, top: Optional[float] = None) -> "Fit":
        return Fit(fit_type="/FitH", fit_args=(top,))

    @classmethod
    def fit_vertically(cls, left: Optional[float] = None) -> "Fit":
        return Fit(fit_type="/FitV", fit_args=(left,))

    @classmethod
    def fit_rectangle(
        cls,
        left: Optional[float] = None,
        bottom: Optional[float] = None,
        right: Optional[float] = None,
        top: Optional[float] = None,
    ) -> "Fit":
        return Fit(fit_type="/FitR", fit_args=(left, bottom, right, top))

    @classmethod
    def fit_box(cls) -> "Fit":
        return Fit(fit_type="/FitB")

    @classmethod
    def fit_box_horizontally(cls, top: Optional[float] = None) -> "Fit":
        return Fit(fit_type="/FitBH", fit_args=(top,))

    @classmethod
    def fit_box_vertically(cls, left: Optional[float] = None) -> "Fit":
        return Fit(fit_type="/FitBV", fit_args=(left,))

    def __str__(self) -> str:
        if not self.fit_args:
            return f"Fit({self.fit_type})"
        return f"Fit({self.fit_type}, {self.fit_args})"


DEFAULT_FIT = Fit.fit()
