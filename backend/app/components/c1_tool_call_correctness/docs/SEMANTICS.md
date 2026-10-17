# C1 Explainable Tool-Call Correctness Testing — Semantic Specification

**Project**: Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications (J26-SE-341)  
**Component**: IT23236646 — Explainable Tool-Call Correctness Testing  
**Document**: Phase 1 Status, Verdict, and Evidence Rules for Evaluator Implementation  

---

## 1. Status and Verdict Separation

The QA framework enforces strict decoupling between distinct dimensions of test execution:
1. **Candidate Readiness (`CaseReadiness`)**: `READY` vs. `NOT_READY`. Managed strictly at validation time before execution.
2. **Execution Status (`ExecutionStatus`)**: `COMPLETED`, `FAILED`, `TIMEOUT`, `INTERRUPTED`, `PENDING`. Reflects agent/runner lifecycle.
3. **Evaluation Verdict (`EvaluationVerdict`)**: `PASS`, `FAIL`, `INCONCLUSIVE`. Reflects test criteria fulfillment.
4. **Diagnosis Classification (`DiagnosisClassification`)**: `SUPPORTED_CODE_DEFECT`, `AGENT_BEHAVIOUR`, `SPECIFICATION_PROBLEM`, `UNKNOWN`. Reflects root cause analysis.

---

## 2. Core Verdict Determination Rules

### Rule 1: PASS Criteria
An evaluation verdict shall be **`PASS`** if and only if:
- The execution status is `COMPLETED` (uninterrupted).
- Every mandatory tool invocation required by the candidate test case was executed.
- Every atomic parameter check (`CheckOutcome`) succeeded (`PASS`).
- Sufficient runtime evidence exists supporting each mandatory check.

### Rule 2: FAIL Criteria
An evaluation verdict shall be **`FAIL`** if:
- Any mandatory tool invocation was omitted.
- An unauthorized or unregistered tool was invoked.
- A required argument was missing, malformed, had the wrong type, or mismatched expected constraints.
- An unproven or invalid argument source relationship violated task specifications.

### Rule 3: INCONCLUSIVE Criteria
An evaluation verdict shall be **`INCONCLUSIVE`** if:
- Missing telemetry or unrecorded evidence prevents verifying a mandatory correctness check, provided no other check already proved a `FAIL`.
- An execution was `INTERRUPTED`, timed out, or crashed before mandatory expectations could be verified (an interrupted run **must never** become `PASS` simply because earlier calls appeared valid).

### Rule 4: Separation of Test Readiness from Agent Scoring
- If candidate expectations are malformed, contradictory, ambiguous, or reference invalid tool schemas, the test case is classified as **`NOT_READY`**.
- An invalid candidate case is excluded from evaluation scoring; it **must never** be counted as an agent failure (`FAIL`).

---

## 3. Evidence and Attribution Rules

### Rule 5: Value Provenance vs. Value Matching
- A tool argument value that merely matches a previous tool output does **not** by itself prove that the LLM agent derived the value from that tool output.
- Provenance attribution requires explicit data-flow trace evidence (`source_tags` or causal message history). Without evidence, the source relation status remains `INFERRED` or `UNKNOWN`.

### Rule 6: Wrong Argument != Code Defect
- An incorrect or invalid tool argument emitted by an agent does **not** automatically indicate a bug in underlying application code.
- By default, malformed invocations represent `AGENT_BEHAVIOUR` unless static analysis, AST mappings, or tool schema regressions prove that incorrect code/prompts prompted the mistake.

### Rule 7: Lack of Source Access
- Lack of repository source-code access does **not** imply agent error or test invalidity.
- Correctness testing operates as black-box evaluation (`PASS`, `FAIL`, `INCONCLUSIVE`).
- Lack of source access merely marks code defect localization as `UNKNOWN` / unavailable.

### Rule 8: Isolation of Original Failure from Repair Trials
- Original execution traces, failure evidence, and initial diagnosis records must be permanently preserved and immutable.
- Subsequent candidate repair attempts, patch verifications, or re-executions must generate distinct trial records and never overwrite original baseline defect evidence.

---

## 4. Distinguishing Missing Evidence from Explicit Null

- **Missing Evidence (`None` / omitted)**: Telemetry or property was not captured or was unavailable during the run. Triggers `INCONCLUSIVE` if mandatory.
- **Explicit Null (`output_is_explicit_null=True`)**: Tool explicitly returned a JSON `null` / Python `None` value as a valid response. Evaluated as an observed value against expected schema/constraints.
