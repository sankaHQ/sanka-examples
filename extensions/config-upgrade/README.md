# Build your first Sanka extension

This small Sanka Code extension reads `example-app.json` and proposes upgrading
`{"schema_version": 1, "title": "Order tracker"}` to
`{"schema_version": 2, "name": "Order tracker"}`. It leaves the input untouched.
It implements **scan and plan only**. It is a teaching example, not an application
converter, and does not advertise apply, test or verify.

## Run the complete check

Use macOS or Linux with Git, OpenSSL and [uv](https://docs.astral.sh/uv/getting-started/installation/).
If uv is missing, install it and follow its printed shell setup instructions:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then:

```bash
git clone https://github.com/sankaHQ/sanka-examples
cd sanka-examples/extensions/config-upgrade
uv run --no-project --python 3.12 python check.py --report acceptance.json
```

The command downloads Python 3.12 when needed, builds this package and verifies
it against **published CLI 0.2.12 and Extension SDK 0.1.0a4**. It requires internet
access to PyPI and public GitHub releases. No other Sanka repository, account,
API token, project dependencies or preinstalled CLI is required.

A successful run prints `"status": "passed"` and the proposed configuration.
The JSON report records the tested versions and checks. The same command runs
on macOS and Linux in this repository's `Extension developer journey` workflow.
Windows is not covered by this starter harness.

The check uses temporary directories and leaves existing CLI installations and
project locks alone. It removes its environments and stops its HTTPS server
when finished. Only the optional report is retained. A network/download failure
fails the check; it is not reported as successful compatibility evidence.

## What happens

1. Download both SDK wheels from immutable `sdk-v0.1.0a4` assets and verify their
   recorded SHA-256 hashes.
2. Build the starter wheel with the pinned build backend. Install the three wheels
   in a separate developer environment and run the contract tests against that
   installed package, rather than importing the source directory.
3. Install `sanka-cli==0.2.12` from PyPI in a clean CLI environment. Confirm the
   starter cannot be imported there.
4. Fill `extension.template.json` with the built wheel and complete SDK dependency
   closure: filenames, HTTPS URLs and hashes. The template itself is not installable.
5. Serve those wheels on loopback HTTPS using a temporary certificate trusted only
   by the child CLI process. No system trust settings, runtime cache or lock files
   are patched. Hash and metadata verification remain enabled.
6. Use the public CLI to trust the marketplace, install the wheel, scan and plan.
   Verify the plan contents, preserved source and isolated extension import.
7. Verify that missing marketplace trust, invalid input and a modified wheel fail.

The actual CLI commands used by the harness are:

```bash
sanka extension marketplace add "$CATALOG" --name starter --trust --json
sanka extension add example/config-upgrade --marketplace starter --json
sanka scan . --json
sanka plan . --to example-config-v2 --json
```

`CATALOG` is the generated local marketplace directory; run these commands from
the fixture project while its wheel server is running. `check.py` owns that
setup and shutdown, so the four commands above explain the sequence rather than
form a standalone installation recipe.

## Edit the extension

| File | Responsibility |
| --- | --- |
| `src/example_config_upgrade/__init__.py` | Decode a request, validate input, return a correlated SDK response |
| `pyproject.toml` | Distribution identity, SDK dependency, executable and build backend |
| `extension.template.json` | Runtime compatibility, project matching, target and supported commands |
| `fixture/example-app.json` | Input exercised through the CLI |
| `tests/test_contract.py` | Input rejection, plan identity, source preservation and malformed transport |
| `check.py` | Public artifact downloads, packaging and full developer journey |

Change the source, then rerun `check.py`. It rebuilds and reinstalls the wheel,
so a stale editable install cannot hide packaging errors. Diagnostics belong on
stderr; stdout must contain exactly one `sanka-extension/v1` response. Use
`decode_request`, `success_response` / `failure_response`, and `encode_response`
from `sanka_extensions.code`; do not import `sanka` runtime internals.

The example rejects unknown source keys, unsupported schemas and unsupported
commands explicitly. It hashes the actual input and plan bytes. Its plan artifact
lives inside the runtime-provided artifact root; the CLI separately records its
own reviewed-plan hash. Neither hash implies that a migration has been applied.

## Publish your own extension

Replace the `example/` ID, package/module/executable names, target and matcher.
Keep distribution versions consistent across package metadata, manifest and
responses. The starter pins CLI compatibility to `==0.2.12`, the version it tests.
Broaden the range only after testing additional versions. Use the same principle
when upgrading the SDK: update its exact dependency and both published wheel
hashes, then run the complete check before changing the compatibility claim.

Host your built wheel and its complete dependency closure at immutable public
HTTPS URLs. Replace the temporary loopback URLs in the manifest, verify every
hash, and publish the manifest with a `sanka-marketplace/v1` catalog. Consumers
explicitly trust your catalog before installing. The generated local certificate
and localhost URLs are only for testing and must not be published.

See the [SDK development guide](https://github.com/sankaHQ/extensions/blob/main/docs/extension-development.md)
and [CLI compatibility table](https://github.com/sankaHQ/sanka/blob/main/docs/compatibility.md).
Do not add hosted SaaS clients or credentials to a local extension. A subprocess
is an execution boundary, not a complete operating-system sandbox.

Apache-2.0; see the bundled [LICENSE](LICENSE).
