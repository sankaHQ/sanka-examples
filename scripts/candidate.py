# SPDX-License-Identifier: Apache-2.0
"""Install an immutable, unpublished converter through the public CLI marketplace.

Only setup downloads dependencies. Migration itself uses no Sanka service or model.
Each invocation owns a fresh source copy, CLI, extension store and loopback server.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

EXTENSIONS_REVISION = "edc6e27744e9a0cb1a8f72cd5bb0f3003288fc20"
# The scoped Go and Rust prerelease: catalog commit and GitHub release tag.
PUBLISHED_REVISION = "db8953b596325b8ed982c69e92a5a08ad0d3a5d6"
PUBLISHED_TAG = "api-converters-v0.1.0a1"
# The scoped React Native prerelease: catalog commit and GitHub release tag.
MOBILE_PUBLISHED_REVISION = "826005294a616ae52bd166ee534a5b66513328b3"
MOBILE_PUBLISHED_TAG = "mobile-converters-v0.1.0a1"
PUBLISHED_TAGS = {
    "python-to-golang": PUBLISHED_TAG,
    "typescript-to-rust": PUBLISHED_TAG,
    "react-native-to-native": MOBILE_PUBLISHED_TAG,
}
EXTENSIONS_GIT = "https://github.com/sankaHQ/extensions.git"
RELEASE_DOWNLOADS = "https://github.com/sankaHQ/extensions/releases/download"
CLI_VERSION = "0.2.12"
SDK_RELEASE = "https://github.com/sankaHQ/extensions/releases/download/sdk-v0.1.0a4"
SDK_WHEELS = {
    "sanka_connector_sdk-0.1.0a12-py3-none-any.whl": "34da5c35aaa60fc19258e76b72a3eca58bf52fff96e2ccf9a0aa1115f8878d8e",
    "sanka_extension_sdk-0.1.0a4-py3-none-any.whl": "f1a6655095ab81e549137e1d9604492bda2a31677d674c6359b0a39a2da96307",
}
IGNORED = {
    ".git",
    ".sanka",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    ".expo",
    ".build",
    "target",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


class Candidate:
    def __init__(
        self,
        example: Path,
        extension: str,
        packages: list[str],
        targets: list[str],
        match_file: str,
        revision: str = EXTENSIONS_REVISION,
        cli_version: str = CLI_VERSION,
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Candidate revision must be a full immutable commit hash")
        self.revision = revision
        self.example = example.resolve()
        self.extension = extension
        self.packages = packages
        self.targets = targets
        self.match_file = match_file
        self.cli_version = cli_version
        self.report: dict = {
            "cli_version": self.cli_version,
            "extension_revision": self.revision,
            "extension_id": f"sanka/{extension}",
            "sdk_version": "0.1.0a4",
            "release_status": "experimental-unpublished",
            "commands": [],
        }
        self.server = None
        self.thread = None
        self.temporary = None
        self.cli_env: dict[str, str] = {}

    def run(self, *args: str, cwd: Path | None = None, env: dict | None = None) -> str:
        command = [str(arg) for arg in args]
        print("candidate: " + " ".join(command[:4]), file=sys.stderr, flush=True)
        result = subprocess.run(
            command,
            cwd=cwd or self.project,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Command failed ({result.returncode}): {command}\n"
                f"{result.stdout[-16000:]}\n{result.stderr[-16000:]}"
            )
        return result.stdout

    def cli(self, *args: str) -> dict:
        command = [*args, "--json"]
        self.report["commands"].append(command)
        output = self.run(
            str(self.root / "cli/bin/sanka"),
            *command,
            env=self.env | self.cli_env,
        )
        data = json.loads(output)
        if data.get("outcome") == "error":
            raise RuntimeError(f"CLI reported failure: {data}")
        return data

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sanka-example-")
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        try:
            self._setup()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def _download(self, url: str, path: Path, digest: str) -> None:
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
        if sha(path) != digest:
            raise ValueError(f"Download checksum mismatch: {path.name}")

    def _setup(self) -> None:
        uv = shutil.which("uv")
        if not uv or not shutil.which("openssl"):
            raise RuntimeError("Install uv and OpenSSL first")
        self._prepare_workspace()
        checkout = self._fetch_extensions()
        catalog = json.loads((checkout / "marketplace.json").read_text())
        if any(
            item["id"] == f"sanka/{self.extension}" for item in catalog["extensions"]
        ):
            raise ValueError(
                "Candidate is now catalogued; review release status before using this installer"
            )
        self.report["catalog_sha256"] = sha(checkout / "marketplace.json")
        wheels = self.root / "wheels"
        wheels.mkdir()
        for filename, digest in SDK_WHEELS.items():
            self._download(f"{SDK_RELEASE}/{filename}", wheels / filename, digest)
        constraints = self.root / "build-constraints.txt"
        constraints.write_text(
            "hatchling==1.27.0\npackaging==25.0\npathspec==0.12.1\npluggy==1.6.0\ntrove-classifiers==2025.9.11.17\n"
        )
        if "sanka-ts-capture" in self.packages:
            bundle_env = self.env | {
                "PYTHONPATH": str(checkout / "packages/sanka-ts-capture/src")
            }
            self.run(
                sys.executable,
                str(checkout / "scripts/fetch_typescript_bundle.py"),
                env=bundle_env,
            )
        for package in [*self.packages, f"sanka-extension-{self.extension}"]:
            self.run(
                uv,
                "build",
                "--wheel",
                "--build-constraint",
                str(constraints),
                "--out-dir",
                str(wheels),
                str(checkout / "packages" / package),
            )
        self.report["wheels"] = {p.name: sha(p) for p in sorted(wheels.glob("*.whl"))}
        self._install_cli()
        self._serve_candidate(wheels)

    def _prepare_workspace(self) -> None:
        self.env = {
            k: os.environ[k]
            for k in ("PATH", "TMPDIR", "LANG", "SYSTEMROOT", "DEVELOPER_DIR")
            if k in os.environ
        }
        self.env.update(
            UV_NO_CONFIG="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            SOURCE_DATE_EPOCH="315532800",
            PYTHONHASHSEED="0",
        )
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "SANKA_HOME"):
            directory = self.root / name.lower()
            directory.mkdir()
            self.env[name] = str(directory)
        shutil.copytree(
            self.example,
            self.project,
            ignore=lambda _p, names: [
                n for n in names if n in IGNORED or n.endswith(".pyc")
            ],
        )

    def _fetch_extensions(self) -> Path:
        """Fetch exactly the pinned public extensions commit into a fresh checkout."""
        checkout = self.root / "extensions"
        self.run("git", "init", str(checkout))
        self.run(
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/sankaHQ/extensions.git",
            cwd=checkout,
        )
        self.run("git", "fetch", "--depth", "1", "origin", self.revision, cwd=checkout)
        self.run("git", "checkout", "--detach", "FETCH_HEAD", cwd=checkout)
        if self.run("git", "rev-parse", "HEAD", cwd=checkout).strip() != self.revision:
            raise ValueError("Unexpected converter revision")
        return checkout

    def _install_cli(self) -> None:
        """Install the published CLI into an isolated environment owned by this run."""
        uv = shutil.which("uv")
        cli_env = self.root / "cli"
        self.run(uv, "venv", "--python", "3.12", str(cli_env))
        self.run(
            uv,
            "pip",
            "install",
            "--python",
            str(cli_env / "bin/python"),
            f"sanka-cli=={self.cli_version}",
        )
        self.report["cli_dependencies"] = self.run(
            uv, "pip", "freeze", "--python", str(cli_env / "bin/python")
        ).splitlines()

    def _serve_candidate(self, wheels: Path) -> None:
        """Serve the built wheels over loopback HTTPS through a temporary trusted marketplace."""
        config = self.root / "openssl.cnf"
        config.write_text(
            "[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
            "[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:TRUE\n"
        )
        cert, key = self.root / "localhost.pem", self.root / "localhost.key"
        self.run(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-config",
            str(config),
            "-keyout",
            str(key),
            "-out",
            str(cert),
        )
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(wheels))
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cli_env = {"SSL_CERT_FILE": str(cert)}
        marketplace = self.root / "marketplace"
        marketplace.mkdir()
        distribution = f"sanka-extension-{self.extension}"
        manifest = {
            "schema_version": "sanka-extension-manifest/v2",
            "id": f"sanka/{self.extension}",
            "version": "0.1.0a1",
            "kind": "migration",
            "runtime": {"sanka_cli": f"=={self.cli_version}"},
            "distribution": {
                "name": distribution,
                "version": "0.1.0a1",
                "executable": distribution,
            },
            "protocol_version": "sanka-extension/v1",
            "commands": ["scan", "plan", "apply", "test", "verify"],
            "targets": self.targets,
            "match": {"all": [{"kind": "file", "value": self.match_file}], "any": []},
            "wheels": [
                {
                    "name": p.name,
                    "sha256": sha(p),
                    "url": f"https://localhost:{self.server.server_port}/{p.name}",
                }
                for p in sorted(wheels.glob("*.whl"))
            ],
        }
        (marketplace / "extension.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        (marketplace / "marketplace.json").write_text(
            json.dumps(
                {
                    "schema_version": "sanka-marketplace/v1",
                    "extensions": [
                        {"id": manifest["id"], "manifest": "extension.json"}
                    ],
                }
            )
        )
        self.cli(
            "extension",
            "marketplace",
            "add",
            str(marketplace),
            "--name",
            "candidate",
            "--trust",
        )
        self.cli("extension", "add", manifest["id"], "--marketplace", "candidate")

    def __exit__(self, *_args):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)
        if self.temporary:
            self.temporary.cleanup()


class Published(Candidate):
    """Install a converter that is published in the public catalog at an immutable commit.

    The same isolated CLI environment and fresh source copy as ``Candidate``, but the
    extension comes from the public Git catalog pinned to ``revision`` with the
    public CLI's own marketplace commands. The manifest at that commit must be the
    one attached to the GitHub release ``release_tag``; nothing is built locally.
    """

    def __init__(
        self,
        example: Path,
        extension: str,
        packages: list[str],
        targets: list[str],
        match_file: str,
        revision: str = PUBLISHED_REVISION,
        release_tag: str | None = None,
        cli_version: str = CLI_VERSION,
    ):
        super().__init__(
            example, extension, packages, targets, match_file, revision, cli_version
        )
        self.release_tag = release_tag or PUBLISHED_TAGS[extension]
        self.report["release_status"] = "experimental-published"
        self.report["release_tag"] = self.release_tag

    def _setup(self) -> None:
        if not shutil.which("uv"):
            raise RuntimeError("Install uv first")
        self._prepare_workspace()
        checkout = self._fetch_extensions()
        catalog = json.loads((checkout / "marketplace.json").read_text())
        identifier = f"sanka/{self.extension}"
        entries = [item for item in catalog["extensions"] if item["id"] == identifier]
        if len(entries) != 1:
            raise ValueError(f"{identifier} is not catalogued at {self.revision}")
        self.report["catalog_sha256"] = sha(checkout / "marketplace.json")
        manifest = json.loads((checkout / entries[0]["manifest"]).read_text())
        asset = self.root / f"sanka-extension-{self.extension}.json"
        with urllib.request.urlopen(
            f"{RELEASE_DOWNLOADS}/{self.release_tag}/{asset.name}", timeout=120
        ) as response:
            asset.write_bytes(response.read())
        if json.loads(asset.read_text()) != manifest:
            raise ValueError("Public Git manifest differs from the released asset")
        prefix = f"{RELEASE_DOWNLOADS}/{self.release_tag}/"
        if not manifest.get("wheels") or any(
            not wheel["url"].startswith(prefix) for wheel in manifest["wheels"]
        ):
            raise ValueError("Released wheels must come from the release itself")
        self.report["manifest_sha256"] = sha(asset)
        self.report["wheels"] = {w["name"]: w["sha256"] for w in manifest["wheels"]}
        self._install_cli()
        self.cli(
            "extension",
            "marketplace",
            "add",
            EXTENSIONS_GIT,
            "--revision",
            self.revision,
            "--name",
            "release",
            "--trust",
        )
        self.cli("extension", "add", identifier, "--marketplace", "release")
