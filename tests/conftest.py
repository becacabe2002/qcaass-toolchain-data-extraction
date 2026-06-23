"""Shared fixtures: a fully-populated example ToolRecord."""

from __future__ import annotations

import pytest

from qcaass_extraction.schema import (
    AlgorithmsSection,
    Architecture,
    Challenge,
    ChallengesSection,
    ContributionTypeField,
    GeneralInfo,
    OverviewCharacteristics,
    QuantumAlgorithm,
    SourceTypeField,
    ToolRecord,
    YesNoField,
    AutomationLevelField,
    EvaluationTypeField,
    InputInstructionField,
    OutputTypeField,
    TypedEvidence,
    empty_architecture,
)

SAMPLE_SOURCE = (
    "Qubitron is an open-source toolchain for quantum software development. "
    "It provides an orchestrator that schedules circuits across backends. "
    "The tool exposes a high-level instruction interface and emits metrics. "
    "Users have reported that documentation is sparse and onboarding is slow. "
    "Qubitron offers a built-in implementation of the Grover search algorithm."
)


@pytest.fixture
def sample_record() -> ToolRecord:
    arch = empty_architecture()
    arch.design_principles = "Modular, backend-agnostic design."
    arch.technological_foundation = "Python and OpenQASM."
    arch.orchestrator = YesNoField(
        value="Yes",
        evidence="It provides an orchestrator that schedules circuits across backends.",
    )
    return ToolRecord(
        tool_id="T000",
        source_doc_path="data/qubitron.txt",
        general=GeneralInfo(
            tool_name="Qubitron",
            purpose="Open-source quantum software toolchain.",
            source_type=SourceTypeField(
                value="OS",
                evidence="Qubitron is an open-source toolchain for quantum software development.",
            ),
            contribution_type=ContributionTypeField(value="Not stated"),
        ),
        overview=OverviewCharacteristics(
            input_instruction=InputInstructionField(
                value="HL",
                type_evidence=[
                    TypedEvidence(
                        type="HL",
                        evidence="The tool exposes a high-level instruction interface and emits metrics.",
                    )
                ],
            ),
            output_type=OutputTypeField(
                value="Metrics",
                type_evidence=[
                    TypedEvidence(
                        type="Metrics",
                        evidence="The tool exposes a high-level instruction interface and emits metrics.",
                    )
                ],
            ),
            automation_level=AutomationLevelField(value="Not stated"),
            evaluation_type=EvaluationTypeField(value="Not stated"),
        ),
        architecture=arch,
        algorithms=AlgorithmsSection(
            offers_algorithms="Yes",
            overall_evidence="Qubitron offers a built-in implementation of the Grover search algorithm.",
            algorithms=[
                QuantumAlgorithm(
                    name="Grover search",
                    algorithm_type="Search",
                    evidence="Qubitron offers a built-in implementation of the Grover search algorithm.",
                )
            ],
        ),
        challenges=ChallengesSection(
            challenges=[
                Challenge(
                    statement="Documentation is sparse.",
                    category="Usability",
                    category_evidence="documentation is sparse and onboarding is slow.",
                    evidence_strength="Implicit anecdotal",
                    strength_evidence="Users have reported that documentation is sparse and onboarding is slow.",
                )
            ]
        ),
    )
