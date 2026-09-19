"""Exercise the compiled source launcher over real loopback HTTP, without paid services."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "/health": (200, {"status": "ok"}),
    "/status": (202, {"service": "status-api", "ready": True, "revision": 1}),
}


def observe(base_url: str) -> dict:
    results = {}
    for path, (status, body) in EXPECTED.items():
        with urlopen(base_url + path, timeout=5) as response:
            raw = response.read().decode()
            media_type = response.headers.get_content_type()
            actual = json.loads(raw)
            assert (response.status, media_type, actual) == (status, "application/json", body)
            results[path] = {"status": response.status, "content_type": response.headers["Content-Type"], "body": actual, "raw_body": raw}
    return results


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_observe(process: subprocess.Popen, port: int) -> dict:
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError(f"server exited with {process.returncode}")
        try:
            return observe(f"http://127.0.0.1:{port}")
        except (ConnectionError, OSError):
            time.sleep(0.05)
    raise RuntimeError("server did not become ready")


def main() -> None:
    port = available_port()
    node = ROOT / "node_modules/node/bin/node"
    process = subprocess.Popen([str(node), ".sanka/source/server.js"], cwd=ROOT, env={**os.environ, "PORT": str(port)})
    try:
        print(json.dumps({"source_http": wait_observe(process, port)}, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    main()
