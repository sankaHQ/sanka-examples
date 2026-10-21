# Laravel orders API

Synthetic Apache-2.0 source for the unpublished PHP conversion candidate.
The source is original PHP; targets are generated into ignored `.sanka/` directories.

Five route closures exercise owner-scoped orders, bearer authentication, validation, MySQL decimals, identity sequences and transactions.

Run both FastAPI and Go/chi through the public CLI in a prepared disposable Linux
environment using the [PHP walkthrough](../README.md). PHP, Laravel, Python and Go
versions are pinned there. No Sanka account or production database is needed.

This fixture qualifies only its declared route closures and ordered scenarios.
It does not qualify controllers, Sanctum, Eloquent, arbitrary Composer packages,
or whole-application migration. Review `source/sanka-verify.json` for the exact
requests, including denied requests and failure paths.
