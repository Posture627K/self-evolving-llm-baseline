---
name: safe-refactoring
description: Refactor duplicated logic (e.g. near-identical payload validation across multiple handlers/routes/endpoints) into a single reusable decorator, decorator factory, or shared abstraction without changing externally observable behavior. Use when a task says "reduce duplication", "extract shared logic", "refactor in place", "use a decorator/decorator factory", when multiple handler files (users.py, products.py, orders.py, reviews.py style) repeat required/optional field checks, type checks, range/enum/length/regex checks, or when the instructions require keeping status codes, error payload shapes, and boundary values (e.g. reject age=-1, price=0) byte-for-byte identical after refactoring. Do not use for algorithmic optimization, performance tuning, or refactors where behavior is explicitly allowed to change.
---

# Safe refactoring of duplicated logic into shared abstractions

## When to use
- Multiple files/functions implement near-identical validation, formatting, or
  gatekeeping logic with small per-instance differences (different required
  fields, different bounds, different enums).
- The task demands the refactor be "in place", runnable, and behavior-preserving:
  same status codes, same error payload shape, same boundary rejections, same
  optional-field semantics.
- Do NOT use when the task explicitly wants behavior changes, new features, or
  a full architecture rewrite ("do not replace with stubs / different structure"
  language signals behavior-preservation is the goal).

## Workflow
1. **Map the full call graph before touching anything.** Read every file the
   task points to, then run `find <root> -name "*.py" | grep -v __pycache__`
   to discover files NOT explicitly listed (helper/audit modules, `__init__.py`,
   entrypoint `app.py`, admin/legacy modules). Duplicated handlers often share
   a hidden helper module (e.g. `audit.py` with `prepare_payload` /
   `record_validation_attempt`) that performs side effects — these calls MUST
   be preserved inside the new abstraction, not dropped.
2. **Ignore decoys.** Docs or files referencing legacy/unrelated endpoints
   (e.g. an `admin.py`, `legacy_metrics.py`, or a contract-notes doc that says
   "none of this applies to the current handlers") are scope traps. Confirm a
   file is actually imported by the target handlers before including it in the
   refactor.
3. **Establish a baseline before editing.** Run the existing test suite
   (install `pytest` if missing: `pip install pytest -q`) and capture the
   pass/fail state. If tests are absent, write a quick throwaway sanity script
   that calls each handler with its current success and failure inputs, and
   record the exact outputs (status, error field, error message).
4. **Design ONE parameterized abstraction**, not per-case exceptions. A field
   declaration data structure (dataclass or dict) plus a decorator factory
   generalizes required/optional, type, and value checks:
   - `required` flag + `required_message`
   - expected `type` (tuple for multiple allowed types, e.g. `(int, float)`)
     + `type_message`
   - a list of composable `checks` (small closures) for range, enum,
     min/max length, regex-match, non-empty, etc. Each check returns `None`
     on success or an error message string on failure.
   - Skip type/value checks when an optional field is present but `None`
     (matches typical "optional field may be omitted or null" semantics).
5. **Preserve validation ORDER exactly.** Run a first pass checking all
   `required`-field presence/emptiness (matches the common pattern of
   checking required fields before types), THEN a second pass checking
   type + value checks for whichever fields are present. If the original
   code interleaves required/type checks per field in a specific order,
   verify your two-pass structure still returns the SAME first-failing-field
   for every original invalid-input example before assuming it's fine.
6. **Keep the shared helper functions untouched** (e.g. `ok()`, `bad_request()`
   returning `{"status":.., "error": {"field":.., "message":..}}`) and reuse
   them from inside the decorator — do not reinvent the response shape.
7. **Rewrite each call site to declare data, not logic**: a short `FIELDS`
   list plus `@validate_payload("route_name", FIELDS)` on the handler. The
   handler body should shrink to just building the success response.
8. **Re-run the baseline test suite** and confirm identical pass count.
9. **Run a targeted parity script** exercising every boundary/edge case named
   in the task (missing required field, wrong type for required AND optional
   fields, values at and past each boundary, enum rejection, optional-field
   omitted vs. `None` vs. present-and-invalid) and diff the printed
   `{status, error}` dicts against what the ORIGINAL code would have produced
   for the same inputs (compute this mentally/by inspection from the pre-edit
   source, since the tests may not cover every boundary).
10. **Sanity-check imports/entrypoint** (`python3 -c "import app"` or
    equivalent) after the rewrite. If an unrelated import path is already
    broken before your edit (e.g. an empty `__init__.py` that never exported
    the handlers), do not "fix" it as part of this task — verify it was
    already broken pre-refactor and leave it alone unless the task asks for it.

## Gotchas
- **Silent side-effect loss**: dropping a call to a shared audit/logging/
  context-prep helper when consolidating handlers is a correctness bug even
  though it won't show up in a naive happy-path test — always grep for what
  each original handler called before the validation logic and replicate it
  inside the new decorator.
- **False failure from an unrelated pre-existing bug**: don't spend cycles
  fixing an import error or issue that already existed before your changes;
  confirm by checking whether the same failure occurs on the ORIGINAL file
  content, or whether the failing import path is even used by the app's real
  entrypoint.
- **Order-sensitive error messages**: reordering when a required-check runs
  relative to a type-check can silently change which field's error is
  reported first for a payload with multiple defects — this passes shallow
  "handler still returns 400" tests but fails a hidden test asserting a
  specific `field`/`message`.
- **Optional field with `None`**: many handlers treat `field present but None`
  as "not provided" (skip type/value checks) rather than a type violation —
  encode this explicitly (`if not required and value is None: continue`)
  rather than assuming `isinstance(None, expected_type)` will naturally do
  the right thing (it won't; it'll incorrectly reject).
- **`pytest` may not be pre-installed** in the sandbox; `pip install pytest -q`
  before assuming "no tests exist".
