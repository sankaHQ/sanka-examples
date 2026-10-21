# PHP to FastAPI and Go

These are unpublished converter candidates. Package publication and hosted
activation require separate release approval. The public marketplace does not
install them yet.

| Example | Source | Targets | Database |
| --- | --- | --- | --- |
| [Custom JSON API](custom-json-api/) | Explicit PHP functions | FastAPI, chi | None |
| [Laravel orders API](laravel-orders-api/) | Laravel 12 route closures | FastAPI, chi | MySQL remains MySQL |

The candidate supports selected API routes and their declared dependencies.
Unknown middleware, controllers, Sanctum, Eloquent, dynamic routes and unsupported
Composer dependencies block Apply. WordPress and Drupal are outside this profile.
Keep a patched PHP deployment while evaluating a migration; a generated candidate
is not a security patch or a production cutover.

## Prepare a disposable Linux environment

Use PHP 8.4.27 with PDO MySQL/SQLite and mbstring, Laravel 12.70.1, Python 3.12.13,
Go 1.27.0 and MySQL 8.4.11. Build the reviewed extensions revision with
`uv run python scripts/build_php_release.py`. Its shared PHP wheel contains
Composer, Python and Go dependency locks. Install those dependencies before
starting isolated replay, with Composer scripts and plugins disabled.

Set the prepared source framework directory, Python target interpreter and Go
module/build caches through `SANKA_PHP_FRAMEWORK`, `SANKA_PHP_PYTHON`,
`SANKA_PHP_GOMODCACHE` and `SANKA_PHP_GOCACHE`. MySQL requires a disposable
`sanka_php_admin` database on localhost or `mysql`, supplied through
`SANKA_PHP_MYSQL_ADMIN_URL`. The optional `SANKA_PHP_MYSQL_SOCKET` selects a Unix
socket for a network-isolated worker. Never use production database credentials.
`SANKA_PHP_REPLAY=1` confirms that this Linux environment is disposable and isolated.

From this repository, run:

```bash
python3 php/check.py --bundle /absolute/path/to/release/php-converters \
  --revision FULL_REVIEWED_EXTENSIONS_COMMIT
```

The harness installs a fresh published CLI and the exact candidate wheel closure
through a temporary HTTPS marketplace. It checks every wheel digest, copies each
source, runs Scan → Plan → Apply → Test → Verify for both targets, and checks source
preservation. Reports remain in `php/.sanka/evidence/`; an absent report is not a pass.
No generated target is maintained by hand. A candidate response is deliberately
changed in the extension's Linux gate to prove Verify can fail.

## What Verify establishes

Each selected route must have a scenario with an independently declared expected
status. Verify executes the original PHP and native candidate, comparing status,
JSON media type and body, every declared table and identity sequence after each
request. Source and target use separate disposable schemas and users. It does
not establish arbitrary response headers, streaming, all possible inputs or
whole-backend parity. Unselected and unresolved routes remain unverified.

## Real GitHub assessment corpus

The user-requested real-world pilot research selected two MIT-licensed projects:
[guillaumebriday/laravel-blog](https://github.com/guillaumebriday/laravel-blog) for
its Laravel/Sanctum API and feature tests, and
[mevdschee/php-crud-api](https://github.com/mevdschee/php-crud-api) for PDO/MySQL,
auth middleware and functional fixtures. [pilots.json](pilots.json) records exact
commits and static assessment results. Neither project currently passes the
bounded conversion profile. Zero resolved routes in those reports means the
inventory is incomplete, not that the project contains no routes.

Their source was inspected as data without installing dependencies or executing
PHP. No copied third-party application is presented as a successful migration.
The next qualification must retain a real endpoint's auth, validation and data
closure and its tests; replacing it with a toy endpoint would not count.
