After reviewing the code, the **agent routing is simpler than a true LangGraph/AgentCore-style multi-agent system**.

### What is actually happening?

The flow is:

```text
chat.py
   ↓
process_patient_message()
   ↓
chat_orchestrator.py
   ↓
multi_agent_supervisor.process()
   ↓
Intent Detection
   ↓
Select Specialist Agent
   ↓
Generate Response
```

The "agents" are effectively specialized workflows rather than independent AI agents.

---

# Agent Selection Logic

The supervisor appears to route users based on conversation state (`session`) and detected intent.

## 1. Health Assistant Agent

Triggered when:

```text
What is Vitamin D deficiency?
How to improve sleep?
What causes anemia?
```

Purpose:

* General health education
* Healthcare Q&A
* Wellness information

Uses:

```python
LLMClient.generate()
```

This typically goes to Gemini/LLM.

---

## 2. Symptom Assessment Agent

Triggered when:

```text
I have fever
I have headache
I am feeling sick
```

Detection:

```python
looks_like_health_complaint()
```

or

```python
is_symptom_triage_kickoff()
```

Examples:

```text
Check symptoms
Analyze my symptoms
I'm not feeling well
```

Workflow:

```text
Collect Symptoms
      ↓
Collect Duration
      ↓
Collect Severity
      ↓
Additional Symptoms
      ↓
Risk Assessment
```

Session variables used:

```python
session["triage_collected"]
session["detected_symptoms"]
session["awaiting"]
```

---

## 3. Emergency Agent

Triggered when:

```text
Chest pain
Breathing difficulty
Heart attack symptoms
```

Uses:

```python
needs_cardiac_emergency_screen()
```

Then:

```python
_cardiac_emergency_screen_turn()
```

Follow-up questions:

```python
CARDIAC_SCREEN_QUESTIONS
```

Examples:

```text
Does pain spread to arm?
Shortness of breath?
Sweating?
```

If confirmed:

```python
build_emergency_reply()
```

No LLM required.

---

## 4. Report Analysis Agent

Triggered when:

```text
Analyze my report
Explain my blood report
```

Key functions:

```python
rehydrate_report_discussion_session()
```

Session fields:

```python
session["report_analysis"]
session["report_discussion"]
```

Supports:

### Initial Report Analysis

Upload report.

### Follow-up Questions

Example:

```text
Why is my hemoglobin low?
```

Maintains report context.

---

## 5. Scheduling Agent

Triggered when:

```text
Book appointment
Find doctor
Recommended doctors
```

Also:

```python
START_FIND_DOCTOR_TOKEN
```

Sets:

```python
session["care_goal"] = "find_doctor"
session["active_specialist"] = "scheduling_agent"
```

Workflow:

```text
Doctor Recommendation
      ↓
Availability Check
      ↓
Booking
```

---

# Offline Fallback Coverage

One thing I noticed:

Your offline fallback implementation is actually quite comprehensive.

It handles:

## Greetings

```text
Hi
Hello
Good morning
```

Functions:

```python
build_greeting_reply()
```

---

## Thanks

```text
Thanks
Thank you
```

Functions:

```python
build_thanks_reply()
```

---

## Symptom Detection

```text
Fever
Cough
Headache
Pain
Nausea
```

Functions:

```python
extract_symptoms_offline()
```

---

## Duration Detection

Examples:

```text
3 days
2 weeks
Yesterday
Last night
Couple of days
Few days
```

Functions:

```python
extract_duration()
```

---

## Severity Detection

Examples:

```text
Mild
Moderate
Severe
Pain 8/10
```

Functions:

```python
_parse_severity()
```

---

## More Symptoms Flow

Examples:

```text
Yes
No
```

Functions:

```python
_is_affirmative_more_symptoms()
```

---

## Appointment Intent

Examples:

```text
Book appointment
Need doctor
Recommended doctors
```

Handled even without LLM.

---

# Existing Test Cases Covered

Based on code paths, these scenarios are already handled:

### Greetings

✅ Hello

✅ Hi

✅ Good Morning

---

### Health Questions

✅ General healthcare questions

---

### Symptom Triage

✅ Single symptom

```text
Fever
```

✅ Multiple symptoms

```text
Fever + headache
```

---

### Duration Collection

✅ 3 days

✅ 2 weeks

✅ Yesterday

✅ Last night

---

### Severity Collection

✅ Mild

✅ Moderate

✅ Severe

✅ Pain scale 8/10

---

### Additional Symptoms

✅ Yes

✅ No

---

### Emergency

✅ Chest pain

✅ Cardiac screening

✅ Emergency escalation

---

### Reports

✅ Upload report

✅ Follow-up report discussion

---

### Scheduling

✅ Find doctor

✅ Book appointment

✅ Resume booking after login

---

### Guest Flow

✅ Guest consultation

✅ Guest booking

✅ Resume after authentication

---

# Missing Test Cases I Would Add

These are not obvious from the code and should be tested:

### Symptom Edge Cases

```text
I feel weird
Not feeling right
Something is wrong
```

---

### Mixed Messages

```text
I have fever and want to book an appointment
```

---

### Report + Symptom

```text
My report shows low hemoglobin and I feel dizzy
```

---

### Emergency Variations

```text
Left arm pain
Pressure in chest
Tightness in chest
```

---

### Doctor Search

```text
Need skin doctor
Need child specialist
Need heart doctor
```

---

### Multi-language

```text
Hindi
Gujarati
Mixed language
```

---

### LLM Failure

Force:

```text
Gemini timeout
Quota exceeded
No API key
```

Verify offline fallback still completes the workflow.

### Overall Assessment

The current implementation is **not purely LLM-driven**. It is a **hybrid healthcare chatbot** with:

* Rule-based triage
* Rule-based emergency handling
* Rule-based scheduling workflows
* Session-driven conversation state
* LLM for explanations and natural conversation
* Offline fallback when AI is unavailable

That's actually the right architecture for a medical assistant MVP.
