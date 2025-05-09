import warnings
from binascii import unhexlify
from math import ceil
from typing import Any, Dict, List, Tuple, Union, cast

from ._codecs import adobe_glyphs, charset_encoding
from ._utils import logger_warning
from .errors import PdfReadWarning
from .generic import DecodedStreamObject, DictionaryObject, StreamObject

def build_char_map(
    font_name: str, space_width: float, obj: DictionaryObject
) -> Tuple[
    str, float, Union[str, Dict[int, str]], Dict, DictionaryObject
]:

    ft: DictionaryObject = obj["/Resources"]["/Font"][font_name] 
    font_type: str = cast(str, ft["/Subtype"])

    space_code = 32
    encoding, space_code = parse_encoding(ft, space_code)
    map_dict, space_code, int_entry = parse_to_unicode(ft, space_code)
    if encoding == "":
        if -1 not in map_dict or map_dict[-1] == 1:
            encoding = "charmap"
        else:
            encoding = "utf-16-be"
    elif isinstance(encoding, dict):
        for x in int_entry:
            if x <= 255:
                encoding[x] = chr(x)
    try:
        space_width = _default_fonts_space_width[cast(str, ft["/BaseFont"])]
    except Exception:
        pass
    if isinstance(space_code, str):
        try:
            sp = space_code.encode("charmap")[0]
        except Exception:
            sp = space_code.encode("utf-16-be")
            sp = sp[0] + 256 * sp[1]
    else:
        sp = space_code
    sp_width = compute_space_width(ft, sp, space_width)

    return (
        font_type,
        float(sp_width / 2),
        encoding,
        map_dict,
        ft,
    )

unknown_char_map: Tuple[str, float, Union[str, Dict[int, str]], Dict[Any, Any]] = (
    "Unknown",
    9999,
    dict(zip(range(256), ["�"] * 256)),
    {},
)


_predefined_cmap: Dict[str, str] = {
    "/Identity-H": "utf-16-be",
    "/Identity-V": "utf-16-be",
    "/GB-EUC-H": "gbk",  
    "/GB-EUC-V": "gbk",  
    "/GBpc-EUC-H": "gb2312",  
    "/GBpc-EUC-V": "gb2312",  
}

_default_fonts_space_width: Dict[str, int] = {
    "/Courrier": 600,
    "/Courier-Bold": 600,
    "/Courier-BoldOblique": 600,
    "/Courier-Oblique": 600,
    "/Helvetica": 278,
    "/Helvetica-Bold": 278,
    "/Helvetica-BoldOblique": 278,
    "/Helvetica-Oblique": 278,
    "/Helvetica-Narrow": 228,
    "/Helvetica-NarrowBold": 228,
    "/Helvetica-NarrowBoldOblique": 228,
    "/Helvetica-NarrowOblique": 228,
    "/Times-Roman": 250,
    "/Times-Bold": 250,
    "/Times-BoldItalic": 250,
    "/Times-Italic": 250,
    "/Symbol": 250,
    "/ZapfDingbats": 278,
}


def parse_encoding(
    ft: DictionaryObject, space_code: int
) -> Tuple[Union[str, Dict[int, str]], int]:
    encoding: Union[str, List[str], Dict[int, str]] = []
    if "/Encoding" not in ft:
        try:
            if "/BaseFont" in ft and cast(str, ft["/BaseFont"]) in charset_encoding:
                encoding = dict(
                    zip(range(256), charset_encoding[cast(str, ft["/BaseFont"])])
                )
            else:
                encoding = "charmap"
            return encoding, _default_fonts_space_width[cast(str, ft["/BaseFont"])]
        except Exception:
            if cast(str, ft["/Subtype"]) == "/Type1":
                return "charmap", space_code
            else:
                return "", space_code
    enc: Union(str, DictionaryObject) = ft["/Encoding"].get_object()  # type: ignore
    if isinstance(enc, str):
        try:
            if enc in charset_encoding:
                encoding = charset_encoding[enc].copy()
            elif enc in _predefined_cmap:
                encoding = _predefined_cmap[enc]
            else:
                raise Exception("not found")
        except Exception:
            warnings.warn(
                f"Advanced encoding {enc} not implemented yet",
                PdfReadWarning,
            )
            encoding = enc
    elif isinstance(enc, DictionaryObject) and "/BaseEncoding" in enc:
        try:
            encoding = charset_encoding[cast(str, enc["/BaseEncoding"])].copy()
        except Exception:
            warnings.warn(
                f"Advanced encoding {encoding} not implemented yet",
                PdfReadWarning,
            )
            encoding = charset_encoding["/StandardCoding"].copy()
    else:
        encoding = charset_encoding["/StandardCoding"].copy()
    if "/Differences" in enc:
        x: int = 0
        o: Union[int, str]
        for o in cast(DictionaryObject, cast(DictionaryObject, enc)["/Differences"]):
            if isinstance(o, int):
                x = o
            else:
                try:
                    encoding[x] = adobe_glyphs[o]
                except Exception:
                    encoding[x] = o
                    if o == " ":
                        space_code = x
                x += 1
    if isinstance(encoding, list):
        encoding = dict(zip(range(256), encoding))
    return encoding, space_code


def parse_to_unicode(
    ft: DictionaryObject, space_code: int
) -> Tuple[Dict[Any, Any], int, List[int]]:
    map_dict: Dict[Any, Any] = {}
    int_entry: List[int] = []

    if "/ToUnicode" not in ft:
        return {}, space_code, []
    process_rg: bool = False
    process_char: bool = False
    multiline_rg: Union[
        None, Tuple[int, int]
    ] = None
    cm = prepare_cm(ft)
    for l in cm.split(b"\n"):
        process_rg, process_char, multiline_rg = process_cm_line(
            l.strip(b" "), process_rg, process_char, multiline_rg, map_dict, int_entry
        )

    for a, value in map_dict.items():
        if value == " ":
            space_code = a
    return map_dict, space_code, int_entry


def prepare_cm(ft: DictionaryObject) -> bytes:
    tu = ft["/ToUnicode"]
    cm: bytes
    if isinstance(tu, StreamObject):
        cm = cast(DecodedStreamObject, ft["/ToUnicode"]).get_data()
    elif isinstance(tu, str) and tu.startswith("/Identity"):
        cm = b"beginbfrange\n<0000> <0001> <0000>\nendbfrange"
    if isinstance(cm, str):
        cm = cm.encode()
    cm = (
        cm.strip()
        .replace(b"beginbfchar", b"\nbeginbfchar\n")
        .replace(b"endbfchar", b"\nendbfchar\n")
        .replace(b"beginbfrange", b"\nbeginbfrange\n")
        .replace(b"endbfrange", b"\nendbfrange\n")
        .replace(b"<<", b"\n{\n")
        .replace(b">>", b"\n}\n")
    )
    ll = cm.split(b"<")
    for i in range(len(ll)):
        j = ll[i].find(b">")
        if j >= 0:
            if j == 0:
                content = b"."
            else:
                content = ll[i][:j].replace(b" ", b"")
            ll[i] = content + b" " + ll[i][j + 1 :]
    cm = (
        (b" ".join(ll))
        .replace(b"[", b" [ ")
        .replace(b"]", b" ]\n ")
        .replace(b"\r", b"\n")
    )
    return cm


def process_cm_line(
    l: bytes,
    process_rg: bool,
    process_char: bool,
    multiline_rg: Union[None, Tuple[int, int]],
    map_dict: Dict[Any, Any],
    int_entry: List[int],
) -> Tuple[bool, bool, Union[None, Tuple[int, int]]]:
    if l in (b"", b" ") or l[0] == 37:
        return process_rg, process_char, multiline_rg
    if b"beginbfrange" in l:
        process_rg = True
    elif b"endbfrange" in l:
        process_rg = False
    elif b"beginbfchar" in l:
        process_char = True
    elif b"endbfchar" in l:
        process_char = False
    elif process_rg:
        multiline_rg = parse_bfrange(l, map_dict, int_entry, multiline_rg)
    elif process_char:
        parse_bfchar(l, map_dict, int_entry)
    return process_rg, process_char, multiline_rg


def parse_bfrange(
    l: bytes,
    map_dict: Dict[Any, Any],
    int_entry: List[int],
    multiline_rg: Union[None, Tuple[int, int]],
) -> Union[None, Tuple[int, int]]:
    lst = [x for x in l.split(b" ") if x]
    closure_found = False
    nbi = max(len(lst[0]), len(lst[1]))
    map_dict[-1] = ceil(nbi / 2)
    fmt = b"%%0%dX" % (map_dict[-1] * 2)
    if multiline_rg is not None:
        a = multiline_rg[0]
        b = multiline_rg[1]
        for sq in lst[1:]:
            if sq == b"]":
                closure_found = True
                break
            map_dict[
                unhexlify(fmt % a).decode(
                    "charmap" if map_dict[-1] == 1 else "utf-16-be",
                    "surrogatepass",
                )
            ] = unhexlify(sq).decode("utf-16-be", "surrogatepass")
            int_entry.append(a)
            a += 1
    else:
        a = int(lst[0], 16)
        b = int(lst[1], 16)
        if lst[2] == b"[":
            for sq in lst[3:]:
                if sq == b"]":
                    closure_found = True
                    break
                map_dict[
                    unhexlify(fmt % a).decode(
                        "charmap" if map_dict[-1] == 1 else "utf-16-be",
                        "surrogatepass",
                    )
                ] = unhexlify(sq).decode("utf-16-be", "surrogatepass")
                int_entry.append(a)
                a += 1
        else:
            c = int(lst[2], 16)
            fmt2 = b"%%0%dX" % max(4, len(lst[2]))
            closure_found = True
            while a <= b:
                map_dict[
                    unhexlify(fmt % a).decode(
                        "charmap" if map_dict[-1] == 1 else "utf-16-be",
                        "surrogatepass",
                    )
                ] = unhexlify(fmt2 % c).decode("utf-16-be", "surrogatepass")
                int_entry.append(a)
                a += 1
                c += 1
    return None if closure_found else (a, b)


def parse_bfchar(l: bytes, map_dict: Dict[Any, Any], int_entry: List[int]) -> None:
    lst = [x for x in l.split(b" ") if x]
    map_dict[-1] = len(lst[0]) // 2
    while len(lst) > 1:
        map_to = ""
        if lst[1] != b".":
            map_to = unhexlify(lst[1]).decode(
                "charmap" if len(lst[1]) < 4 else "utf-16-be", "surrogatepass"
            )
        map_dict[
            unhexlify(lst[0]).decode(
                "charmap" if map_dict[-1] == 1 else "utf-16-be", "surrogatepass"
            )
        ] = map_to
        int_entry.append(int(lst[0], 16))
        lst = lst[2:]


def compute_space_width(
    ft: DictionaryObject, space_code: int, space_width: float
) -> float:
    sp_width: float = space_width * 2
    w = []
    w1 = {}
    st: int = 0
    if "/DescendantFonts" in ft:
        ft1 = ft["/DescendantFonts"][0].get_object()
        try:
            w1[-1] = cast(float, ft1["/DW"])
        except Exception:
            w1[-1] = 1000.0
        if "/W" in ft1:
            w = list(ft1["/W"])
        else:
            w = []
        while len(w) > 0:
            st = w[0]
            second = w[1]
            if isinstance(second, int):
                for x in range(st, second):
                    w1[x] = w[2]
                w = w[3:]
            elif isinstance(second, list):
                for y in second:
                    w1[st] = y
                    st += 1
                w = w[2:]
            else:
                logger_warning(
                    "unknown widths : \n" + (ft1["/W"]).__repr__(),
                    __name__,
                )
                break
        try:
            sp_width = w1[space_code]
        except Exception:
            sp_width = (
                w1[-1] / 2.0
            )
    elif "/Widths" in ft:
        w = list(ft["/Widths"])
        try:
            st = cast(int, ft["/FirstChar"])
            en: int = cast(int, ft["/LastChar"])
            if st > space_code or en < space_code:
                raise Exception("Not in range")
            if w[space_code - st] == 0:
                raise Exception("null width")
            sp_width = w[space_code - st]
        except Exception:
            if "/FontDescriptor" in ft and "/MissingWidth" in cast(
                DictionaryObject, ft["/FontDescriptor"]
            ):
                sp_width = ft["/FontDescriptor"]["/MissingWidth"]
            else:
                m = 0
                cpt = 0
                for x in w:
                    if x > 0:
                        m += x
                        cpt += 1
                sp_width = m / max(1, cpt) / 2
    return sp_width
