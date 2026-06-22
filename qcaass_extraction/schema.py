"""Pydantic extraction schema
Every categorical field is wrapped so ``value`` and ``evidence`` travel
together. Free-text fields stay plain strings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------- Reusable coded-field wrappers ----------


class YesNoField(BaseModel):
    value: Literal["Yes", "No", "Not stated"]
    evidence: str = ""  # verbatim quote; empty only when Not stated


class SourceTypeField(BaseModel):
    value: Literal["OS", "CS", "Not stated"]
    evidence: str = ""


class ContributionTypeField(BaseModel):
    value: Literal[
        "Methodology-vision",
        "Proof of concept",
        "Practical for customers",
        "Not stated",
    ]
    evidence: str = ""


class InputInstructionField(BaseModel):
    value: Literal["HL", "QI", "MV", "Multiple", "Not stated"]
    evidence: str = ""


class OutputTypeField(BaseModel):
    value: Literal["QSC", "SF", "Metrics", "Logs", "Multiple", "Not stated"]
    evidence: str = ""


class AutomationLevelField(BaseModel):
    value: Literal["FA", "SA", "NA", "Not stated"]
    evidence: str = ""


class EvaluationTypeField(BaseModel):
    value: Literal["EX", "IM", "None", "Not stated"]
    evidence: str = ""


# ---------- Category 1: General Information ----------


class GeneralInfo(BaseModel):
    tool_name: str
    purpose: str = Field(description="1-2 sentence summary, free text")
    source_type: SourceTypeField
    contribution_type: ContributionTypeField


# ---------- Category 2: Overview Characteristics ----------


class OverviewCharacteristics(BaseModel):
    input_instruction: InputInstructionField
    output_type: OutputTypeField
    automation_level: AutomationLevelField
    evaluation_type: EvaluationTypeField


# ---------- Bundled general + overview (single strong-model call) ----------


class GeneralAndOverview(BaseModel):
    general: GeneralInfo
    overview: OverviewCharacteristics


# ---------- Category 3: Architectural and Technical Features ----------
# 12 fields total: 2 free-text + 10 YesNoField components.


class Architecture(BaseModel):
    design_principles: str  # free text
    technological_foundation: str  # free text
    orchestrator: YesNoField
    manager_controller: YesNoField
    vendor_agnostic_layer: YesNoField
    backend_integration: YesNoField
    debugging_testing: YesNoField
    simulation_support: YesNoField
    security_mechanisms: YesNoField
    scalability_mechanisms: YesNoField
    telemetry_monitoring: YesNoField
    user_interface: YesNoField


# ---------- Category 4: Quantum Algorithms ----------


class QuantumAlgorithm(BaseModel):
    name: str
    algorithm_type: str
    evidence: str  # quote showing this algorithm is offered as built-in/selectable


class AlgorithmsSection(BaseModel):
    offers_algorithms: Literal["Yes", "No", "Not stated"]
    overall_evidence: str = ""
    algorithms: list[QuantumAlgorithm] = Field(default_factory=list)


# ---------- Category 5: Challenges ----------

ChallengeCategory = Literal[
    "Usability",
    "Performance",
    "Reliability",
    "Scalability",
    "Interoperability",
    "Access",
    "Security",
    "Maintainability",
]


class Challenge(BaseModel):
    statement: str  # free text describing the limitation
    category: ChallengeCategory
    category_evidence: str  # quote justifying the categorization
    evidence_strength: Literal["Explicit empirical", "Implicit anecdotal"]
    strength_evidence: str  # quote justifying the strength rating


class ChallengesSection(BaseModel):
    challenges: list[Challenge] = Field(default_factory=list)


# ---------- Top-level record per document ----------


class ToolRecord(BaseModel):
    tool_id: str
    source_doc_path: str
    general: GeneralInfo
    overview: OverviewCharacteristics
    architecture: Architecture
    algorithms: AlgorithmsSection
    challenges: ChallengesSection
    needs_review: bool = False  # set if the validator escalated any field
    validation_errors: list[dict] = Field(default_factory=list)


# ---------- Merged single-call extraction target ----------
# One structured-output call returns the whole record's category payload; the
# four-way fan-out is kept only as the per-category fallback (see extractors).


class FullExtraction(BaseModel):
    general: GeneralInfo
    overview: OverviewCharacteristics
    architecture: Architecture
    algorithms: AlgorithmsSection
    challenges: ChallengesSection


# ---------- Safe empty defaults (used on parse failure) ----------


def empty_general() -> GeneralInfo:
    return GeneralInfo(
        tool_name="",
        purpose="",
        source_type=SourceTypeField(value="Not stated"),
        contribution_type=ContributionTypeField(value="Not stated"),
    )


def empty_overview() -> OverviewCharacteristics:
    return OverviewCharacteristics(
        input_instruction=InputInstructionField(value="Not stated"),
        output_type=OutputTypeField(value="Not stated"),
        automation_level=AutomationLevelField(value="Not stated"),
        evaluation_type=EvaluationTypeField(value="Not stated"),
    )


def empty_architecture() -> Architecture:
    return Architecture(
        design_principles="",
        technological_foundation="",
        orchestrator=YesNoField(value="Not stated"),
        manager_controller=YesNoField(value="Not stated"),
        vendor_agnostic_layer=YesNoField(value="Not stated"),
        backend_integration=YesNoField(value="Not stated"),
        debugging_testing=YesNoField(value="Not stated"),
        simulation_support=YesNoField(value="Not stated"),
        security_mechanisms=YesNoField(value="Not stated"),
        scalability_mechanisms=YesNoField(value="Not stated"),
        telemetry_monitoring=YesNoField(value="Not stated"),
        user_interface=YesNoField(value="Not stated"),
    )


def empty_algorithms() -> AlgorithmsSection:
    return AlgorithmsSection(offers_algorithms="Not stated")


def empty_challenges() -> ChallengesSection:
    return ChallengesSection()


# Architecture component fields (the 10 YesNoFields), in declaration order.
ARCHITECTURE_COMPONENTS = [
    "orchestrator",
    "manager_controller",
    "vendor_agnostic_layer",
    "backend_integration",
    "debugging_testing",
    "simulation_support",
    "security_mechanisms",
    "scalability_mechanisms",
    "telemetry_monitoring",
    "user_interface",
]
