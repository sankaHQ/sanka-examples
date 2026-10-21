# Spring Boot greetings → FastAPI

This synthetic Apache-2.0 example exercises the unpublished
`sanka/java-to-python` candidate through all five public CLI stages. Its three GET
routes cover literal JSON, a record response, a nullable field, string path/query
parameters, defaults, repeated query values, Unicode and an integer above 2^53.

The source has three native JUnit tests. Migration Test runs nine Python cases;
Verify compares nine ordered requests using Spring MockMvc and FastAPI TestClient.
The walkthrough deliberately changes a generated response and requires Verify to
fail, then retains the original generated candidate. See [evidence.json](evidence.json)
for the recorded scope and immutable converter revision.

No database, customer data, Sanka account or model API is needed. Authentication,
CRUD, custom service logic, default error responses, arbitrary headers,
HEAD/OPTIONS and live TCP parity are outside this example. The packages have not
been published to the official marketplace.

## Prepare the pinned converter

Prerequisites: macOS or Linux, a Java 21 JDK, Git, OpenSSL and uv 0.11.21.
Use a separate checkout of the converter revision recorded in
[migration.json](migration.json). The following commands run from this example:

```sh
JAVA_CONVERTER_REVISION=$(python3 -c 'import json; print(json.load(open("migration.json"))["destinations"][0]["candidate_revision"])')
git clone https://github.com/sankaHQ/extensions .sanka/extensions
git -C .sanka/extensions checkout --detach "$JAVA_CONVERTER_REVISION"
cd .sanka/extensions
python3 scripts/fetch_java_parser.py
python3 scripts/fetch_java_maven.py
uv sync --frozen --all-packages
uv venv --python 3.12.13 .java-tools/python
uv pip sync --python .java-tools/python/bin/python --require-hashes \
  packages/sanka-extension-java-to-python/src/sanka_extension_java_to_python/requirements.lock
export SANKA_JAVA_REPLAY=1
export SANKA_JAVA_MAVEN="$PWD/.java-tools/apache-maven-3.9.16/bin/mvn"
export SANKA_JAVA_MAVEN_REPO="$PWD/.java-tools/maven-repository"
export SANKA_JAVA_PYTHON="$PWD/.java-tools/python/bin/python"
uv run python scripts/prepare_java_fixture.py
uv run python scripts/build_java_release.py
cd ../..
```

Preparation downloads pinned tools/dependencies and executes a trusted synthetic
source fixture. Scan itself never executes application code. Replay executes code
in disposable copies with a minimal environment; these copies are not a security
sandbox. Use an isolated machine/container for unfamiliar source applications.

## Run the migration and verification

```sh
python3 check.py --bundle .sanka/extensions/release/java-converters
```

The harness verifies bundle provenance and wheel hashes, creates a fresh source
copy, installs **CLI 0.3.9**, and installs the candidate through a temporary
loopback HTTPS marketplace. The certificate is trusted only by that child CLI;
your installed CLI and system trust store are unchanged. It executes:

```text
sanka scan <source>
sanka plan <source> --to python-fastapi
sanka apply --root <source> --plan-hash <reviewed runtime hash>
sanka test <source>
sanka verify <source>
```

The harness forwards only the explicitly named Java/Python toolchain variables to
the extension. It checks the example's own JUnit tests, source preservation, every
lifecycle result, actual parity observations and an intentional mismatch. It
writes a fresh `.sanka/evidence.json` and retains `.sanka/python-fastapi` for review.
Move that generated directory before another run; existing output is preserved.

## Run either application

The original Spring service:

```sh
cd source
"$SANKA_JAVA_MAVEN" -Dmaven.repo.local="$SANKA_JAVA_MAVEN_REPO" test
"$SANKA_JAVA_MAVEN" -Dmaven.repo.local="$SANKA_JAVA_MAVEN_REPO" spring-boot:run
```

The `spring-boot:run` Maven goal may download its additional plugin dependencies.
The service listens on port 8080 by default. From another terminal:

```sh
curl 'http://127.0.0.1:8080/api/greetings?name=Alice&name=Bob'
```

The generated service runs independently with Python:

```sh
cd .sanka/python-fastapi
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes requirements.lock
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn app:app --port 8000
```

Its response to `/api/greetings?name=Alice&name=Bob` is:

```json
{"message":"Hello, Alice,Bob","requestId":9007199254740993,"active":true,"note":null}
```

The generated service does not require a JVM, Sanka runtime, or original source.
Passing these cases establishes this example's recorded behavior; it does not
establish whole-application or production-cutover compatibility.
