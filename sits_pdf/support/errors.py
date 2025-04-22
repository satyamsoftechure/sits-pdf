class DeprecationError(Exception):
    pass


class DependencyError(Exception):
    pass


class PyPdfError(Exception):
    pass


class PdfReadError(PyPdfError):
    pass


class PageSizeNotDefinedError(PyPdfError):
    pass


class PdfReadWarning(UserWarning):
    pass


class PdfStreamError(PdfReadError):
    pass


class ParseError(Exception):
    pass


class FileNotDecryptedError(PdfReadError):
    pass


class WrongPasswordError(FileNotDecryptedError):
    pass


class EmptyFileError(PdfReadError):
    pass


STREAM_TRUNCATED_PREMATURELY = "Stream has ended unexpectedly"
