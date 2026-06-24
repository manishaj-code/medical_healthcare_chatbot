# AI Healthcare Assistant - Agent Inventory

| Agent                | Purpose                                                                        | Example Use Cases                                                    | Key Tools / Functions                                                                             | Uses LLM   | Offline Support | Criticality |
| -------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------- | --------------- | ----------- |
| **Supervisor Agent** | Routes requests to the correct specialist agent and manages conversation state | "I have fever" → Triage Agent, "Book appointment" → Scheduling Agent | Intent Detection, Session Management, Agent Handoff                                               | ❌ No       | ✅ Fully Offline | Critical    |
| **Education Agent**  | General healthcare Q&A and patient education                                   | What is diabetes? What causes anemia?                                | Knowledge Retrieval, FAQ Search, Context Management                                               | ✅ Yes      | ⚠️ Partial      | Medium      |
| **Triage Agent**     | Symptom assessment and risk evaluation                                         | I have fever, headache, cough                                        | Symptom Extraction, Duration Parser, Severity Parser, Triage Workflow                             | ✅ Yes      | ✅ Strong        | High        |
| **Scheduling Agent** | Doctor recommendations and appointment booking                                 | Find a doctor, Book appointment, Show slots                          | search_doctors(), get_doctor_slots(), book_slot(), cancel_appointment(), reschedule_appointment() | ⚠️ Partial | ✅ Yes           | High        |
| **Report Agent**     | Medical report analysis and explanation                                        | Analyze my blood report, Explain my report                           | list_reports(), analyze_report(), get_report_analysis()                                           | ✅ Yes      | ⚠️ Partial      | High        |
| **Follow-up Agent**  | Post-consultation guidance and follow-up support                               | What should I do next? How am I progressing?                         | Patient History, Consultation History, Follow-up Workflows                                        | ✅ Yes      | ❌ Minimal       | Medium      |
| **Refill Agent**     | Prescription refill management                                                 | Refill my medication, Request prescription renewal                   | get_medications(), request_refill()                                                               | ⚠️ Partial | ✅ Yes           | Medium      |
| **Safety Agent**     | Emergency and crisis detection                                                 | Chest pain, Difficulty breathing, Suicidal thoughts                  | Emergency Rules Engine, Cardiac Screening, Crisis Detection                                       | ❌ No       | ✅ Fully Offline | Critical    |

---

## Offline Capabilities Summary

| Capability                     | Offline Supported |
| ------------------------------ | ----------------- |
| Greeting Handling              | ✅                 |
| Symptom Detection              | ✅                 |
| Duration Parsing               | ✅                 |
| Severity Parsing               | ✅                 |
| Emergency Detection            | ✅                 |
| Doctor Recommendation Workflow | ✅                 |
| Appointment Booking Workflow   | ✅                 |
| Refill Workflow                | ✅                 |
| Session Management             | ✅                 |
| Report Retrieval               | ✅                 |
| Report Explanation             | ⚠️ Partial        |
| Health Education Answers       | ⚠️ Partial        |
| Patient Summary Generation     | ❌                 |
| Follow-up Guidance             | ❌                 |

---

## LLM Usage Summary

| Agent            | LLM Dependency |
| ---------------- | -------------- |
| Supervisor Agent | ❌ No           |
| Education Agent  | ✅ High         |
| Triage Agent     | ✅ Medium       |
| Scheduling Agent | ⚠️ Low         |
| Report Agent     | ✅ High         |
| Follow-up Agent  | ✅ High         |
| Refill Agent     | ⚠️ Low         |
| Safety Agent     | ❌ No           |

---

## Architecture Overview

| Layer                   | Components                                                                        |
| ----------------------- | --------------------------------------------------------------------------------- |
| **Orchestration Layer** | Supervisor Agent                                                                  |
| **Healthcare Agents**   | Education, Triage, Scheduling, Report, Follow-up, Refill, Safety                  |
| **Rule Engine Layer**   | Emergency Detection, Symptom Parsing, Appointment Rules                           |
| **LLM Layer**           | Health Education, Report Explanation, Patient Summaries, Conversational Responses |
| **Persistence Layer**   | Conversations, Reports, Appointments, Session State                               |

### Total Components

| Type                      | Count |
| ------------------------- | ----- |
| Specialist Agents         | **7** |
| Supervisor / Orchestrator | **1** |
| Total Logical Agents      | **8** |


## Agent 1: Education Agent

### Purpose

Provides general healthcare information and answers patient questions.

### Example Questions

* What is Vitamin D deficiency?
* What causes anemia?
* What is diabetes?
* How can I improve sleep?

### Tools

* Knowledge Base Search
* Medical Content Retrieval
* Conversation Context

### Uses LLM?

✅ Yes

### Offline Support?

✅ Partial

Can answer common predefined FAQs through offline fallback, but most responses are generated through the LLM.

### Risk Level

Low

---

## Agent 2: Triage Agent

### Purpose

Conducts symptom assessment and gathers clinical information.

### Example Inputs

* I have fever.
* I have headache and cough.
* I am feeling dizzy.

### Responsibilities

* Collect symptoms
* Ask follow-up questions
* Collect duration
* Collect severity
* Generate risk assessment

### Tools

* Symptom Extraction
* Duration Parser
* Severity Parser
* Triage Workflow Engine

### Uses LLM?

✅ Yes

For natural conversation.

### Offline Support?

✅ Strong

Can continue triage even if LLM is unavailable.

### Offline Features

* Symptom detection
* Duration extraction
* Severity extraction
* Follow-up workflow

### Risk Level

Medium

---

## Agent 3: Scheduling Agent

### Purpose

Handles doctor recommendations and appointment workflows.

### Example Inputs

* Find a doctor
* Book appointment
* Need dermatologist
* Show available slots

### Tools

* search_doctors()
* get_doctor_slots()
* book_slot()
* cancel_appointment()
* reschedule_appointment()

### Uses LLM?

⚠️ Limited

LLM may be used for conversational responses.

Actual booking logic is rule-based.

### Offline Support?

✅ Yes

Appointment workflows do not require LLM.

### Risk Level

Low

---

## Agent 4: Report Agent

### Purpose

Handles medical report analysis and report discussions.

### Example Inputs

* Analyze my report
* Explain my blood report
* Why is my hemoglobin low?

### Tools

* list_reports()
* analyze_report()
* get_report_analysis()

### Uses LLM?

✅ Yes

Primary functionality depends on LLM explanations.

### Offline Support?

⚠️ Partial

Can retrieve report data but detailed explanations require LLM.

### Risk Level

Medium

---

## Agent 5: Follow-up Agent

### Purpose

Supports post-consultation patient engagement.

### Example Inputs

* How am I progressing?
* What should I do next?
* Follow-up recommendations

### Tools

* Appointment history
* Consultation history
* Patient context

### Uses LLM?

✅ Yes

Generates personalized follow-up guidance.

### Offline Support?

❌ Minimal

Mostly LLM-driven.

### Risk Level

Low

---

## Agent 6: Refill Agent

### Purpose

Handles prescription refill workflows.

### Example Inputs

* Refill my medication
* Request prescription renewal

### Tools

* get_medications()
* request_refill()

### Uses LLM?

⚠️ Limited

Workflow is rule-based.

LLM only improves conversation quality.

### Offline Support?

✅ Yes

Can process refill requests without LLM.

### Risk Level

Low

---

## Agent 7: Safety Agent

### Purpose

Emergency and crisis detection.

### Example Inputs

* Chest pain
* Difficulty breathing
* Heart attack symptoms
* Suicidal thoughts

### Responsibilities

* Emergency screening
* Escalation
* Safety response

### Tools

* Emergency Detection Rules
* Cardiac Screening Workflow
* Crisis Detection Logic

### Uses LLM?

❌ No (Preferred)

Emergency decisions are rule-based.

### Offline Support?

✅ Fully Offline

Works even when LLM is unavailable.

### Risk Level

Critical

---

# Supervisor Agent

## File

supervisor.py

## Purpose

Acts as the master orchestrator.

### Responsibilities

* Detect intent
* Select specialist agent
* Manage conversation state
* Handle agent handoffs
* Track active workflow
* Route messages

### Example

Patient:
"I have fever"

↓

Triage Agent

Patient:
"Book appointment"

↓

Scheduling Agent

### Uses LLM?

❌ No

Decision making is rule-based.

### Offline Support?

✅ Fully Offline

---

# Offline Components Summary

| Component                      | Offline |
| ------------------------------ | ------- |
| Supervisor                     | ✅       |
| Safety Agent                   | ✅       |
| Symptom Detection              | ✅       |
| Duration Parsing               | ✅       |
| Severity Parsing               | ✅       |
| Appointment Booking Workflow   | ✅       |
| Doctor Recommendation Workflow | ✅       |
| Refill Workflow                | ✅       |
| Greeting Handling              | ✅       |
| Report Retrieval               | ✅       |

---

# LLM Dependent Components

| Component                    | LLM |
| ---------------------------- | --- |
| Health Education             | ✅   |
| Medical Explanations         | ✅   |
| Report Explanation           | ✅   |
| Follow-up Guidance           | ✅   |
| Patient Summary Generation   | ✅   |
| Natural Symptom Conversation | ✅   |

---

# Overall Architecture

```text
Patient
   ↓
Supervisor
   ↓
┌──────────────────────┐
│ Education Agent      │
│ Triage Agent         │
│ Scheduling Agent     │
│ Report Agent         │
│ Follow-up Agent      │
│ Refill Agent         │
│ Safety Agent         │
└──────────────────────┘
   ↓
Tools + Rules + LLM
   ↓
Response
```

## Current Agent Count

* 7 Specialist Agents
* 1 Supervisor / Orchestrator

Total: **8 logical agents/components**
