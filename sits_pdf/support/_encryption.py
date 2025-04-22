import hashlib
import random
import struct
from enum import IntEnum
from typing import Any, Dict, Optional, Tuple, Union, cast
from ._utils import logger_warning
from .errors import DependencyError
from .generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    PdfObject,
    StreamObject,
    TextStringObject,
    create_string_object,
)


class CryptBase:
    def encrypt(self, data: bytes) -> bytes:  
        return data

    def decrypt(self, data: bytes) -> bytes:  
        return data


class CryptIdentity(CryptBase):
    pass


try:
    from Crypto.Cipher import AES, ARC4  # type: ignore[import]
    from Crypto.Util.Padding import pad  # type: ignore[import]

    class CryptRC4(CryptBase):
        def __init__(self, key: bytes) -> None:
            self.key = key

        def encrypt(self, data: bytes) -> bytes:
            return ARC4.ARC4Cipher(self.key).encrypt(data)

        def decrypt(self, data: bytes) -> bytes:
            return ARC4.ARC4Cipher(self.key).decrypt(data)

    class CryptAES(CryptBase):
        def __init__(self, key: bytes) -> None:
            self.key = key

        def encrypt(self, data: bytes) -> bytes:
            iv = bytes(bytearray(random.randint(0, 255) for _ in range(16)))
            p = 16 - len(data) % 16
            data += bytes(bytearray(p for _ in range(p)))
            aes = AES.new(self.key, AES.MODE_CBC, iv)
            return iv + aes.encrypt(data)

        def decrypt(self, data: bytes) -> bytes:
            iv = data[:16]
            data = data[16:]
            aes = AES.new(self.key, AES.MODE_CBC, iv)
            if len(data) % 16:
                data = pad(data, 16)
            d = aes.decrypt(data)
            if len(d) == 0:
                return d
            else:
                return d[: -d[-1]]

    def RC4_encrypt(key: bytes, data: bytes) -> bytes:
        return ARC4.ARC4Cipher(key).encrypt(data)

    def RC4_decrypt(key: bytes, data: bytes) -> bytes:
        return ARC4.ARC4Cipher(key).decrypt(data)

    def AES_ECB_encrypt(key: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_ECB).encrypt(data)

    def AES_ECB_decrypt(key: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_ECB).decrypt(data)

    def AES_CBC_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_CBC, iv).encrypt(data)

    def AES_CBC_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_CBC, iv).decrypt(data)

except ImportError:

    class CryptRC4(CryptBase):  # type: ignore
        def __init__(self, key: bytes) -> None:
            self.S = list(range(256))
            j = 0
            for i in range(256):
                j = (j + self.S[i] + key[i % len(key)]) % 256
                self.S[i], self.S[j] = self.S[j], self.S[i]

        def encrypt(self, data: bytes) -> bytes:
            S = list(self.S)
            out = list(0 for _ in range(len(data)))
            i, j = 0, 0
            for k in range(len(data)):
                i = (i + 1) % 256
                j = (j + S[i]) % 256
                S[i], S[j] = S[j], S[i]
                x = S[(S[i] + S[j]) % 256]
                out[k] = data[k] ^ x
            return bytes(bytearray(out))

        def decrypt(self, data: bytes) -> bytes:
            return self.encrypt(data)

    class CryptAES(CryptBase): 
        def __init__(self, key: bytes) -> None:
            pass

        def encrypt(self, data: bytes) -> bytes:
            raise DependencyError("PyCryptodome is required for AES algorithm")

        def decrypt(self, data: bytes) -> bytes:
            raise DependencyError("PyCryptodome is required for AES algorithm")

    def RC4_encrypt(key: bytes, data: bytes) -> bytes:
        return CryptRC4(key).encrypt(data)

    def RC4_decrypt(key: bytes, data: bytes) -> bytes:
        return CryptRC4(key).decrypt(data)

    def AES_ECB_encrypt(key: bytes, data: bytes) -> bytes:
        raise DependencyError("PyCryptodome is required for AES algorithm")

    def AES_ECB_decrypt(key: bytes, data: bytes) -> bytes:
        raise DependencyError("PyCryptodome is required for AES algorithm")

    def AES_CBC_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
        raise DependencyError("PyCryptodome is required for AES algorithm")

    def AES_CBC_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
        raise DependencyError("PyCryptodome is required for AES algorithm")


class CryptFilter:
    def __init__(
        self, stmCrypt: CryptBase, strCrypt: CryptBase, efCrypt: CryptBase
    ) -> None:
        self.stmCrypt = stmCrypt
        self.strCrypt = strCrypt
        self.efCrypt = efCrypt

    def encrypt_object(self, obj: PdfObject) -> PdfObject:
        # TODO
        return NotImplemented

    def decrypt_object(self, obj: PdfObject) -> PdfObject:
        if isinstance(obj, (ByteStringObject, TextStringObject)):
            data = self.strCrypt.decrypt(obj.original_bytes)
            obj = create_string_object(data)
        elif isinstance(obj, StreamObject):
            obj._data = self.stmCrypt.decrypt(obj._data)
        elif isinstance(obj, DictionaryObject):
            for dictkey, value in list(obj.items()):
                obj[dictkey] = self.decrypt_object(value)
        elif isinstance(obj, ArrayObject):
            for i in range(len(obj)):
                obj[i] = self.decrypt_object(obj[i])
        return obj


_PADDING = bytes(
    [
        0x28,
        0xBF,
        0x4E,
        0x5E,
        0x4E,
        0x75,
        0x8A,
        0x41,
        0x64,
        0x00,
        0x4E,
        0x56,
        0xFF,
        0xFA,
        0x01,
        0x08,
        0x2E,
        0x2E,
        0x00,
        0xB6,
        0xD0,
        0x68,
        0x3E,
        0x80,
        0x2F,
        0x0C,
        0xA9,
        0xFE,
        0x64,
        0x53,
        0x69,
        0x7A,
    ]
)


def _padding(data: bytes) -> bytes:
    return (data + _PADDING)[:32]


class AlgV4:
    @staticmethod
    def compute_key(
        password: bytes,
        rev: int,
        key_size: int,
        o_entry: bytes,
        P: int,
        id1_entry: bytes,
        metadata_encrypted: bool,
    ) -> bytes:
        a = _padding(password)
        u_hash = hashlib.md5(a)
        u_hash.update(o_entry)
        u_hash.update(struct.pack("<I", P))
        u_hash.update(id1_entry)
        if rev >= 4 and metadata_encrypted is False:
            u_hash.update(b"\xff\xff\xff\xff")
        u_hash_digest = u_hash.digest()
        length = key_size // 8
        if rev >= 3:
            for _ in range(50):
                u_hash_digest = hashlib.md5(u_hash_digest[:length]).digest()
        return u_hash_digest[:length]

    @staticmethod
    def compute_O_value_key(owner_password: bytes, rev: int, key_size: int) -> bytes:
        a = _padding(owner_password)
        o_hash_digest = hashlib.md5(a).digest()

        if rev >= 3:
            for _ in range(50):
                o_hash_digest = hashlib.md5(o_hash_digest).digest()

        rc4_key = o_hash_digest[: key_size // 8]
        return rc4_key

    @staticmethod
    def compute_O_value(rc4_key: bytes, user_password: bytes, rev: int) -> bytes:
        """See :func:`compute_O_value_key`."""
        a = _padding(user_password)
        rc4_enc = RC4_encrypt(rc4_key, a)
        if rev >= 3:
            for i in range(1, 20):
                key = bytes(bytearray(x ^ i for x in rc4_key))
                rc4_enc = RC4_encrypt(key, rc4_enc)
        return rc4_enc

    @staticmethod
    def compute_U_value(key: bytes, rev: int, id1_entry: bytes) -> bytes:
        if rev <= 2:
            value = RC4_encrypt(key, _PADDING)
            return value
        u_hash = hashlib.md5(_PADDING)
        u_hash.update(id1_entry)
        rc4_enc = RC4_encrypt(key, u_hash.digest())
        for i in range(1, 20):
            rc4_key = bytes(bytearray(x ^ i for x in key))
            rc4_enc = RC4_encrypt(rc4_key, rc4_enc)
        return _padding(rc4_enc)

    @staticmethod
    def verify_user_password(
        user_password: bytes,
        rev: int,
        key_size: int,
        o_entry: bytes,
        u_entry: bytes,
        P: int,
        id1_entry: bytes,
        metadata_encrypted: bool,
    ) -> bytes:
        key = AlgV4.compute_key(
            user_password, rev, key_size, o_entry, P, id1_entry, metadata_encrypted
        )
        u_value = AlgV4.compute_U_value(key, rev, id1_entry)
        if rev >= 3:
            u_value = u_value[:16]
            u_entry = u_entry[:16]
        if u_value != u_entry:
            key = b""
        return key

    @staticmethod
    def verify_owner_password(
        owner_password: bytes,
        rev: int,
        key_size: int,
        o_entry: bytes,
        u_entry: bytes,
        P: int,
        id1_entry: bytes,
        metadata_encrypted: bool,
    ) -> bytes:
        rc4_key = AlgV4.compute_O_value_key(owner_password, rev, key_size)

        if rev <= 2:
            user_password = RC4_decrypt(rc4_key, o_entry)
        else:
            user_password = o_entry
            for i in range(19, -1, -1):
                key = bytes(bytearray(x ^ i for x in rc4_key))
                user_password = RC4_decrypt(key, user_password)
        return AlgV4.verify_user_password(
            user_password,
            rev,
            key_size,
            o_entry,
            u_entry,
            P,
            id1_entry,
            metadata_encrypted,
        )


class AlgV5:
    @staticmethod
    def verify_owner_password(
        R: int, password: bytes, o_value: bytes, oe_value: bytes, u_value: bytes
    ) -> bytes:
        password = password[:127]
        if (
            AlgV5.calculate_hash(R, password, o_value[32:40], u_value[:48])
            != o_value[:32]
        ):
            return b""
        iv = bytes(0 for _ in range(16))
        tmp_key = AlgV5.calculate_hash(R, password, o_value[40:48], u_value[:48])
        key = AES_CBC_decrypt(tmp_key, iv, oe_value)
        return key

    @staticmethod
    def verify_user_password(
        R: int, password: bytes, u_value: bytes, ue_value: bytes
    ) -> bytes:
        password = password[:127]
        if AlgV5.calculate_hash(R, password, u_value[32:40], b"") != u_value[:32]:
            return b""
        iv = bytes(0 for _ in range(16))
        tmp_key = AlgV5.calculate_hash(R, password, u_value[40:48], b"")
        return AES_CBC_decrypt(tmp_key, iv, ue_value)

    @staticmethod
    def calculate_hash(R: int, password: bytes, salt: bytes, udata: bytes) -> bytes:
        K = hashlib.sha256(password + salt + udata).digest()
        if R < 6:
            return K
        count = 0
        while True:
            count += 1
            K1 = password + K + udata
            E = AES_CBC_encrypt(K[:16], K[16:32], K1 * 64)
            hash_fn = (
                hashlib.sha256,
                hashlib.sha384,
                hashlib.sha512,
            )[sum(E[:16]) % 3]
            K = hash_fn(E).digest()
            if count >= 64 and E[-1] <= count - 32:
                break
        return K[:32]

    @staticmethod
    def verify_perms(
        key: bytes, perms: bytes, p: int, metadata_encrypted: bool
    ) -> bool:
        b8 = b"T" if metadata_encrypted else b"F"
        p1 = struct.pack("<I", p) + b"\xff\xff\xff\xff" + b8 + b"adb"
        p2 = AES_ECB_decrypt(key, perms)
        return p1 == p2[:12]

    @staticmethod
    def generate_values(
        user_password: bytes,
        owner_password: bytes,
        key: bytes,
        p: int,
        metadata_encrypted: bool,
    ) -> Dict[Any, Any]:
        u_value, ue_value = AlgV5.compute_U_value(user_password, key)
        o_value, oe_value = AlgV5.compute_O_value(owner_password, key, u_value)
        perms = AlgV5.compute_Perms_value(key, p, metadata_encrypted)
        return {
            "/U": u_value,
            "/UE": ue_value,
            "/O": o_value,
            "/OE": oe_value,
            "/Perms": perms,
        }

    @staticmethod
    def compute_U_value(password: bytes, key: bytes) -> Tuple[bytes, bytes]:
        random_bytes = bytes(random.randrange(0, 256) for _ in range(16))
        val_salt = random_bytes[:8]
        key_salt = random_bytes[8:]
        u_value = hashlib.sha256(password + val_salt).digest() + val_salt + key_salt

        tmp_key = hashlib.sha256(password + key_salt).digest()
        iv = bytes(0 for _ in range(16))
        ue_value = AES_CBC_encrypt(tmp_key, iv, key)
        return u_value, ue_value

    @staticmethod
    def compute_O_value(
        password: bytes, key: bytes, u_value: bytes
    ) -> Tuple[bytes, bytes]:
        random_bytes = bytes(random.randrange(0, 256) for _ in range(16))
        val_salt = random_bytes[:8]
        key_salt = random_bytes[8:]
        o_value = (
            hashlib.sha256(password + val_salt + u_value).digest() + val_salt + key_salt
        )

        tmp_key = hashlib.sha256(password + key_salt + u_value).digest()
        iv = bytes(0 for _ in range(16))
        oe_value = AES_CBC_encrypt(tmp_key, iv, key)
        return o_value, oe_value

    @staticmethod
    def compute_Perms_value(key: bytes, p: int, metadata_encrypted: bool) -> bytes:
        b8 = b"T" if metadata_encrypted else b"F"
        rr = bytes(random.randrange(0, 256) for _ in range(4))
        data = struct.pack("<I", p) + b"\xff\xff\xff\xff" + b8 + b"adb" + rr
        perms = AES_ECB_encrypt(key, data)
        return perms


class PasswordType(IntEnum):
    NOT_DECRYPTED = 0
    USER_PASSWORD = 1
    OWNER_PASSWORD = 2


class Encryption:
    def __init__(
        self,
        algV: int,
        algR: int,
        entry: DictionaryObject,
        first_id_entry: bytes,
        StmF: str,
        StrF: str,
        EFF: str,
    ) -> None:
        self.algV = algV
        self.algR = algR
        self.entry = entry
        self.key_size = entry.get("/Length", 40)
        self.id1_entry = first_id_entry
        self.StmF = StmF
        self.StrF = StrF
        self.EFF = EFF
        self._password_type = PasswordType.NOT_DECRYPTED
        self._key: Optional[bytes] = None

    def is_decrypted(self) -> bool:
        return self._password_type != PasswordType.NOT_DECRYPTED

    def decrypt_object(self, obj: PdfObject, idnum: int, generation: int) -> PdfObject:
        pack1 = struct.pack("<i", idnum)[:3]
        pack2 = struct.pack("<i", generation)[:2]

        assert self._key
        key = self._key
        n = 5 if self.algV == 1 else self.key_size // 8
        key_data = key[:n] + pack1 + pack2
        key_hash = hashlib.md5(key_data)
        rc4_key = key_hash.digest()[: min(n + 5, 16)]
        key_hash.update(b"sAlT")
        aes128_key = key_hash.digest()[: min(n + 5, 16)]
        aes256_key = key

        stmCrypt = self._get_crypt(self.StmF, rc4_key, aes128_key, aes256_key)
        StrCrypt = self._get_crypt(self.StrF, rc4_key, aes128_key, aes256_key)
        efCrypt = self._get_crypt(self.EFF, rc4_key, aes128_key, aes256_key)

        cf = CryptFilter(stmCrypt, StrCrypt, efCrypt)
        return cf.decrypt_object(obj)

    @staticmethod
    def _get_crypt(
        method: str, rc4_key: bytes, aes128_key: bytes, aes256_key: bytes
    ) -> CryptBase:
        if method == "/AESV3":
            return CryptAES(aes256_key)
        if method == "/AESV2":
            return CryptAES(aes128_key)
        elif method == "/Identity":
            return CryptIdentity()
        else:
            return CryptRC4(rc4_key)

    def verify(self, password: Union[bytes, str]) -> PasswordType:
        if isinstance(password, str):
            try:
                pwd = password.encode("latin-1")
            except Exception:
                pwd = password.encode("utf-8")
        else:
            pwd = password

        key, rc = self.verify_v4(pwd) if self.algV <= 4 else self.verify_v5(pwd)
        if rc != PasswordType.NOT_DECRYPTED:
            self._password_type = rc
            self._key = key
        return rc

    def verify_v4(self, password: bytes) -> Tuple[bytes, PasswordType]:
        R = cast(int, self.entry["/R"])
        P = cast(int, self.entry["/P"])
        P = (P + 0x100000000) % 0x100000000
        em = self.entry.get("/EncryptMetadata")
        metadata_encrypted = em.value if em else True
        o_entry = cast(ByteStringObject, self.entry["/O"].get_object()).original_bytes
        u_entry = cast(ByteStringObject, self.entry["/U"].get_object()).original_bytes
        key = AlgV4.verify_owner_password(
            password,
            R,
            self.key_size,
            o_entry,
            u_entry,
            P,
            self.id1_entry,
            metadata_encrypted,
        )
        if key:
            return key, PasswordType.OWNER_PASSWORD
        key = AlgV4.verify_user_password(
            password,
            R,
            self.key_size,
            o_entry,
            u_entry,
            P,
            self.id1_entry,
            metadata_encrypted,
        )
        if key:
            return key, PasswordType.USER_PASSWORD
        return b"", PasswordType.NOT_DECRYPTED

    def verify_v5(self, password: bytes) -> Tuple[bytes, PasswordType]:
        o_entry = cast(ByteStringObject, self.entry["/O"].get_object()).original_bytes
        u_entry = cast(ByteStringObject, self.entry["/U"].get_object()).original_bytes
        oe_entry = cast(ByteStringObject, self.entry["/OE"].get_object()).original_bytes
        ue_entry = cast(ByteStringObject, self.entry["/UE"].get_object()).original_bytes
        key = AlgV5.verify_owner_password(
            self.algR, password, o_entry, oe_entry, u_entry
        )
        rc = PasswordType.OWNER_PASSWORD
        if not key:
            key = AlgV5.verify_user_password(self.algR, password, u_entry, ue_entry)
            rc = PasswordType.USER_PASSWORD
        if not key:
            return b"", PasswordType.NOT_DECRYPTED
        perms = cast(ByteStringObject, self.entry["/Perms"].get_object()).original_bytes
        P = cast(int, self.entry["/P"])
        P = (P + 0x100000000) % 0x100000000
        metadata_encrypted = self.entry.get("/EncryptMetadata", True)
        if not AlgV5.verify_perms(key, perms, P, metadata_encrypted):
            logger_warning("ignore '/Perms' verify failed", __name__)
        return key, rc

    @staticmethod
    def read(encryption_entry: DictionaryObject, first_id_entry: bytes) -> "Encryption":
        filter = encryption_entry.get("/Filter")
        if filter != "/Standard":
            raise NotImplementedError(
                "only Standard PDF encryption handler is available"
            )
        if "/SubFilter" in encryption_entry:
            raise NotImplementedError("/SubFilter NOT supported")

        StmF = "/V2"
        StrF = "/V2"
        EFF = "/V2"

        V = encryption_entry.get("/V", 0)
        if V not in (1, 2, 3, 4, 5):
            raise NotImplementedError(f"Encryption V={V} NOT supported")
        if V >= 4:
            filters = encryption_entry["/CF"]

            StmF = encryption_entry.get("/StmF", "/Identity")
            StrF = encryption_entry.get("/StrF", "/Identity")
            EFF = encryption_entry.get("/EFF", StmF)

            if StmF != "/Identity":
                StmF = filters[StmF]["/CFM"]
            if StrF != "/Identity":
                StrF = filters[StrF]["/CFM"]  # type: ignore
            if EFF != "/Identity":
                EFF = filters[EFF]["/CFM"]  # type: ignore

            allowed_methods = ("/Identity", "/V2", "/AESV2", "/AESV3")
            if StmF not in allowed_methods:
                raise NotImplementedError("StmF Method {StmF} NOT supported!")
            if StrF not in allowed_methods:
                raise NotImplementedError(f"StrF Method {StrF} NOT supported!")
            if EFF not in allowed_methods:
                raise NotImplementedError(f"EFF Method {EFF} NOT supported!")

        R = cast(int, encryption_entry["/R"])
        return Encryption(V, R, encryption_entry, first_id_entry, StmF, StrF, EFF)
