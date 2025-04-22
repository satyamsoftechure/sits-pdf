from typing import Optional, Tuple, Union

from ._base import (
    BooleanObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from ._data_structures import ArrayObject, DictionaryObject
from ._fit import DEFAULT_FIT, Fit
from ._rectangle import RectangleObject
from .__utils import hex_to_rgb


class AnnotationBuilder:
    from ._types import FitType, ZoomArgType

    @staticmethod
    def text(
        rect: Union[RectangleObject, Tuple[float, float, float, float]],
        text: str,
        open: bool = False,
        flags: int = 0,
    ) -> DictionaryObject:
        text_obj = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Text"),
                NameObject("/Rect"): RectangleObject(rect),
                NameObject("/Contents"): TextStringObject(text),
                NameObject("/Open"): BooleanObject(open),
                NameObject("/Flags"): NumberObject(flags),
            }
        )
        return text_obj

    @staticmethod
    def free_text(
        text: str,
        rect: Union[RectangleObject, Tuple[float, float, float, float]],
        font: str = "Helvetica",
        bold: bool = False,
        italic: bool = False,
        font_size: str = "14pt",
        font_color: str = "000000",
        border_color: str = "000000",
        background_color: str = "ffffff",
    ) -> DictionaryObject:
        font_str = "font: "
        if bold is True:
            font_str = font_str + "bold "
        if italic is True:
            font_str = font_str + "italic "
        font_str = font_str + font + " " + font_size
        font_str = font_str + ";text-align:left;color:#" + font_color

        bg_color_str = ""
        for st in hex_to_rgb(border_color):
            bg_color_str = bg_color_str + str(st) + " "
        bg_color_str = bg_color_str + "rg"

        free_text = DictionaryObject()
        free_text.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/FreeText"),
                NameObject("/Rect"): RectangleObject(rect),
                NameObject("/Contents"): TextStringObject(text),
                NameObject("/DS"): TextStringObject(font_str),
                NameObject("/DA"): TextStringObject(bg_color_str),
                NameObject("/C"): ArrayObject(
                    [FloatObject(n) for n in hex_to_rgb(background_color)]
                ),
            }
        )
        return free_text

    @staticmethod
    def line(
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        rect: Union[RectangleObject, Tuple[float, float, float, float]],
        text: str = "",
        title_bar: str = "",
    ) -> DictionaryObject:
        line_obj = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Line"),
                NameObject("/Rect"): RectangleObject(rect),
                NameObject("/T"): TextStringObject(title_bar),
                NameObject("/L"): ArrayObject(
                    [
                        FloatObject(p1[0]),
                        FloatObject(p1[1]),
                        FloatObject(p2[0]),
                        FloatObject(p2[1]),
                    ]
                ),
                NameObject("/LE"): ArrayObject(
                    [
                        NameObject(None),
                        NameObject(None),
                    ]
                ),
                NameObject("/IC"): ArrayObject(
                    [
                        FloatObject(0.5),
                        FloatObject(0.5),
                        FloatObject(0.5),
                    ]
                ),
                NameObject("/Contents"): TextStringObject(text),
            }
        )
        return line_obj

    @staticmethod
    def rectangle(
        rect: Union[RectangleObject, Tuple[float, float, float, float]],
        interiour_color: Optional[str] = None,
    ) -> DictionaryObject:
        square_obj = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Square"),
                NameObject("/Rect"): RectangleObject(rect),
            }
        )

        if interiour_color:
            square_obj[NameObject("/IC")] = ArrayObject(
                [FloatObject(n) for n in hex_to_rgb(interiour_color)]
            )

        return square_obj

    @staticmethod
    def link(
        rect: Union[RectangleObject, Tuple[float, float, float, float]],
        border: Optional[ArrayObject] = None,
        url: Optional[str] = None,
        target_page_index: Optional[int] = None,
        fit: Fit = DEFAULT_FIT,
    ) -> DictionaryObject:
        from ._types import BorderArrayType

        is_external = url is not None
        is_internal = target_page_index is not None
        if not is_external and not is_internal:
            raise ValueError(
                "Either 'url' or 'target_page_index' have to be provided. Both were None."
            )
        if is_external and is_internal:
            raise ValueError(
                f"Either 'url' or 'target_page_index' have to be provided. url={url}, target_page_index={target_page_index}"
            )

        border_arr: BorderArrayType
        if border is not None:
            border_arr = [NameObject(n) for n in border[:3]]
            if len(border) == 4:
                dash_pattern = ArrayObject([NameObject(n) for n in border[3]])
                border_arr.append(dash_pattern)
        else:
            border_arr = [NumberObject(0)] * 3

        link_obj = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): RectangleObject(rect),
                NameObject("/Border"): ArrayObject(border_arr),
            }
        )
        if is_external:
            link_obj[NameObject("/A")] = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/Type"): NameObject("/Action"),
                    NameObject("/URI"): TextStringObject(url),
                }
            )
        if is_internal:
            dest_deferred = DictionaryObject(
                {
                    "target_page_index": NumberObject(target_page_index),
                    "fit": NameObject(fit.fit_type),
                    "fit_args": fit.fit_args,
                }
            )
            link_obj[NameObject("/Dest")] = dest_deferred
        return link_obj
