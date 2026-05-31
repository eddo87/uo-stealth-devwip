//! UO Packet Injector DLL
//!
//! Injected into UO Stealth. Captures the game server socket by hooking the
//! WinSock send() IAT entry, then listens on a local TCP port (48821) for
//! raw packet injection commands from Python.
//!
//! Zero external crate dependencies beyond once_cell (no windows crate needed).

use once_cell::sync::OnceCell;
use std::ffi::c_void;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::thread;

// ---------------------------------------------------------------------------
// FFI: raw WinSock send() — we only need this one function
// ---------------------------------------------------------------------------
extern "system" {
    fn send(socket: usize, buf: *const u8, len: i32, flags: i32) -> i32;
    fn getpeername(socket: usize, name: *mut u8, namelen: *mut i32) -> i32;
}

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

/// The raw socket handle Stealth uses to talk to the UO server.
static CAPTURED_SOCKET: AtomicUsize = AtomicUsize::new(0);
static SOCKET_CAPTURED: AtomicBool = AtomicBool::new(false);

/// TCP port for the Python command channel.
const LISTEN_PORT: u16 = 48821;

/// Log file handle.
static LOG_FILE: OnceCell<std::sync::Mutex<std::fs::File>> = OnceCell::new();

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

fn log(msg: &str) {
    if let Some(file) = LOG_FILE.get() {
        if let Ok(mut f) = file.lock() {
            let _ = writeln!(f, "{}", msg);
            let _ = f.flush();
        }
    }
}

fn init_log() {
    // Log next to stealth.exe
    let path = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("uo_packet_injector.log")))
        .unwrap_or_else(|| "uo_packet_injector.log".into());
    if let Ok(f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = LOG_FILE.set(std::sync::Mutex::new(f));
    }
}

// ---------------------------------------------------------------------------
// Socket capture via periodic polling
// ---------------------------------------------------------------------------
// Instead of hooking send(), we let Python tell us the socket handle.
// Stealth's Python API can discover it: the gump serial from GetGumpInfo
// isn't the socket, but Python can find the socket via OS APIs.
//
// Alternatively, the Python injector can pass the socket handle via the
// 0xFF command after using netstat/psutil to find Stealth's game connection.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// TCP Command Listener
// ---------------------------------------------------------------------------

/// Protocol:
///   Client sends: [4 bytes LE length] [N bytes payload]
///   Payload byte 0 determines the command:
///     0x00 → status query. Response: "captured={} socket={}\n"
///     0xFF → set socket. Payload bytes 1-8 = u64 LE socket handle. Response: "OK\n"
///     anything else → raw packet to inject on the UO socket. Response: "{bytes_sent}\n"
fn handle_client(mut stream: TcpStream) {
    log("Client connected");
    stream.set_nodelay(true).ok();

    let mut header = [0u8; 4];
    loop {
        // Read 4-byte length
        if stream.read_exact(&mut header).is_err() {
            break;
        }
        let pkt_len = u32::from_le_bytes(header) as usize;
        if pkt_len == 0 || pkt_len > 8192 {
            log(&format!("Bad length: {}", pkt_len));
            break;
        }

        // Read payload
        let mut buf = vec![0u8; pkt_len];
        if stream.read_exact(&mut buf).is_err() {
            break;
        }

        match buf[0] {
            0x00 => {
                // Status query
                let captured = SOCKET_CAPTURED.load(Ordering::SeqCst);
                let sock = CAPTURED_SOCKET.load(Ordering::SeqCst);
                let resp = format!("captured={} socket={}\n", captured, sock);
                stream.write_all(resp.as_bytes()).ok();
            }
            0xFF => {
                // Set socket handle manually
                if pkt_len >= 9 {
                    let mut arr = [0u8; 8];
                    arr.copy_from_slice(&buf[1..9]);
                    let sock = u64::from_le_bytes(arr) as usize;
                    CAPTURED_SOCKET.store(sock, Ordering::SeqCst);
                    SOCKET_CAPTURED.store(true, Ordering::SeqCst);
                    log(&format!("Socket set to: {}", sock));
                    stream.write_all(b"OK\n").ok();
                } else {
                    stream.write_all(b"ERR: need 9 bytes\n").ok();
                }
            }
            0xFE => {
                // Peer probe: takes 8-byte LE socket handle, returns getpeername() result
                if pkt_len >= 9 {
                    let mut arr = [0u8; 8];
                    arr.copy_from_slice(&buf[1..9]);
                    let probe_sock = u64::from_le_bytes(arr) as usize;
                    let mut addr = [0u8; 16]; // sockaddr_in
                    let mut addrlen: i32 = 16;
                    let ret = unsafe { getpeername(probe_sock, addr.as_mut_ptr(), &mut addrlen) };
                    if ret == 0 {
                        let port = u16::from_be_bytes([addr[2], addr[3]]);
                        let ip = format!("{}.{}.{}.{}", addr[4], addr[5], addr[6], addr[7]);
                        let resp = format!("peer={}:{}\n", ip, port);
                        stream.write_all(resp.as_bytes()).ok();
                    } else {
                        stream.write_all(b"peer=none\n").ok();
                    }
                } else {
                    stream.write_all(b"ERR: need 9 bytes\n").ok();
                }
            }
            _ => {
                // Raw packet injection
                let sock = CAPTURED_SOCKET.load(Ordering::SeqCst);
                if sock == 0 {
                    stream.write_all(b"-1\n").ok();
                    log("Inject failed: no socket");
                    continue;
                }

                let sent = unsafe { send(sock, buf.as_ptr(), pkt_len as i32, 0) };

                let resp = format!("{}\n", sent);
                stream.write_all(resp.as_bytes()).ok();

                if sent > 0 {
                    log(&format!("Injected: 0x{:02X} len={} sent={}", buf[0], pkt_len, sent));
                } else {
                    log(&format!("Inject FAILED: 0x{:02X} len={} result={}", buf[0], pkt_len, sent));
                }
            }
        }
    }
    log("Client disconnected");
}

fn listener_thread() {
    let addr = format!("127.0.0.1:{}", LISTEN_PORT);
    let listener = match TcpListener::bind(&addr) {
        Ok(l) => l,
        Err(e) => {
            log(&format!("Failed to bind {}: {}", addr, e));
            return;
        }
    };
    log(&format!("Listening on {}", addr));

    for stream in listener.incoming() {
        match stream {
            Ok(s) => {
                thread::spawn(move || handle_client(s));
            }
            Err(e) => {
                log(&format!("Accept error: {}", e));
            }
        }
    }
}

// ---------------------------------------------------------------------------
// DLL Entry Point
// ---------------------------------------------------------------------------

#[no_mangle]
#[allow(non_snake_case)]
unsafe extern "system" fn DllMain(
    _dll_module: *mut c_void,
    call_reason: u32,
    _reserved: *mut c_void,
) -> bool {
    const DLL_PROCESS_ATTACH: u32 = 1;

    if call_reason == DLL_PROCESS_ATTACH {
        init_log();
        log("=== UO Packet Injector loaded ===");
        thread::spawn(|| listener_thread());
    }
    true
}
