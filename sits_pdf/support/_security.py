import struct
from hashlib import md5
from typing import Tuple, Union
from ._utils import b_, ord_, str_
from .generic import ByteStringObject
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
_encryption_padding = (
    b"\x28\xbf\x4e\x5e\x4e\x75\x8a\x41\x64\x00\x4e\x56"
    b"\xff\xfa\x01\x08\x2e\x2e\x00\xb6\xd0\x68\x3e\x80\x2f\x0c"
    b"\xa9\xfe\x64\x53\x69\x7a"
)
def _alg32(
    password: str,
    rev: Literal[2, 3, 4],
    keylen: int,
    owner_entry: ByteStringObject,
    p_entry: int,
    id1_entry: ByteStringObject,
    metadata_encrypt: bool = True,
) -> bytes:
    password_bytes = b_((str_(password) + str_(_encryption_padding))[:32])
    m = md5(password_bytes)
    m.update(owner_entry.original_bytes)
    p_entry_bytes = struct.pack("<i", p_entry)
    m.update(p_entry_bytes)
    m.update(id1_entry.original_bytes)
    if rev >= 3 and not metadata_encrypt:
        m.update(b"\xff\xff\xff\xff")
    md5_hash = m.digest()
    if rev >= 3:
        for _ in range(50):
            md5_hash = md5(md5_hash[:keylen]).digest()
    return md5_hash[:keylen]

def _alg33(
    owner_password: str, user_password: str, rev: Literal[2, 3, 4], keylen: int
) -> bytes:
    key = _alg33_1(owner_password, rev, keylen)
    user_password_bytes = b_((user_password + str_(_encryption_padding))[:32])
    val = RC4_encrypt(key, user_password_bytes)
    if rev >= 3:
        for i in range(1, 20):
            new_key = ""
            for key_char in key:
                new_key += chr(ord_(key_char) ^ i)
            val = RC4_encrypt(new_key, val)
    return val


def _alg33_1(password: str, rev: Literal[2, 3, 4], keylen: int) -> bytes:
    password_bytes = b_((password + str_(_encryption_padding))[:32])
    m = md5(password_bytes)
    md5_hash = m.digest()
    if rev >= 3:
        for _ in range(50):
            md5_hash = md5(md5_hash).digest()
    key = md5_hash[:keylen]
    return key


def _alg34(
    password: str,
    owner_entry: ByteStringObject,
    p_entry: int,
    id1_entry: ByteStringObject,
) -> Tuple[bytes, bytes]:
    rev: Literal[2] = 2
    keylen = 5
    key = _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry)
    U = RC4_encrypt(key, _encryption_padding)
    return U, key


def _alg35(
    password: str,
    rev: Literal[2, 3, 4],
    keylen: int,
    owner_entry: ByteStringObject,
    p_entry: int,
    id1_entry: ByteStringObject,
    metadata_encrypt: bool,
) -> Tuple[bytes, bytes]:
    key = _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry)
    m = md5()
    m.update(_encryption_padding)
    m.update(id1_entry.original_bytes)
    md5_hash = m.digest()
    val = RC4_encrypt(key, md5_hash)
    for i in range(1, 20):
        new_key = b""
        for k in key:
            new_key += b_(chr(ord_(k) ^ i))
        val = RC4_encrypt(new_key, val)
    return val + (b"\x00" * 16), key


def RC4_encrypt(key: Union[str, bytes], plaintext: bytes) -> bytes:  # TODO
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + ord_(key[i % len(key)])) % 256
        S[i], S[j] = S[j], S[i]
    i, j = 0, 0
    retval = []
    for plaintext_char in plaintext:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        t = S[(S[i] + S[j]) % 256]
        retval.append(b_(chr(ord_(plaintext_char) ^ t)))
    return b"".join(retval)
