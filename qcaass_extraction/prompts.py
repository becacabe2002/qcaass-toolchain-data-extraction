"""Prompt skeletons (Section 6 of the blueprint)."""

from __future__ import annotations

LOCATE_PROMPT = """You will be given a document about a quantum-computing toolchain.
For each of these five categories, find any passages from the document that
could plausibly contain information for that category. Be generous — include
passages that are even tangentially relevant.

For EACH relevant passage, return a SHORT verbatim snippet of about 8-20 words
copied exactly from that passage (enough to locate it uniquely). Do NOT echo
back whole paragraphs — a single distinctive sentence or clause is enough. A
downstream step re-expands each snippet to its full surrounding context, so
brevity here is important to avoid truncating your own output.

Categories:
- general:        tool name, purpose, source type (open/closed), contribution type
- overview:       input instruction type, output type, automation level, evaluation
- architecture:   design principles, languages/tech, components (orchestrator,
                  manager, abstraction layer, backends, debugging, simulation,
                  security, scalability, telemetry, UI)
- algorithms:     built-in or selectable quantum algorithms offered by the tool
- challenges:     limitations, barriers, problems with adopting/using the tool

Return ONLY a JSON object, no prose or markdown fences, shaped as:
{"general": ["snippet", ...], "overview": [...], "architecture": [...],
 "algorithms": [...], "challenges": [...]}
"""

STRONG_SYSTEM_GUARDRAILS = """You extract structured data from a quantum-computing
toolchain document. Follow these rules without exception:

- Quotes in `evidence` must be VERBATIM from the provided spans,
  character-for-character. No paraphrasing, no ellipsis-stitching of
  non-adjacent text.
- Quotes should be short — one sentence or one clause, not paragraphs.
- If no verbatim quote supports a coded value, set the value to "Not stated"
  and leave evidence empty. DO NOT fabricate quotes.
- Distinguish carefully between Yes, No, and Not stated:
  - Yes — verbatim quote showing they talk about and cover the feature/module, even partially.
  - No — verbatim quote showing they explicitly say they do not have this feature/module (for example, in a limitations or challenges section).
  - Not stated — the document does not talk about or engage with the feature/module at all; evidence empty.
"""

STRICT_RETRY_SUFFIX = """

RETRY — the previous attempt produced one or more quotes that were NOT verbatim
substrings of the source. Re-extract this category. Every `evidence` quote MUST
be copied character-for-character from the spans below. If you cannot find an
exact supporting quote, use "Not stated" with empty evidence rather than
paraphrasing. Absolutely no paraphrase.
"""

MERGED_HEADER = """Extract ALL of the following categories from the document in a
single pass: general information, overview characteristics, architectural and
technical features, quantum algorithms, and challenges. Apply each category's
rules exactly as written below.

"""

# Per-category extraction instructions. Each embeds the operational decision
# rules from the study's data-extraction codebook (Appendix B) so the model
# classifies the way a human coder would, rather than guessing label meanings.
CATEGORY_INSTRUCTIONS = {
    "general_overview": (
        "Extract general information and overview characteristics.\n\n"
        "tool_name: the name the authors give the tool/platform/framework. "
        "purpose: 1-2 sentences, the authors' stated objective, paraphrased.\n\n"
        "source_type (OS / CS / Not stated):\n"
        "- OS only when the study explicitly states the tool is open source OR "
        "names an explicit open-source license. A public repository link WITHOUT "
        "a stated license is NOT enough -> Not stated.\n"
        "- CS when explicitly described as proprietary/closed source.\n\n"
        "contribution_type (Methodology-vision / Proof of concept / Practical "
        "for customers / Not stated): assign only if explicit; do not infer.\n\n"
        "input_instruction (HL / QI / MV / Multiple (types) / Not stated):\n"
        "- HL: high-level code or APIs (abstraction, ease of use).\n"
        "- QI: quantum circuits/gates specified directly at a low level.\n"
        "- MV: symbolic or algebraic / mathematical-variable inputs.\n"
        "- When more than one of the above is explicitly supported, set value to "
        "'Multiple (X, Y)' listing the specific types that apply, "
        "e.g. 'Multiple (HL, QI)'.\n\n"
        "output_type (QSC / SF / Metrics / Logs / Multiple (types) / Not stated):\n"
        "- QSC: quantum source code or intermediate representation produced.\n"
        "- SF: execution/simulation results (measurement outcomes, distributions).\n"
        "- Metrics: performance indicators (gate fidelity, error rates, latency).\n"
        "- Logs: operational indicators (system health, usage logs).\n"
        "- When several output kinds are stated, set value to 'Multiple (X, Y)' "
        "listing the specific types that apply, e.g. 'Multiple (QSC, Metrics)'. "
        "Code regardless of whether exposed to the end user through the workflow "
        "interface.\n\n"
        "automation_level (FA / SA / NA / Not stated): judged on the CORE "
        "operational workflow.\n"
        "- FA: the workflow executes without human intervention. Human work "
        "limited to initial configuration, parameter setting, or constraint "
        "specification does NOT disqualify FA.\n"
        "- SA: the operational loop requires user confirmation/intervention.\n"
        "- NA: fully manual execution.\n\n"
        "evaluation_type (EX / IM / None / Not stated): judged on the NUMBER of "
        "distinct evaluations (benchmarks, use cases, or scenarios).\n"
        "- EX: systematic evaluation - MORE THAN 2 distinct evaluations, or most "
        "aspects of the toolchain evaluated.\n"
        "- IM: implicit/partial - 2 OR FEWER distinct evaluations / use cases (a "
        "small, limited illustrative demonstration). For example, 'We present two "
        "practical use cases and perform the evaluations on quantum computers and "
        "simulators' is IM (two use cases).\n"
        "- None: no evaluation reported."
    ),
    "architecture": (
        "Extract architectural and technical features.\n\n"
        "design_principles (free text): Foundational software engineering strategies guiding the architecture. Focus strictly on quantum-specific paradigms or major architectural decisions (e.g., quantum hardware agnosticism, hybrid classical-quantum systems). Explicitly exclude generic software quality attributes (e.g., scalability, security, usability, extensibility) unless they describe a unique quantum mechanism.\n\n"
        "technological_foundation (free text): Stated programming languages, frameworks, development methodologies, libraries, and internal tools used to build the software implementation. Explicitly exclude external third-party quantum hardware providers, service environments, or backend integration targets (e.g., IBM, Rigetti, D-Wave, Google, Microsoft). List items directly from the text without interpretation.\n\n"
        "For each component below, return Yes / No / Not stated with a verbatim "
        "quote when Yes/No. Yes = quote showing they talk about and cover the component "
        "even partially; No = quote showing they explicitly state they don't have "
        "this component (e.g., in a limitations section); Not stated = the document "
        "does not talk about the component at all (empty evidence).\n"
        "- orchestrator: a coordination/backbone component or mechanism "
        "(workflow engine, pipeline, flow editor, coordination of "
        "classical-quantum steps), centralized or distributed.\n"
        "- manager_controller (free text): A dedicated software component or automated service responsible for the execution or deployment of quantum applications. NOTE the distinction: an orchestrator coordinates components and workflows, whereas a manager handles the actual execution or deployment. Explicitly exclude human actors (e.g., \"the user\", \"developers\", \"administrators\", or \"the team\") who perform manual execution or deployment.\n"
        "- vendor_agnostic_layer: execution across multiple quantum providers via "
        "translation/abstraction/backend-independence (Yes even if "
        "provider-specific code remains an option).\n"
        "- backend_integration (free text): Mechanisms linking the toolchain directly to external quantum service providers and hardware. Specifically look for middleware-based connectors, abstraction layers, or provider-specific APIs. Explicitly exclude internal system APIs (e.g., frontend-to-backend REST APIs), general cloud hosting infrastructure (e.g., AWS EC2, SQL databases), and internal simulation engines that do not connect to external quantum hardware.\n"
        "- debugging_testing: explicit debugging tools or test environments.\n"
        "- simulation_support: a simulator (local or external) is mentioned. "
        "Record independently of debugging_testing even if a local simulator "
        "also enables testing.\n"
        "- security_mechanisms: authentication, access control, or secure "
        "execution.\n"
        "- scalability_mechanisms: load balancing, elasticity, or parallel "
        "execution.\n"
        "- telemetry_monitoring: logging, monitoring dashboards, or runtime "
        "metrics.\n"
        "- user_interface: a GUI, dashboard, command-line, or even a "
        "configuration interface for managing tasks/workflows/results.\n\n"
        "For a vision or conceptual paper, the mere proposal or high-level design "
        "of a component counts as Yes (present)."
    ),
    "algorithms": (
        "Extract quantum algorithms the tool exposes. Count an algorithm only "
        "if it is offered as a built-in capability, service, or selectable "
        "option of the toolchain. EXCLUDE algorithms used solely as illustrative "
        "examples, validation case studies, or evaluation scenarios. For each "
        "included algorithm give name, type (e.g. optimization, factorization, "
        "search, variational), and a verbatim quote showing it is offered."
    ),
    "challenges": (
        "Extract only the tool's OWN remaining/unresolved limitations - "
        "limitations of THIS tool that the authors leave open. EXCLUDE (a) "
        "general quantum-computing or field-wide challenges not specific to this "
        "tool, and (b) challenges the tool itself addresses or solves. For each "
        "included limitation: a free-text statement "
        "(paraphrased or quoted); a category - one of Usability, Performance, "
        "Reliability, Scalability, Interoperability, Access, Security, "
        "Maintainability (the dominant/primary focus); a verbatim quote "
        "justifying the category; an evidence_strength - 'Explicit empirical' "
        "when backed by data/experiments, 'Implicit anecdotal' for observations "
        "without empirical validation; and a verbatim quote justifying the "
        "strength."
    ),
}

# Combined instruction for the default single-call (merged) extractor. Stitches
# the four per-category instructions together so one structured-output call can
# populate the whole record. The fan-out instructions above are reused verbatim
# on the fallback path.
MERGED_INSTRUCTION = (
    MERGED_HEADER
    + "\n\n".join(
        f"## {name}\n{text}" for name, text in CATEGORY_INSTRUCTIONS.items()
    )
)
