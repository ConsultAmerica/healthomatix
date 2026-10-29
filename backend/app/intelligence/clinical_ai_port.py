"""Clinical AI drafts and V1.5 copilot helpers. Fake adapter for CI; production requires BAA LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


MODEL_ID = "fake-clinical-ai-v1.5"
PROMPT_VERSION = "v1.5.0"


@dataclass(frozen=True)
class DraftBundle:
    title: str
    content: dict[str, Any]
    source_links: list[dict[str, Any]]


@dataclass(frozen=True)
class QualityFindingDraft:
    finding_type: str
    severity: str
    description: str
    source_reference: str
    suggested_action: str


@dataclass(frozen=True)
class MessageDraftBundle:
    category: str
    content: str
    urgency_hint: str


@dataclass(frozen=True)
class EducationBundle:
    topic: str
    answer: str
    source_references: list[dict[str, Any]]
    escalate: bool


class ClinicalAiPort(Protocol):
    def previsit_summary(
        self,
        *,
        patient_id: str,
        observations: list[dict[str, Any]],
        encounters: list[dict[str, Any]],
    ) -> DraftBundle: ...

    def visit_note(
        self,
        *,
        patient_id: str,
        follow_up_plan: str,
        observations: list[dict[str, Any]],
        transcript: str,
    ) -> DraftBundle: ...

    def follow_up_tasks(
        self,
        *,
        patient_id: str,
        follow_up_plan: str,
    ) -> DraftBundle: ...

    def generate_soap_draft(
        self,
        *,
        patient_id: str,
        visit_reason: str,
        clinician_notes: str,
        transcript: str,
        observations: list[dict[str, Any]],
    ) -> DraftBundle: ...

    def analyze_note_quality(
        self,
        *,
        subjective: str,
        objective: str,
        assessment: str,
        plan: str,
    ) -> list[QualityFindingDraft]: ...

    def draft_patient_message(
        self,
        *,
        subject: str,
        latest_patient_message: str,
    ) -> MessageDraftBundle: ...

    def generate_patient_education(
        self,
        *,
        question: str,
    ) -> EducationBundle: ...

    def suggest_care_tasks(
        self,
        *,
        instructions: str,
        existing_tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


class FakeClinicalAiAdapter:
    """Deterministic drafts — never auto-written to Clinical Records or sent to patients."""

    model_identifier = MODEL_ID
    prompt_version = PROMPT_VERSION

    def previsit_summary(
        self,
        *,
        patient_id: str,
        observations: list[dict[str, Any]],
        encounters: list[dict[str, Any]],
    ) -> DraftBundle:
        points: list[dict[str, Any]] = []
        source_links: list[dict[str, Any]] = []
        for obs in observations[:8]:
            code = (obs.get("code") or {}).get("text") or "Finding"
            value = obs.get("valueQuantity") or {}
            text = f"{code}: {value.get('value', obs.get('valueString', '—'))} {value.get('unit', '')}".strip()
            points.append({"text": text, "source": f"Observation/{obs.get('id')}"})
            source_links.append({"label": code, "reference": f"Observation/{obs.get('id')}"})
        for enc in encounters[:3]:
            points.append(
                {
                    "text": f"Prior visit ({(enc.get('type') or [{}])[0].get('text', 'Encounter')})",
                    "source": f"Encounter/{enc.get('id')}",
                }
            )
            source_links.append({"label": "Prior encounter", "reference": f"Encounter/{enc.get('id')}"})
        if not points:
            points.append(
                {
                    "text": "No verified chart data available yet for this patient.",
                    "source": f"Patient/{patient_id}",
                }
            )
            source_links.append({"label": "Patient", "reference": f"Patient/{patient_id}"})
        return DraftBundle(
            title="Pre-visit summary (draft)",
            content={
                "kind": "previsit_summary",
                "points": points,
                "disclaimer": "Draft only — requires clinician approval before chart entry.",
            },
            source_links=source_links,
        )

    def visit_note(
        self,
        *,
        patient_id: str,
        follow_up_plan: str,
        observations: list[dict[str, Any]],
        transcript: str,
    ) -> DraftBundle:
        labs = []
        source_links: list[dict[str, Any]] = []
        for obs in observations[:5]:
            code = (obs.get("code") or {}).get("text") or "Finding"
            labs.append(code)
            source_links.append({"label": code, "reference": f"Observation/{obs.get('id')}"})
        narrative = (
            "Telehealth visit completed. "
            + (f"Reviewed labs: {', '.join(labs)}. " if labs else "")
            + (f"Follow-up plan: {follow_up_plan.strip()}. " if follow_up_plan.strip() else "")
            + (
                f"Visit transcript excerpt: {transcript[:240].strip()}"
                if transcript.strip()
                else "No transcript provided."
            )
        )
        source_links.append({"label": "Patient", "reference": f"Patient/{patient_id}"})
        return DraftBundle(
            title="Visit note (draft)",
            content={
                "kind": "visit_note",
                "narrative": narrative,
                "follow_up_plan": follow_up_plan.strip(),
                "disclaimer": "Draft only — requires clinician approval before chart entry.",
            },
            source_links=source_links,
        )

    def follow_up_tasks(
        self,
        *,
        patient_id: str,
        follow_up_plan: str,
    ) -> DraftBundle:
        plan = follow_up_plan.strip() or "Follow up with care team as discussed."
        tasks = [
            {
                "description": plan[:240],
                "priority": "routine",
                "for": f"Patient/{patient_id}",
            },
            {
                "description": "Patient reminder: review after-visit instructions in the portal.",
                "priority": "routine",
                "for": f"Patient/{patient_id}",
            },
        ]
        return DraftBundle(
            title="Suggested follow-up tasks (draft)",
            content={
                "kind": "follow_up_tasks",
                "tasks": tasks,
                "disclaimer": "Draft only — requires clinician approval before chart entry.",
            },
            source_links=[{"label": "Patient", "reference": f"Patient/{patient_id}"}],
        )

    def generate_soap_draft(
        self,
        *,
        patient_id: str,
        visit_reason: str,
        clinician_notes: str,
        transcript: str,
        observations: list[dict[str, Any]],
    ) -> DraftBundle:
        labs = []
        source_links: list[dict[str, Any]] = [
            {"label": "Patient", "reference": f"Patient/{patient_id}"}
        ]
        for obs in observations[:5]:
            code = (obs.get("code") or {}).get("text") or "Finding"
            value = obs.get("valueQuantity") or {}
            labs.append(
                f"{code} {value.get('value', '')} {value.get('unit', '')}".strip()
            )
            source_links.append({"label": code, "reference": f"Observation/{obs.get('id')}"})
        subjective = (
            visit_reason.strip()
            or (transcript[:280] if transcript.strip() else "")
            or "Patient concerns as documented by clinician."
        )
        objective = clinician_notes.strip() or (
            "Verified labs reviewed: " + "; ".join(labs) if labs else "No verified labs cited."
        )
        return DraftBundle(
            title="SOAP draft (AI-assisted)",
            content={
                "kind": "soap_draft",
                "subjective": subjective,
                "objective": objective,
                "assessment": "Assessment as stated by clinician — AI did not invent a diagnosis.",
                "plan": "Plan as documented by clinician — AI did not prescribe treatment.",
                "disclaimer": "Draft only. Clinician must edit and sign. No autonomous diagnosis or orders.",
            },
            source_links=source_links,
        )

    def analyze_note_quality(
        self,
        *,
        subjective: str,
        objective: str,
        assessment: str,
        plan: str,
    ) -> list[QualityFindingDraft]:
        findings: list[QualityFindingDraft] = []
        if not subjective.strip():
            findings.append(
                QualityFindingDraft(
                    finding_type="completeness",
                    severity="review_recommended",
                    description="Subjective section is empty.",
                    source_reference="ClinicalNote.subjective",
                    suggested_action="Document the patient-reported concern or visit reason.",
                )
            )
        if not assessment.strip():
            findings.append(
                QualityFindingDraft(
                    finding_type="completeness",
                    severity="review_recommended",
                    description="Assessment section is empty.",
                    source_reference="ClinicalNote.assessment",
                    suggested_action="Record clinician assessment before signing.",
                )
            )
        if not plan.strip():
            findings.append(
                QualityFindingDraft(
                    finding_type="completeness",
                    severity="review_recommended",
                    description="Plan section is empty.",
                    source_reference="ClinicalNote.plan",
                    suggested_action="Document follow-up or treatment plan.",
                )
            )
        for section_name, text in (
            ("subjective", subjective),
            ("objective", objective),
            ("assessment", assessment),
            ("plan", plan),
        ):
            if "TODO" in text.upper() or "PLACEHOLDER" in text.upper():
                findings.append(
                    QualityFindingDraft(
                        finding_type="completeness",
                        severity="high_priority",
                        description=f"Unresolved placeholder text in {section_name}.",
                        source_reference=f"ClinicalNote.{section_name}",
                        suggested_action="Replace placeholder text before signing.",
                    )
                )
        if subjective.strip() and subjective.strip() == objective.strip():
            findings.append(
                QualityFindingDraft(
                    finding_type="consistency",
                    severity="informational",
                    description="Subjective and objective sections are identical.",
                    source_reference="ClinicalNote",
                    suggested_action="Confirm sections were not accidentally duplicated.",
                )
            )
        if not findings:
            findings.append(
                QualityFindingDraft(
                    finding_type="documentation_quality",
                    severity="informational",
                    description="No automated completeness issues detected.",
                    source_reference="ClinicalNote",
                    suggested_action="Proceed with clinician review as usual.",
                )
            )
        return findings

    def draft_patient_message(
        self,
        *,
        subject: str,
        latest_patient_message: str,
    ) -> MessageDraftBundle:
        text = latest_patient_message.lower()
        if any(word in text for word in ("chest pain", "can't breathe", "suicidal", "emergency")):
            return MessageDraftBundle(
                category="potentially_urgent",
                urgency_hint="review_immediately",
                content=(
                    "Thank you for contacting the clinic. Portal messaging is not for emergencies. "
                    "If this is urgent, please call emergency services or go to the nearest emergency department. "
                    "A care team member will review your message shortly."
                ),
            )
        if "appointment" in text or "reschedul" in text:
            category = "appointment_change" if "reschedul" in text else "appointment_request"
            content = (
                f"Thank you for your message about “{subject or 'your appointment'}”. "
                "We can help with scheduling through the Care page or this thread. "
                "A team member will confirm the next available options."
            )
        elif "record" in text or "document" in text:
            category = "records_request"
            content = (
                "You can upload documents securely from Medical Records. "
                "Our team will review uploads separately from this conversation."
            )
        elif any(word in text for word in ("medication", "prescription", "dose", "refill")):
            category = "medication_question"
            content = (
                "A clinician will review your medication question. "
                "We cannot change prescriptions through automated replies."
            )
        else:
            category = "general_clinic_information"
            content = (
                "Thank you for reaching out. A clinic team member will respond with guidance. "
                "This channel is not for emergencies."
            )
        return MessageDraftBundle(category=category, content=content, urgency_hint="routine")

    def generate_patient_education(self, *, question: str) -> EducationBundle:
        q = question.lower()
        if any(word in q for word in ("diagnose me", "what do i have", "prescribe", "should i take")):
            return EducationBundle(
                topic="escalation",
                answer=(
                    "I can share general educational information, but I cannot diagnose conditions "
                    "or recommend treatments. Please contact your care team through Messages for "
                    "personal medical advice. If this is an emergency, call emergency services."
                ),
                source_references=[
                    {
                        "title": "Healthomatix safety policy",
                        "source_id": "hmx-edu-safety-v1",
                        "version": "1.0",
                        "passage": "Education is not personalized medical advice.",
                    }
                ],
                escalate=True,
            )
        if "a1c" in q or "hba1c" in q or "glucose" in q:
            return EducationBundle(
                topic="laboratory_concepts",
                answer=(
                    "HbA1c is a common blood test that reflects average blood glucose over roughly "
                    "the prior three months. Your clinician interprets your personal results in "
                    "context of your history. Verified values appear in your Health Timeline after "
                    "clinic review."
                ),
                source_references=[
                    {
                        "title": "Approved lab education — HbA1c overview",
                        "source_id": "hmx-edu-lab-a1c-v1",
                        "version": "1.0",
                        "passage": "General purpose of HbA1c testing.",
                        "reviewed": "2026-01-15",
                    }
                ],
                escalate=False,
            )
        return EducationBundle(
            topic="general_healthomatix",
            answer=(
                "Healthomatix helps you manage appointments, records, and approved visit instructions. "
                "For personal medical questions, message your clinic. Portal messaging is not an "
                "emergency service."
            ),
            source_references=[
                {
                    "title": "Healthomatix patient guide",
                    "source_id": "hmx-edu-portal-v1",
                    "version": "1.0",
                    "passage": "Portal features and emergency disclaimer.",
                }
            ],
            escalate=False,
        )

    def suggest_care_tasks(
        self,
        *,
        instructions: str,
        existing_tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        if instructions.strip():
            suggestions.append(
                {
                    "task_category": "patient_instruction",
                    "description": instructions.strip()[:400],
                    "assigned_role": "patient",
                }
            )
        for task in existing_tasks[:5]:
            desc = str(task.get("description") or "").strip()
            if desc:
                suggestions.append(
                    {
                        "task_category": "follow_up",
                        "description": desc[:400],
                        "assigned_role": "patient",
                    }
                )
        if not suggestions:
            suggestions.append(
                {
                    "task_category": "follow_up",
                    "description": "Review approved visit summary in the patient portal.",
                    "assigned_role": "patient",
                }
            )
        # Deduplicate by description
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in suggestions:
            key = item["description"].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique


def build_clinical_ai_adapter() -> ClinicalAiPort:
    return FakeClinicalAiAdapter()
