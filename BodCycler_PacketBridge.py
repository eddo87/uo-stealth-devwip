# BodCycler_PacketBridge.py
# Python bridge to the UO Packet Injector DLL.
# Connects via named pipe to send raw UO packets (0xB1 gump responses)
# bypassing Stealth's client-side button validation.

import socket
import struct
import time
from BodCycler_Utils import BOOK_GUMP_ID

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 48821

_sock = None


def connect():
    """Connects to the injector DLL's TCP listener. Returns True on success."""
    global _sock
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _sock.settimeout(5)
        _sock.connect((BRIDGE_HOST, BRIDGE_PORT))
        _sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return True
    except Exception:
        _sock = None
        return False


def disconnect():
    """Closes the TCP connection."""
    global _sock
    if _sock:
        try:
            _sock.close()
        except Exception:
            pass
        _sock = None


def is_connected():
    """Checks if the socket is open."""
    return _sock is not None


def _send_command(data):
    """Sends a length-prefixed command to the DLL and reads the response."""
    global _sock
    if not _sock:
        if not connect():
            return None
    try:
        header = struct.pack("<I", len(data))
        _sock.sendall(header + data)
        # Read response (line-terminated)
        response = b""
        while True:
            ch = _sock.recv(1)
            if not ch or ch == b"\n":
                break
            response += ch
        return response.decode("utf-8", errors="replace")
    except Exception:
        disconnect()
        return None


def status():
    """Queries the DLL for socket capture status.
    Returns dict: {"captured": bool, "socket": int}
    """
    resp = _send_command(b"\x00")
    if not resp:
        return {"captured": False, "socket": 0}
    parts = resp.strip().split()
    result = {}
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            if k == "captured":
                result["captured"] = v.lower() == "true"
            elif k == "socket":
                result["socket"] = int(v)
    return result


def set_socket(socket_handle):
    """Manually sets the socket handle in the DLL (if auto-capture hasn't fired)."""
    data = b"\xFF" + struct.pack("<Q", socket_handle)
    resp = _send_command(data)
    return resp and "OK" in resp


def inject_raw(packet_bytes):
    """Sends a raw UO packet on the game server socket.
    Returns bytes sent (int) or -1 on failure.
    """
    resp = _send_command(packet_bytes)
    if resp is None:
        return -1
    try:
        return int(resp.strip())
    except ValueError:
        return -1


def send_gump_response(gump_serial, gump_id, button_id):
    """Constructs and sends a 0xB1 Gump Menu Selection packet.

    Args:
        gump_serial: The gump's serial (from GetGumpInfo()["Serial"])
        gump_id:     The gump type ID (e.g., 0x54F555DF for BOD books)
        button_id:   The button to press (e.g., 5 + (pos * 2) for BOD drops)

    Returns:
        bytes sent (23 on success) or -1 on failure.
    """
    # 0xB1 packet: cmd(1) + length(2) + serial(4) + gumpId(4) + buttonId(4) + switches(4) + textcount(4)
    packet = struct.pack(">B", 0xB1)           # cmd
    packet += struct.pack(">H", 23)             # total length (big-endian per UO protocol)
    packet += struct.pack(">I", gump_serial)    # gump serial
    packet += struct.pack(">I", gump_id)        # gump type ID
    packet += struct.pack(">I", button_id)      # button pressed
    packet += struct.pack(">I", 0)              # switch count
    packet += struct.pack(">I", 0)              # text entry count
    return inject_raw(packet)


def drop_bod(gump_serial, global_pos):
    """Shortcut: drops a BOD from a book at the given global position.

    Args:
        gump_serial: Current gump serial (changes after each drop!)
        global_pos:  0-indexed position of the BOD in the book

    Returns:
        bytes sent or -1 on failure.
    """
    button_id = 5 + (global_pos * 2)
    return send_gump_response(gump_serial, BOOK_GUMP_ID, button_id)


# ---------------------------------------------------------------------------
# Batch operations (for ConservaManager integration)
# ---------------------------------------------------------------------------

def drop_bods_batch(get_serial_fn, positions, pause_ms=150):
    """Drops multiple BODs by position, re-reading the gump serial between each.

    Args:
        get_serial_fn: Callable that returns the current gump serial (e.g.,
                        lambda: GetGumpInfo(idx)["Serial"])
        positions:      List of global positions to drop (MUST be descending)
        pause_ms:       Milliseconds to wait between drops for server to refresh gump

    Returns:
        Number of successful drops.
    """
    dropped = 0
    for pos in positions:
        serial = get_serial_fn()
        if not serial:
            break
        result = drop_bod(serial, pos)
        if result > 0:
            dropped += 1
        time.sleep(pause_ms / 1000.0)
    return dropped
