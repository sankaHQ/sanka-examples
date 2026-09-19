# SPDX-License-Identifier: Apache-2.0
"""Validate the companion index without dependencies or network access."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["scan", "plan", "apply", "test", "verify"]


def validate(root: Path) -> None:
    legacy = json.loads((root / "manifest.json").read_text())
    if legacy["schema"] != "sanka-examples/manifest/v1":
        raise ValueError("Legacy manifest schema must remain v1")
    index = json.loads((root / "migrations.json").read_text())
    if index["schema"] != "sanka-examples/migrations/v1":
        raise ValueError("Unsupported migration index")
    seen = set()
    for entry in index["examples"]:
        identifier = entry["id"]
        if identifier in seen:
            raise ValueError(f"Duplicate example: {identifier}")
        seen.add(identifier)
        directory = root / identifier
        if directory.is_symlink() or root.resolve() not in directory.resolve().parents:
            raise ValueError("Example must be inside repository")
        for filename in ("README.md", "LICENSE", "migration.json"):
            if not (directory / filename).is_file():
                raise ValueError(f"Missing {identifier}/{filename}")
        if entry.get("status") != "checked-in":
            raise ValueError("Runnable entries must be checked-in")
        metadata = json.loads((directory / "migration.json").read_text())
        if (
            metadata["schema"] != "sanka-examples/migration/v1"
            or metadata["id"] != identifier
        ):
            raise ValueError(f"Metadata identity mismatch: {identifier}")
        if (
            metadata["source"] != entry["source"]
            or metadata["destinations"] != entry["destinations"]
        ):
            raise ValueError(f"Index differs from example: {identifier}")
        if metadata["license"] != "Apache-2.0" or metadata["provenance"] != "synthetic":
            raise ValueError(f"Review source provenance: {identifier}")
        for key in ("language", "framework"):
            if (
                not isinstance(metadata["source"].get(key), str)
                or not metadata["source"][key]
            ):
                raise ValueError(f"Missing source {key}")
        if not metadata["destinations"]:
            raise ValueError("A migration needs a destination")
        for destination in metadata["destinations"]:
            for key in ("language", "framework", "extension_id", "release_status"):
                if not isinstance(destination[key], str) or not destination[key]:
                    raise ValueError(f"Missing destination {key}")
            stages = destination["supported_stages"]
            if not stages or stages != [s for s in STAGES if s in stages]:
                raise ValueError("Unsupported or unordered lifecycle stages")
            if destination["framework"] == "compose" and stages != ["scan", "plan"]:
                raise ValueError("Compose is scan/plan only")
        evidence = directory / entry["evidence"]
        if (
            not evidence.is_file()
            or directory.resolve() not in evidence.resolve().parents
        ):
            raise ValueError(f"Missing acceptance evidence: {identifier}")
        receipt = json.loads(evidence.read_text())
        for destination in metadata["destinations"]:
            result = receipt.get("targets", {}).get(destination["framework"], receipt)
            if result.get("status", result.get("outcome")) not in (
                "passed",
                "passed_within_scope",
                "success",
            ):
                raise ValueError(
                    f"Failed acceptance: {identifier}/{destination['framework']}"
                )
            for stage in destination["supported_stages"]:
                observed = result.get("stages", {}).get(stage)
                if isinstance(observed, dict):
                    observed = observed.get("outcome")
                if observed not in ("success", "passed"):
                    raise ValueError(f"Stage not passed: {identifier}/{stage}")
            candidate = result.get("candidate", result)
            published = destination["release_status"] == "experimental-published"
            revision = (
                destination.get("release_revision")
                if published
                else destination.get(
                    "candidate_revision", metadata.get("candidate_revision")
                )
            )
            if published:
                if (
                    candidate.get("release_status") != "experimental-published"
                    or candidate.get("release_tag") != destination.get("release_tag")
                    or not destination.get("release_tag")
                    or candidate.get("manifest_sha256")
                    != destination.get("manifest_sha256")
                    or not re.fullmatch(
                        r"[0-9a-f]{64}", destination.get("manifest_sha256", "")
                    )
                    or not candidate.get("wheels")
                ):
                    raise ValueError(
                        f"Published release evidence mismatch: {identifier}"
                    )
            if not isinstance(revision, str) or not re.fullmatch(
                r"[0-9a-f]{40}", revision
            ):
                raise ValueError("Migration metadata must pin its converter commit")
            if (
                candidate.get("extension_revision") != revision
                or candidate.get("extension_id") != destination["extension_id"]
            ):
                raise ValueError(f"Candidate identity mismatch: {identifier}")
            if result.get("source_preserved") is not True or not result.get(
                "source_sha256"
            ):
                raise ValueError(f"Source preservation not proven: {identifier}")
            source = (directory / metadata["source"].get("path", ".")).resolve()
            if (
                directory.resolve() != source
                and directory.resolve() not in source.parents
            ):
                raise ValueError("Source must be inside the example")
            for name, digest in result["source_sha256"].items():
                path = (source / name).resolve()
                if source not in path.parents or not path.is_file():
                    raise ValueError(
                        f"Missing source receipt input: {identifier}/{name}"
                    )
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Stale source evidence: {identifier}/{name}")
            if "apply" in destination["supported_stages"] and not result.get(
                "generated_sha256"
            ):
                raise ValueError(f"Missing generated artifact hashes: {identifier}")
    for entry in index["planned"]:
        if entry["id"] in seen or entry["status"] != "planned":
            raise ValueError("Planned examples cannot be checked-in migrations")
        seen.add(entry["id"])
    for entry in index.get("separately_tracked", []):
        if entry["id"] in seen or entry["status"] != "tracked-separately":
            raise ValueError(
                "Separately tracked examples must have distinct identities"
            )
        seen.add(entry["id"])
        readme = (root / entry["readme"]).resolve()
        if root.resolve() not in readme.parents or not readme.is_file():
            raise ValueError(
                "Separately tracked cookbook must exist inside the repository"
            )
    print(
        f"Catalog valid: {len(index['examples'])} qualified, "
        f"{len(index['planned'])} planned, {len(index.get('separately_tracked', []))} separately tracked"
    )


if __name__ == "__main__":
    validate(ROOT)
