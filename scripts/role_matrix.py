"""
role_matrix.py — Writes docs/ROLE_PERMISSION_MATRIX.md from app/permissions.py.

The matrix is generated, never edited by hand, so the document Compliance
signs off is always the one the code enforces. tests/api/test_role_matrix.py
fails when the two drift apart.

    python scripts/role_matrix.py           # rewrite the document
    python scripts/role_matrix.py --check   # exit 1 if it is out of date
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.permissions import PERMISSIONS, ROLE_DEFINITIONS  # noqa: E402

MATRIX_PATH = Path(__file__).resolve().parent.parent / "docs" / "ROLE_PERMISSION_MATRIX.md"

# Permissions grouped the way Compliance reads them
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cases and alerts", ("cases.view", "cases.view_all", "alerts.assign", "assignment.manage", "alerts.close_false_positive",
                          "alerts.close", "alerts.escalate", "alerts.qa", "alerts.baseline")),
    ("SAR", ("sar.view", "sar.approve", "sar.grant_access", "emergency.request")),
    ("Customers and KYC", ("customers.view_all", "customers.edit", "customers.assess_risk", "kyc.review", "screening.run",
                           "ubo.verify", "documents.manage")),
    ("Rules and regulation", ("rules.propose", "rules.approve", "rules.edit_direct", "regulatory.ingest", "obligations.manage",
                              "mappings.manage", "changes.assess")),
    ("Data and system", ("transactions.ingest", "feeds.load", "watchlists.ingest", "ml.train", "ai.status", "ai.admin",
                         "audit.read", "users.manage")),
)


def render() -> str:
    grouped = [code for _, codes in GROUPS for code in codes]
    missing = set(PERMISSIONS) - set(grouped)
    assert not missing, f"Add {sorted(missing)} to a group in scripts/role_matrix.py"

    roles = [r for r in ROLE_DEFINITIONS if not r.legacy] + [r for r in ROLE_DEFINITIONS if r.legacy]
    header = "| Permission | " + " | ".join(r.code for r in roles) + " |"
    rule = "|---|" + "---|" * len(roles)

    out = [
        "# KYRO Role Permission Matrix",
        "",
        "Generated from `app/permissions.py` by `scripts/role_matrix.py`. Do not edit by hand.",
        "",
        "✔ = the role holds the permission. Read-only roles cannot change any record whatever they hold.",
        "",
        "## Visibility rules (app/visibility.py)",
        "",
        "- Without `cases.view_all` a role sees only cases assigned to it and the unassigned pool.",
        "- Without `customers.view_all` a role sees only customers that have such a case.",
        "- A SAR-filed case, its documents and the fact a SAR was filed are visible only with `sar.view`; to anyone else they do not exist (404).",
        "- Every opening of a SAR-filed case is written to the audit log (`SAR` / `VIEW`).",
        "- A case escalated as a potential SAR stays visible, but without `sar.view` its escalation notes and reasons, later notes,"
        " later summaries and narratives are withheld; its progress shows as a general status (In progress / With the MLRO / Closed).",
        "- An approved emergency access grant lets one user read one case for a limited time; each use is audited (`EMERGENCY_ACCESS` / `VIEW`).",
        "",
        "## Matrix",
        "",
    ]
    for title, codes in GROUPS:
        out += [f"### {title}", "", header, rule]
        for code in codes:
            cells = " | ".join("✔" if code in r.permissions else "" for r in roles)
            out.append(f"| `{code}` — {PERMISSIONS[code]} | {cells} |")
        out.append("")

    out += ["## Roles", ""]
    for r in roles:
        flags = [f for f, on in (("read-only", r.read_only), ("legacy", r.legacy)) if on]
        out += [f"### {r.label} (`{r.code}`){' — ' + ', '.join(flags) if flags else ''}", "", r.purpose, "",
                "**Does:**", *[f"- {x}" for x in r.responsibilities], "", "**Cannot:**", *[f"- {x}" for x in r.limits], ""]
    return "\n".join(out)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = MATRIX_PATH.read_text(encoding="utf-8") if MATRIX_PATH.exists() else ""
        if current != text:
            print(f"{MATRIX_PATH} is out of date; run python scripts/role_matrix.py")
            return 1
        return 0
    MATRIX_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {MATRIX_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
