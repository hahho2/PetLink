"""Windows Credential Manager; secrets never enter QSettings or SQLite."""
import ctypes
from ctypes import wintypes
import sys


class Credential(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


class CredentialStore:
    def __init__(self):
        self.api = None
        if sys.platform == "win32":
            self.api = ctypes.WinDLL("Advapi32", use_last_error=True)
            self.api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
            self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                         ctypes.POINTER(ctypes.POINTER(Credential))]
            self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self.api.CredFree.argtypes = [ctypes.c_void_p]
            self.api.CredFree.restype = None

    def read(self, provider):
        if self.api is None:
            return ""
        pointer = ctypes.POINTER(Credential)()
        if not self.api.CredReadW("PetLink/model/" + provider, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:  # not found
                return ""
            raise OSError("Could not read Windows Credential Manager.")
        try:
            value = pointer.contents
            return ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode("utf-16-le")
        finally:
            self.api.CredFree(pointer)

    def write(self, provider, secret):
        if self.api is None:
            raise OSError("Remembering API keys requires Windows Credential Manager.")
        data = secret.encode("utf-16-le")
        if len(data) > 2560:
            raise ValueError("API key is too long.")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = Credential(Type=1, TargetName="PetLink/model/" + provider,
            CredentialBlobSize=len(data), CredentialBlob=blob, Persist=2, UserName="PetLink")
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise OSError("Could not save the key in Windows Credential Manager.")

    def delete(self, provider):
        if self.api is not None and not self.api.CredDeleteW("PetLink/model/" + provider, 1, 0):
            if ctypes.get_last_error() != 1168:
                raise OSError("Could not remove the key from Windows Credential Manager.")
