# React Native task list → SwiftUI

A synthetic two-screen TypeScript / React Native application. Expo supplies the
source runtime and Metro configuration; the source is not just a scanner fixture.
The published converter generates Swift / SwiftUI. Kotlin / Compose is a separate
**scan/plan-only** walkthrough; it does not produce a completed application.

## Source setup and behavior

Use Node.js **22** and npm, then run from this directory:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run check
EXPO_NO_TELEMETRY=1 npm run bundle
npm start
```

`package-lock.json` pins the dependency closure. The runtime is Expo 54.0.37,
React Native 0.81.5 and React 19.1.0, with React Navigation 7. The dependency override
pins React Navigation Elements to the version compatible with the selected native
package. The Expo entry point loads `App.tsx`; no missing generated native project
is required for the Expo Go route. Open the Metro URL with an Expo Go build matching
SDK 54. A configured iOS simulator or Android emulator can use `npm run ios` or
`npm run android`. Those platform launch commands are provided as manual steps;
they were **not executed** in acceptance. `npm run bundle` builds a real Hermes iOS
bundle under ignored `.sanka/source-bundle/`, but does not launch the app.

| Action / state | Source and expected generated behavior |
| --- | --- |
| Open Home | `Tasks (1)`, empty `New task` input, one task named `Read migration guide` |
| Enter a title | Update local `title` state |
| Press Add task | Append a task with next numeric ID, current title and `done: false`; clear the input; increase count |
| Press a task | Navigate to Detail with its typed numeric `id` and string `title` |
| Open Detail | Show the route title, `Task #<id>`, off switch and `Open` |
| Toggle switch | Update Detail's local `done`; show `Completed` when true and `Open` when false |
| Back | Return to Home; the Detail switch does not update Home's task objects |

State is in memory. Empty task titles are allowed by this deliberately small
application. There is no database, network request, persistence, paid inference or
customer information.

## Published converter and toolchains

Extension ID: `sanka/react-native-to-native`; distribution version: `0.1.0a1`.
It is **experimental**, published as the scoped GitHub prerelease
[`mobile-converters-v0.1.0a1`](https://github.com/sankaHQ/extensions/releases/tag/mobile-converters-v0.1.0a1)
from catalog commit
[`826005294a616ae52bd166ee534a5b66513328b3`](https://github.com/sankaHQ/extensions/commit/826005294a616ae52bd166ee534a5b66513328b3).
The consumer uses published `sanka-cli==0.2.12`, extension SDK `0.1.0a4`, and the
released `sanka-ts-capture` wheel (vendored TypeScript 5.9.3). The public CLI installs
it from the public catalog pinned to that exact commit:

```sh
sanka extension marketplace add https://github.com/sankaHQ/extensions.git \
  --revision 826005294a616ae52bd166ee534a5b66513328b3 --name release --trust --json
sanka extension add sanka/react-native-to-native --marketplace release --json
```

The CLI's default marketplace snapshot predates this release, so the explicit
revision is required.

Prerequisites for the clean consumer walkthrough: Python 3.10 or later, `uv`, Git,
OpenSSL, Node 22 and npm. SwiftUI also requires macOS 14 or later with the Swift
compiler and macOS SDK. This example was checked using Apple Swift 6.3.3 on macOS.
On hosts using Command Line Tools, the documented environment selection is:

```sh
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
```

A generated iOS app requires the separate XcodeGen 2.46.0 / Xcode 16+ toolchain.
That simulator/device build and execution were **not run** here. No command in this
walkthrough accepts an Xcode license or changes the system developer-directory
selection.

## SwiftUI: clean consumer lifecycle

From the repository root, run:

```sh
python3 react-native/task-list/check.py --target swiftui
```

[`check.py`](check.py) uses the shared [`candidate.py`](../../scripts/candidate.py)
consumer (`Published`). It fetches the immutable public Git revision into a fresh
temporary checkout, requires the extension to be catalogued there, checks that the
manifest at that commit is byte-identical to the released asset and that every wheel
URL points at the release, creates an isolated CLI environment and installs with
the two **public CLI extension commands** above. There is no dependency on a
sibling checkout and nothing is built locally. Setup needs public package
downloads; migration uses local files only.

Within the clean source copy, the harness installs and checks the source, then
runs these public CLI commands (each also receives `--json`):

```sh
sanka scan . --artifact-dir .sanka/swiftui \
  --extension-config '{"target_framework":"swiftui"}' \
  --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS --extension-env DEVELOPER_DIR
sanka plan . --to swiftui --artifact-dir .sanka/swiftui \
  --extension-config '{"target_framework":"swiftui"}' \
  --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS --extension-env DEVELOPER_DIR
sanka apply --root . --to swiftui --plan-hash "$REVIEWED_PLAN_HASH" \
  --artifact-dir .sanka/swiftui --extension-config '{"target_framework":"swiftui"}' \
  --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS --extension-env DEVELOPER_DIR
sanka test --root . --to swiftui --artifact-dir .sanka/swiftui \
  --extension-config '{"target_framework":"swiftui"}' \
  --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS --extension-env DEVELOPER_DIR
sanka verify --root . --to swiftui --artifact-dir .sanka/swiftui \
  --extension-config '{"target_framework":"swiftui"}' \
  --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS --extension-env DEVELOPER_DIR
```

These are the harness's lifecycle commands, not a standalone installer. It sets
`SANKA_NODE` to the Node 22 executable, `SANKA_NODE_TOOLS` to the clean source's
`node_modules`, and forwards `DEVELOPER_DIR` only if set. The reviewed runtime plan
hash comes from `plan`'s `data.plan_hash`; the runtime supplies the extension's
separate plan hash. Review the capture, gaps, generated files and destinations
before using this pattern for any other source. The automated example validates
its fixed contract before applying and rejects a non-success result at any stage.

The harness checks repeated plan identity and source preservation, then saves the
generated files, stage results, wheel identities and SHA-256 artifact hashes in:

```text
.sanka/acceptance-swiftui/report.json
.sanka/acceptance-swiftui/artifacts/
```

Output remains ignored and is regenerated from the source; no second handwritten
Swift app is maintained. Re-running the harness creates another clean consumer
environment. Core runtime hashes can include the temporary environment identity;
compare the extension plan and generated-file digests when comparing runs.

## What structural replay proves

`test` builds the generated Swift package for **macOS** and runs its
`sanka-tree-dump` executable. `verify` transpiles the actual source screen modules,
renders them with React 19.1.0 / react-test-renderer 19.1.0 against the extension's
React Native **stubs**, and compares normalized trees and recorded actions with the
generated native trees. It checks initial screen structure, typed text, task
addition and switch changes in five scenarios: Home initial/type/press and Detail
initial/toggle. Each action scenario starts from the initial state; it does not
exercise the combined type-then-add sequence. Navigation intents are represented in trees; this is
not an end-to-end navigation session. Replay uses deterministic sample route
parameters rather than traversing from Home to Detail.

This does **not** establish pixels, layout, fonts, simulator/device behavior,
accessibility behavior, real React Native component rendering or full-app parity.
The SwiftUI view and normalized tree are emitted from the same intermediate
representation; the latter is not an independently observed screenshot or view
hierarchy. Source device execution and generated iOS execution remain unverified.
`complete_app` remains `false` even when structural comparison passes.

## Compose: scan and plan only

Node 22 is required; macOS and Swift are not required for this path. From the
repository root:

```sh
python3 react-native/task-list/check.py --target compose
```

The same clean installer/source checks run, then the harness invokes:

```sh
sanka scan . --artifact-dir .sanka/compose --extension-config '{"target_framework":"compose"}' --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS
sanka plan . --to compose --artifact-dir .sanka/compose --extension-config '{"target_framework":"compose"}' --extension-env SANKA_NODE --extension-env SANKA_NODE_TOOLS
```

Evidence is saved under `.sanka/acceptance-compose/`. Apply, Kotlin generation,
Android compilation, test and verify are **unsupported and not run**. Scan/plan
success is not an app conversion. This destination does not imply support for
arbitrary React web, Kotlin source or Swift source migrations.

## Provenance and acceptance

The application is synthetic, authored for this repository under Apache-2.0;
see [LICENSE](LICENSE). Its small supported syntax follows the pinned converter's
Apache-2.0 React Navigation fixture recipe. Dependencies retain their own licenses.
[evidence.json](evidence.json) records the checked toolchains and stage status;
the reproducible harness creates detailed evidence under ignored `.sanka/`.
