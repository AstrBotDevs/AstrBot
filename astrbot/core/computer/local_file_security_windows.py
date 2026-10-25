"""Handle-relative Windows file access for workspace-scoped Local tools."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Literal


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_uint16),
        ("MaximumLength", ctypes.c_uint16),
        ("Buffer", ctypes.c_wchar_p),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_uint32),
        ("RootDirectory", ctypes.c_void_p),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", ctypes.c_uint32),
        ("SecurityDescriptor", ctypes.c_void_p),
        ("SecurityQualityOfService", ctypes.c_void_p),
    ]


class _IoStatusBlock(ctypes.Structure):
    # The first field is a union of NTSTATUS and a pointer, hence pointer-sized.
    _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]


class _FileInformation(ctypes.Structure):
    _fields_ = [
        ("Attributes", ctypes.c_uint32),
        ("CreationTime", ctypes.c_uint32 * 2),
        ("LastAccessTime", ctypes.c_uint32 * 2),
        ("LastWriteTime", ctypes.c_uint32 * 2),
        ("VolumeSerialNumber", ctypes.c_uint32),
        ("FileSizeHigh", ctypes.c_uint32),
        ("FileSizeLow", ctypes.c_uint32),
        ("NumberOfLinks", ctypes.c_uint32),
        ("FileIndexHigh", ctypes.c_uint32),
        ("FileIndexLow", ctypes.c_uint32),
    ]


def open_windows_file(
    root: Path,
    parts: tuple[str, ...],
    *,
    access: Literal["read", "write", "edit"],
    create_parents: bool,
) -> int:
    """Open a checked workspace file through stable, non-reparse handles.

    Resolve the drive or share anchor before enabling OBJ_DONT_REPARSE so normal
    Windows device mappings are allowed. Open every filesystem component below
    that anchor relative to a checked handle without following reparse points.

    Args:
        root: Absolute trusted directory containing the requested file.
        parts: Validated path components relative to the trusted directory.
        access: Whether the descriptor is used for reading, writing, or editing.
        create_parents: Whether to create missing directories and the final file.

    Returns:
        A non-inheritable binary file descriptor owned by the caller.

    Raises:
        OSError: If a native file operation fails.
        PermissionError: If a reparse point, alternate stream, special file, or
            multiply linked file would be accessed.
        IsADirectoryError: If the final component is a directory.
        ValueError: If the access mode or filename is invalid.
    """
    import msvcrt

    modes = {"read": os.O_RDONLY, "write": os.O_WRONLY, "edit": os.O_RDWR}
    if access not in modes:
        raise ValueError(f"Unsupported restricted file access mode: {access}.")
    # Native relative opens must receive one ordinary component, never an ADS,
    # device path, or a name with Win32 trimming/normalization ambiguities.
    if not parts or any(
        not part
        or part in {".", ".."}
        or any(character in part for character in "\\/:\x00")
        or part.endswith((".", " "))
        for part in parts
    ):
        raise PermissionError("Access denied: unsafe restricted Windows path.")

    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = ntdll.NtCreateFile
    create_file.restype = ctypes.c_int32
    create_file.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint32,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    status_to_error = ntdll.RtlNtStatusToDosError
    status_to_error.argtypes = [ctypes.c_int32]
    status_to_error.restype = ctypes.c_uint32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    file_information = kernel32.GetFileInformationByHandle
    file_information.argtypes = [ctypes.c_void_p, ctypes.POINTER(_FileInformation)]
    file_information.restype = ctypes.c_int
    file_type = kernel32.GetFileType
    file_type.argtypes = [ctypes.c_void_p]
    file_type.restype = ctypes.c_uint32

    native_root = root.anchor
    if native_root.startswith("\\\\?\\"):
        native_root = "\\??\\" + native_root[4:]
    elif native_root.startswith("\\\\"):
        native_root = "\\??\\UNC\\" + native_root[2:]
    else:
        native_root = "\\??\\" + native_root

    root_parts = root.parts[1:]
    components = (native_root, *root_parts, *parts)
    handles: list[int] = []
    try:
        for index, name in enumerate(components):
            terminal = index == len(components) - 1
            encoded_length = len(name.encode("utf-16-le"))
            if encoded_length > 65532:
                raise ValueError("Restricted Windows filename is too long.")
            name_buffer = ctypes.create_unicode_buffer(name)
            unicode_name = _UnicodeString(
                encoded_length,
                encoded_length + 2,
                ctypes.cast(name_buffer, ctypes.c_wchar_p),
            )
            attributes = _ObjectAttributes(
                ctypes.sizeof(_ObjectAttributes),
                handles[-1] if handles else None,
                ctypes.pointer(unicode_name),
                0x40 if index == 0 else 0x1040,
                None,
                None,
            )
            desired_access = 0x1000A0  # SYNCHRONIZE | READ_ATTRIBUTES | TRAVERSE
            if terminal:
                desired_access = 0x100080  # SYNCHRONIZE | READ_ATTRIBUTES
                if access in {"read", "edit"}:
                    desired_access |= 0x80000000  # GENERIC_READ
                if access in {"write", "edit"}:
                    desired_access |= 0x40000000  # GENERIC_WRITE
            handle = ctypes.c_void_p()
            io_status = _IoStatusBlock()
            status = create_file(
                ctypes.byref(handle),
                desired_access,
                ctypes.byref(attributes),
                ctypes.byref(io_status),
                None,
                0x80,  # FILE_ATTRIBUTE_NORMAL
                0x3,  # Share read/write, but keep opened objects from being renamed.
                3 if create_parents and index > len(root_parts) else 1,
                0x200020 | (0x40 if terminal else 0x1),
                # OPEN_REPARSE_POINT | SYNCHRONOUS_IO_NONALERT | NON_DIRECTORY/DIRECTORY
                None,
                0,
            )
            if status < 0:
                if status & 0xFFFFFFFF == 0xC000050B:
                    raise PermissionError(
                        "Access denied: restricted path contains a reparse point."
                    )
                if terminal and status & 0xFFFFFFFF == 0xC00000BA:
                    raise IsADirectoryError(str(root.joinpath(*parts)))
                raise ctypes.WinError(status_to_error(status))
            handles.append(handle.value)
            information = _FileInformation()
            if not file_information(handle, ctypes.byref(information)):
                raise ctypes.WinError(ctypes.get_last_error())
            if information.Attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
                raise PermissionError(
                    "Access denied: restricted path contains a reparse point."
                )
            if terminal:
                if file_type(handle) != 1:  # FILE_TYPE_DISK
                    raise PermissionError(
                        "Access denied: restricted path is not a file."
                    )
                if information.NumberOfLinks > 1:
                    raise PermissionError(
                        "Access denied: file has multiple hard links and may alias "
                        "content outside allowed directories."
                    )
                # Do not truncate before checking the opened object's identity.
                descriptor = msvcrt.open_osfhandle(
                    handle.value, modes[access] | os.O_BINARY | os.O_NOINHERIT
                )
                handles.pop()  # The CRT descriptor now owns this handle.
                return descriptor
    finally:
        for handle in reversed(handles):
            close_handle(handle)
