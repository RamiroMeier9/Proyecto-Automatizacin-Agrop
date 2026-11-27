from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def read_reference_csv(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class EvidenceCatalog:
    def __init__(self, reference_dir: str | Path) -> None:
        self.reference_dir = Path(reference_dir)

    def studies(self) -> list[dict[str, Any]]:
        return read_reference_csv(self.reference_dir / "studies.csv")

    def observations(self) -> list[dict[str, Any]]:
        return read_reference_csv(self.reference_dir / "regional_evidence.csv")

    def treatments(self) -> list[dict[str, Any]]:
        return read_reference_csv(self.reference_dir / "trial_treatments.csv")

    def observations_for(self, alternative_id: str) -> list[dict[str, Any]]:
        return [
            row
            for row in self.observations()
            if row.get("alternative_id") in {alternative_id, "pasturas_perennes", "verdeos_anuales"}
        ]

    def coverage(self) -> dict[str, int]:
        observations = self.observations()
        return {
            "studies": len(self.studies()),
            "observations": len(observations),
            "years": len({row.get("year") for row in observations if row.get("year")}),
            "treatments": len(self.treatments()),
        }
