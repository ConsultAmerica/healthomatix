# Healthomatix V2.1.1 — Architecture Audit (V2.0 Verified)

**Date:** 2026-10-29  
**Scope:** Actual repository inspection of V2.0 AI orchestration and clinical dependencies.  
**Launch posture:** V1.8 NO-GO for real PHI; Fake models only.

---

## 1. Verified architecture diagram

```text
Next.js (apps/web)
  /platform/ai          → governance overview, agents, tools
  /clinic/ai-approvals  → hash-bound proposal review
  /clinic/ai-scribe     → V1.5 scribe (consent-gated)
        │
        ▼
FastAPI (backend/app)
  agent_routes.py ──► agent_orchestrator.py
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
   agent_models.py   agent_tools.py   clinical_ai_port (Fake)
          │               │
          ▼               ▼
   PostgreSQL        FHIR store / consent / membership
   (0014 tables)     (existing clinical SoT)
```

---

## 2. Capability inventory

| Component | Status | Source | APIs / DB | Tests | Gaps |
|---|---|---|---|---|---|
| AI Orchestrator | Implemented | `agent_orchestrator.py` (`create_agent_run`, `execute_agent_run`, `cancel_run`, transitions) | `POST/GET .../ai/agent-runs*` | `test_ai_orchestration_v20.py` | In-process only; weak background timeout worker |
| Agent Registry | Implemented | `AiAgentDefinition`, `AiAgentVersion` | `GET /platform/ai/agents` | V2.0 | No fine-grained **capability** versions separate from agents |
| Tool Gateway | Implemented | `agent_tools.py` READ/PROPOSAL/FORBIDDEN | listed on platform tools API | V2.0 | Capability↔tool join table missing |
| Approval Engine | Implemented | `decide_approval`, `AiAgentApproval` hash | `.../ai/approvals*` | V2.0 tamper test | Policy decision contract not first-class |
| AI Provider Layer | Partial | Fake `build_clinical_ai_adapter`, `model_identifier` | usage tables | V1.5/V2.0 | No multi-provider routing / BAA gate |
| Agent Governance | Partial | evaluations, safety events, usage | `/platform/ai/*` | partial | Capability lifecycle / readiness APIs missing |
| Clinical Copilot | Partial | orchestrator clinical_copilot + V1.5 routes | pre-visit + agent-runs | V2.0 + V1.5 | No unified clinical context service |
| Medical Scribe | Implemented | `ai_copilot_routes`, consent | scribe sessions | V1.5 | Signing remains clinician-only (correct) |
| Clinical Data | Implemented | FHIR resources, timeline, observations | FHIR R4 + clinic APIs | V1.3–V1.7 | Agents call tools ad hoc; need provenance records |
| Interoperability | Implemented | V1.7 hub | interop routes | V1.7 | Agent integration tools metadata-only (correct) |
| Background Jobs | Partial | document jobs etc. | existing | prior | Agent runs not job-queue backed |
| Audit | Implemented | `append_audit_event` + tool exec rows | — | V2.0 | Clinical context access events missing |
| Frontend AI admin | Partial | `/platform/ai`, `/clinic/ai-approvals` | — | manual | Readiness / capability / evidence UIs missing |
| Tests | Partial | `test_ai_orchestration_v20.py` (7) | — | pass | Delegation, clinical context, capability lifecycle uncovered |

---

## 3. Dependency map

```text
Agent run → Agent definition/version → allowed_tools (JSON)
         → Tool gateway → FHIR / SupportTicket / IntegrationTransaction
         → Approval (hash) → SafetyEvent on tamper
         → AiAgentUsage

Missing for V2.1.1:
  Capability registry ──► tool permissions
  Execution context record (server-minted, expiring)
  Delegation parent→child (permission intersection)
  Clinical context service + evidence references + access audit
```

---

## 4. Security gaps (prioritized)

1. **No capability lifecycle** — agents enabled as wholes; cannot gate individual skills.  
2. **No trusted execution context object** — tenant/patient/capability resolved inline; harder to revalidate.  
3. **Delegation is workflow-level only** — `start_workflow` fans out; no depth limits / parent cancel cascade.  
4. **Clinical provenance not persisted** on agent runs (sources only in output JSON).  
5. **Policy decision** not a reusable `allow|deny|requires_approval` contract.  
6. **Tenant AI budgets** still incomplete (V2.0 limitation).

---

## 5. Clinical data readiness

| Category | Ready? | Source |
|---|---|---|
| Demographics | Yes | FHIR Patient via `get_resource` |
| Encounters | Partial | Consultation / FHIR Encounter where present |
| Labs | Yes | Observations + verified vs `imported_unverified` |
| Documents | Yes | Document / extraction pipelines |
| Notes | Yes | SOAP drafts + signed notes (V1.4/V1.5) |
| Allergies/Meds/Dx | Only if documented in FHIR | Do not invent |

**Principle:** reuse FHIR/clinical SoT; never invent missing clinical facts.

---

## 6. Database migration requirements (V2.1.1)

Additive migration `0015` (extends V2.0; no clinical table destruction):

- `ai_agent_capabilities`
- `ai_capability_tool_permissions`
- `ai_agent_delegations`
- `ai_clinical_context_access_events`
- `ai_evidence_references`
- `ai_execution_context_records`

---

## 7. Recommended implementation sequence

1. **2.1.1-B** Capability contracts + seed inventory (disabled until approved/enabled).  
2. **2.1.1-C** Server-side execution context + delegation with intersection + limits.  
3. **2.1.1-D** Clinical context service + evidence + access events.  
4. **2.1.1-E** Policy evaluate + wire approvals.  
5. **2.1.1-F** Readiness / capability / clinical inspector UI.  
6. **2.1.1-G** Security tests + acceptance report.

**Exit criterion:** No undocumented architectural assumptions — this audit is the baseline for V2.1.1 implementation.
