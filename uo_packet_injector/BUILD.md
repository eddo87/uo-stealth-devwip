# Building the UO Packet Injector DLL

## Prerequisites

1. Install Rust: https://rustup.rs/
   ```
   winget install Rustlang.Rustup
   ```
2. Restart terminal after install

## Build

```bash
cd uo_packet_injector
cargo build --release
```

Output: `target/release/uo_packet_injector.dll`

## Usage

1. Start UO Stealth and connect to the game
2. Inject the DLL:
   ```
   python inject_dll.py
   ```
3. From your Stealth Python script:
   ```python
   import BodCycler_PacketBridge as pb
   pb.connect()
   print(pb.status())  # Should show captured=True

   # Drop a BOD at position 50 without page flipping:
   serial = GetGumpInfo(idx)["Serial"]
   pb.drop_bod(serial, 50)
   ```

## Architecture

```
Stealth.exe (Delphi)
  └─ ws2_32.dll send() ─── captured socket handle
  └─ uo_packet_injector.dll (injected)
       └─ Named pipe: \\.\pipe\uo_packet_injector
            └─ BodCycler_PacketBridge.py (Python)
                 └─ ConservaManager / scripts
```
