from enum import IntFlag
from typing import Dict, Tuple


class Core:
    OUTLINES = "/Outlines"
    THREADS = "/Threads"
    PAGE = "/Page"
    PAGES = "/Pages"
    CATALOG = "/Catalog"


class TrailerKeys:
    ROOT = "/Root"
    ENCRYPT = "/Encrypt"
    ID = "/ID"
    INFO = "/Info"
    SIZE = "/Size"


class CatalogAttributes:
    NAMES = "/Names"
    DESTS = "/Dests"


class EncryptionDictAttributes:
    R = "/R"
    O = "/O"
    U = "/U"
    P = "/P"
    ENCRYPT_METADATA = "/EncryptMetadata"


class UserAccessPermissions(IntFlag):
    R1 = 1
    R2 = 2
    PRINT = 4
    MODIFY = 8
    EXTRACT = 16
    ADD_OR_MODIFY = 32
    R7 = 64
    R8 = 128
    FILL_FORM_FIELDS = 256
    EXTRACT_TEXT_AND_GRAPHICS = 512
    ASSEMBLE_DOC = 1024
    PRINT_TO_REPRESENTATION = 2048
    R13 = 2**12
    R14 = 2**13
    R15 = 2**14
    R16 = 2**15
    R17 = 2**16
    R18 = 2**17
    R19 = 2**18
    R20 = 2**19
    R21 = 2**20
    R22 = 2**21
    R23 = 2**22
    R24 = 2**23
    R25 = 2**24
    R26 = 2**25
    R27 = 2**26
    R28 = 2**27
    R29 = 2**28
    R30 = 2**29
    R31 = 2**30
    R32 = 2**31


class Ressources:
    EXT_G_STATE = "/ExtGState"
    COLOR_SPACE = "/ColorSpace"
    PATTERN = "/Pattern"
    SHADING = "/Shading"
    XOBJECT = "/XObject"
    FONT = "/Font"
    PROC_SET = "/ProcSet"
    PROPERTIES = "/Properties"


class PagesAttributes:
    TYPE = "/Type"
    KIDS = "/Kids"
    COUNT = "/Count"
    PARENT = "/Parent"


class PageAttributes:
    TYPE = "/Type"
    PARENT = "/Parent"
    LAST_MODIFIED = "/LastModified"
    RESOURCES = "/Resources"
    MEDIABOX = "/MediaBox"
    CROPBOX = "/CropBox"
    BLEEDBOX = "/BleedBox"
    TRIMBOX = "/TrimBox"
    ARTBOX = "/ArtBox"
    BOX_COLOR_INFO = "/BoxColorInfo"
    CONTENTS = "/Contents"
    ROTATE = "/Rotate"
    GROUP = "/Group"
    THUMB = "/Thumb"
    B = "/B"
    DUR = "/Dur"
    TRANS = "/Trans"
    ANNOTS = "/Annots"
    AA = "/AA"
    METADATA = "/Metadata"
    PIECE_INFO = "/PieceInfo"
    STRUCT_PARENTS = "/StructParents"
    ID = "/ID"
    PZ = "/PZ"
    TABS = "/Tabs"
    TEMPLATE_INSTANTIATED = "/TemplateInstantiated"
    PRES_STEPS = "/PresSteps"
    USER_UNIT = "/UserUnit"
    VP = "/VP"


class FileSpecificationDictionaryEntries:
    Type = "/Type"
    FS = "/FS"
    F = "/F"
    EF = "/EF"


class StreamAttributes:
    LENGTH = "/Length"
    FILTER = "/Filter"
    DECODE_PARMS = "/DecodeParms"


class FilterTypes:
    ASCII_HEX_DECODE = "/ASCIIHexDecode"
    ASCII_85_DECODE = "/ASCII85Decode"
    LZW_DECODE = "/LZWDecode"
    FLATE_DECODE = "/FlateDecode"
    RUN_LENGTH_DECODE = "/RunLengthDecode"
    CCITT_FAX_DECODE = "/CCITTFaxDecode"
    DCT_DECODE = "/DCTDecode"


class FilterTypeAbbreviations:
    AHx = "/AHx"
    A85 = "/A85"
    LZW = "/LZW"
    FL = "/Fl"
    RL = "/RL"
    CCF = "/CCF"
    DCT = "/DCT"


class LzwFilterParameters:
    PREDICTOR = "/Predictor"
    COLUMNS = "/Columns"
    COLORS = "/Colors"
    BITS_PER_COMPONENT = "/BitsPerComponent"
    EARLY_CHANGE = "/EarlyChange"


class CcittFaxDecodeParameters:
    K = "/K"
    END_OF_LINE = "/EndOfLine"
    ENCODED_BYTE_ALIGN = "/EncodedByteAlign"
    COLUMNS = "/Columns"
    ROWS = "/Rows"
    END_OF_BLOCK = "/EndOfBlock"
    BLACK_IS_1 = "/BlackIs1"
    DAMAGED_ROWS_BEFORE_ERROR = "/DamagedRowsBeforeError"


class ImageAttributes:
    TYPE = "/Type"
    SUBTYPE = "/Subtype"
    NAME = "/Name"
    WIDTH = "/Width"
    HEIGHT = "/Height"
    BITS_PER_COMPONENT = "/BitsPerComponent"
    COLOR_SPACE = "/ColorSpace"
    DECODE = "/Decode"
    INTERPOLATE = "/Interpolate"
    IMAGE_MASK = "/ImageMask"


class ColorSpaces:
    DEVICE_RGB = "/DeviceRGB"
    DEVICE_CMYK = "/DeviceCMYK"
    DEVICE_GRAY = "/DeviceGray"


class TypArguments:
    LEFT = "/Left"
    RIGHT = "/Right"
    BOTTOM = "/Bottom"
    TOP = "/Top"


class TypFitArguments:
    FIT = "/Fit"
    FIT_V = "/FitV"
    FIT_BV = "/FitBV"
    FIT_B = "/FitB"
    FIT_H = "/FitH"
    FIT_BH = "/FitBH"
    FIT_R = "/FitR"
    XYZ = "/XYZ"


class GoToActionArguments:
    S = "/S"
    D = "/D"


class AnnotationDictionaryAttributes:
    Type = "/Type"
    Subtype = "/Subtype"
    Rect = "/Rect"
    Contents = "/Contents"
    P = "/P"
    NM = "/NM"
    M = "/M"
    F = "/F"
    AP = "/AP"
    AS = "/AS"
    Border = "/Border"
    C = "/C"
    StructParent = "/StructParent"
    OC = "/OC"


class InteractiveFormDictEntries:
    Fields = "/Fields"
    NeedAppearances = "/NeedAppearances"
    SigFlags = "/SigFlags"
    CO = "/CO"
    DR = "/DR"
    DA = "/DA"
    Q = "/Q"
    XFA = "/XFA"


class FieldDictionaryAttributes:
    FT = "/FT"
    Parent = "/Parent"
    Kids = "/Kids"
    T = "/T"
    TU = "/TU"
    TM = "/TM"
    Ff = "/Ff"
    V = "/V"
    DV = "/DV"
    AA = "/AA"

    @classmethod
    def attributes(cls) -> Tuple[str, ...]:
        return (
            cls.TM,
            cls.T,
            cls.FT,
            cls.Parent,
            cls.TU,
            cls.Ff,
            cls.V,
            cls.DV,
            cls.Kids,
            cls.AA,
        )

    @classmethod
    def attributes_dict(cls) -> Dict[str, str]:
        return {
            cls.FT: "Field Type",
            cls.Parent: "Parent",
            cls.T: "Field Name",
            cls.TU: "Alternate Field Name",
            cls.TM: "Mapping Name",
            cls.Ff: "Field Flags",
            cls.V: "Value",
            cls.DV: "Default Value",
        }


class CheckboxRadioButtonAttributes:
    Opt = "/Opt"

    @classmethod
    def attributes(cls) -> Tuple[str, ...]:
        return (cls.Opt,)

    @classmethod
    def attributes_dict(cls) -> Dict[str, str]:
        return {
            cls.Opt: "Options",
        }


class FieldFlag(IntFlag):
    READ_ONLY = 1
    REQUIRED = 2
    NO_EXPORT = 4


class DocumentInformationAttributes:
    TITLE = "/Title"
    AUTHOR = "/Author"
    SUBJECT = "/Subject"
    KEYWORDS = "/Keywords"
    CREATOR = "/Creator"
    PRODUCER = "/Producer"
    CREATION_DATE = "/CreationDate"
    MOD_DATE = "/ModDate"
    TRAPPED = "/Trapped"


class PageLayouts:
    SINGLE_PAGE = "/SinglePage"
    ONE_COLUMN = "/OneColumn"
    TWO_COLUMN_LEFT = "/TwoColumnLeft"
    TWO_COLUMN_RIGHT = "/TwoColumnRight"


class GraphicsStateParameters:
    TYPE = "/Type"
    LW = "/LW"
    # TODO: Many more!
    FONT = "/Font"
    S_MASK = "/SMask"


class CatalogDictionary:
    TYPE = "/Type"
    VERSION = "/Version"
    PAGES = "/Pages"
    PAGE_LABELS = "/PageLabels"
    NAMES = "/Names"
    DESTS = "/Dests"
    VIEWER_PREFERENCES = "/ViewerPreferences"
    PAGE_LAYOUT = "/PageLayout"
    PAGE_MODE = "/PageMode"
    OUTLINES = "/Outlines"
    THREADS = "/Threads"
    OPEN_ACTION = "/OpenAction"
    AA = "/AA"
    URI = "/URI"
    ACRO_FORM = "/AcroForm"
    METADATA = "/Metadata"
    STRUCT_TREE_ROOT = "/StructTreeRoot"
    MARK_INFO = "/MarkInfo"
    LANG = "/Lang"
    SPIDER_INFO = "/SpiderInfo"
    OUTPUT_INTENTS = "/OutputIntents"
    PIECE_INFO = "/PieceInfo"
    OC_PROPERTIES = "/OCProperties"
    PERMS = "/Perms"
    LEGAL = "/Legal"
    REQUIREMENTS = "/Requirements"
    COLLECTION = "/Collection"
    NEEDS_RENDERING = "/NeedsRendering"


class OutlineFontFlag(IntFlag):
    italic = 1
    bold = 2


PDF_KEYS = (
    AnnotationDictionaryAttributes,
    CatalogAttributes,
    CatalogDictionary,
    CcittFaxDecodeParameters,
    CheckboxRadioButtonAttributes,
    ColorSpaces,
    Core,
    DocumentInformationAttributes,
    EncryptionDictAttributes,
    FieldDictionaryAttributes,
    FilterTypeAbbreviations,
    FilterTypes,
    GoToActionArguments,
    GraphicsStateParameters,
    ImageAttributes,
    FileSpecificationDictionaryEntries,
    LzwFilterParameters,
    PageAttributes,
    PageLayouts,
    PagesAttributes,
    Ressources,
    StreamAttributes,
    TrailerKeys,
    TypArguments,
    TypFitArguments,
)
