"""
Async TCP Service (client)
"""
import argparse                 # Parse command line args
import asyncio                  # Async I/O
import json                     # Encode/decode JSON
import struct                   # Pack/unpack message headers
from typing import Dict, Any    # Type hints

HEADER = struct.Struct("!I")   # Define 4-byte length prefix format

# ---------------- Framing ----------------

async def read_frame(reader: asyncio.StreamReader) -> Dict[str, Any]:
    hdr = await reader.readexactly(HEADER.size)     # Read 4 bytes for header
    (length,) = HEADER.unpack(hdr)                 # Unpack length
    data = await reader.readexactly(length)        # Read full payload
    return json.loads(data.decode("utf-8"))        # Return JSON object

async def write_frame(writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    writer.write(HEADER.pack(len(data)) + data)    # Prefix message with length
    await writer.drain()                           # Flush to network

# ---------------- Request helpers ----------------

async def send_request(host: str, port: int, payload: Dict[str, Any]):
    reader, writer = await asyncio.open_connection(host, port) # Connect to server
    try:
        await write_frame(writer, payload)         # Send request
        resp = await read_frame(reader)            # Wait for reply
        return resp
    finally:
        writer.close()                             # Close socket
        await writer.wait_closed()

# Interactive client loop
async def interactive(host: str, port: int):
    print("Commands: PING | LOAN <username> <amount> <years> <rate> | SET <k> <v...> | GET <k> | DEL <k> | KEYS | CLEAR | EXIT")
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, lambda: input('> ').strip())  # Get user input
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].upper()                       # First word = command
        if cmd in {"EXIT", "QUIT"}:                 # Exit commands
            print("bye")
            return
        try:
            if cmd == "PING":
                payload = {"cmd": "PING"}
            elif cmd == "LOAN" and len(parts) == 5:
                _, username, amount, years, rate = parts
                payload = {
                    "cmd": "LOAN",
                    "username": username,
                    "loan_amount": float(amount),
                    "years": int(years),
                    "annual_rate": float(rate),
                }
            elif cmd == "SET" and len(parts) >= 3:
                key = parts[1]
                value = " ".join(parts[2:])
                payload = {"cmd": "SET", "key": key, "value": value}
            elif cmd == "GET" and len(parts) == 2:
                payload = {"cmd": "GET", "key": parts[1]}
            elif cmd == "DEL" and len(parts) == 2:
                payload = {"cmd": "DEL", "key": parts[1]}
            elif cmd == "KEYS" and len(parts) == 1:
                payload = {"cmd": "KEYS"}
            elif cmd == "CLEAR" and len(parts) == 1:
                payload = {"cmd": "CLEAR"}
            else:
                print("Unknown/invalid command.")
                continue

            resp = await send_request(host, port, payload)  # Send to server
            print(json.dumps(resp, indent=2))              # Print nicely
        except Exception as e:
            print(f"Error: {e}")

# One-shot helper for loan
async def loan_oneshot(host: str, port: int, username: str, amount: float, years: int, rate: float):
    payload = {
        "cmd": "LOAN",
        "username": username,
        "loan_amount": amount,
        "years": years,
        "annual_rate": rate,
    }
    resp = await send_request(host, port, payload)
    print(json.dumps(resp, indent=2))

# One-shot helper for KV GET
async def kv_get_oneshot(host: str, port: int, key: str):
    payload = {"cmd": "GET", "key": key}
    resp = await send_request(host, port, payload)
    print(json.dumps(resp, indent=2))

# ---------------- Entrypoint ----------------

def parse_args():
    p = argparse.ArgumentParser(description="Async TCP Service (client)")
    p.add_argument("--host", default="127.0.0.1", help="server host")
    p.add_argument("--port", type=int, default=13000, help="server port")

    sub = p.add_subparsers(dest="mode")
    sub.add_parser("interactive", help="interactive mode")

    p1 = sub.add_parser("loan", help="one-shot loan request")
    p1.add_argument("username")
    p1.add_argument("amount", type=float)
    p1.add_argument("years", type=int)
    p1.add_argument("rate", type=float)

    p2 = sub.add_parser("get", help="one-shot KV get")
    p2.add_argument("key")

    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if args.mode == "loan":
        asyncio.run(loan_oneshot(args.host, args.port, args.username, args.amount, args.years, args.rate))
    elif args.mode == "get":
        asyncio.run(kv_get_oneshot(args.host, args.port, args.key))
    elif args.mode == "ping":
        asyncio.run(ping_oneshot(args.host, args.port))
    else:
        asyncio.run(interactive(args.host, args.port))