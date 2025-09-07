"""
Async TCP Service (server)
"""
import argparse                 # For parsing command-line arguments
import asyncio                  # For asynchronous sockets and tasks
import json                     # For encoding/decoding JSON messages
import signal                   # For handling Ctrl+C shutdown signals
import struct                   # For packing/unpacking binary message length headers
from datetime import datetime, timezone   # For timestamps in logs
from typing import Any, Dict, Tuple       # For type hints

# Create a struct to pack/unpack 4-byte big-endian integers (message length headers)
HEADER = struct.Struct("!I")

# ---------------- Loan math ----------------

def calculate_payments(loan_amount: float, years: int, annual_rate: float) -> Tuple[float, float]:
    """Calculate monthly and total payments."""
    monthly_rate = (annual_rate / 100.0) / 12.0     # Convert annual rate (percent) to monthly decimal
    total_payments = years * 12                     # Number of months = years × 12
    if monthly_rate == 0:                           # Handle zero-interest loans
        monthly_payment = loan_amount / total_payments
    else:
        # Amortization formula for monthly loan repayment
        monthly_payment = (loan_amount * monthly_rate) / (1 - (1 / (1 + monthly_rate)) ** total_payments)
    total_payment = monthly_payment * total_payments  # Multiply by number of months to get total
    return round(monthly_payment, 2), round(total_payment, 2)

# ---------------- File logger ----------------

class JsonlLogger:
    """Thread-safe logger that appends JSON lines to a file."""
    def __init__(self, path: str):
        self.path = path                   # Path to log file (set via --log argument)
        self._lock = asyncio.Lock()        # Lock to prevent race conditions when multiple clients log

    async def log(self, record: Dict[str, Any]) -> None:
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)   # Serialize dict as compact JSON string
        async with self._lock:             # Ensure only one task writes at a time
            await asyncio.to_thread(self._append_line, line)   # Offload file write to thread pool

    def _append_line(self, line: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")           # Append JSON object as a line in the file

# ---------------- Framing ----------------

async def read_frame(reader: asyncio.StreamReader) -> Dict[str, Any]:
    hdr = await reader.readexactly(HEADER.size)      # Read exactly 4 bytes (the header)
    (length,) = HEADER.unpack(hdr)                  # Extract message length
    if length < 0 or length > 10_000_000:           # Prevent abuse (too big frame)
        raise ValueError("invalid frame length")
    data = await reader.readexactly(length)         # Read exact payload bytes
    return json.loads(data.decode("utf-8"))         # Decode JSON string into Python dict

async def write_frame(writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")  # Serialize dict to JSON bytes
    writer.write(HEADER.pack(len(data)) + data)      # Prefix with 4-byte length header
    await writer.drain()                            # Ensure bytes are sent out

# ---------------- Server core ----------------

class KVStore:
    """Simple in-memory key-value store."""
    def __init__(self):
        self._data: Dict[str, Any] = {}            # Dictionary to store key-value pairs
        self._lock = asyncio.Lock()                # Async lock to ensure safe access

    async def set(self, key: str, value: Any) -> Dict[str, Any]:
        async with self._lock:
            self._data[key] = value
        return {"ok": True}

    async def get(self, key: str) -> Dict[str, Any]:
        async with self._lock:
            if key not in self._data:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "value": self._data[key]}

    async def delete(self, key: str) -> Dict[str, Any]:
        async with self._lock:
            existed = self._data.pop(key, None) is not None
        return {"ok": True, "deleted": existed}

    async def keys(self) -> Dict[str, Any]:
        async with self._lock:
            return {"ok": True, "keys": list(self._data.keys())}

    async def clear(self) -> Dict[str, Any]:
        async with self._lock:
            self._data.clear()
        return {"ok": True}

# Handle one client connection (called for each client)
async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, logger: JsonlLogger, store: KVStore):
    peer = writer.get_extra_info("peername") or ("?", 0)  # Get client IP and port
    client_ip, client_port = str(peer[0]), int(peer[1])
    try:
        while True:
            try:
                req = await asyncio.wait_for(read_frame(reader), timeout=300)  # Wait for request, with idle timeout
            except asyncio.TimeoutError:
                resp = {"ok": False, "error": "idle timeout"}  # If idle too long, send timeout error
                await write_frame(writer, resp)
                await logger.log({        # Log timeout event
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "peer": {"ip": client_ip, "port": client_port},
                    "event": "timeout",
                    "response": resp,
                })
                break
            except asyncio.IncompleteReadError:
                break    # Client closed connection
            except Exception as e:
                resp = {"ok": False, "error": str(e)}  # Catch any parsing/decoding errors
                await write_frame(writer, resp)
                await logger.log({        # Log the error
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "peer": {"ip": client_ip, "port": client_port},
                    "event": "read_error",
                    "error": str(e),
                })
                continue

            cmd = (req.get("cmd") or "").upper()   # Extract the "cmd" field

            # Dispatch by command type
            if cmd == "PING":
                response = {"ok": True, "reply": "PONG"}

            elif cmd == "LOAN":
                try:
                    username = str(req.get("username") or "")
                    loan_amount = float(req["loan_amount"])
                    years = int(req["years"])
                    annual_rate = float(req["annual_rate"])
                    monthly, total = calculate_payments(loan_amount, years, annual_rate)
                    response = {"ok": True, "monthly_payment": monthly, "total_payment": total}
                except KeyError as e:
                    response = {"ok": False, "error": f"missing field: {e}"}
                except Exception as e:
                    response = {"ok": False, "error": str(e)}

            elif cmd == "SET":
                key = req.get("key")
                if key is None or "value" not in req:
                    response = {"ok": False, "error": "SET requires 'key' and 'value'"}
                else:
                    response = await store.set(str(key), req["value"])

            elif cmd == "GET":
                key = req.get("key")
                if key is None:
                    response = {"ok": False, "error": "GET requires 'key'"}
                else:
                    response = await store.get(str(key))

            elif cmd == "DEL":
                key = req.get("key")
                if key is None:
                    response = {"ok": False, "error": "DEL requires 'key'"}
                else:
                    response = await store.delete(str(key))

            elif cmd == "KEYS":
                response = await store.keys()

            elif cmd == "CLEAR":
                response = await store.clear()

            else:
                response = {"ok": False, "error": f"unknown cmd: {cmd}"}

            # Send response back to client
            await write_frame(writer, response)
            # Log the request and response
            await logger.log({
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "peer": {"ip": client_ip, "port": client_port},
                "request": req,
                "response": response,
            })

    finally:
        writer.close()                        # Ensure socket is closed
        try:
            await writer.wait_closed()        # Wait until it’s fully closed
        except Exception:
            pass

# Start server, setup graceful shutdown
async def run_server(host: str, port: int, log_path: str):
    logger = JsonlLogger(log_path)    # Logger instance writing to local file
    store = KVStore()                 # Shared in-memory key-value store

    server = await asyncio.start_server(lambda r, w: handle_client(r, w, logger, store), host, port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"Serving on {addrs}")

    stop = asyncio.Event()            # Async event used to stop the server

    def _graceful(*_):
        stop.set()                    # Set stop event on SIGINT/SIGTERM

    loop = asyncio.get_running_loop()
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                loop.add_signal_handler(sig, _graceful)   # Register graceful shutdown
            except NotImplementedError:
                pass

    async with server:
        await stop.wait()             # Keep server alive until stop event is set
        print("Shutting down...")

# ---------------- Entrypoint ----------------

def parse_args():
    p = argparse.ArgumentParser(description="Async TCP Service (server)")
    p.add_argument("--host", default="0.0.0.0", help="bind address")
    p.add_argument("--port", type=int, default=13000, help="port number")
    # <<< CHANGE THIS PATH to where you want logs saved locally >>>
    p.add_argument("--log", default=r"C:\Users\pg84s\GitHub\Socket-Client-Server-Loan-Calculator\server_logs.jsonl", help="path to JSON Lines log file")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_server(args.host, args.port, args.log))