# BodCycler_PacketBridge_linux.py
# Linux backend for the packet bridge — native Stealth (no DLL, no TCP listener).
#
# On Windows a DLL is injected into Stealth so it can call WinSock send() on
# Stealth's private game-server socket (FDs are process-local on Windows). On
# Linux we don't inject anything: the game socket is a real kernel FD owned by
# the UOStealth process, and pidfd_getfd(2) (Linux >= 5.6) lets us clone that FD
# into our own process and send() on it directly.
#
# Requires ptrace permission over the target: run as the same user as Stealth
# with CAP_SYS_PTRACE, or set kernel.yama.ptrace_scope=0. In the Docker/RDP
# container, add `cap_add: [SYS_PTRACE]` to compose.yml.

import ctypes
import errno
import os
import socket
import struct
import time

try:
    from BodCycler_Utils import BOOK_GUMP_ID
except Exception:
    BOOK_GUMP_ID = 0x54F555DF  # standalone-test fallback (real value lives in Utils)

# AddToSystemJournal is injected into module globals by the Stealth Python host.
# Provide a fallback so this module can be imported / self-tested standalone.
try:
    AddToSystemJournal  # type: ignore  # noqa: F821
except NameError:
    def AddToSystemJournal(msg):
        print(msg)

# --- syscall numbers (x86_64). Override via env on other architectures. ---
_NR_pidfd_open = int(os.environ.get("NR_PIDFD_OPEN", 434))
_NR_pidfd_getfd = int(os.environ.get("NR_PIDFD_GETFD", 438))

_libc = ctypes.CDLL(None, use_errno=True)
_libc.syscall.restype = ctypes.c_long

STEALTH_PROC_NAMES = ("UOStealth", "Stealth")

# --- module state ---
_dup_fd = -1        # our cloned copy of Stealth's game socket (-1 = none)
_target_pid = 0     # UOStealth PID
_target_fd = 0      # the fd number as seen inside the Stealth process
_peer = None        # "ip:port" of the game server, for diagnostics


# ---------------------------------------------------------------------------
# Raw syscalls
# ---------------------------------------------------------------------------

def _syscall(nr, *args):
    res = _libc.syscall(ctypes.c_long(nr), *[ctypes.c_long(a) for a in args])
    if res == -1:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))
    return res


def _pidfd_open(pid):
    return _syscall(_NR_pidfd_open, pid, 0)


def _pidfd_getfd(pidfd, targetfd):
    return _syscall(_NR_pidfd_getfd, pidfd, targetfd, 0)


# ---------------------------------------------------------------------------
# Target discovery (/proc)
# ---------------------------------------------------------------------------

def _find_stealth_pid():
    """Returns the PID of the UOStealth process, or 0."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm") as f:
                comm = f.read().strip()
        except OSError:
            continue
        if any(name.lower() in comm.lower() for name in STEALTH_PROC_NAMES):
            return int(entry)
    return 0


def _decode_addr(hexaddr, ipv6=False):
    """Decodes a /proc/net/tcp 'HEXIP:HEXPORT' field. Returns (ip, port)."""
    try:
        ip_hex, port_hex = hexaddr.split(":")
        port = int(port_hex, 16)
        if ipv6:
            b = bytes.fromhex(ip_hex)
            raw = b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4))
            ip = socket.inet_ntop(socket.AF_INET6, raw)
        else:
            raw = bytes.fromhex(ip_hex)[::-1]  # stored little-endian
            ip = socket.inet_ntop(socket.AF_INET, raw)
        return ip, port
    except (ValueError, OSError):
        return None, None


def _established_remotes(pid):
    """Returns {socket_inode: (ip, port)} for ESTABLISHED, non-loopback peers
    in the target's network namespace."""
    result = {}
    for fname in ("tcp", "tcp6"):
        try:
            with open(f"/proc/{pid}/net/{fname}") as f:
                lines = f.readlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 10:
                continue
            rem, state, inode = parts[2], parts[3], parts[9]
            if state != "01":  # 01 = TCP_ESTABLISHED
                continue
            ip, port = _decode_addr(rem, ipv6=(fname == "tcp6"))
            if not ip or ip.startswith("127.") or ip in ("0.0.0.0", "::1", "::"):
                continue
            result[inode] = (ip, port)
    return result


def _find_game_fd(pid):
    """Finds the fd inside the target that backs its established remote socket.
    Returns (fd, (ip, port)) or (0, None)."""
    remotes = _established_remotes(pid)
    if not remotes:
        return 0, None
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except OSError:
        return 0, None
    for fd_name in fds:
        try:
            link = os.readlink(f"{fd_dir}/{fd_name}")
        except OSError:
            continue
        if link.startswith("socket:["):
            inode = link[len("socket:["):-1]
            if inode in remotes:
                return int(fd_name), remotes[inode]
    return 0, None


# ---------------------------------------------------------------------------
# Public API (mirrors BodCycler_PacketBridge on Windows)
# ---------------------------------------------------------------------------

def is_connected():
    return _dup_fd >= 0


def connect():
    """Locates UOStealth and clones its game-server socket FD into this process.
    Returns True on success."""
    global _dup_fd, _target_pid, _target_fd, _peer
    if is_connected():
        return True

    pid = _find_stealth_pid()
    if not pid:
        AddToSystemJournal("PacketBridge(linux): UOStealth process not found.")
        return False

    fd, peer = _find_game_fd(pid)
    if not fd:
        AddToSystemJournal("PacketBridge(linux): no established game socket in Stealth "
                           "(is the character logged in?).")
        return False

    try:
        pidfd = _pidfd_open(pid)
    except OSError as e:
        AddToSystemJournal(f"PacketBridge(linux): pidfd_open failed: {e}")
        return False

    try:
        dup = _pidfd_getfd(pidfd, fd)
    except OSError as e:
        if e.errno in (errno.EPERM, errno.EACCES):
            AddToSystemJournal("PacketBridge(linux): pidfd_getfd permission denied — grant "
                               "CAP_SYS_PTRACE (cap_add in compose.yml) or set "
                               "kernel.yama.ptrace_scope=0.")
        elif e.errno == errno.ENOSYS:
            AddToSystemJournal("PacketBridge(linux): pidfd_getfd not available — kernel < 5.6 "
                               "or blocked by seccomp (try security_opt seccomp=unconfined).")
        else:
            AddToSystemJournal(f"PacketBridge(linux): pidfd_getfd failed: {e}")
        return False
    finally:
        try:
            os.close(pidfd)
        except OSError:
            pass

    _dup_fd = dup
    _target_pid = pid
    _target_fd = fd
    _peer = f"{peer[0]}:{peer[1]}" if peer else None
    AddToSystemJournal(f"PacketBridge(linux): cloned Stealth socket fd {fd} "
                       f"(pid {pid}) -> {_peer}")
    return True


def disconnect():
    """Closes our cloned FD. Stealth's original socket is unaffected."""
    global _dup_fd, _peer
    if _dup_fd >= 0:
        try:
            os.close(_dup_fd)
        except OSError:
            pass
    _dup_fd = -1
    _peer = None


def status():
    """Returns {"captured": bool, "socket": int} — matches the Windows backend."""
    return {"captured": _dup_fd >= 0, "socket": _target_fd if _dup_fd >= 0 else 0}


def set_socket(handle):
    """No external handle to set on Linux — the FD is cloned in connect().
    Accepts the call for API parity; ensures we're connected."""
    return is_connected() or connect()


def set_socket_by_probe(force=False):
    """(Re)acquires Stealth's game socket. Returns a non-zero handle or 0.
    force=True drops the current clone and re-grabs (used before drop sessions)."""
    if force:
        disconnect()
    if connect():
        return _target_fd or 1
    return 0


def clear_cached_handle():
    disconnect()


def probe_peer(handle=None):
    """Returns the cached 'ip:port' of the game server, or None."""
    return _peer


def inject_raw(packet_bytes):
    """Sends a raw UO packet on the cloned game socket. Returns bytes sent or -1."""
    global _dup_fd
    if _dup_fd < 0 and not connect():
        return -1
    try:
        total = 0
        view = memoryview(packet_bytes)
        while total < len(packet_bytes):
            n = os.write(_dup_fd, view[total:])
            if n <= 0:
                break
            total += n
        return total
    except OSError as e:
        AddToSystemJournal(f"PacketBridge(linux).inject_raw: write failed ({e}); "
                           "dropping socket so it re-grabs next call.")
        disconnect()  # likely a relog — force a fresh grab next time
        return -1


def send_gump_response(gump_serial, gump_id, button_id):
    """Constructs and sends a 0xB1 Gump Menu Selection packet (23 bytes).
    Returns bytes sent (23 on success) or -1."""
    packet = struct.pack(">B", 0xB1)        # cmd
    packet += struct.pack(">H", 23)         # total length
    packet += struct.pack(">I", gump_serial)
    packet += struct.pack(">I", gump_id)
    packet += struct.pack(">I", button_id)
    packet += struct.pack(">I", 0)          # switch count
    packet += struct.pack(">I", 0)          # text entry count
    return inject_raw(packet)


def drop_bod(gump_serial, global_pos):
    """Drops a BOD from a book at the given 0-indexed global position."""
    return send_gump_response(gump_serial, BOOK_GUMP_ID, 5 + (global_pos * 2))


def drop_bods_batch(get_serial_fn, positions, pause_ms=150):
    """Drops multiple BODs by position, re-reading the gump serial between each.
    positions MUST be descending. Returns the number of successful drops."""
    dropped = 0
    for pos in positions:
        serial = get_serial_fn()
        if not serial:
            break
        if drop_bod(serial, pos) > 0:
            dropped += 1
        time.sleep(pause_ms / 1000.0)
    return dropped


# ---------------------------------------------------------------------------
# Standalone self-test: python3 BodCycler_PacketBridge_linux.py
# Locates Stealth's game socket and clones it WITHOUT sending anything.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pid = _find_stealth_pid()
    print(f"UOStealth PID: {pid or 'NOT FOUND'}")
    if pid:
        fd, peer = _find_game_fd(pid)
        print(f"game socket fd in target: {fd or 'NONE'}  peer: {peer}")
        if fd:
            if connect():
                print(f"OK: cloned fd {fd} as local fd {_dup_fd} -> {_peer}")
                print("(no packet sent — read-only test)")
                disconnect()
            else:
                print("connect() failed — see message above (likely a permission issue).")
