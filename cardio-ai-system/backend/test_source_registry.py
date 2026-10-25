"""Tests for the citation verifier itself.

The verifier is what makes "every rule is traceable to a source" mean the
document exists, so its two easy-to-get-wrong pieces get pinned here: DOI
extraction from a publisher URL (not only from a doi.org link) and the title
agreement rule that decides whether Crossref resolved the document we cite
rather than merely some document with that identifier.

Network behaviour is not exercised: the checks it performs depend on publishers
that block automated clients, and a test that fails when AHA serves a 403 would
be testing the internet rather than the code. The structural pass — the part CI
can rely on everywhere — is asserted directly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_sources", ROOT / "scripts" / "verify_sources.py")
verify_sources = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(verify_sources)

from agents import pharmacology_agent  # noqa: E402


def test_the_registry_passes_its_own_structural_pass() -> None:
    assert verify_sources.structural_problems() == []


def test_every_registered_source_is_cited_and_every_citation_registered() -> None:
    cited = set()
    for entry in [*pharmacology_agent.DRUGS, *pharmacology_agent.INTERACTIONS]:
        cited.update(verify_sources.source_ids(entry))
    assert cited == set(pharmacology_agent.SOURCES)


def test_doi_is_extracted_from_both_url_shapes() -> None:
    assert (
        verify_sources.doi_of("https://doi.org/10.1016/j.kint.2023.10.018")
        == "10.1016/j.kint.2023.10.018"
    )
    # Publisher paths carry the same identifier; a checker that only understood
    # doi.org would send AHA eleven requests and call them dead on a 403.
    assert (
        verify_sources.doi_of("https://www.ahajournals.org/doi/10.1161/CIR.0000000000001168")
        == "10.1161/CIR.0000000000001168"
    )
    assert verify_sources.doi_of("https://goldcopd.org/2025-gold-report/") is None


def test_title_agreement_accepts_a_shortened_metadata_title() -> None:
    # Crossref holds the bulletin's short title; the registry names the number.
    assert verify_sources.titles_agree(
        "Gestational Hypertension and Preeclampsia: ACOG Practice Bulletin, Number 222",
        "Gestational Hypertension and Preeclampsia",
    )
    assert verify_sources.titles_agree(
        "2018 AHA/ACC/Multisociety Guideline on the Management of Blood Cholesterol",
        "2018 AHA/ACC/AACVPR/AAPA/ABC/ACPM/ADA/AGS/APhA/ASPC/NLA/PCNA Guideline on the "
        "Management of Blood Cholesterol: A Report of the American College of Cardiology",
    )


def test_title_agreement_rejects_a_different_document_with_the_same_id() -> None:
    assert not verify_sources.titles_agree(
        "2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        "Global Strategy for the Prevention, Diagnosis and Management of COPD",
    )
    assert not verify_sources.titles_agree("Short title", "2022 Heart Failure Guideline")
