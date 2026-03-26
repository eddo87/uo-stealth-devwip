r"""
inject_dll.py
=============
Injects uo_packet_injector.dll into a running UO Stealth process.

Usage:
    python inject_dll.py [stealth_pid]

If no PID is provided, finds the first process named "stealth.exe".
The DLL path is auto-detected relative to this script.

After injection, the DLL:
  1. Captures Stealth's UO server socket from WinSock send() calls
  2. Listens on TCP port 48821
  3. Accepts raw packet injection commands from BodCycler_PacketBridge.py
"""

import ctypes
import ctypes.wintypes
import os
import sys

# Windows API constants
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

kernel32 = ctypes.windll.kernel32


def find_stealth_pid():
    """Finds the PID of stealth.exe using Windows toolhelp snapshots."""
    import ctypes.wintypes

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.wintypes.DWORD),
            ("cntUsage", ctypes.wintypes.DWORD),
            ("th32ProcessID", ctypes.wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", ctypes.wintypes.DWORD),
            ("cntThreads", ctypes.wintypes.DWORD),
            ("th32ParentProcessID", ctypes.wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
    Process32First = kernel32.Process32First
    Process32Next = kernel32.Process32Next
    CloseHandle = kernel32.CloseHandle

    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return None

    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

    if not Process32First(snapshot, ctypes.byref(pe)):
        CloseHandle(snapshot)
        return None

    pid = None
    while True:
        name = pe.szExeFile.decode("utf-8", errors="replace").lower()
        if "stealth" in name:
            pid = pe.th32ProcessID
            break
        if not Process32Next(snapshot, ctypes.byref(pe)):
            break

    CloseHandle(snapshot)
    return pid


def check_process_arch(pid):
    """Returns 32 or 64 for the target process architecture."""
    import platform
    is_wow64 = ctypes.c_int(0)
    h = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
    if h:
        kernel32.IsWow64Process(h, ctypes.byref(is_wow64))
        kernel32.CloseHandle(h)
    # WoW64 = 32-bit process on 64-bit Windows
    if is_wow64.value:
        return 32
    if platform.machine().endswith("64"):
        return 64
    return 32


def inject(pid, dll_path):
    """Injects a DLL into a process by PID using CreateRemoteThread + LoadLibraryA."""
    import platform

    dll_path = os.path.abspath(dll_path)
    if not os.path.exists(dll_path):
        print(f"ERROR: DLL not found: {dll_path}")
        return False

    # Check architecture match
    target_arch = check_process_arch(pid)
    python_arch = 64 if sys.maxsize > 2**32 else 32
    print(f"  Target process: {target_arch}-bit")
    print(f"  Python: {python_arch}-bit")

    if target_arch != python_arch:
        print(f"ERROR: Architecture mismatch! Stealth is {target_arch}-bit but Python is {python_arch}-bit.")
        print(f"  The DLL must be built for {target_arch}-bit AND injected from {target_arch}-bit Python.")
        if target_arch == 32:
            print(f"  Fix: Install 32-bit Python, or build DLL with:")
            print(f"    rustup target add i686-pc-windows-msvc")
            print(f"    cargo build --release --target i686-pc-windows-msvc")
        return False

    dll_bytes = dll_path.encode("utf-8") + b"\x00"

    # Set proper argtypes for 64-bit compatibility
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]

    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.VirtualAllocEx.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]

    kernel32.WriteProcessMemory.restype = ctypes.wintypes.BOOL
    kernel32.WriteProcessMemory.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

    kernel32.CreateRemoteThread.restype = ctypes.wintypes.HANDLE
    kernel32.CreateRemoteThread.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD)]

    kernel32.GetProcAddress.restype = ctypes.c_void_p
    kernel32.GetProcAddress.argtypes = [ctypes.wintypes.HMODULE, ctypes.c_char_p]

    kernel32.GetModuleHandleA.restype = ctypes.wintypes.HMODULE
    kernel32.GetModuleHandleA.argtypes = [ctypes.c_char_p]

    # Open the target process
    h_process = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        err = ctypes.get_last_error()
        print(f"ERROR: Cannot open process {pid} (error={err})")
        return False

    # Allocate memory in the target process for the DLL path
    remote_mem = kernel32.VirtualAllocEx(
        h_process, None, len(dll_bytes), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
    )
    if not remote_mem:
        err = ctypes.get_last_error()
        print(f"ERROR: VirtualAllocEx failed (error={err})")
        kernel32.CloseHandle(h_process)
        return False

    print(f"  Allocated remote memory at: {hex(remote_mem)}")

    # Write the DLL path into the allocated memory
    written = ctypes.c_size_t(0)
    result = kernel32.WriteProcessMemory(
        h_process, remote_mem, dll_bytes, len(dll_bytes), ctypes.byref(written)
    )
    if not result:
        err = ctypes.get_last_error()
        print(f"ERROR: WriteProcessMemory failed (error={err}, written={written.value})")
        kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(h_process)
        return False

    print(f"  Wrote {written.value} bytes to remote process")

    # Get LoadLibraryA address (same in all processes on Windows)
    h_kernel32 = kernel32.GetModuleHandleA(b"kernel32.dll")
    load_library_addr = kernel32.GetProcAddress(h_kernel32, b"LoadLibraryA")

    if not load_library_addr:
        print("ERROR: Cannot find LoadLibraryA")
        kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(h_process)
        return False

    print(f"  LoadLibraryA at: {hex(load_library_addr)}")

    # Create remote thread that calls LoadLibraryA(dll_path)
    thread_id = ctypes.wintypes.DWORD(0)
    h_thread = kernel32.CreateRemoteThread(
        h_process,
        None,
        0,
        load_library_addr,
        remote_mem,
        0,
        ctypes.byref(thread_id),
    )

    if not h_thread:
        err = ctypes.get_last_error()
        print(f"ERROR: CreateRemoteThread failed (error={err})")
        kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(h_process)
        return False

    print(f"DLL injected! Thread ID: {thread_id.value}")
    print(f"  Target PID: {pid}")
    print(f"  DLL: {dll_path}")
    print(f"  TCP port: 48821")

    # Wait for the remote thread to finish loading
    kernel32.WaitForSingleObject(h_thread, 5000)

    # Cleanup
    kernel32.CloseHandle(h_thread)
    kernel32.VirtualFreeEx.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.wintypes.DWORD]
    kernel32.VirtualFreeEx(h_process, ctypes.c_void_p(remote_mem), 0, MEM_RELEASE)
    kernel32.CloseHandle(h_process)
    return True


def main():
    # Find DLL next to this script, or in uo_packet_injector/target/release/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dll_candidates = [
        os.path.join(script_dir, "uo_packet_injector.dll"),
        os.path.join(script_dir, "uo_packet_injector", "target", "release", "uo_packet_injector.dll"),
        os.path.join(script_dir, "uo_packet_injector", "target", "debug", "uo_packet_injector.dll"),
    ]

    dll_path = None
    for candidate in dll_candidates:
        if os.path.exists(candidate):
            dll_path = candidate
            break

    if not dll_path:
        print("ERROR: Cannot find uo_packet_injector.dll")
        print("Build it first: cd uo_packet_injector && cargo build --release")
        sys.exit(1)

    # Get target PID
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
    else:
        pid = find_stealth_pid()
        if not pid:
            print("ERROR: Cannot find stealth.exe process. Pass PID manually:")
            print("  python inject_dll.py <PID>")
            sys.exit(1)

    print(f"Found Stealth process: PID {pid}")
    if inject(pid, dll_path):
        print("\nReady! Use BodCycler_PacketBridge.py to send packets.")
        print("Test: python -c \"import BodCycler_PacketBridge as pb; pb.connect(); print(pb.status())\"")
    else:
        print("\nInjection FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
