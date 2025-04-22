import sys
import os
import zlib
import argparse
from PIL import Image, TiffImagePlugin, GifImagePlugin, ImageCms
if hasattr(GifImagePlugin, "LoadingStrategy"):
    GifImagePlugin.LOADING_STRATEGY = (
        GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY
    )
from PIL.ExifTags import TAGS
from datetime import datetime, timezone
import jp2
from enum import Enum
from io import BytesIO
import logging
import struct
import platform
import hashlib
from itertools import chain
import re
import io

logger = logging.getLogger(__name__)

have_pdfrw = True
try:
    import pdfrw
except ImportError:
    have_pdfrw = False

have_pikepdf = True
try:
    import pikepdf
except ImportError:
    have_pikepdf = False

__version__ = "0.5.1"
default_dpi = 96.0
papersizes = {
    "letter": "8.5inx11in",
    "a0": "841mmx1189mm",
    "a1": "594mmx841mm",
    "a2": "420mmx594mm",
    "a3": "297mmx420mm",
    "a4": "210mmx297mm",
    "a5": "148mmx210mm",
    "a6": "105mmx148mm",
    "b0": "1000mmx1414mm",
    "b1": "707mmx1000mm",
    "b2": "500mmx707mm",
    "b3": "353mmx500mm",
    "b4": "250mmx353mm",
    "b5": "176mmx250mm",
    "b6": "125mmx176mm",
    "jb0": "1030mmx1456mm",
    "jb1": "728mmx1030mm",
    "jb2": "515mmx728mm",
    "jb3": "364mmx515mm",
    "jb4": "257mmx364mm",
    "jb5": "182mmx257mm",
    "jb6": "128mmx182mm",
    "legal": "8.5inx14in",
    "tabloid": "11inx17in",
}
papernames = {
    "letter": "Letter",
    "a0": "A0",
    "a1": "A1",
    "a2": "A2",
    "a3": "A3",
    "a4": "A4",
    "a5": "A5",
    "a6": "A6",
    "b0": "B0",
    "b1": "B1",
    "b2": "B2",
    "b3": "B3",
    "b4": "B4",
    "b5": "B5",
    "b6": "B6",
    "jb0": "JB0",
    "jb1": "JB1",
    "jb2": "JB2",
    "jb3": "JB3",
    "jb4": "JB4",
    "jb5": "JB5",
    "jb6": "JB6",
    "legal": "Legal",
    "tabloid": "Tabloid",
}

Engine = Enum("Engine", "internal pdfrw pikepdf")

Rotation = Enum("Rotation", "auto none ifvalid 0 90 180 270")

FitMode = Enum("FitMode", "into fill exact shrink enlarge")

PageOrientation = Enum("PageOrientation", "portrait landscape")

Colorspace = Enum("Colorspace", "RGB RGBA L LA 1 CMYK CMYK;I P PA other")

ImageFormat = Enum(
    "ImageFormat", "JPEG JPEG2000 CCITTGroup4 PNG GIF TIFF MPO MIFF other"
)

PageMode = Enum("PageMode", "none outlines thumbs")

PageLayout = Enum(
    "PageLayout",
    "single onecolumn twocolumnright twocolumnleft twopageright twopageleft",
)

Magnification = Enum("Magnification", "fit fith fitbh")

ImgSize = Enum("ImgSize", "abs perc dpi")

Unit = Enum("Unit", "pt cm mm inch")

ImgUnit = Enum("ImgUnit", "pt cm mm inch perc dpi")

TIFFBitRevTable = [
    0x00,
    0x80,
    0x40,
    0xC0,
    0x20,
    0xA0,
    0x60,
    0xE0,
    0x10,
    0x90,
    0x50,
    0xD0,
    0x30,
    0xB0,
    0x70,
    0xF0,
    0x08,
    0x88,
    0x48,
    0xC8,
    0x28,
    0xA8,
    0x68,
    0xE8,
    0x18,
    0x98,
    0x58,
    0xD8,
    0x38,
    0xB8,
    0x78,
    0xF8,
    0x04,
    0x84,
    0x44,
    0xC4,
    0x24,
    0xA4,
    0x64,
    0xE4,
    0x14,
    0x94,
    0x54,
    0xD4,
    0x34,
    0xB4,
    0x74,
    0xF4,
    0x0C,
    0x8C,
    0x4C,
    0xCC,
    0x2C,
    0xAC,
    0x6C,
    0xEC,
    0x1C,
    0x9C,
    0x5C,
    0xDC,
    0x3C,
    0xBC,
    0x7C,
    0xFC,
    0x02,
    0x82,
    0x42,
    0xC2,
    0x22,
    0xA2,
    0x62,
    0xE2,
    0x12,
    0x92,
    0x52,
    0xD2,
    0x32,
    0xB2,
    0x72,
    0xF2,
    0x0A,
    0x8A,
    0x4A,
    0xCA,
    0x2A,
    0xAA,
    0x6A,
    0xEA,
    0x1A,
    0x9A,
    0x5A,
    0xDA,
    0x3A,
    0xBA,
    0x7A,
    0xFA,
    0x06,
    0x86,
    0x46,
    0xC6,
    0x26,
    0xA6,
    0x66,
    0xE6,
    0x16,
    0x96,
    0x56,
    0xD6,
    0x36,
    0xB6,
    0x76,
    0xF6,
    0x0E,
    0x8E,
    0x4E,
    0xCE,
    0x2E,
    0xAE,
    0x6E,
    0xEE,
    0x1E,
    0x9E,
    0x5E,
    0xDE,
    0x3E,
    0xBE,
    0x7E,
    0xFE,
    0x01,
    0x81,
    0x41,
    0xC1,
    0x21,
    0xA1,
    0x61,
    0xE1,
    0x11,
    0x91,
    0x51,
    0xD1,
    0x31,
    0xB1,
    0x71,
    0xF1,
    0x09,
    0x89,
    0x49,
    0xC9,
    0x29,
    0xA9,
    0x69,
    0xE9,
    0x19,
    0x99,
    0x59,
    0xD9,
    0x39,
    0xB9,
    0x79,
    0xF9,
    0x05,
    0x85,
    0x45,
    0xC5,
    0x25,
    0xA5,
    0x65,
    0xE5,
    0x15,
    0x95,
    0x55,
    0xD5,
    0x35,
    0xB5,
    0x75,
    0xF5,
    0x0D,
    0x8D,
    0x4D,
    0xCD,
    0x2D,
    0xAD,
    0x6D,
    0xED,
    0x1D,
    0x9D,
    0x5D,
    0xDD,
    0x3D,
    0xBD,
    0x7D,
    0xFD,
    0x03,
    0x83,
    0x43,
    0xC3,
    0x23,
    0xA3,
    0x63,
    0xE3,
    0x13,
    0x93,
    0x53,
    0xD3,
    0x33,
    0xB3,
    0x73,
    0xF3,
    0x0B,
    0x8B,
    0x4B,
    0xCB,
    0x2B,
    0xAB,
    0x6B,
    0xEB,
    0x1B,
    0x9B,
    0x5B,
    0xDB,
    0x3B,
    0xBB,
    0x7B,
    0xFB,
    0x07,
    0x87,
    0x47,
    0xC7,
    0x27,
    0xA7,
    0x67,
    0xE7,
    0x17,
    0x97,
    0x57,
    0xD7,
    0x37,
    0xB7,
    0x77,
    0xF7,
    0x0F,
    0x8F,
    0x4F,
    0xCF,
    0x2F,
    0xAF,
    0x6F,
    0xEF,
    0x1F,
    0x9F,
    0x5F,
    0xDF,
    0x3F,
    0xBF,
    0x7F,
    0xFF,
]


class NegativeDimensionError(Exception):
    pass


class UnsupportedColorspaceError(Exception):
    pass


class ImageOpenError(Exception):
    pass


class JpegColorspaceError(Exception):
    pass


class PdfTooLargeError(Exception):
    pass


class AlphaChannelError(Exception):
    pass


class ExifOrientationError(Exception):
    pass
class temp_attr:
    def __init__(self, obj, field, value):
        self.obj = obj
        self.field = field
        self.value = value

    def __enter__(self):
        self.exists = False
        if hasattr(self.obj, self.field):
            self.exists = True
            self.old_value = getattr(self.obj, self.field)
        logger.debug(f"setting {self.obj}.{self.field} = {self.value}")
        setattr(self.obj, self.field, self.value)

    def __exit__(self, exctype, excinst, exctb):
        if self.exists:
            setattr(self.obj, self.field, self.old_value)
        else:
            delattr(self.obj, self.field)
def my_convert_load(string):
    return string


def parse(cont, indent=1):
    if type(cont) is dict:
        return (
            b"<<\n"
            + b"\n".join(
                [
                    4 * indent * b" " + k + b" " + parse(v, indent + 1)
                    for k, v in sorted(cont.items())
                ]
            )
            + b"\n"
            + 4 * (indent - 1) * b" "
            + b">>"
        )
    elif type(cont) is int:
        return str(cont).encode()
    elif type(cont) is float:
        if int(cont) == cont:
            return parse(int(cont))
        else:
            return ("%0.4f" % cont).rstrip("0").encode()
    elif isinstance(cont, MyPdfDict):
        if hasattr(cont, "identifier"):
            return ("%d 0 R" % cont.identifier).encode()
        else:
            return parse(cont.content, indent)
    elif type(cont) is str or isinstance(cont, bytes):
        if type(cont) is str and type(cont) is not bytes:
            raise TypeError(
                "parse must be passed a bytes object in py3. Got: %s" % cont
            )
        return cont
    elif isinstance(cont, list):
        return b"[ " + b" ".join([parse(c, indent) for c in cont]) + b" ]"
    else:
        raise TypeError("cannot handle type %s with content %s" % (type(cont), cont))


class MyPdfDict(object):
    def __init__(self, *args, **kw):
        self.content = dict()
        if args:
            if len(args) == 1:
                args = args[0]
            self.content.update(args)
        self.stream = None
        for key, value in kw.items():
            if key == "stream":
                self.stream = value
                self.content[MyPdfName.Length] = len(value)
            elif key == "indirect":
                pass
            else:
                self.content[getattr(MyPdfName, key)] = value

    def tostring(self):
        if self.stream is not None:
            return (
                ("%d 0 obj\n" % self.identifier).encode()
                + parse(self.content)
                + b"\nstream\n"
                + self.stream
                + b"\nendstream\nendobj\n"
            )
        else:
            return (
                ("%d 0 obj\n" % self.identifier).encode()
                + parse(self.content)
                + b"\nendobj\n"
            )

    def __setitem__(self, key, value):
        self.content[key] = value

    def __getitem__(self, key):
        return self.content[key]

    def __contains__(self, key):
        return key in self.content


class MyPdfName:
    def __getattr__(self, name):
        return b"/" + name.encode("ascii")


MyPdfName = MyPdfName()


class MyPdfObject(bytes):
    def __new__(cls, string):
        return bytes.__new__(cls, string.encode("ascii"))


class MyPdfArray(list):
    pass


class MyPdfWriter:
    def __init__(self):
        self.objects = []
        self.pages = MyPdfDict(Type=MyPdfName.Pages, Kids=[], Count=0)
        self.catalog = MyPdfDict(Pages=self.pages, Type=MyPdfName.Catalog)
        self.pagearray = []

    def addobj(self, obj):
        newid = len(self.objects) + 1
        obj.identifier = newid
        self.objects.append(obj)

    def tostream(self, info, stream, version="1.3", ident=None):
        xreftable = list()
        pdfheader = ("%%PDF-%s\n" % version).encode("ascii")
        pdfheader += b"%\xe2\xe3\xcf\xd3\n"
        stream.write(pdfheader)
        pos = len(pdfheader)
        xreftable.append(b"0000000000 65535 f \n")
        for o in self.objects:
            xreftable.append(("%010d 00000 n \n" % pos).encode())
            content = o.tostring()
            stream.write(content)
            pos += len(content)

        xrefoffset = pos
        stream.write(b"xref\n")
        stream.write(("0 %d\n" % len(xreftable)).encode())
        for x in xreftable:
            stream.write(x)
        stream.write(b"trailer\n")
        trailer = {b"/Size": len(xreftable), b"/Info": info, b"/Root": self.catalog}
        if ident is not None:
            md5 = hashlib.md5(ident).hexdigest().encode("ascii")
            trailer[b"/ID"] = b"[<%s><%s>]" % (md5, md5)
        stream.write(parse(trailer) + b"\n")
        stream.write(b"startxref\n")
        stream.write(("%d\n" % xrefoffset).encode())
        stream.write(b"%%EOF\n")
        return

    def addpage(self, page):
        page[b"/Parent"] = self.pages
        self.pagearray.append(page)
        self.pages.content[b"/Kids"].append(page)
        self.pages.content[b"/Count"] += 1
        self.addobj(page)


class MyPdfString:
    @classmethod
    def encode(cls, string, hextype=False):
        if hextype:
            return (
                b"< " + b" ".join(("%06x" % c).encode("ascii") for c in string) + b" >"
            )
        else:
            try:
                string = string.encode("ascii")
            except UnicodeEncodeError:
                string = b"\xfe\xff" + string.encode("utf-16-be")
            string = string.replace(b"\\", b"\\\\")
            string = string.replace(b"(", b"\\(")
            string = string.replace(b")", b"\\)")
            return b"(" + string + b")"


class pdfdoc(object):
    def __init__(
        self,
        engine=Engine.internal,
        version="1.3",
        title=None,
        author=None,
        creator=None,
        producer=None,
        creationdate=None,
        moddate=None,
        subject=None,
        keywords=None,
        nodate=False,
        panes=None,
        initial_page=None,
        magnification=None,
        page_layout=None,
        fit_window=False,
        center_window=False,
        fullscreen=False,
        pdfa=None,
    ):
        if engine is None:
            if have_pikepdf:
                engine = Engine.pikepdf
            elif have_pdfrw:
                engine = Engine.pdfrw
            else:
                engine = Engine.internal

        if engine == Engine.pikepdf:
            PdfWriter = pikepdf.new
            PdfDict = pikepdf.Dictionary
            PdfName = pikepdf.Name
        elif engine == Engine.pdfrw:
            from pdfrw import PdfWriter, PdfDict, PdfName, PdfString
        elif engine == Engine.internal:
            PdfWriter = MyPdfWriter
            PdfDict = MyPdfDict
            PdfName = MyPdfName
            PdfString = MyPdfString
        else:
            raise ValueError("unknown engine: %s" % engine)

        self.writer = PdfWriter()
        if engine != Engine.pikepdf:
            self.writer.docinfo = PdfDict(indirect=True)

        def datetime_to_pdfdate(dt):
            return dt.astimezone(tz=timezone.utc).strftime("%Y%m%d%H%M%SZ")

        for k in ["Title", "Author", "Creator", "Producer", "Subject"]:
            v = locals()[k.lower()]
            if v is None or v == "":
                continue
            if engine != Engine.pikepdf:
                v = PdfString.encode(v)
            self.writer.docinfo[getattr(PdfName, k)] = v

        now = datetime.now().astimezone()
        for k in ["CreationDate", "ModDate"]:
            v = locals()[k.lower()]
            if v is None and nodate:
                continue
            if v is None:
                v = now
            v = ("D:" + datetime_to_pdfdate(v)).encode("ascii")
            if engine == Engine.internal:
                v = b"(" + v + b")"
            self.writer.docinfo[getattr(PdfName, k)] = v
        if keywords is not None:
            if engine == Engine.pikepdf:
                self.writer.docinfo[PdfName.Keywords] = ",".join(keywords)
            else:
                self.writer.docinfo[PdfName.Keywords] = PdfString.encode(
                    ",".join(keywords)
                )

        def datetime_to_xmpdate(dt):
            return dt.astimezone(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self.xmp = b"""<?xpacket begin='\xef\xbb\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='XMP toolkit 2.9.1-13, framework 1.6'>
<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' xmlns:iX='http://ns.adobe.com/iX/1.0/'>
  <rdf:Description rdf:about='' xmlns:pdf='http://ns.adobe.com/pdf/1.3/'%s/>
  <rdf:Description rdf:about='' xmlns:xmp='http://ns.adobe.com/xap/1.0/'>
    %s
    %s
  </rdf:Description>
  <rdf:Description rdf:about='' xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/' pdfaid:part='1' pdfaid:conformance='B'/>
</rdf:RDF>
</x:xmpmeta>

<?xpacket end='w'?>
""" % (
            b" pdf:Producer='%s'" % producer.encode("ascii")
            if producer is not None
            else b"",
            b""
            if creationdate is None and nodate
            else b"<xmp:ModifyDate>%s</xmp:ModifyDate>"
            % datetime_to_xmpdate(now if creationdate is None else creationdate).encode(
                "ascii"
            ),
            b""
            if moddate is None and nodate
            else b"<xmp:CreateDate>%s</xmp:CreateDate>"
            % datetime_to_xmpdate(now if moddate is None else moddate).encode("ascii"),
        )

        if engine != Engine.pikepdf:
            # this is done because pdfrw adds info, catalog and pages as the first
            # three objects in this order
            if engine == Engine.internal:
                self.writer.addobj(self.writer.docinfo)
                self.writer.addobj(self.writer.catalog)
                self.writer.addobj(self.writer.pages)

        self.panes = panes
        self.initial_page = initial_page
        self.magnification = magnification
        self.page_layout = page_layout
        self.fit_window = fit_window
        self.center_window = center_window
        self.fullscreen = fullscreen
        self.engine = engine
        self.output_version = version
        self.pdfa = pdfa

    def add_imagepage(
        self,
        color,
        imgwidthpx,
        imgheightpx,
        imgformat,
        imgdata,
        smaskdata,
        imgwidthpdf,
        imgheightpdf,
        imgxpdf,
        imgypdf,
        pagewidth,
        pageheight,
        userunit=None,
        palette=None,
        inverted=False,
        depth=0,
        rotate=0,
        cropborder=None,
        bleedborder=None,
        trimborder=None,
        artborder=None,
        iccp=None,
    ):
        assert (
            color not in [Colorspace.RGBA, Colorspace.LA]
            or (imgformat == ImageFormat.PNG and smaskdata is not None)
            or imgformat == ImageFormat.JPEG2000
        )

        if self.engine == Engine.pikepdf:
            PdfArray = pikepdf.Array
            PdfDict = pikepdf.Dictionary
            PdfName = pikepdf.Name
        elif self.engine == Engine.pdfrw:
            from pdfrw import PdfDict, PdfName, PdfObject, PdfString
            from pdfrw.py23_diffs import convert_load
        elif self.engine == Engine.internal:
            PdfDict = MyPdfDict
            PdfName = MyPdfName
            PdfObject = MyPdfObject
            PdfString = MyPdfString
            convert_load = my_convert_load
        else:
            raise ValueError("unknown engine: %s" % self.engine)
        TrueObject = True if self.engine == Engine.pikepdf else PdfObject("true")
        FalseObject = False if self.engine == Engine.pikepdf else PdfObject("false")

        if color == Colorspace["1"] or color == Colorspace.L or color == Colorspace.LA:
            colorspace = PdfName.DeviceGray
        elif color == Colorspace.RGB or color == Colorspace.RGBA:
            if color == Colorspace.RGBA and imgformat == ImageFormat.JPEG2000:
                colorspace = None
            else:
                colorspace = PdfName.DeviceRGB
        elif color == Colorspace.CMYK or color == Colorspace["CMYK;I"]:
            colorspace = PdfName.DeviceCMYK
        elif color == Colorspace.P:
            if self.engine == Engine.pdfrw:
                raise Exception(
                    "pdfrw does not support hex strings for "
                    "palette image input, re-run with "
                    "--engine=internal or --engine=pikepdf"
                )
            assert len(palette) % 3 == 0
            colorspace = [
                PdfName.Indexed,
                PdfName.DeviceRGB,
                (len(palette) // 3) - 1,
                bytes(palette)
                if self.engine == Engine.pikepdf
                else PdfString.encode(
                    [
                        int.from_bytes(palette[i : i + 3], "big")
                        for i in range(0, len(palette), 3)
                    ],
                    hextype=True,
                ),
            ]
        else:
            raise UnsupportedColorspaceError("unsupported color space: %s" % color.name)

        if iccp is not None:
            if self.engine == Engine.pikepdf:
                iccpdict = self.writer.make_stream(iccp)
            else:
                iccpdict = PdfDict(stream=convert_load(iccp))
            iccpdict[PdfName.Alternate] = colorspace
            if (
                color == Colorspace["1"]
                or color == Colorspace.L
                or color == Colorspace.LA
            ):
                iccpdict[PdfName.N] = 1
            elif color == Colorspace.RGB or color == Colorspace.RGBA:
                iccpdict[PdfName.N] = 3
            elif color == Colorspace.CMYK or color == Colorspace["CMYK;I"]:
                iccpdict[PdfName.N] = 4
            elif color == Colorspace.P:
                raise Exception("Cannot have Palette images with ICC profile")
            colorspace = [PdfName.ICCBased, iccpdict]
        if imgformat is ImageFormat.JPEG:
            ofilter = PdfName.DCTDecode
        elif imgformat is ImageFormat.JPEG2000:
            ofilter = PdfName.JPXDecode
            self.output_version = "1.5"
        elif imgformat is ImageFormat.CCITTGroup4:
            ofilter = [PdfName.CCITTFaxDecode]
        else:
            ofilter = PdfName.FlateDecode

        if self.engine == Engine.pikepdf:
            image = self.writer.make_stream(imgdata)
        else:
            image = PdfDict(stream=convert_load(imgdata))

        image[PdfName.Type] = PdfName.XObject
        image[PdfName.Subtype] = PdfName.Image
        image[PdfName.Filter] = ofilter
        image[PdfName.Width] = imgwidthpx
        image[PdfName.Height] = imgheightpx
        if colorspace is not None:
            image[PdfName.ColorSpace] = colorspace
        image[PdfName.BitsPerComponent] = depth

        smask = None

        if color == Colorspace["CMYK;I"]:
            image[PdfName.Decode] = [1, 0, 1, 0, 1, 0, 1, 0]

        if imgformat is ImageFormat.CCITTGroup4:
            decodeparms = PdfDict()
            decodeparms[PdfName.K] = -1
            if inverted:
                decodeparms[PdfName.BlackIs1] = FalseObject
            else:
                decodeparms[PdfName.BlackIs1] = TrueObject
            decodeparms[PdfName.Columns] = imgwidthpx
            decodeparms[PdfName.Rows] = imgheightpx
            image[PdfName.DecodeParms] = [decodeparms]
        elif imgformat is ImageFormat.PNG:
            if smaskdata is not None:
                if self.engine == Engine.pikepdf:
                    smask = self.writer.make_stream(smaskdata)
                else:
                    smask = PdfDict(stream=convert_load(smaskdata))
                smask[PdfName.Type] = PdfName.XObject
                smask[PdfName.Subtype] = PdfName.Image
                smask[PdfName.Filter] = PdfName.FlateDecode
                smask[PdfName.Width] = imgwidthpx
                smask[PdfName.Height] = imgheightpx
                smask[PdfName.ColorSpace] = PdfName.DeviceGray
                smask[PdfName.BitsPerComponent] = depth

                decodeparms = PdfDict()
                decodeparms[PdfName.Predictor] = 15
                decodeparms[PdfName.Colors] = 1
                decodeparms[PdfName.Columns] = imgwidthpx
                decodeparms[PdfName.BitsPerComponent] = depth
                smask[PdfName.DecodeParms] = decodeparms

                image[PdfName.SMask] = smask
                if self.output_version < "1.4":
                    self.output_version = "1.4"

            decodeparms = PdfDict()
            decodeparms[PdfName.Predictor] = 15
            if color in [Colorspace.P, Colorspace["1"], Colorspace.L, Colorspace.LA]:
                decodeparms[PdfName.Colors] = 1
            else:
                decodeparms[PdfName.Colors] = 3
            decodeparms[PdfName.Columns] = imgwidthpx
            decodeparms[PdfName.BitsPerComponent] = depth
            image[PdfName.DecodeParms] = decodeparms

        text = (
            "q\n%0.4f 0 0 %0.4f %0.4f %0.4f cm\n/Im0 Do\nQ"
            % (imgwidthpdf, imgheightpdf, imgxpdf, imgypdf)
        ).encode("ascii")

        if self.engine == Engine.pikepdf:
            content = self.writer.make_stream(text)
        else:
            content = PdfDict(stream=convert_load(text))
        resources = PdfDict(XObject=PdfDict(Im0=image))

        if self.engine == Engine.pikepdf:
            page = self.writer.add_blank_page(page_size=(pagewidth, pageheight))
        else:
            page = PdfDict(indirect=True)
            page[PdfName.Type] = PdfName.Page
            page[PdfName.MediaBox] = [0, 0, pagewidth, pageheight]
        if cropborder is not None:
            page[PdfName.CropBox] = [
                cropborder[1],
                cropborder[0],
                pagewidth - cropborder[1],
                pageheight - cropborder[0],
            ]
        if bleedborder is None:
            if PdfName.CropBox in page:
                page[PdfName.BleedBox] = page[PdfName.CropBox]
        else:
            page[PdfName.BleedBox] = [
                bleedborder[1],
                bleedborder[0],
                pagewidth - bleedborder[1],
                pageheight - bleedborder[0],
            ]
        if trimborder is None:
            if PdfName.CropBox in page:
                page[PdfName.TrimBox] = page[PdfName.CropBox]
        else:
            page[PdfName.TrimBox] = [
                trimborder[1],
                trimborder[0],
                pagewidth - trimborder[1],
                pageheight - trimborder[0],
            ]
        if artborder is None:
            if PdfName.CropBox in page:
                page[PdfName.ArtBox] = page[PdfName.CropBox]
        else:
            page[PdfName.ArtBox] = [
                artborder[1],
                artborder[0],
                pagewidth - artborder[1],
                pageheight - artborder[0],
            ]
        page[PdfName.Resources] = resources
        page[PdfName.Contents] = content
        if rotate != 0:
            page[PdfName.Rotate] = rotate
        if userunit is not None:
            if self.output_version < "1.6":
                self.output_version = "1.6"
            page[PdfName.UserUnit] = userunit

        if self.engine != Engine.pikepdf:
            self.writer.addpage(page)

            if self.engine == Engine.internal:
                self.writer.addobj(content)
                self.writer.addobj(image)
                if smask is not None:
                    self.writer.addobj(smask)
                if iccp is not None:
                    self.writer.addobj(iccpdict)

    def tostring(self):
        stream = BytesIO()
        self.tostream(stream)
        return stream.getvalue()

    def tostream(self, outputstream):
        if self.engine == Engine.pikepdf:
            PdfArray = pikepdf.Array
            PdfDict = pikepdf.Dictionary
            PdfName = pikepdf.Name
        elif self.engine == Engine.pdfrw:
            from pdfrw import PdfDict, PdfName, PdfArray, PdfObject
            from pdfrw.py23_diffs import convert_load
        elif self.engine == Engine.internal:
            PdfDict = MyPdfDict
            PdfName = MyPdfName
            PdfObject = MyPdfObject
            PdfArray = MyPdfArray
            convert_load = my_convert_load
        else:
            raise ValueError("unknown engine: %s" % self.engine)
        NullObject = None if self.engine == Engine.pikepdf else PdfObject("null")
        TrueObject = True if self.engine == Engine.pikepdf else PdfObject("true")

        if self.engine == Engine.pikepdf:
            catalog = self.writer.Root
        elif self.engine == Engine.pdfrw:
            catalog = self.writer.trailer.Root
        elif self.engine == Engine.internal:
            catalog = self.writer.catalog
        else:
            raise ValueError("unknown engine: %s" % self.engine)

        if (
            self.fullscreen
            or self.fit_window
            or self.center_window
            or self.panes is not None
        ):
            catalog[PdfName.ViewerPreferences] = PdfDict()

        if self.fullscreen:
            catalog[PdfName.ViewerPreferences][
                PdfName.NonFullScreenPageMode
            ] = PdfName.UseNone

        if self.panes == PageMode.thumbs:
            catalog[PdfName.ViewerPreferences][
                PdfName.NonFullScreenPageMode
            ] = PdfName.UseThumbs
            catalog[PdfName.PageMode] = PdfName.UseThumbs
        elif self.panes == PageMode.outlines:
            catalog[PdfName.ViewerPreferences][
                PdfName.NonFullScreenPageMode
            ] = PdfName.UseOutlines
            catalog[PdfName.PageMode] = PdfName.UseOutlines
        elif self.panes in [PageMode.none, None]:
            pass
        else:
            raise ValueError("unknown page mode: %s" % self.panes)

        if self.fit_window:
            catalog[PdfName.ViewerPreferences][PdfName.FitWindow] = TrueObject

        if self.center_window:
            catalog[PdfName.ViewerPreferences][PdfName.CenterWindow] = TrueObject

        if self.fullscreen:
            catalog[PdfName.PageMode] = PdfName.FullScreen
        if self.engine == Engine.pikepdf:
            initial_page = self.writer.pages[0]
        else:
            initial_page = self.writer.pagearray[0]
        if self.initial_page is not None:
            if self.engine == Engine.pikepdf:
                initial_page = self.writer.pages[self.initial_page - 1]
            else:
                initial_page = self.writer.pagearray[self.initial_page - 1]
            catalog[PdfName.OpenAction] = PdfArray(
                [initial_page, PdfName.XYZ, NullObject, NullObject, 0]
            )
        if self.engine == Engine.pikepdf:
            if isinstance(initial_page, pikepdf.Page):
                initial_page = self.writer.make_indirect(initial_page.obj)
            else:
                initial_page = self.writer.make_indirect(initial_page)

        if self.magnification == Magnification.fit:
            catalog[PdfName.OpenAction] = PdfArray([initial_page, PdfName.Fit])
        elif self.magnification == Magnification.fith:
            pagewidth = initial_page[PdfName.MediaBox][2]
            catalog[PdfName.OpenAction] = PdfArray(
                [initial_page, PdfName.FitH, pagewidth]
            )
        elif self.magnification == Magnification.fitbh:
            imgwidth = float(initial_page[PdfName.Contents].stream.split()[4])
            catalog[PdfName.OpenAction] = PdfArray(
                [initial_page, PdfName.FitBH, imgwidth]
            )
        elif isinstance(self.magnification, float):
            catalog[PdfName.OpenAction] = PdfArray(
                [initial_page, PdfName.XYZ, NullObject, NullObject, self.magnification]
            )
        elif self.magnification is None:
            pass
        else:
            raise ValueError("unknown magnification: %s" % self.magnification)

        if self.page_layout == PageLayout.single:
            catalog[PdfName.PageLayout] = PdfName.SinglePage
        elif self.page_layout == PageLayout.onecolumn:
            catalog[PdfName.PageLayout] = PdfName.OneColumn
        elif self.page_layout == PageLayout.twocolumnright:
            catalog[PdfName.PageLayout] = PdfName.TwoColumnRight
        elif self.page_layout == PageLayout.twocolumnleft:
            catalog[PdfName.PageLayout] = PdfName.TwoColumnLeft
        elif self.page_layout == PageLayout.twopageright:
            catalog[PdfName.PageLayout] = PdfName.TwoPageRight
            if self.output_version < "1.5":
                self.output_version = "1.5"
        elif self.page_layout == PageLayout.twopageleft:
            catalog[PdfName.PageLayout] = PdfName.TwoPageLeft
            if self.output_version < "1.5":
                self.output_version = "1.5"
        elif self.page_layout is None:
            pass
        else:
            raise ValueError("unknown page layout: %s" % self.page_layout)

        if self.pdfa is not None:
            if self.engine == Engine.pikepdf:
                metadata = self.writer.make_stream(self.xmp)
            else:
                metadata = PdfDict(stream=convert_load(self.xmp))
                metadata[PdfName.Subtype] = PdfName.XML
                metadata[PdfName.Type] = PdfName.Metadata
            with open(self.pdfa, "rb") as f:
                icc = f.read()
            intents = PdfDict()
            if self.engine == Engine.pikepdf:
                iccstream = self.writer.make_stream(icc)
                iccstream.stream_dict.N = 3
            else:
                iccstream = PdfDict(stream=convert_load(zlib.compress(icc)))
                iccstream[PdfName.N] = 3
                iccstream[PdfName.Filter] = PdfName.FlateDecode
            intents[PdfName.S] = PdfName.GTS_PDFA1
            intents[PdfName.Type] = PdfName.OutputIntent
            intents[PdfName.OutputConditionIdentifier] = (
                b"sRGB" if self.engine == Engine.pikepdf else b"(sRGB)"
            )
            intents[PdfName.DestOutputProfile] = iccstream
            catalog[PdfName.OutputIntents] = PdfArray([intents])
            catalog[PdfName.Metadata] = metadata

            if self.engine == Engine.internal:
                self.writer.addobj(metadata)
                self.writer.addobj(iccstream)
        if self.engine == Engine.pikepdf:
            kwargs = {}
            if pikepdf.__version__ >= "6.2.0":
                kwargs["deterministic_id"] = True
            self.writer.save(
                outputstream, min_version=self.output_version, linearize=True, **kwargs
            )
        elif self.engine == Engine.pdfrw:
            self.writer.trailer.Info = self.writer.docinfo
            self.writer.version = self.output_version
            if self.pdfa:
                md5 = hashlib.md5(b"").hexdigest().encode("ascii")
                self.writer.trailer[PdfName.ID] = PdfArray([md5, md5])
            self.writer.write(outputstream)
        elif self.engine == Engine.internal:
            self.writer.tostream(
                self.writer.docinfo,
                outputstream,
                self.output_version,
                None if self.pdfa is None else b"",
            )
        else:
            raise ValueError("unknown engine: %s" % self.engine)


def get_imgmetadata(
    imgdata, imgformat, default_dpi, colorspace, rawdata=None, rotreq=None
):
    if imgformat == ImageFormat.JPEG2000 and rawdata is not None and imgdata is None:
        imgwidthpx, imgheightpx, ics, hdpi, vdpi, channels, bpp = jp2.parse(rawdata)

        if hdpi is None:
            hdpi = default_dpi
        if vdpi is None:
            vdpi = default_dpi
        ndpi = (hdpi, vdpi)
    else:
        imgwidthpx, imgheightpx = imgdata.size

        ndpi = imgdata.info.get("dpi")
        if ndpi is None:
            if imgformat == ImageFormat.PNG and imgdata.info.get("aspect") is not None:
                aspect = imgdata.info["aspect"]
                if aspect[0] > aspect[1]:
                    ndpi = (default_dpi * aspect[0] / aspect[1], default_dpi)
                else:
                    ndpi = (default_dpi, default_dpi * aspect[1] / aspect[0])
            else:
                ndpi = (default_dpi, default_dpi)
        ndpi = (int(round(ndpi[0])), int(round(ndpi[1])))
        ics = imgdata.mode
    if imgformat in [ImageFormat.PNG, ImageFormat.GIF, ImageFormat.JPEG2000] and (
        ics in ["RGBA", "LA"] or "transparency" in imgdata.info
    ):
        if imgformat == ImageFormat.PNG and rawdata is not None:
            depth = rawdata[24]
            if depth > 8:
                logger.warning("Image with transparency and a bit depth of %d." % depth)
                logger.warning("This is unsupported due to PIL limitations.")
                logger.warning(
                    "If you accept a lossy conversion, you can manually convert "
                    "your images to 8 bit using `convert -depth 8` from imagemagick"
                )
                raise AlphaChannelError(
                    "Refusing to work with multiple >8bit channels."
                )
    elif ics in ["LA", "PA", "RGBA"] or "transparency" in imgdata.info:
        raise AlphaChannelError("This function must not be called on images with alpha")
    if ndpi == (0, 0):
        ndpi = (default_dpi, default_dpi)
    if ndpi == (1, 1) and imgformat == ImageFormat.TIFF:
        ndpi = (
            imgdata.tag_v2.get(TiffImagePlugin.X_RESOLUTION, default_dpi),
            imgdata.tag_v2.get(TiffImagePlugin.Y_RESOLUTION, default_dpi),
        )

    logger.debug("input dpi = %d x %d", *ndpi)

    rotation = 0
    if rotreq in (None, Rotation.auto, Rotation.ifvalid):
        if hasattr(imgdata, "_getexif") and imgdata._getexif() is not None:
            for tag, value in imgdata._getexif().items():
                if TAGS.get(tag, tag) == "Orientation":
                    if value == 1:
                        rotation = 0
                    elif value == 6:
                        rotation = 90
                    elif value == 3:
                        rotation = 180
                    elif value == 8:
                        rotation = 270
                    elif value in (2, 4, 5, 7):
                        if rotreq == Rotation.ifvalid:
                            logger.warning(
                                "Unsupported flipped rotation mode (%d): use "
                                "--rotation=ifvalid or "
                                "rotation=img2pdf.Rotation.ifvalid to ignore",
                                value,
                            )
                        else:
                            raise ExifOrientationError(
                                "Unsupported flipped rotation mode (%d): use "
                                "--rotation=ifvalid or "
                                "rotation=img2pdf.Rotation.ifvalid to ignore" % value
                            )
                    else:
                        if rotreq == Rotation.ifvalid:
                            logger.warning("Invalid rotation (%d)", value)
                        else:
                            raise ExifOrientationError(
                                "Invalid rotation (%d): use --rotation=ifvalid "
                                "or rotation=img2pdf.Rotation.ifvalid to ignore" % value
                            )
    elif rotreq in (Rotation.none, Rotation["0"]):
        rotation = 0
    elif rotreq == Rotation["90"]:
        rotation = 90
    elif rotreq == Rotation["180"]:
        rotation = 180
    elif rotreq == Rotation["270"]:
        rotation = 270
    else:
        raise Exception("invalid rotreq")

    logger.debug("rotation = %d°", rotation)

    if colorspace:
        color = colorspace
        logger.debug("input colorspace (forced) = %s", color)
    else:
        color = None
        for c in Colorspace:
            if c.name == ics:
                color = c
        if color is None:
            if (
                rawdata is not None
                and imgformat == ImageFormat.PNG
                and rawdata[25] == 0
            ):
                color = Colorspace.L
            else:
                raise ValueError("unknown colorspace")
        if color == Colorspace.CMYK and imgformat == ImageFormat.JPEG:
            if "adobe" in imgdata.info:
                color = Colorspace["CMYK;I"]
        logger.debug("input colorspace = %s", color.name)

    iccp = None
    if "icc_profile" in imgdata.info:
        iccp = imgdata.info.get("icc_profile")
    if iccp is not None and (
        (color == Colorspace["1"] and imgformat == ImageFormat.TIFF)
        or (
            imgformat == ImageFormat.PNG
            and color == Colorspace.P
            and rawdata is not None
            and parse_png(rawdata)[1]
            in [b"\x00\x00\x00\xff\xff\xff", b"\xff\xff\xff\x00\x00\x00"]
        )
    ):
        with io.BytesIO(iccp) as f:
            prf = ImageCms.ImageCmsProfile(f)
        if (
            prf.profile.model == "sRGB"
            and prf.profile.manufacturer == "GIMP"
            and prf.profile.profile_description == "GIMP built-in sRGB"
        ):
            if imgformat == ImageFormat.TIFF:
                logger.warning(
                    "Ignoring RGB ICC profile in bilevel TIFF produced by GIMP."
                )
            elif imgformat == ImageFormat.PNG:
                logger.warning(
                    "Ignoring RGB ICC profile in 2-color palette PNG produced by GIMP."
                )
            logger.warning("https://gitlab.gnome.org/GNOME/gimp/-/issues/3438")
            iccp = None
    if iccp is not None and (
        (color == Colorspace["L"] and imgformat == ImageFormat.JPEG)
    ):
        with io.BytesIO(iccp) as f:
            prf = ImageCms.ImageCmsProfile(f)

        if prf.profile.xcolor_space not in ("GRAY"):
            logger.warning("Ignoring non-GRAY ICC profile in Grayscale JPG")
            iccp = None

    logger.debug("width x height = %dpx x %dpx", imgwidthpx, imgheightpx)

    return (color, ndpi, imgwidthpx, imgheightpx, rotation, iccp)


def ccitt_payload_location_from_pil(img):
    if img.info["compression"] != "group4":
        raise ValueError(
            "Image not compressed with CCITT Group 4 but with: %s"
            % img.info["compression"]
        )
    strip_offsets = img.tag_v2[TiffImagePlugin.STRIPOFFSETS]
    strip_bytes = img.tag_v2[TiffImagePlugin.STRIPBYTECOUNTS]
    if len(strip_offsets) != 1 or len(strip_bytes) != 1:
        raise NotImplementedError(
            "Transcoding multiple strips not supported by the PDF format"
        )

    (offset,), (length,) = strip_offsets, strip_bytes

    logger.debug("TIFF strip_offsets: %d" % offset)
    logger.debug("TIFF strip_bytes: %d" % length)

    return offset, length


def transcode_monochrome(imgdata):

    logger.debug("Converting monochrome to CCITT Group4")
    newimgio = BytesIO()
    im = Image.frombytes(imgdata.mode, imgdata.size, imgdata.tobytes())
    tmp_strip_size = (imgdata.size[0] + 7) // 8 * imgdata.size[1]
    if hasattr(TiffImagePlugin, "STRIP_SIZE"):
        with temp_attr(TiffImagePlugin, "STRIP_SIZE", tmp_strip_size):
            im.save(newimgio, format="TIFF", compression="group4")
    else:
        pillow__getitem__ = TiffImagePlugin.ImageFileDirectory_v2.__getitem__

        def __getitem__(self, tag):
            overrides = {
                TiffImagePlugin.ROWSPERSTRIP: imgdata.size[1],
                TiffImagePlugin.STRIPBYTECOUNTS: [tmp_strip_size],
                TiffImagePlugin.STRIPOFFSETS: [0],
            }
            return overrides.get(tag, pillow__getitem__(self, tag))

        with temp_attr(
            TiffImagePlugin.ImageFileDirectory_v2, "__getitem__", __getitem__
        ):
            im.save(newimgio, format="TIFF", compression="group4")
    newimgio.seek(0)
    newimg = Image.open(newimgio)

    offset, length = ccitt_payload_location_from_pil(newimg)

    newimgio.seek(offset)
    return newimgio.read(length)


def parse_png(rawdata):
    pngidat = b""
    palette = b""
    i = 16
    while i < len(rawdata):
        (n,) = struct.unpack(">I", rawdata[i - 8 : i - 4])
        if i + n > len(rawdata):
            raise Exception("invalid png: %d %d %d" % (i, n, len(rawdata)))
        if rawdata[i - 4 : i] == b"IDAT":
            pngidat += rawdata[i : i + n]
        elif rawdata[i - 4 : i] == b"PLTE":
            palette += rawdata[i : i + n]
        i += n
        i += 12
    return pngidat, palette


miff_re = re.compile(
    r"""
    [^\x00-\x20\x7f-\x9f] 
    [^=]+                 
    =                     
    (?:
        [^\x00-\x20\x7f-\x9f{}] 
        |{[^}]*}                
    )+""",
    re.VERBOSE,
)
def parse_miff(data):
    results = []
    header, rest = data.split(b":\x1a", 1)
    header = header.decode("ISO-8859-1")
    assert header.lower().startswith("id=imagemagick")
    hdata = {}
    for i, line in enumerate(re.findall(miff_re, header)):
        if not line:
            continue
        k, v = line.split("=", 1)
        if i == 0:
            assert k.lower() == "id"
            assert v.lower() == "imagemagick"
        if k.lower() == "class":

                if v in ["DirectClass", "PseudoClass"]:
                        hdata["class"] = v
                else:
                        print("cannot understand class", v)
        elif k.lower() == "colorspace":
                if v in ["sRGB", "CMYK", "Gray"]:
                        hdata["colorspace"] = v
                else:
                        print("cannot understand colorspace", v)
        elif k.lower() == "depth":
                if v in ["8", "16", "32"]:
                        hdata["depth"] = int(v)
                else:
                        print("cannot understand depth", v)
        elif k.lower() == "colors":
                hdata["colors"] = int(v)
        elif k.lower() == "matte":
                if v == "True":
                        hdata["matte"] = True
                elif v == "False":
                        hdata["matte"] = False
                else:
                        print("cannot understand matte", v)
        elif k.lower() in ["columns", "rows"]:
                hdata[k.lower()] = int(v)
        elif k.lower() == "compression":
                print("compression not yet supported")
        elif k.lower() == "profile":
                assert v in ["icc", "exif"]
                hdata["profile"] = v
        elif k.lower() == "resolution":
                dpix, dpiy = v.split("x", 1)
                hdata["resolution"] = (float(dpix), float(dpiy))

    assert "depth" in hdata
    assert "columns" in hdata
    assert "rows" in hdata

    if hdata["class"] == "DirectClass":
            if "colors" in hdata:
                assert hdata["colors"] == 0
            if hdata["colorspace"] == "sRGB":
                    numchannels = 3
                    colorspace = Colorspace.RGB
            elif hdata["colorspace"] == "CMYK":
                    numchannels = 4
                    colorspace = Colorspace.CMYK
            elif hdata["colorspace"] == "Gray":
                    numchannels = 1
                    colorspace = Colorspace.L
            if hdata.get("matte"):
                numchannels += 1
            if hdata.get("profile"):
                print("FAIL: exif")
            else:
                lenimgdata = (
                    hdata["depth"] // 8 * numchannels * hdata["columns"] * hdata["rows"]
                )
                assert len(rest) >= lenimgdata, (
                    len(rest),
                    hdata["depth"],
                    numchannels,
                    hdata["columns"],
                    hdata["rows"],
                    lenimgdata,
                )
                if colorspace == Colorspace.RGB and hdata["depth"] == 8:
                    newimg = Image.frombytes("RGB", (hdata["columns"], hdata["rows"]), rest[:lenimgdata])
                    imgdata, palette, depth = to_png_data(newimg)
                    assert palette == b""
                    assert depth == hdata["depth"]
                    imgfmt = ImageFormat.PNG
                else:
                    imgdata = zlib.compress(rest[:lenimgdata])
                    imgfmt = ImageFormat.MIFF
                results.append(
                    (
                        colorspace,
                        hdata.get("resolution") or (default_dpi, default_dpi),
                        imgfmt,
                        imgdata,
                        None,  
                        hdata["columns"],
                        hdata["rows"],
                        [],  
                        False,  
                        hdata["depth"],
                        0,  
                        None, 
                    )
                )
                if len(rest) > lenimgdata:
                    assert rest[lenimgdata:][:14].lower() == b"id=imagemagick"
                    results.extend(parse_miff(rest[lenimgdata:]))
    elif hdata["class"] == "PseudoClass":
            assert "colors" in hdata
            if hdata.get("matte"):
                numchannels = 2
            else:
                numchannels = 1
            lenpal = 3 * hdata["colors"] * hdata["depth"] // 8
            lenimgdata = numchannels * hdata["rows"] * hdata["columns"]
            assert len(rest) >= lenpal + lenimgdata, (len(rest), lenpal, lenimgdata)
            results.append(
                (
                    Colorspace.RGB,
                    hdata.get("resolution") or (default_dpi, default_dpi),
                    ImageFormat.MIFF,
                    zlib.compress(rest[lenpal : lenpal + lenimgdata]),
                    None, 
                    hdata["columns"],
                    hdata["rows"],
                    rest[:lenpal],  
                    False, 
                    hdata["depth"],
                    0,  
                    None, 
                )
            )
            if len(rest) > lenpal + lenimgdata:
                assert rest[lenpal + lenimgdata :][:14].lower() == b"id=imagemagick", (
                    len(rest),
                    lenpal,
                    lenimgdata,
                )
                results.extend(parse_miff(rest[lenpal + lenimgdata :]))
    return results


def read_images(
    rawdata, colorspace, first_frame_only=False, rot=None, include_thumbnails=False
):
    im = BytesIO(rawdata)
    im.seek(0)
    imgdata = None
    try:
        imgdata = Image.open(im)
    except IOError as e:
        if rawdata[:12] == b"\x00\x00\x00\x0C\x6A\x50\x20\x20\x0D\x0A\x87\x0A":
            imgformat = ImageFormat.JPEG2000
        if rawdata[:14].lower() == b"id=imagemagick":
            imgformat = ImageFormat.MIFF
        else:
            raise ImageOpenError(
                "cannot read input image (not jpeg2000). "
                "PIL: error reading image: %s" % e
            )
    else:
        logger.debug("PIL format = %s", imgdata.format)
        imgformat = None
        for f in ImageFormat:
            if f.name == imgdata.format:
                imgformat = f
        if imgformat is None:
            imgformat = ImageFormat.other

    def cleanup():
        if imgdata is not None:
            try:
                imgdata.close()
            except AttributeError:
                pass
        im.close()

    logger.debug("imgformat = %s", imgformat.name)
    if imgformat == ImageFormat.JPEG or imgformat == ImageFormat.JPEG2000:
        color, ndpi, imgwidthpx, imgheightpx, rotation, iccp = get_imgmetadata(
            imgdata, imgformat, default_dpi, colorspace, rawdata, rot
        )
        if color == Colorspace["1"]:
            raise JpegColorspaceError("jpeg can't be monochrome")
        if color == Colorspace["P"]:
            raise JpegColorspaceError("jpeg can't have a color palette")
        if color == Colorspace["RGBA"] and imgformat != ImageFormat.JPEG2000:
            raise JpegColorspaceError("jpeg can't have an alpha channel")
        logger.debug("read_images() embeds a JPEG")
        cleanup()
        depth = 8
        if imgformat == ImageFormat.JPEG2000:
            *_, depth = jp2.parse(rawdata)
        return [
            (
                color,
                ndpi,
                imgformat,
                rawdata,
                None,
                imgwidthpx,
                imgheightpx,
                [],
                False,
                depth,
                rotation,
                iccp,
            )
        ]
    if imgformat == ImageFormat.MPO:
        result = []
        img_page_count = 0
        assert len(imgdata._MpoImageFile__mpoffsets) == len(imgdata.mpinfo[0xB002])
        num_frames = len(imgdata.mpinfo[0xB002])
        num_main_frames = 0
        num_thumbnail_frames = 0
        for i, mpent in enumerate(imgdata.mpinfo[0xB002]):
            if (
                i == 0
                and mpent["Attribute"]["DependentParentImageFlag"]
                and not mpent["Attribute"]["DependentChildImageFlag"]
                and mpent["Attribute"]["RepresentativeImageFlag"]
                and mpent["Attribute"]["MPType"] == "Baseline MP Primary Image"
            ):
                num_main_frames += 1
            elif (
                not mpent["Attribute"]["DependentParentImageFlag"]
                and mpent["Attribute"]["DependentChildImageFlag"]
                and not mpent["Attribute"]["RepresentativeImageFlag"]
                and mpent["Attribute"]["MPType"]
                in [
                    "Large Thumbnail (VGA Equivalent)",
                    "Large Thumbnail (Full HD Equivalent)",
                ]
            ):
                num_thumbnail_frames += 1
        logger.debug(f"number of frames: {num_frames}")
        logger.debug(f"number of main frames: {num_main_frames}")
        logger.debug(f"number of thumbnail frames: {num_thumbnail_frames}")
        if num_frames == 1 or (
            not include_thumbnails
            and num_main_frames == 1
            and num_thumbnail_frames + 1 == num_frames
        ):
            color, ndpi, imgwidthpx, imgheightpx, rotation, iccp = get_imgmetadata(
                imgdata, imgformat, default_dpi, colorspace, rawdata, rot
            )
            if color == Colorspace["1"]:
                raise JpegColorspaceError("jpeg can't be monochrome")
            if color == Colorspace["P"]:
                raise JpegColorspaceError("jpeg can't have a color palette")
            if color == Colorspace["RGBA"]:
                raise JpegColorspaceError("jpeg can't have an alpha channel")
            logger.debug("read_images() embeds an MPO verbatim")
            cleanup()
            return [
                (
                    color,
                    ndpi,
                    ImageFormat.JPEG,
                    rawdata,
                    None,
                    imgwidthpx,
                    imgheightpx,
                    [],
                    False,
                    8,
                    rotation,
                    iccp,
                )
            ]
        for offset, mpent in zip(
            imgdata._MpoImageFile__mpoffsets, imgdata.mpinfo[0xB002]
        ):
            if first_frame_only and img_page_count > 0:
                break
            with BytesIO(rawdata[offset : offset + mpent["Size"]]) as rawframe:
                with Image.open(rawframe) as imframe:
                    if img_page_count > 0 and imframe.format != "JPEG":
                        raise Exception("MPO payload must be a JPEG %s", imframe.format)
                    (
                        color,
                        ndpi,
                        imgwidthpx,
                        imgheightpx,
                        rotation,
                        iccp,
                    ) = get_imgmetadata(
                        imframe, ImageFormat.JPEG, default_dpi, colorspace, rotreq=rot
                    )
            if color == Colorspace["1"]:
                raise JpegColorspaceError("jpeg can't be monochrome")
            if color == Colorspace["P"]:
                raise JpegColorspaceError("jpeg can't have a color palette")
            if color == Colorspace["RGBA"]:
                raise JpegColorspaceError("jpeg can't have an alpha channel")
            logger.debug("read_images() embeds a JPEG from MPO")
            result.append(
                (
                    color,
                    ndpi,
                    ImageFormat.JPEG,
                    rawdata[offset : offset + mpent["Size"]],
                    None,
                    imgwidthpx,
                    imgheightpx,
                    [],
                    False,
                    8,
                    rotation,
                    iccp,
                )
            )
            img_page_count += 1
        cleanup()
        return result
    if imgformat == ImageFormat.PNG and rawdata[28] == 0:
        color, ndpi, imgwidthpx, imgheightpx, rotation, iccp = get_imgmetadata(
            imgdata, imgformat, default_dpi, colorspace, rawdata, rot
        )
        if (
            color != Colorspace.RGBA
            and color != Colorspace.LA
            and color != Colorspace.PA
            and "transparency" not in imgdata.info
        ):
            pngidat, palette = parse_png(rawdata)
            depth = rawdata[24]
            if depth not in [1, 2, 4, 8, 16]:
                raise ValueError("invalid bit depth: %d" % depth)
            if palette == b"" or iccp is None:
                logger.debug("read_images() embeds a PNG")
                cleanup()
                return [
                    (
                        color,
                        ndpi,
                        imgformat,
                        pngidat,
                        None,
                        imgwidthpx,
                        imgheightpx,
                        palette,
                        False,
                        depth,
                        rotation,
                        iccp,
                    )
                ]

    if imgformat == ImageFormat.MIFF:
        return parse_miff(rawdata)

    result = []
    img_page_count = 0
    while True:
        try:
            imgdata.seek(img_page_count)
        except EOFError:
            break

        if first_frame_only and img_page_count > 0:
            break
        if (
            imgformat == ImageFormat.TIFF
            and max(imgdata.tag_v2.get(TiffImagePlugin.BITSPERSAMPLE, [1])) > 8
        ):
            raise ValueError("PIL is unable to preserve more than 8 bits per sample")
        if (
            imgformat == ImageFormat.TIFF
            and imgdata.info["compression"] == "group4"
            and len(imgdata.tag_v2[TiffImagePlugin.STRIPOFFSETS]) == 1
            and len(imgdata.tag_v2[TiffImagePlugin.STRIPBYTECOUNTS]) == 1
        ):
            photo = imgdata.tag_v2[TiffImagePlugin.PHOTOMETRIC_INTERPRETATION]
            inverted = False
            if photo == 0:
                inverted = True
            elif photo != 1:
                raise ValueError(
                    "unsupported photometric interpretation for "
                    "group4 tiff: %d" % photo
                )
            color, ndpi, imgwidthpx, imgheightpx, rotation, iccp = get_imgmetadata(
                imgdata, imgformat, default_dpi, colorspace, rawdata, rot
            )
            offset, length = ccitt_payload_location_from_pil(imgdata)
            im.seek(offset)
            rawdata = im.read(length)
            fillorder = imgdata.tag_v2.get(TiffImagePlugin.FILLORDER)
            if fillorder is None:
                pass
            elif fillorder == 1:
                pass
            elif fillorder == 2:
                logger.debug("fillorder is lsb-to-msb => reverse bits")
                rawdata = bytearray(rawdata)
                for i in range(len(rawdata)):
                    rawdata[i] = TIFFBitRevTable[rawdata[i]]
                rawdata = bytes(rawdata)
            else:
                raise ValueError("unsupported FillOrder: %d" % fillorder)
            logger.debug("read_images() embeds Group4 from TIFF")
            result.append(
                (
                    color,
                    ndpi,
                    ImageFormat.CCITTGroup4,
                    rawdata,
                    None,
                    imgwidthpx,
                    imgheightpx,
                    [],
                    inverted,
                    1,
                    rotation,
                    iccp,
                )
            )
            img_page_count += 1
            continue

        logger.debug("Converting frame: %d" % img_page_count)

        color, ndpi, imgwidthpx, imgheightpx, rotation, iccp = get_imgmetadata(
            imgdata, imgformat, default_dpi, colorspace, rotreq=rot
        )

        newimg = None
        if color == Colorspace["1"]:
            try:
                ccittdata = transcode_monochrome(imgdata)
                logger.debug("read_images() encoded a B/W image as CCITT group 4")
                result.append(
                    (
                        color,
                        ndpi,
                        ImageFormat.CCITTGroup4,
                        ccittdata,
                        None,
                        imgwidthpx,
                        imgheightpx,
                        [],
                        False,
                        1,
                        rotation,
                        iccp,
                    )
                )
                img_page_count += 1
                continue
            except Exception as e:
                logger.debug(e)
                logger.debug("Converting colorspace 1 to L")
                newimg = imgdata.convert("L")
                color = Colorspace.L
        elif color in [
            Colorspace.RGB,
            Colorspace.RGBA,
            Colorspace.L,
            Colorspace.LA,
            Colorspace.CMYK,
            Colorspace["CMYK;I"],
            Colorspace.P,
        ]:
            logger.debug("Colorspace is OK: %s", color)
            newimg = imgdata
        else:
            raise ValueError("unknown or unsupported colorspace: %s" % color.name)
        if color in [Colorspace.CMYK, Colorspace["CMYK;I"]]:
            imggz = zlib.compress(newimg.tobytes())
            logger.debug("read_images() encoded CMYK with flate compression")
            result.append(
                (
                    color,
                    ndpi,
                    imgformat,
                    imggz,
                    None,
                    imgwidthpx,
                    imgheightpx,
                    [],
                    False,
                    8,
                    rotation,
                    iccp,
                )
            )
        else:
            if color in [Colorspace.P, Colorspace.PA] and iccp is not None:
                if color == Colorspace.P:
                    newcolor = Colorspace.RGB
                    newimg = newimg.convert(mode="RGB")
                elif color == Colorspace.PA:
                    newcolor = Colorspace.RGBA
                    newimg = newimg.convert(mode="RGBA")
                smaskidat = None
            elif (
                color == Colorspace.RGBA
                or color == Colorspace.LA
                or color == Colorspace.PA
                or "transparency" in newimg.info
            ):
                if color == Colorspace.RGBA:
                    newcolor = color
                    r, g, b, a = newimg.split()
                    newimg = Image.merge("RGB", (r, g, b))
                elif color == Colorspace.LA:
                    newcolor = color
                    l, a = newimg.split()
                    newimg = l
                elif color == Colorspace.PA or (
                    color == Colorspace.P and "transparency" in newimg.info
                ):
                    newcolor = color
                    a = newimg.convert(mode="RGBA").split()[-1]
                else:
                    newcolor = Colorspace.RGBA
                    r, g, b, a = newimg.convert(mode="RGBA").split()
                    newimg = Image.merge("RGB", (r, g, b))

                smaskidat, *_ = to_png_data(a)
                logger.warning(
                    "Image contains an alpha channel. Computing a separate "
                    "soft mask (/SMask) image to store transparency in PDF."
                )
            else:
                newcolor = color
                smaskidat = None

            pngidat, palette, depth = to_png_data(newimg)
            logger.debug("read_images() encoded an image as PNG")
            result.append(
                (
                    newcolor,
                    ndpi,
                    ImageFormat.PNG,
                    pngidat,
                    smaskidat,
                    imgwidthpx,
                    imgheightpx,
                    palette,
                    False,
                    depth,
                    rotation,
                    iccp,
                )
            )
        img_page_count += 1
    cleanup()
    return result


def to_png_data(img):
    pngbuffer = BytesIO()
    img.save(pngbuffer, format="png")

    pngidat, palette = parse_png(pngbuffer.getvalue())
    pngbuffer.seek(24)
    depth = ord(pngbuffer.read(1))
    if depth not in [1, 2, 4, 8, 16]:
        raise ValueError("invalid bit depth: %d" % depth)
    return pngidat, palette, depth
def px_to_pt(length, dpi):
    return 72.0 * length / dpi


def cm_to_pt(length):
    return (72.0 * length) / 2.54


def mm_to_pt(length):
    return (72.0 * length) / 25.4


def in_to_pt(length):
    return 72.0 * length


def get_layout_fun(
    pagesize=None, imgsize=None, border=None, fit=None, auto_orient=False
):
    def fitfun(fit, imgwidth, imgheight, fitwidth, fitheight):
        if fitwidth is None and fitheight is None:
            raise ValueError("fitwidth and fitheight cannot both be None")
        if (
            fit in [FitMode.fill, FitMode.enlarge]
            and fitwidth is not None
            and fitwidth < 0
            and fitheight is not None
            and fitheight < 0
        ):
            raise ValueError(
                "cannot fit into a rectangle where both dimensions are negative"
            )
        elif fit not in [FitMode.fill, FitMode.enlarge] and (
            (fitwidth is not None and fitwidth < 0)
            or (fitheight is not None and fitheight < 0)
        ):
            raise Exception(
                "cannot fit into a rectangle where either dimensions are negative"
            )

        def default():
            if fitwidth is not None and fitheight is not None:
                newimgwidth = fitwidth
                newimgheight = (newimgwidth * imgheight) / imgwidth
                if newimgheight > fitheight:
                    newimgheight = fitheight
                    newimgwidth = (newimgheight * imgwidth) / imgheight
            elif fitwidth is None and fitheight is not None:
                newimgheight = fitheight
                newimgwidth = (newimgheight * imgwidth) / imgheight
            elif fitheight is None and fitwidth is not None:
                newimgwidth = fitwidth
                newimgheight = (newimgwidth * imgheight) / imgwidth
            else:
                raise ValueError("fitwidth and fitheight cannot both be None")
            return newimgwidth, newimgheight

        if fit is None or fit == FitMode.into:
            return default()
        elif fit == FitMode.fill:
            if fitwidth is not None and fitheight is not None:
                newimgwidth = fitwidth
                newimgheight = (newimgwidth * imgheight) / imgwidth
                if newimgheight < fitheight:
                    newimgheight = fitheight
                    newimgwidth = (newimgheight * imgwidth) / imgheight
            elif fitwidth is None and fitheight is not None:
                newimgheight = fitheight
                newimgwidth = (newimgheight * imgwidth) / imgheight
            elif fitheight is None and fitwidth is not None:
                newimgwidth = fitwidth
                newimgheight = (newimgwidth * imgheight) / imgwidth
            else:
                raise ValueError("fitwidth and fitheight cannot both be None")
            return newimgwidth, newimgheight
        elif fit == FitMode.exact:
            if fitwidth is not None and fitheight is not None:
                return fitwidth, fitheight
            elif fitwidth is None and fitheight is not None:
                newimgheight = fitheight
                newimgwidth = (newimgheight * imgwidth) / imgheight
            elif fitheight is None and fitwidth is not None:
                newimgwidth = fitwidth
                newimgheight = (newimgwidth * imgheight) / imgwidth
            else:
                raise ValueError("fitwidth and fitheight cannot both be None")
            return newimgwidth, newimgheight
        elif fit == FitMode.shrink:
            if fitwidth is not None and fitheight is not None:
                if imgwidth <= fitwidth and imgheight <= fitheight:
                    return imgwidth, imgheight
            elif fitwidth is None and fitheight is not None:
                if imgheight <= fitheight:
                    return imgwidth, imgheight
            elif fitheight is None and fitwidth is not None:
                if imgwidth <= fitwidth:
                    return imgwidth, imgheight
            else:
                raise ValueError("fitwidth and fitheight cannot both be None")
            return default()
        elif fit == FitMode.enlarge:
            if fitwidth is not None and fitheight is not None:
                if imgwidth > fitwidth or imgheight > fitheight:
                    return imgwidth, imgheight
            elif fitwidth is None and fitheight is not None:
                if imgheight > fitheight:
                    return imgwidth, imgheight
            elif fitheight is None and fitwidth is not None:
                if imgwidth > fitwidth:
                    return imgwidth, imgheight
            else:
                raise ValueError("fitwidth and fitheight cannot both be None")
            return default()
        else:
            raise NotImplementedError
    if pagesize is None and imgsize is None and border is None:
        return default_layout_fun
    if pagesize is None and imgsize is None and border is not None:

        def layout_fun(imgwidthpx, imgheightpx, ndpi):
            imgwidthpdf = px_to_pt(imgwidthpx, ndpi[0])
            imgheightpdf = px_to_pt(imgheightpx, ndpi[1])
            pagewidth = imgwidthpdf + 2 * border[1]
            pageheight = imgheightpdf + 2 * border[0]
            return pagewidth, pageheight, imgwidthpdf, imgheightpdf

        return layout_fun
    if border is None:
        border = (0, 0)
    if pagesize is not None and imgsize is None:

        def layout_fun(imgwidthpx, imgheightpx, ndpi):
            if (
                pagesize[0] is not None
                and pagesize[1] is not None
                and auto_orient
                and (
                    (imgwidthpx > imgheightpx and pagesize[0] < pagesize[1])
                    or (imgwidthpx < imgheightpx and pagesize[0] > pagesize[1])
                )
            ):
                pagewidth, pageheight = pagesize[1], pagesize[0]
                newborder = border[1], border[0]
            else:
                pagewidth, pageheight = pagesize[0], pagesize[1]
                newborder = border
            if pagewidth is not None:
                fitwidth = pagewidth - 2 * newborder[1]
            else:
                fitwidth = None
            if pageheight is not None:
                fitheight = pageheight - 2 * newborder[0]
            else:
                fitheight = None
            if (
                fit in [FitMode.fill, FitMode.enlarge]
                and fitwidth is not None
                and fitwidth < 0
                and fitheight is not None
                and fitheight < 0
            ):
                raise NegativeDimensionError(
                    "at least one border dimension musts be smaller than half "
                    "the respective page dimension"
                )
            elif fit not in [FitMode.fill, FitMode.enlarge] and (
                (fitwidth is not None and fitwidth < 0)
                or (fitheight is not None and fitheight < 0)
            ):
                raise NegativeDimensionError(
                    "one border dimension is larger than half of the "
                    "respective page dimension"
                )
            imgwidthpdf, imgheightpdf = fitfun(
                fit,
                px_to_pt(imgwidthpx, ndpi[0]),
                px_to_pt(imgheightpx, ndpi[1]),
                fitwidth,
                fitheight,
            )
            if pagewidth is None:
                pagewidth = imgwidthpdf + border[1] * 2
            if pageheight is None:
                pageheight = imgheightpdf + border[0] * 2
            return pagewidth, pageheight, imgwidthpdf, imgheightpdf

        return layout_fun

    def scale_imgsize(s, px, dpi):
        if s is None:
            return None
        mode, value = s
        if mode == ImgSize.abs:
            return value
        if mode == ImgSize.perc:
            return (px_to_pt(px, dpi) * value) / 100
        if mode == ImgSize.dpi:
            return px_to_pt(px, value)
        raise NotImplementedError

    if pagesize is None and imgsize is not None:

        def layout_fun(imgwidthpx, imgheightpx, ndpi):
            imgwidthpdf, imgheightpdf = fitfun(
                fit,
                px_to_pt(imgwidthpx, ndpi[0]),
                px_to_pt(imgheightpx, ndpi[1]),
                scale_imgsize(imgsize[0], imgwidthpx, ndpi[0]),
                scale_imgsize(imgsize[1], imgheightpx, ndpi[1]),
            )
            pagewidth = imgwidthpdf + 2 * border[1]
            pageheight = imgheightpdf + 2 * border[0]
            return pagewidth, pageheight, imgwidthpdf, imgheightpdf

        return layout_fun
    if pagesize is not None and imgsize is not None:

        def layout_fun(imgwidthpx, imgheightpx, ndpi):
            if (
                pagesize[0] is not None
                and pagesize[1] is not None
                and auto_orient
                and (
                    (imgwidthpx > imgheightpx and pagesize[0] < pagesize[1])
                    or (imgwidthpx < imgheightpx and pagesize[0] > pagesize[1])
                )
            ):
                pagewidth, pageheight = pagesize[1], pagesize[0]
            else:
                pagewidth, pageheight = pagesize[0], pagesize[1]
            imgwidthpdf, imgheightpdf = fitfun(
                fit,
                px_to_pt(imgwidthpx, ndpi[0]),
                px_to_pt(imgheightpx, ndpi[1]),
                scale_imgsize(imgsize[0], imgwidthpx, ndpi[0]),
                scale_imgsize(imgsize[1], imgheightpx, ndpi[1]),
            )
            return pagewidth, pageheight, imgwidthpdf, imgheightpdf

        return layout_fun
    raise NotImplementedError


def default_layout_fun(imgwidthpx, imgheightpx, ndpi):
    imgwidthpdf = pagewidth = px_to_pt(imgwidthpx, ndpi[0])
    imgheightpdf = pageheight = px_to_pt(imgheightpx, ndpi[1])
    return pagewidth, pageheight, imgwidthpdf, imgheightpdf


def get_fixed_dpi_layout_fun(fixed_dpi):

    def fixed_dpi_layout_fun(imgwidthpx, imgheightpx, ndpi):
        return default_layout_fun(imgwidthpx, imgheightpx, fixed_dpi)

    return fixed_dpi_layout_fun


def find_scale(pagewidth, pageheight):
    from math import log10, ceil

    major = max(pagewidth, pageheight)
    oversized = major / 14400.0

    return 10 ** ceil(log10(oversized))

def convert(*images, **kwargs):
    _default_kwargs = dict(
        engine=None,
        title=None,
        author=None,
        creator=None,
        producer=None,
        creationdate=None,
        moddate=None,
        subject=None,
        keywords=None,
        colorspace=None,
        nodate=False,
        layout_fun=default_layout_fun,
        viewer_panes=None,
        viewer_initial_page=None,
        viewer_magnification=None,
        viewer_page_layout=None,
        viewer_fit_window=False,
        viewer_center_window=False,
        viewer_fullscreen=False,
        outputstream=None,
        first_frame_only=False,
        allow_oversized=True,
        cropborder=None,
        bleedborder=None,
        trimborder=None,
        artborder=None,
        pdfa=None,
        rotation=None,
        include_thumbnails=False,
    )
    for kwname, default in _default_kwargs.items():
        if kwname not in kwargs:
            kwargs[kwname] = default

    pdf = pdfdoc(
        kwargs["engine"],
        "1.3",
        kwargs["title"],
        kwargs["author"],
        kwargs["creator"],
        kwargs["producer"],
        kwargs["creationdate"],
        kwargs["moddate"],
        kwargs["subject"],
        kwargs["keywords"],
        kwargs["nodate"],
        kwargs["viewer_panes"],
        kwargs["viewer_initial_page"],
        kwargs["viewer_magnification"],
        kwargs["viewer_page_layout"],
        kwargs["viewer_fit_window"],
        kwargs["viewer_center_window"],
        kwargs["viewer_fullscreen"],
        kwargs["pdfa"],
    )
    if len(images) == 1:
        if isinstance(images[0], (list, tuple)):
            images = images[0]

    if not isinstance(images, (list, tuple)):
        images = [images]
    else:
        if len(images) == 0:
            raise ValueError("Unable to process empty list")

    for img in images:
        rawdata = None
        for fun in "read", "read_bytes":
            try:
                rawdata = getattr(img, fun)()
            except AttributeError:
                pass
        if rawdata is None:
            if not isinstance(img, (str, bytes)):
                raise TypeError("Neither read(), read_bytes() nor is str or bytes")
            try:
                f = open(img, "rb")
            except Exception:
                rawdata = img
            else:
                rawdata = f.read()
                f.close()

        for (
            color,
            ndpi,
            imgformat,
            imgdata,
            smaskdata,
            imgwidthpx,
            imgheightpx,
            palette,
            inverted,
            depth,
            rotation,
            iccp,
        ) in read_images(
            rawdata,
            kwargs["colorspace"],
            kwargs["first_frame_only"],
            kwargs["rotation"],
            kwargs["include_thumbnails"],
        ):
            pagewidth, pageheight, imgwidthpdf, imgheightpdf = kwargs["layout_fun"](
                imgwidthpx, imgheightpx, ndpi
            )

            userunit = None
            if pagewidth < 3.00 or pageheight < 3.00:
                logger.warning(
                    "pdf width or height is below 3.00 - too small for some viewers!"
                )
            elif pagewidth > 14400.0 or pageheight > 14400.0:
                if kwargs["allow_oversized"]:
                    userunit = find_scale(pagewidth, pageheight)
                    pagewidth /= userunit
                    pageheight /= userunit
                    imgwidthpdf /= userunit
                    imgheightpdf /= userunit
                else:
                    raise PdfTooLargeError(
                        "pdf width or height must not exceed 200 inches."
                    )
            for border in ["crop", "bleed", "trim", "art"]:
                if kwargs[border + "border"] is None:
                    continue
                if pagewidth < 2 * kwargs[border + "border"][1]:
                    raise ValueError(
                        "horizontal %s border larger than page width" % border
                    )
                if pageheight < 2 * kwargs[border + "border"][0]:
                    raise ValueError(
                        "vertical %s border larger than page height" % border
                    )
            imgxpdf = (pagewidth - imgwidthpdf) / 2.0
            imgypdf = (pageheight - imgheightpdf) / 2.0
            pdf.add_imagepage(
                color,
                imgwidthpx,
                imgheightpx,
                imgformat,
                imgdata,
                smaskdata,
                imgwidthpdf,
                imgheightpdf,
                imgxpdf,
                imgypdf,
                pagewidth,
                pageheight,
                userunit,
                palette,
                inverted,
                depth,
                rotation,
                kwargs["cropborder"],
                kwargs["bleedborder"],
                kwargs["trimborder"],
                kwargs["artborder"],
                iccp,
            )

    if kwargs["outputstream"]:
        pdf.tostream(kwargs["outputstream"])
        return

    return pdf.tostring()


def parse_num(num, name):
    if num == "":
        return None
    unit = None
    if num.endswith("pt"):
        unit = Unit.pt
    elif num.endswith("cm"):
        unit = Unit.cm
    elif num.endswith("mm"):
        unit = Unit.mm
    elif num.endswith("in"):
        unit = Unit.inch
    else:
        try:
            num = float(num)
        except ValueError:
            msg = (
                "%s is not a floating point number and doesn't have a "
                "valid unit: %s" % (name, num)
            )
            raise argparse.ArgumentTypeError(msg)
    if unit is None:
        unit = Unit.pt
    else:
        num = num[:-2]
        try:
            num = float(num)
        except ValueError:
            msg = "%s is not a floating point number: %s" % (name, num)
            raise argparse.ArgumentTypeError(msg)
    if num < 0:
        msg = "%s must not be negative: %s" % (name, num)
        raise argparse.ArgumentTypeError(msg)
    if unit == Unit.cm:
        num = cm_to_pt(num)
    elif unit == Unit.mm:
        num = mm_to_pt(num)
    elif unit == Unit.inch:
        num = in_to_pt(num)
    return num


def parse_imgsize_num(num, name):
    if num == "":
        return None
    unit = None
    if num.endswith("pt"):
        unit = ImgUnit.pt
    elif num.endswith("cm"):
        unit = ImgUnit.cm
    elif num.endswith("mm"):
        unit = ImgUnit.mm
    elif num.endswith("in"):
        unit = ImgUnit.inch
    elif num.endswith("dpi"):
        unit = ImgUnit.dpi
    elif num.endswith("%"):
        unit = ImgUnit.perc
    else:
        try:
            num = float(num)
        except ValueError:
            msg = (
                "%s is not a floating point number and doesn't have a "
                "valid unit: %s" % (name, num)
            )
            raise argparse.ArgumentTypeError(msg)
    if unit is None:
        unit = ImgUnit.pt
    else:
        # strip off unit from string
        if unit == ImgUnit.dpi:
            num = num[:-3]
        elif unit == ImgUnit.perc:
            num = num[:-1]
        else:
            num = num[:-2]
        try:
            num = float(num)
        except ValueError:
            msg = "%s is not a floating point number: %s" % (name, num)
            raise argparse.ArgumentTypeError(msg)
    if unit == ImgUnit.cm:
        num = (ImgSize.abs, cm_to_pt(num))
    elif unit == ImgUnit.mm:
        num = (ImgSize.abs, mm_to_pt(num))
    elif unit == ImgUnit.inch:
        num = (ImgSize.abs, in_to_pt(num))
    elif unit == ImgUnit.pt:
        num = (ImgSize.abs, num)
    elif unit == ImgUnit.dpi:
        num = (ImgSize.dpi, num)
    elif unit == ImgUnit.perc:
        num = (ImgSize.perc, num)
    return num


def parse_pagesize_rectarg(string):
    transposed = string.endswith("^T")
    if transposed:
        string = string[:-2]
    if papersizes.get(string.lower()):
        string = papersizes[string.lower()]
    if "x" not in string:
        w = parse_num(string, "width")
        h = None
    else:
        w, h = string.split("x", 1)
        w = parse_num(w, "width")
        h = parse_num(h, "height")
    if transposed:
        w, h = h, w
    if w is None and h is None:
        raise argparse.ArgumentTypeError("at least one dimension must be specified")
    return w, h


def parse_imgsize_rectarg(string):
    transposed = string.endswith("^T")
    if transposed:
        string = string[:-2]
    if papersizes.get(string.lower()):
        string = papersizes[string.lower()]
    if "x" not in string:
        w = parse_imgsize_num(string, "width")
        h = None
    else:
        w, h = string.split("x", 1)
        w = parse_imgsize_num(w, "width")
        h = parse_imgsize_num(h, "height")
    if transposed:
        w, h = h, w
    if w is None and h is None:
        raise argparse.ArgumentTypeError("at least one dimension must be specified")
    return w, h


def parse_colorspacearg(string):
    for c in Colorspace:
        if c.name == string:
            return c
    allowed = ", ".join([c.name for c in Colorspace])
    raise argparse.ArgumentTypeError(
        "Unsupported colorspace: %s. Must be one of: %s." % (string, allowed)
    )


def parse_enginearg(string):
    for c in Engine:
        if c.name == string:
            return c
    allowed = ", ".join([c.name for c in Engine])
    raise argparse.ArgumentTypeError(
        "Unsupported engine: %s. Must be one of: %s." % (string, allowed)
    )


def parse_borderarg(string):
    if ":" in string:
        h, v = string.split(":", 1)
        if h == "":
            raise argparse.ArgumentTypeError("missing value before colon")
        if v == "":
            raise argparse.ArgumentTypeError("missing value after colon")
    else:
        if string == "":
            raise argparse.ArgumentTypeError("border option cannot be empty")
        h, v = string, string
    h, v = parse_num(h, "left/right border"), parse_num(v, "top/bottom border")
    if h is None and v is None:
        raise argparse.ArgumentTypeError("missing value")
    return h, v


def from_file(path):
    result = []
    if path == "-":
        content = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            content = f.read()
    for path in content.split(b"\0"):
        if path == b"":
            continue
        try:
            with open(path, "rb") as im:
                im.read(1)
        except IsADirectoryError:
            raise argparse.ArgumentTypeError('"%s" is a directory' % path)
        except PermissionError:
            raise argparse.ArgumentTypeError('"%s" permission denied' % path)
        except FileNotFoundError:
            raise argparse.ArgumentTypeError('"%s" does not exist' % path)
        result.append(path)
    return result


def input_images(path_expr):
    if path_expr == "-":
        result = [sys.stdin.buffer.read()]
        if len(result) == 0:
            raise argparse.ArgumentTypeError('"%s" is empty' % path_expr)
    else:
        result = []
        paths = [path_expr]
        if sys.platform == "win32" and ("*" in path_expr or "?" in path_expr):
            from glob import glob

            paths = sorted(glob(path_expr))
        for path in paths:
            try:
                if os.path.getsize(path) == 0:
                    raise argparse.ArgumentTypeError('"%s" is empty' % path)
                with open(path, "rb") as im:
                    im.read(1)
            except IsADirectoryError:
                raise argparse.ArgumentTypeError('"%s" is a directory' % path)
            except PermissionError:
                raise argparse.ArgumentTypeError('"%s" permission denied' % path)
            except FileNotFoundError:
                raise argparse.ArgumentTypeError('"%s" does not exist' % path)
            result.append(path)
    return result


def parse_rotationarg(string):
    for m in Rotation:
        if m.name == string.lower():
            return m
    raise argparse.ArgumentTypeError("unknown rotation value: %s" % string)


def parse_fitarg(string):
    for m in FitMode:
        if m.name == string.lower():
            return m
    raise argparse.ArgumentTypeError("unknown fit mode: %s" % string)


def parse_panes(string):
    for m in PageMode:
        if m.name == string.lower():
            return m
    allowed = ", ".join([m.name for m in PageMode])
    raise argparse.ArgumentTypeError(
        "Unsupported page mode: %s. Must be one of: %s." % (string, allowed)
    )


def parse_magnification(string):
    for m in Magnification:
        if m.name == string.lower():
            return m
    try:
        return float(string)
    except ValueError:
        pass
    allowed = ", ".join([m.name for m in Magnification])
    raise argparse.ArgumentTypeError(
        "Unsupported magnification: %s. Must be "
        "a floating point number or one of: %s." % (string, allowed)
    )


def parse_layout(string):
    for l in PageLayout:
        if l.name == string.lower():
            return l
    allowed = ", ".join([l.name for l in PageLayout])
    raise argparse.ArgumentTypeError(
        "Unsupported page layout: %s. Must be one of: %s." % (string, allowed)
    )


def valid_date(string):
    try:
        return datetime.strptime(string, "%Y-%m-%d")
    except ValueError:
        pass
    try:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    try:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass
    try:
        from dateutil import parser
    except ImportError:
        pass
    else:
        try:
            return parser.parse(string)
        except:
            pass
    try:
        import subprocess
    except ImportError:
        pass
    else:
        try:
            utime = subprocess.check_output(["date", "--date", string, "+%s"])
        except subprocess.CalledProcessError:
            pass
        else:
            return datetime.fromtimestamp(int(utime))
    raise argparse.ArgumentTypeError("cannot parse date: %s" % string)


def gui():
    import tkinter
    import tkinter.filedialog

    have_fitz = True
    try:
        import fitz
    except ImportError:
        have_fitz = False

    class VerticalScrolledFrame(tkinter.Frame):

        def __init__(self, parent, *args, **kw):
            tkinter.Frame.__init__(self, parent, *args, **kw)
            vscrollbar = tkinter.Scrollbar(self, orient=tkinter.VERTICAL)
            vscrollbar.pack(fill=tkinter.Y, side=tkinter.RIGHT, expand=tkinter.FALSE)
            canvas = tkinter.Canvas(
                self,
                borderwidth=0,
                highlightthickness=0,
                yscrollcommand=vscrollbar.set,
                width=240,
            )
            canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=tkinter.TRUE)
            vscrollbar.config(command=canvas.yview)

            canvas.xview_moveto(0)
            canvas.yview_moveto(0)

            self.interior = interior = tkinter.Frame(canvas)
            interior_id = canvas.create_window(0, 0, window=interior, anchor=tkinter.NW)

            def _configure_interior(event):
                size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
                canvas.config(scrollregion="0 0 %s %s" % size)

            interior.bind("<Configure>", _configure_interior)

            def _configure_canvas(event):
                if interior.winfo_reqwidth() != canvas.winfo_width():
                    # Update the inner frame's width to fill the canvas.
                    canvas.itemconfigure(interior_id, width=canvas.winfo_width())

            canvas.bind("<Configure>", _configure_canvas)

            return

    class OptionMenu(tkinter.Menubutton):
        """OptionMenu which allows the user to select a value from a menu."""

        def __init__(self, master, variable, value, *values, **kwargs):
            """Construct an optionmenu widget with the parent MASTER, with
            the resource textvariable set to VARIABLE, the initially selected
            value VALUE, the other menu values VALUES and an additional
            keyword argument command."""
            kw = {
                "borderwidth": 2,
                "textvariable": variable,
                "indicatoron": 1,
                "relief": tkinter.RAISED,
                "anchor": "c",
                "highlightthickness": 2,
            }
            if "state" in kwargs:
                kw["state"] = kwargs["state"]
                del kwargs["state"]
            if "name" in kwargs:
                kw["name"] = kwargs["name"]
                del kwargs["name"]
            tkinter.Widget.__init__(self, master, "menubutton", kw)
            self.widgetName = "tk_optionMenu"
            self.callback = kwargs.get("command")
            self.variable = variable
            if "command" in kwargs:
                del kwargs["command"]
            if kwargs:
                raise tkinter.TclError("unknown option -" + list(kwargs.keys())[0])
            self.set_values([value] + list(values))

        def __getitem__(self, name):
            if name == "menu":
                return self.__menu
            return tkinter.Widget.__getitem__(self, name)

        def set_values(self, values):
            menu = self.__menu = tkinter.Menu(self, name="menu", tearoff=0)
            self.menuname = menu._w
            for v in values:
                menu.add_command(
                    label=v, command=tkinter._setit(self.variable, v, self.callback)
                )
            self["menu"] = menu

        def destroy(self):
            """Destroy this widget and the associated menu."""
            tkinter.Menubutton.destroy(self)
            self.__menu = None

    root = tkinter.Tk()
    app = tkinter.Frame(master=root)

    infiles = []
    maxpagewidth = 0
    maxpageheight = 0
    doc = None

    args = {
        "engine": tkinter.StringVar(),
        "auto_orient": tkinter.BooleanVar(),
        "fit": tkinter.StringVar(),
        "title": tkinter.StringVar(),
        "author": tkinter.StringVar(),
        "creator": tkinter.StringVar(),
        "producer": tkinter.StringVar(),
        "subject": tkinter.StringVar(),
        "keywords": tkinter.StringVar(),
        "nodate": tkinter.BooleanVar(),
        "creationdate": tkinter.StringVar(),
        "moddate": tkinter.StringVar(),
        "viewer_panes": tkinter.StringVar(),
        "viewer_initial_page": tkinter.IntVar(),
        "viewer_magnification": tkinter.StringVar(),
        "viewer_page_layout": tkinter.StringVar(),
        "viewer_fit_window": tkinter.BooleanVar(),
        "viewer_center_window": tkinter.BooleanVar(),
        "viewer_fullscreen": tkinter.BooleanVar(),
        "pagesize_dropdown": tkinter.StringVar(),
        "pagesize_width": tkinter.DoubleVar(),
        "pagesize_height": tkinter.DoubleVar(),
        "imgsize_dropdown": tkinter.StringVar(),
        "imgsize_width": tkinter.DoubleVar(),
        "imgsize_height": tkinter.DoubleVar(),
        "colorspace": tkinter.StringVar(),
        "first_frame_only": tkinter.BooleanVar(),
    }
    args["engine"].set("auto")
    args["title"].set("")
    args["auto_orient"].set(False)
    args["fit"].set("into")
    args["colorspace"].set("auto")
    args["viewer_panes"].set("auto")
    args["viewer_initial_page"].set(1)
    args["viewer_magnification"].set("auto")
    args["viewer_page_layout"].set("auto")
    args["first_frame_only"].set(False)
    args["pagesize_dropdown"].set("auto")
    args["imgsize_dropdown"].set("auto")

    def on_open_button():
        nonlocal infiles
        nonlocal doc
        nonlocal maxpagewidth
        nonlocal maxpageheight
        infiles = tkinter.filedialog.askopenfilenames(
            parent=root,
            title="open image",
            filetypes=[
                (
                    "images",
                    "*.bmp *.eps *.gif *.ico *.jpeg *.jpg *.jp2 *.pcx *.png *.ppm *.tiff",
                ),
                ("all files", "*"),
            ],
            # initialdir="/home/josch/git/plakativ",
            # initialfile="test.pdf",
        )
        if have_fitz:
            with BytesIO() as f:
                save_pdf(f)
                f.seek(0)
                doc = fitz.open(stream=f, filetype="pdf")
            for page in doc:
                if page.getDisplayList().rect.width > maxpagewidth:
                    maxpagewidth = page.getDisplayList().rect.width
                if page.getDisplayList().rect.height > maxpageheight:
                    maxpageheight = page.getDisplayList().rect.height
        draw()

    def save_pdf(stream):
        pagesizearg = None
        if args["pagesize_dropdown"].get() == "auto":
            # nothing to do
            pass
        elif args["pagesize_dropdown"].get() == "custom":
            pagesizearg = args["pagesize_width"].get(), args["pagesize_height"].get()
        elif args["pagesize_dropdown"].get() in papernames.values():
            raise NotImplemented()
        else:
            raise Exception("no such pagesize: %s" % args["pagesize_dropdown"].get())
        imgsizearg = None
        if args["imgsize_dropdown"].get() == "auto":
            # nothing to do
            pass
        elif args["imgsize_dropdown"].get() == "custom":
            imgsizearg = args["imgsize_width"].get(), args["imgsize_height"].get()
        elif args["imgsize_dropdown"].get() in papernames.values():
            raise NotImplemented()
        else:
            raise Exception("no such imgsize: %s" % args["imgsize_dropdown"].get())
        borderarg = None
        layout_fun = get_layout_fun(
            pagesizearg,
            imgsizearg,
            borderarg,
            args["fit"].get(),
            args["auto_orient"].get(),
        )
        viewer_panesarg = None
        if args["viewer_panes"].get() == "auto":
            # nothing to do
            pass
        elif args["viewer_panes"].get() in PageMode:
            viewer_panesarg = args["viewer_panes"].get()
        else:
            raise Exception("no such viewer_panes: %s" % args["viewer_panes"].get())
        viewer_magnificationarg = None
        if args["viewer_magnification"].get() == "auto":
            # nothing to do
            pass
        elif args["viewer_magnification"].get() in Magnification:
            viewer_magnificationarg = args["viewer_magnification"].get()
        else:
            raise Exception(
                "no such viewer_magnification: %s" % args["viewer_magnification"].get()
            )
        viewer_page_layoutarg = None
        if args["viewer_page_layout"].get() == "auto":
            # nothing to do
            pass
        elif args["viewer_page_layout"].get() in PageLayout:
            viewer_page_layoutarg = args["viewer_page_layout"].get()
        else:
            raise Exception(
                "no such viewer_page_layout: %s" % args["viewer_page_layout"].get()
            )
        colorspacearg = None
        if args["colorspace"].get() != "auto":
            colorspacearg = next(
                v for v in Colorspace if v.name == args["colorspace"].get()
            )
        enginearg = None
        if args["engine"].get() != "auto":
            enginearg = next(v for v in Engine if v.name == args["engine"].get())

        convert(
            *infiles,
            engine=enginearg,
            title=args["title"].get() if args["title"].get() else None,
            author=args["author"].get() if args["author"].get() else None,
            creator=args["creator"].get() if args["creator"].get() else None,
            producer=args["producer"].get() if args["producer"].get() else None,
            creationdate=args["creationdate"].get()
            if args["creationdate"].get()
            else None,
            moddate=args["moddate"].get() if args["moddate"].get() else None,
            subject=args["subject"].get() if args["subject"].get() else None,
            keywords=args["keywords"].get() if args["keywords"].get() else None,
            colorspace=colorspacearg,
            nodate=args["nodate"].get(),
            layout_fun=layout_fun,
            viewer_panes=viewer_panesarg,
            viewer_initial_page=args["viewer_initial_page"].get()
            if args["viewer_initial_page"].get() > 1
            else None,
            viewer_magnification=viewer_magnificationarg,
            viewer_page_layout=viewer_page_layoutarg,
            viewer_fit_window=(args["viewer_fit_window"].get() or None),
            viewer_center_window=(args["viewer_center_window"].get() or None),
            viewer_fullscreen=(args["viewer_fullscreen"].get() or None),
            outputstream=stream,
            first_frame_only=args["first_frame_only"].get(),
            cropborder=None,
            bleedborder=None,
            trimborder=None,
            artborder=None,
        )

    def on_save_button():
        filename = tkinter.filedialog.asksaveasfilename(
            parent=root,
            title="save PDF",
            defaultextension=".pdf",
            filetypes=[("pdf documents", "*.pdf"), ("all files", "*")],
            # initialdir="/home/josch/git/plakativ",
            # initialfile=base + "_poster" + ext,
        )
        with open(filename, "wb") as f:
            save_pdf(f)

    root.title("img2pdf")
    app.pack(fill=tkinter.BOTH, expand=tkinter.TRUE)

    canvas = tkinter.Canvas(app, bg="black")

    def draw():
        canvas.delete(tkinter.ALL)
        if not infiles:
            canvas.create_text(
                canvas.size[0] / 2,
                canvas.size[1] / 2,
                text='Click on the "Open Image(s)" button in the upper right.',
                fill="white",
            )
            return

        if not doc:
            canvas.create_text(
                canvas.size[0] / 2,
                canvas.size[1] / 2,
                text="PyMuPDF not available. Install the Python fitz module\n"
                + "for preview functionality.",
                fill="white",
            )
            return

        canvas_padding = 10
        # factor to convert from pdf dimensions (given in pt) into canvas
        # dimensions (given in pixels)
        zoom = min(
            (canvas.size[0] - canvas_padding) / maxpagewidth,
            (canvas.size[1] - canvas_padding) / maxpageheight,
        )

        pagenum = 0
        mat_0 = fitz.Matrix(zoom, zoom)
        canvas.image = tkinter.PhotoImage(
            data=doc[pagenum]
            .getDisplayList()
            .getPixmap(matrix=mat_0, alpha=False)
            .getImageData("ppm")
        )
        canvas.create_image(
            (canvas.size[0] - maxpagewidth * zoom) / 2,
            (canvas.size[1] - maxpageheight * zoom) / 2,
            anchor=tkinter.NW,
            image=canvas.image,
        )

        canvas.create_rectangle(
            (canvas.size[0] - maxpagewidth * zoom) / 2,
            (canvas.size[1] - maxpageheight * zoom) / 2,
            (canvas.size[0] - maxpagewidth * zoom) / 2 + canvas.image.width(),
            (canvas.size[1] - maxpageheight * zoom) / 2 + canvas.image.height(),
            outline="red",
        )

    def on_resize(event):
        canvas.size = (event.width, event.height)
        draw()

    canvas.pack(fill=tkinter.BOTH, side=tkinter.LEFT, expand=tkinter.TRUE)
    canvas.bind("<Configure>", on_resize)

    frame_right = tkinter.Frame(app)
    frame_right.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.Y)

    top_frame = tkinter.Frame(frame_right)
    top_frame.pack(fill=tkinter.X)

    tkinter.Button(top_frame, text="Open Image(s)", command=on_open_button).pack(
        side=tkinter.LEFT, expand=tkinter.TRUE, fill=tkinter.X
    )
    tkinter.Button(top_frame, text="Help", state=tkinter.DISABLED).pack(
        side=tkinter.RIGHT, expand=tkinter.TRUE, fill=tkinter.X
    )

    frame1 = VerticalScrolledFrame(frame_right)
    frame1.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.Y)

    output_options = tkinter.LabelFrame(frame1.interior, text="Output Options")
    output_options.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    tkinter.Label(output_options, text="colorspace").grid(
        row=0, column=0, sticky=tkinter.W
    )
    OptionMenu(output_options, args["colorspace"], "auto", state=tkinter.DISABLED).grid(
        row=0, column=1, sticky=tkinter.W
    )
    tkinter.Label(output_options, text="engine").grid(row=1, column=0, sticky=tkinter.W)
    OptionMenu(output_options, args["engine"], "auto", state=tkinter.DISABLED).grid(
        row=1, column=1, sticky=tkinter.W
    )
    tkinter.Checkbutton(
        output_options,
        text="Suppress timestamp",
        variable=args["nodate"],
        state=tkinter.DISABLED,
    ).grid(row=2, column=0, columnspan=2, sticky=tkinter.W)
    tkinter.Checkbutton(
        output_options,
        text="only first frame",
        variable=args["first_frame_only"],
        state=tkinter.DISABLED,
    ).grid(row=3, column=0, columnspan=2, sticky=tkinter.W)
    tkinter.Checkbutton(
        output_options, text="force large input", state=tkinter.DISABLED
    ).grid(row=4, column=0, columnspan=2, sticky=tkinter.W)
    image_size_frame = tkinter.LabelFrame(frame1.interior, text="Image size")
    image_size_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    OptionMenu(
        image_size_frame,
        args["imgsize_dropdown"],
        *(["auto", "custom"] + sorted(papernames.values())),
        state=tkinter.DISABLED,
    ).grid(row=1, column=0, columnspan=3, sticky=tkinter.W)

    tkinter.Label(
        image_size_frame, text="Width:", state=tkinter.DISABLED, name="size_label_width"
    ).grid(row=2, column=0, sticky=tkinter.W)
    tkinter.Spinbox(
        image_size_frame,
        format="%.2f",
        increment=0.01,
        from_=0,
        to=100,
        width=5,
        state=tkinter.DISABLED,
        name="spinbox_width",
    ).grid(row=2, column=1, sticky=tkinter.W)
    tkinter.Label(
        image_size_frame, text="mm", state=tkinter.DISABLED, name="size_label_width_mm"
    ).grid(row=2, column=2, sticky=tkinter.W)

    tkinter.Label(
        image_size_frame,
        text="Height:",
        state=tkinter.DISABLED,
        name="size_label_height",
    ).grid(row=3, column=0, sticky=tkinter.W)
    tkinter.Spinbox(
        image_size_frame,
        format="%.2f",
        increment=0.01,
        from_=0,
        to=100,
        width=5,
        state=tkinter.DISABLED,
        name="spinbox_height",
    ).grid(row=3, column=1, sticky=tkinter.W)
    tkinter.Label(
        image_size_frame, text="mm", state=tkinter.DISABLED, name="size_label_height_mm"
    ).grid(row=3, column=2, sticky=tkinter.W)

    page_size_frame = tkinter.LabelFrame(frame1.interior, text="Page size")
    page_size_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    OptionMenu(
        page_size_frame,
        args["pagesize_dropdown"],
        *(["auto", "custom"] + sorted(papernames.values())),
        state=tkinter.DISABLED,
    ).grid(row=1, column=0, columnspan=3, sticky=tkinter.W)

    tkinter.Label(
        page_size_frame, text="Width:", state=tkinter.DISABLED, name="size_label_width"
    ).grid(row=2, column=0, sticky=tkinter.W)
    tkinter.Spinbox(
        page_size_frame,
        format="%.2f",
        increment=0.01,
        from_=0,
        to=100,
        width=5,
        state=tkinter.DISABLED,
        name="spinbox_width",
    ).grid(row=2, column=1, sticky=tkinter.W)
    tkinter.Label(
        page_size_frame, text="mm", state=tkinter.DISABLED, name="size_label_width_mm"
    ).grid(row=2, column=2, sticky=tkinter.W)

    tkinter.Label(
        page_size_frame,
        text="Height:",
        state=tkinter.DISABLED,
        name="size_label_height",
    ).grid(row=3, column=0, sticky=tkinter.W)
    tkinter.Spinbox(
        page_size_frame,
        format="%.2f",
        increment=0.01,
        from_=0,
        to=100,
        width=5,
        state=tkinter.DISABLED,
        name="spinbox_height",
    ).grid(row=3, column=1, sticky=tkinter.W)
    tkinter.Label(
        page_size_frame, text="mm", state=tkinter.DISABLED, name="size_label_height_mm"
    ).grid(row=3, column=2, sticky=tkinter.W)
    layout_frame = tkinter.LabelFrame(frame1.interior, text="Layout")
    layout_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    tkinter.Label(layout_frame, text="border", state=tkinter.DISABLED).grid(
        row=0, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(layout_frame, state=tkinter.DISABLED).grid(
        row=0, column=1, sticky=tkinter.W
    )
    tkinter.Label(layout_frame, text="fit", state=tkinter.DISABLED).grid(
        row=1, column=0, sticky=tkinter.W
    )
    OptionMenu(
        layout_frame, args["fit"], *[v.name for v in FitMode], state=tkinter.DISABLED
    ).grid(row=1, column=1, sticky=tkinter.W)
    tkinter.Checkbutton(
        layout_frame,
        text="auto orient",
        state=tkinter.DISABLED,
        variable=args["auto_orient"],
    ).grid(row=2, column=0, columnspan=2, sticky=tkinter.W)
    tkinter.Label(layout_frame, text="crop border", state=tkinter.DISABLED).grid(
        row=3, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(layout_frame, state=tkinter.DISABLED).grid(
        row=3, column=1, sticky=tkinter.W
    )
    tkinter.Label(layout_frame, text="bleed border", state=tkinter.DISABLED).grid(
        row=4, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(layout_frame, state=tkinter.DISABLED).grid(
        row=4, column=1, sticky=tkinter.W
    )
    tkinter.Label(layout_frame, text="trim border", state=tkinter.DISABLED).grid(
        row=5, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(layout_frame, state=tkinter.DISABLED).grid(
        row=5, column=1, sticky=tkinter.W
    )
    tkinter.Label(layout_frame, text="art border", state=tkinter.DISABLED).grid(
        row=6, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(layout_frame, state=tkinter.DISABLED).grid(
        row=6, column=1, sticky=tkinter.W
    )
    metadata_frame = tkinter.LabelFrame(frame1.interior, text="PDF metadata")
    metadata_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    tkinter.Label(metadata_frame, text="title", state=tkinter.DISABLED).grid(
        row=0, column=0, sticky=tkinter.W
    )
    tkinter.Entry(
        metadata_frame, textvariable=args["title"], state=tkinter.DISABLED
    ).grid(row=0, column=1, sticky=tkinter.W)
    tkinter.Label(metadata_frame, text="author", state=tkinter.DISABLED).grid(
        row=1, column=0, sticky=tkinter.W
    )
    tkinter.Entry(
        metadata_frame, textvariable=args["author"], state=tkinter.DISABLED
    ).grid(row=1, column=1, sticky=tkinter.W)
    tkinter.Label(metadata_frame, text="creator", state=tkinter.DISABLED).grid(
        row=2, column=0, sticky=tkinter.W
    )
    tkinter.Entry(
        metadata_frame, textvariable=args["creator"], state=tkinter.DISABLED
    ).grid(row=2, column=1, sticky=tkinter.W)
    tkinter.Label(metadata_frame, text="producer", state=tkinter.DISABLED).grid(
        row=3, column=0, sticky=tkinter.W
    )
    tkinter.Entry(
        metadata_frame, textvariable=args["producer"], state=tkinter.DISABLED
    ).grid(row=3, column=1, sticky=tkinter.W)
    tkinter.Label(metadata_frame, text="creation date", state=tkinter.DISABLED).grid(
        row=4, column=0, sticky=tkinter.W
    )
    tkinter.Entry(
        metadata_frame, textvariable=args["creationdate"], state=tkinter.DISABLED
    ).grid(row=4, column=1, sticky=tkinter.W)
    tkinter.Label(
        metadata_frame, text="modification date", state=tkinter.DISABLED
    ).grid(row=5, column=0, sticky=tkinter.W)
    tkinter.Entry(
        metadata_frame, textvariable=args["moddate"], state=tkinter.DISABLED
    ).grid(row=5, column=1, sticky=tkinter.W)
    tkinter.Label(metadata_frame, text="subject", state=tkinter.DISABLED).grid(
        row=6, column=0, sticky=tkinter.W
    )
    tkinter.Entry(metadata_frame, state=tkinter.DISABLED).grid(
        row=6, column=1, sticky=tkinter.W
    )
    tkinter.Label(metadata_frame, text="keywords", state=tkinter.DISABLED).grid(
        row=7, column=0, sticky=tkinter.W
    )
    tkinter.Entry(metadata_frame, state=tkinter.DISABLED).grid(
        row=7, column=1, sticky=tkinter.W
    )
    viewer_frame = tkinter.LabelFrame(frame1.interior, text="PDF viewer options")
    viewer_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)
    tkinter.Label(viewer_frame, text="panes", state=tkinter.DISABLED).grid(
        row=0, column=0, sticky=tkinter.W
    )
    OptionMenu(
        viewer_frame,
        args["viewer_panes"],
        *(["auto"] + [v.name for v in PageMode]),
        state=tkinter.DISABLED,
    ).grid(row=0, column=1, sticky=tkinter.W)
    tkinter.Label(viewer_frame, text="initial page", state=tkinter.DISABLED).grid(
        row=1, column=0, sticky=tkinter.W
    )
    tkinter.Spinbox(
        viewer_frame,
        increment=1,
        from_=1,
        to=10000,
        width=6,
        textvariable=args["viewer_initial_page"],
        state=tkinter.DISABLED,
        name="viewer_initial_page_spinbox",
    ).grid(row=1, column=1, sticky=tkinter.W)
    tkinter.Label(viewer_frame, text="magnification", state=tkinter.DISABLED).grid(
        row=2, column=0, sticky=tkinter.W
    )
    OptionMenu(
        viewer_frame,
        args["viewer_magnification"],
        *(["auto", "custom"] + [v.name for v in Magnification]),
        state=tkinter.DISABLED,
    ).grid(row=2, column=1, sticky=tkinter.W)
    tkinter.Label(viewer_frame, text="page layout", state=tkinter.DISABLED).grid(
        row=3, column=0, sticky=tkinter.W
    )
    OptionMenu(
        viewer_frame,
        args["viewer_page_layout"],
        *(["auto"] + [v.name for v in PageLayout]),
        state=tkinter.DISABLED,
    ).grid(row=3, column=1, sticky=tkinter.W)
    tkinter.Checkbutton(
        viewer_frame,
        text="fit window to page size",
        variable=args["viewer_fit_window"],
        state=tkinter.DISABLED,
    ).grid(row=4, column=0, columnspan=2, sticky=tkinter.W)
    tkinter.Checkbutton(
        viewer_frame,
        text="center window",
        variable=args["viewer_center_window"],
        state=tkinter.DISABLED,
    ).grid(row=5, column=0, columnspan=2, sticky=tkinter.W)
    tkinter.Checkbutton(
        viewer_frame,
        text="open in fullscreen",
        variable=args["viewer_fullscreen"],
        state=tkinter.DISABLED,
    ).grid(row=6, column=0, columnspan=2, sticky=tkinter.W)

    option_frame = tkinter.LabelFrame(frame1.interior, text="Program options")
    option_frame.pack(side=tkinter.TOP, expand=tkinter.TRUE, fill=tkinter.X)

    tkinter.Label(option_frame, text="Unit:", state=tkinter.DISABLED).grid(
        row=0, column=0, sticky=tkinter.W
    )
    unit = tkinter.StringVar()
    unit.set("mm")
    OptionMenu(option_frame, unit, ["mm"], state=tkinter.DISABLED).grid(
        row=0, column=1, sticky=tkinter.W
    )

    tkinter.Label(option_frame, text="Language:", state=tkinter.DISABLED).grid(
        row=1, column=0, sticky=tkinter.W
    )
    language = tkinter.StringVar()
    language.set("English")
    OptionMenu(option_frame, language, ["English"], state=tkinter.DISABLED).grid(
        row=1, column=1, sticky=tkinter.W
    )

    bottom_frame = tkinter.Frame(frame_right)
    bottom_frame.pack(fill=tkinter.X)

    tkinter.Button(bottom_frame, text="Save PDF", command=on_save_button).pack(
        side=tkinter.LEFT, expand=tkinter.TRUE, fill=tkinter.X
    )
    tkinter.Button(bottom_frame, text="Exit", command=root.destroy).pack(
        side=tkinter.RIGHT, expand=tkinter.TRUE, fill=tkinter.X
    )

    app.mainloop()


def file_is_icc(fname):
    with open(fname, "rb") as f:
        data = f.read(40)
    if len(data) < 40:
        return False
    return data[36:] == b"acsp"


def validate_icc(fname):
    if not file_is_icc(fname):
        raise argparse.ArgumentTypeError('"%s" is not an ICC profile' % fname)
    return fname


def get_default_icc_profile():
    for profile in [
        "/usr/share/color/icc/sRGB.icc",
        "/usr/share/color/icc/OpenICC/sRGB.icc",
        "/usr/share/color/icc/colord/sRGB.icc",
    ]:
        if not os.path.exists(profile):
            continue
        if not file_is_icc(profile):
            continue
        return profile
    return "/usr/share/color/icc/sRGB.icc"


def get_main_parser():
    rendered_papersizes = ""
    for k, v in sorted(papersizes.items()):
        rendered_papersizes += "    %-8s %s\n" % (papernames[k], v)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
Losslessly 
""",
        epilog="""\
Colorspace:
%s

Fit options:
"""
        % rendered_papersizes,
    )

    parser.add_argument(
        "images",
        metavar="infile",
        type=input_images,
        nargs="*",
        help="Specifies the input file(s) in any format that can be read by "
        "the Python Imaging Library (PIL). If no input images are given, then "
        'a single image is read from standard input. The special filename "-" '
        "can be used once to read an image from standard input. To read a "
        'file in the current directory with the filename "-" (or with a '
        'filename starting with "-"), pass it to img2pdf by explicitly '
        'stating its relative path like "./-". Cannot be used together with '
        "--from-file.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Makes the program operate in verbose mode, printing messages on "
        "standard error.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s " + __version__,
        help="Prints version information and exits.",
    )
    parser.add_argument(
        "--gui", dest="gui", action="store_true", help="run experimental tkinter gui"
    )
    parser.add_argument(
        "--from-file",
        metavar="FILE",
        type=from_file,
        default=[],
        help="Read the list of images from FILE instead of passing them as "
        "positional arguments. If this option is used, then the list of "
        "positional arguments must be empty. The paths to the input images "
        'in FILE are separated by NUL bytes. If FILE is "-" then the paths '
        "are expected on standard input. This option is useful if you want "
        "to pass more images than the maximum command length of your shell "
        "permits. This option can be used with commands like `find -print0`.",
    )

    outargs = parser.add_argument_group(
        title="General output arguments",
        description="Arguments controlling the output format.",
    )

    # In Python3 we have to output to sys.stdout.buffer because we write are
    # bytes and not strings. In certain situations, like when the main
    # function is wrapped by contextlib.redirect_stdout(), sys.stdout does not
    # have the buffer attribute. Thus we write to sys.stdout by default and
    # to sys.stdout.buffer if it exists.
    outargs.add_argument(
        "-o",
        "--output",
        metavar="out",
        type=argparse.FileType("wb"),
        default=sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout,
        help="Makes the program output to a file instead of standard output.",
    )
    outargs.add_argument(
        "-C",
        "--colorspace",
        metavar="colorspace",
        type=parse_colorspacearg,
        help="""
Forces the PIL colorspace. See the epilogue for a list of possible values.
Usually the PDF colorspace would be derived from the color space of the input
image. This option overwrites the automatically detected colorspace from the
input image and thus forces a certain colorspace in the output PDF /ColorSpace
property. This is useful for JPEG 2000 images with a different colorspace than
RGB.""",
    )

    outargs.add_argument(
        "-D",
        "--nodate",
        action="store_true",
        help="Suppresses timestamps in the output and thus makes the output "
        "deterministic between individual runs. You can also manually "
        "set a date using the --moddate and --creationdate options.",
    )

    outargs.add_argument(
        "--engine",
        metavar="engine",
        type=parse_enginearg,
        help="Choose PDF engine. Can be either internal, pikepdf or pdfrw. "
        "The internal engine does not have additional requirements and writes "
        "out a human readable PDF. The pikepdf engine requires the pikepdf "
        "Python module and qpdf library, is most featureful, can "
        'linearize PDFs ("fast web view") and can compress more parts of it.'
        "The pdfrw engine requires the pdfrw Python "
        "module but does not support unicode metadata (See "
        "https://github.com/pmaupin/pdfrw/issues/39) or palette data (See "
        "https://github.com/pmaupin/pdfrw/issues/128).",
    )

    outargs.add_argument(
        "--first-frame-only",
        action="store_true",
        help="By default, img2pdf will convert multi-frame images like "
        "multi-page TIFF or animated GIF images to one page per frame. "
        "This option will only let the first frame of every multi-frame "
        "input image be converted into a page in the resulting PDF.",
    )

    outargs.add_argument(
        "--include-thumbnails",
        action="store_true",
        help="Some multi-frame formats like MPO carry a main image and "
        "one or more scaled-down copies of the main image (thumbnails). "
        "In such a case, img2pdf will only include the main image and "
        "not create additional pages for each of the thumbnails. If this "
        "option is set, img2pdf will instead create one page per frame and "
        "thus store each thumbnail on its own page.",
    )

    outargs.add_argument(
        "--pillow-limit-break",
        action="store_true",
        help="img2pdf uses the Python Imaging Library Pillow to read input "
        "images. Pillow limits the maximum input image size to %d pixels "
        "to prevent decompression bomb denial of service attacks. If "
        "your input image contains more pixels than that, use this "
        "option to disable this safety measure during this run of img2pdf"
        % Image.MAX_IMAGE_PIXELS,
    )

    if sys.platform == "win32":
        # on Windows, there are no default paths to search for an ICC profile
        # so make the argument required instead of optional
        outargs.add_argument(
            "--pdfa",
            type=validate_icc,
            help="Output a PDF/A-1b compliant document. The argument to this "
            "option is the path to the ICC profile that will be embedded into "
            "the resulting PDF.",
        )
    else:
        outargs.add_argument(
            "--pdfa",
            nargs="?",
            const=get_default_icc_profile(),
            default=None,
            type=validate_icc,
            help="Output a PDF/A-1b compliant document. By default, this will "
            "embed either /usr/share/color/icc/sRGB.icc, "
            "/usr/share/color/icc/OpenICC/sRGB.icc or "
            "/usr/share/color/icc/colord/sRGB.icc as the color profile, whichever "
            "is found to exist first.",
        )

    sizeargs = parser.add_argument_group(
        title="Image and page size and layout arguments",
        description="""\
Every input image will be placed on its own page. The image size is controlled
by the dpi value of the input image or, if unset or missing, the default dpi of
%.2f. By default, each page will have the same size as the image it shows.
Thus, there will be no visible border between the image and the page border by
default. If image size and page size are made different from each other by the
options in this section, the image will always be centered in both dimensions.

The image size and page size can be explicitly set using the --imgsize and
--pagesize options, respectively.  If either dimension of the image size is
specified but the same dimension of the page size is not, then the latter will
be derived from the former using an optional minimal distance between the image
and the page border (given by the --border option) and/or a certain fitting
strategy (given by the --fit option). The converse happens if a dimension of
the page size is set but the same dimension of the image size is not.

Any length value in below options is represented by the meta variable L which
is a floating point value with an optional unit appended (without a space
between them). The default unit is pt (1/72 inch, the PDF unit) and other
allowed units are cm (centimeter), mm (millimeter), and in (inch).

Any size argument of the format LxL in the options below specifies the width
and height of a rectangle where the first L represents the width and the second
L represents the height with an optional unit following each value as described
above.  Either width or height may be omitted. If the height is omitted, the
separating x can be omitted as well. Omitting the width requires to prefix the
height with the separating x. The missing dimension will be chosen so to not
change the image aspect ratio. Instead of giving the width and height
explicitly, you may also specify some (case-insensitive) common page sizes such
as letter and A4.  See the epilogue at the bottom for a complete list of the
valid sizes.

The --fit option scales to fit the image into a rectangle that is either
derived from the --imgsize option or otherwise from the --pagesize option.
If the --border option is given in addition to the --imgsize option while the
--pagesize option is not given, then the page size will be calculated from the
image size, respecting the border setting. If the --border option is given in
addition to the --pagesize option while the --imgsize option is not given, then
the image size will be calculated from the page size, respecting the border
setting. If the --border option is given while both the --pagesize and
--imgsize options are passed, then the --border option will be ignored.

The --pagesize option or the --imgsize option with the --border option will
determine the MediaBox size of the resulting PDF document.
"""
        % default_dpi,
    )

    sizeargs.add_argument(
        "-S",
        "--pagesize",
        metavar="LxL",
        type=parse_pagesize_rectarg,
        help="""
Sets the size of the PDF pages. The short-option is the upper case S because
it is an mnemonic for being bigger than the image size.""",
    )

    sizeargs.add_argument(
        "-s",
        "--imgsize",
        metavar="LxL",
        type=parse_imgsize_rectarg,
        help="""
Sets the size of the images on the PDF pages.  In addition, the unit dpi is
allowed which will set the image size as a value of dots per inch.  Instead of
a unit, width and height values may also have a percentage sign appended,
indicating a resize of the image by that percentage. The short-option is the
lower case s because it is an mnemonic for being smaller than the page size.
""",
    )
    sizeargs.add_argument(
        "-b",
        "--border",
        metavar="L[:L]",
        type=parse_borderarg,
        help="""
Specifies the minimal distance between the image border and the PDF page
border.  This value Is overwritten by explicit values set by --pagesize or
--imgsize.  The value will be used when calculating page dimensions from the
image dimensions or the other way round. One, or two length values can be given
as an argument, separated by a colon. One value specifies the minimal border on
all four sides. Two values specify the minimal border on the top/bottom and
left/right, respectively. It is not possible to specify asymmetric borders
because images will always be centered on the page.
""",
    )
    sizeargs.add_argument(
        "-f",
        "--fit",
        metavar="FIT",
        type=parse_fitarg,
        default=FitMode.into,
        help="""

If --imgsize is given, fits the image using these dimensions. Otherwise, fit
the image into the dimensions given by --pagesize.  FIT is one of into, fill,
exact, shrink and enlarge. The default value is "into". See the epilogue at the
bottom for a description of the FIT options.

""",
    )
    sizeargs.add_argument(
        "-a",
        "--auto-orient",
        action="store_true",
        help="""
If both dimensions of the page are given via --pagesize, conditionally swaps
these dimensions such that the page orientation is the same as the orientation
of the input image. If the orientation of a page gets flipped, then so do the
values set via the --border option.
""",
    )
    sizeargs.add_argument(
        "-r",
        "--rotation",
        "--orientation",
        metavar="ROT",
        type=parse_rotationarg,
        default=Rotation.auto,
        help="""
Specifies how input images should be rotated. ROT can be one of auto, none,
ifvalid, 0, 90, 180 and 270. The default value is auto and indicates that input
images are rotated according to their EXIF Orientation tag. The values none and
0 ignore the EXIF Orientation values of the input images. The value ifvalid
acts like auto but ignores invalid EXIF rotation values and only issues a
warning instead of throwing an error. This is useful because many devices like
Android phones, Canon cameras or scanners emit an invalid Orientation tag value
of zero. The values 90, 180 and 270 perform a clockwise rotation of the image.
            """,
    )
    sizeargs.add_argument(
        "--crop-border",
        metavar="L[:L]",
        type=parse_borderarg,
        help="""
Specifies the border between the CropBox and the MediaBox. One, or two length
values can be given as an argument, separated by a colon. One value specifies
the border on all four sides. Two values specify the border on the top/bottom
and left/right, respectively. It is not possible to specify asymmetric borders.
""",
    )
    sizeargs.add_argument(
        "--bleed-border",
        metavar="L[:L]",
        type=parse_borderarg,
        help="""
Specifies the border between the BleedBox and the MediaBox. One, or two length
values can be given as an argument, separated by a colon. One value specifies
the border on all four sides. Two values specify the border on the top/bottom
and left/right, respectively. It is not possible to specify asymmetric borders.
""",
    )
    sizeargs.add_argument(
        "--trim-border",
        metavar="L[:L]",
        type=parse_borderarg,
        help="""
Specifies the border between the TrimBox and the MediaBox. One, or two length
values can be given as an argument, separated by a colon. One value specifies
the border on all four sides. Two values specify the border on the top/bottom
and left/right, respectively. It is not possible to specify asymmetric borders.
""",
    )
    sizeargs.add_argument(
        "--art-border",
        metavar="L[:L]",
        type=parse_borderarg,
        help="""
Specifies the border between the ArtBox and the MediaBox. One, or two length
values can be given as an argument, separated by a colon. One value specifies
the border on all four sides. Two values specify the border on the top/bottom
and left/right, respectively. It is not possible to specify asymmetric borders.
""",
    )

    metaargs = parser.add_argument_group(
        title="Arguments setting metadata",
        description="Options handling embedded timestamps, title and author "
        "information.",
    )
    metaargs.add_argument(
        "--title", metavar="title", type=str, help="Sets the title metadata value"
    )
    metaargs.add_argument(
        "--author", metavar="author", type=str, help="Sets the author metadata value"
    )
    metaargs.add_argument(
        "--creator", metavar="creator", type=str, help="Sets the creator metadata value"
    )
    metaargs.add_argument(
        "--producer",
        metavar="producer",
        type=str,
        default="img2pdf " + __version__,
        help="Sets the producer metadata value "
        "(default is: img2pdf " + __version__ + ")",
    )
    metaargs.add_argument(
        "--creationdate",
        metavar="creationdate",
        type=valid_date,
        help="Sets the UTC creation date metadata value in YYYY-MM-DD or "
        "YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS format or any format "
        "understood by python dateutil module or any format understood "
        "by `date --date`",
    )
    metaargs.add_argument(
        "--moddate",
        metavar="moddate",
        type=valid_date,
        help="Sets the UTC modification date metadata value in YYYY-MM-DD "
        "or YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS format or any format "
        "understood by python dateutil module or any format understood "
        "by `date --date`",
    )
    metaargs.add_argument(
        "--subject", metavar="subject", type=str, help="Sets the subject metadata value"
    )
    metaargs.add_argument(
        "--keywords",
        metavar="kw",
        type=str,
        nargs="+",
        help="Sets the keywords metadata value (can be given multiple times)",
    )

    viewerargs = parser.add_argument_group(
        title="PDF viewer arguments",
        description="PDF files can specify how they are meant to be "
        "presented to the user by a PDF viewer",
    )

    viewerargs.add_argument(
        "--viewer-panes",
        metavar="PANES",
        type=parse_panes,
        help="Instruct the PDF viewer which side panes to show. Valid values "
        'are "outlines" and "thumbs". It is not possible to specify both '
        "at the same time.",
    )
    viewerargs.add_argument(
        "--viewer-initial-page",
        metavar="NUM",
        type=int,
        help="Instead of showing the first page, instruct the PDF viewer to "
        "show the given page instead. Page numbers start with 1.",
    )
    viewerargs.add_argument(
        "--viewer-magnification",
        metavar="MAG",
        type=parse_magnification,
        help="Instruct the PDF viewer to open the PDF with a certain zoom "
        "level. Valid values are either a floating point number giving "
        'the exact zoom level, "fit" (zoom to fit whole page), "fith" '
        '(zoom to fit page width) and "fitbh" (zoom to fit visible page '
        "width).",
    )
    viewerargs.add_argument(
        "--viewer-page-layout",
        metavar="LAYOUT",
        type=parse_layout,
        help="Instruct the PDF viewer how to arrange the pages on the screen. "
        'Valid values are "single" (display single pages), "onecolumn" '
        '(one continuous column), "twocolumnright" (two continuous '
        'columns with odd number pages on the right) and "twocolumnleft" '
        "(two continuous columns with odd numbered pages on the left), "
        '"twopageright" (two pages with odd numbered page on the right) '
        'and "twopageleft" (two pages with odd numbered page on the left)',
    )
    viewerargs.add_argument(
        "--viewer-fit-window",
        action="store_true",
        help="Instruct the PDF viewer to resize the window to fit the page size",
    )
    viewerargs.add_argument(
        "--viewer-center-window",
        action="store_true",
        help="Instruct the PDF viewer to center the PDF viewer window",
    )
    viewerargs.add_argument(
        "--viewer-fullscreen",
        action="store_true",
        help="Instruct the PDF viewer to open the PDF in fullscreen mode",
    )
    return parser


def main(argv=sys.argv):
    args = get_main_parser().parse_args(argv[1:])

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.pillow_limit_break:
        Image.MAX_IMAGE_PIXELS = None

    if args.gui:
        gui()
        sys.exit(0)

    layout_fun = get_layout_fun(
        args.pagesize, args.imgsize, args.border, args.fit, args.auto_orient
    )

    if len(args.images) > 0 and len(args.from_file) > 0:
        logger.error(
            "%s: error: cannot use --from-file with positional arguments" % parser.prog
        )
        sys.exit(2)
    elif len(args.images) == 0 and len(args.from_file) == 0:
        # if no positional arguments were supplied, read a single image from
        # standard input
        print(
            "Reading image from standard input...\n"
            "Re-run with -h or --help for usage information.",
            file=sys.stderr,
        )
        try:
            images = [sys.stdin.buffer.read()]
        except KeyboardInterrupt:
            sys.exit(0)
    elif len(args.images) > 0 and len(args.from_file) == 0:
        # On windows, each positional argument can expand into multiple paths
        # because we do globbing ourselves. Here we flatten the list of lists
        # again.
        images = list(chain.from_iterable(args.images))
    elif len(args.images) == 0 and len(args.from_file) > 0:
        images = args.from_file

    # with the number of pages being equal to the number of images, the
    # value passed to --viewer-initial-page must be between 1 and that number
    if args.viewer_initial_page is not None:
        if args.viewer_initial_page < 1:
            parser.print_usage(file=sys.stderr)
            logger.error(
                "%s: error: argument --viewer-initial-page: must be "
                "greater than zero" % parser.prog
            )
            sys.exit(2)
        if args.viewer_initial_page > len(images):
            parser.print_usage(file=sys.stderr)
            logger.error(
                "%s: error: argument --viewer-initial-page: must be "
                "less than or equal to the total number of pages" % parser.prog
            )
            sys.exit(2)

    try:
        convert(
            *images,
            engine=args.engine,
            title=args.title,
            author=args.author,
            creator=args.creator,
            producer=args.producer,
            creationdate=args.creationdate,
            moddate=args.moddate,
            subject=args.subject,
            keywords=args.keywords,
            colorspace=args.colorspace,
            nodate=args.nodate,
            layout_fun=layout_fun,
            viewer_panes=args.viewer_panes,
            viewer_initial_page=args.viewer_initial_page,
            viewer_magnification=args.viewer_magnification,
            viewer_page_layout=args.viewer_page_layout,
            viewer_fit_window=args.viewer_fit_window,
            viewer_center_window=args.viewer_center_window,
            viewer_fullscreen=args.viewer_fullscreen,
            outputstream=args.output,
            first_frame_only=args.first_frame_only,
            cropborder=args.crop_border,
            bleedborder=args.bleed_border,
            trimborder=args.trim_border,
            artborder=args.art_border,
            pdfa=args.pdfa,
            rotation=args.rotation,
            include_thumbnails=args.include_thumbnails,
        )
    except Exception as e:
        logger.error("error: " + str(e))
        if logger.isEnabledFor(logging.DEBUG):
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
