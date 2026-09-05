# SkillEvolBench T4-T6 Verifier Construct Audit

- Scope: 90 tasks, 963 extracted checks
- Functional: 559
- Contract: 237
- Form: 167

## Definitions

- **Functional**: executes the solution or inspects its observable output/state.
- **Contract**: enforces an explicit safety, completeness, schema, provenance, or anti-shortcut obligation.
- **Form**: requires a particular file, symbol, literal, import, or code layout even when another implementation could behave correctly.

The classification is a static first pass. Contract/form boundary cases remain reviewable in the JSON ledger.

## Selected paired runs

| Source | Target | Functional | Contract | Form | Review |
|---|---|---:|---:|---:|---|
| `E1-LS3-T1` | `E1-LS3-T4` | 7 | 3 | 0 | Architectural transfer target: functional plugin tests plus broad modularity obligations stated in the task; no required helper-call location. |
| `E1-LS3-T1` | `E1-LS3-T5` | 8 | 3 | 0 | Boundary-preservation target: executable None/empty-value cases plus the explicitly requested Pipeline and stage-preservation contract. |
| `E1-LS3-T1` | `E1-LS3-T6` | 6 | 5 | 0 | Refactor-and-test target: functional edge cases plus task-declared helper-count, test-count, and coverage obligations. |

Primary interpretation uses functional outcomes. Contract and form results are reported separately; form failures cannot establish negative functional transfer.

## All T4-T6 tasks

| Task | Slug | Functional | Contract | Form |
|---|---|---:|---:|---:|
| `E1-LS1-T4` | `debug-ci-then-add-webhook` | 5 | 5 | 5 |
| `E1-LS1-T5` | `wrong-fix-passes-most-tests` | 15 | 2 | 0 |
| `E1-LS1-T6` | `microservice-error-cascade-diagnosis` | 3 | 5 | 7 |
| `E1-LS2-T4` | `dep-fix-unblocks-ci-then-feature` | 0 | 4 | 8 |
| `E1-LS2-T5` | `numpy-deprecated-alias-runtime-crash` | 0 | 2 | 10 |
| `E1-LS2-T6` | `dep-fix-api-migration-config-update` | 0 | 2 | 12 |
| `E1-LS3-T4` | `refactor-god-module-before-adding-plugin-system` | 7 | 3 | 0 |
| `E1-LS3-T5` | `refactor-breaks-none-handling-chain` | 8 | 3 | 0 |
| `E1-LS3-T6` | `refactor-extract-test-add-coverage` | 6 | 5 | 0 |
| `E1-LS4-T4` | `fix-data-corruption-before-migration` | 6 | 1 | 1 |
| `E1-LS4-T5` | `fix-ui-hides-api-error` | 8 | 1 | 3 |
| `E1-LS4-T6` | `cross-layer-fix-plus-integration-test-plus-docs` | 6 | 3 | 1 |
| `E1-LS5-T4` | `resolve-conflicts-to-unblock-release` | 4 | 2 | 0 |
| `E1-LS5-T5` | `accept-ours-loses-security-fix` | 6 | 2 | 2 |
| `E1-LS5-T6` | `three-way-merge-plus-integration-validation` | 4 | 3 | 0 |
| `E2-LS1-T4` | `validate-and-normalize-before-search-pipeline` | 7 | 4 | 0 |
| `E2-LS1-T5` | `server-returns-detailed-400-trap` | 5 | 3 | 0 |
| `E2-LS1-T6` | `validate-normalize-enrich-then-call` | 7 | 4 | 0 |
| `E2-LS2-T4` | `retry-step-3-in-5-step-pipeline` | 7 | 3 | 0 |
| `E2-LS2-T5` | `retry-masks-auth-expiry-trap` | 7 | 4 | 0 |
| `E2-LS2-T6` | `full-pipeline-with-circuit-breaker` | 7 | 5 | 0 |
| `E2-LS3-T4` | `discover-pagination-requirement` | 8 | 3 | 0 |
| `E2-LS3-T5` | `total-pages-lie-trap` | 5 | 3 | 0 |
| `E2-LS3-T6` | `paginate-retry-merge-sort` | 7 | 6 | 0 |
| `E2-LS4-T4` | `infer-aggregation-flow` | 4 | 4 | 0 |
| `E2-LS4-T5` | `url-redirect-trap` | 5 | 2 | 0 |
| `E2-LS4-T6` | `full-orchestration-retry-validate` | 6 | 5 | 0 |
| `E2-LS5-T4` | `implicit-validation-requirement` | 6 | 3 | 1 |
| `E2-LS5-T5` | `old-format-200-blindtrust-trap` | 5 | 3 | 1 |
| `E2-LS5-T6` | `validate-fallback-merge` | 5 | 4 | 1 |
| `E3-LS1-T4` | `implicit-schema-check-before-join` | 6 | 4 | 0 |
| `E3-LS1-T5` | `case-sensitive-column-trap` | 4 | 3 | 1 |
| `E3-LS1-T6` | `full-schema-inspect-clean-query-validate` | 6 | 6 | 1 |
| `E3-LS2-T4` | `implicit-sort-for-ranking-report` | 6 | 4 | 0 |
| `E3-LS2-T5` | `numeric-string-dictionary-order-trap` | 5 | 4 | 0 |
| `E3-LS2-T6` | `composite-sort-dedup-aggregate` | 6 | 4 | 0 |
| `E3-LS3-T4` | `implicit-key-alignment-for-comparison` | 7 | 5 | 0 |
| `E3-LS3-T5` | `wrong-join-key-plausible-result-trap` | 5 | 3 | 0 |
| `E3-LS3-T6` | `fuzzy-match-dedup-aggregate-pipeline` | 6 | 4 | 0 |
| `E3-LS4-T4` | `implicit-null-causes-division-by-zero` | 5 | 4 | 1 |
| `E3-LS4-T5` | `fillna-zero-destroys-meaning` | 5 | 5 | 0 |
| `E3-LS4-T6` | `multi-source-null-strategy-unification` | 5 | 5 | 1 |
| `E3-LS5-T4` | `implicit-sanity-check-for-report` | 4 | 2 | 2 |
| `E3-LS5-T5` | `correct-syntax-wrong-logic-trap` | 5 | 3 | 2 |
| `E3-LS5-T6` | `multi-layer-sanity-pipeline` | 6 | 5 | 2 |
| `E4-LS1-T4` | `compare-two-quotes-implicit-extraction` | 5 | 4 | 0 |
| `E4-LS1-T5` | `revenue-contradiction-trap` | 5 | 3 | 0 |
| `E4-LS1-T6` | `extract-normalize-fill-validate` | 7 | 4 | 0 |
| `E4-LS2-T4` | `implicit-format-conversion` | 4 | 2 | 0 |
| `E4-LS2-T5` | `excel-multi-sheet-formula-trap` | 6 | 2 | 0 |
| `E4-LS2-T6` | `pdf-json-docx-chain` | 4 | 2 | 0 |
| `E4-LS3-T4` | `implicit-template-requirement` | 1 | 4 | 4 |
| `E4-LS3-T5` | `hallucination-trap-3-missing-fields` | 1 | 3 | 6 |
| `E4-LS3-T6` | `multi-source-fill-conflict-validate` | 1 | 3 | 6 |
| `E4-LS4-T4` | `implicit-diff-for-review` | 3 | 2 | 0 |
| `E4-LS4-T5` | `page-number-reference-error-trap` | 5 | 2 | 0 |
| `E4-LS4-T6` | `multi-version-change-chain` | 7 | 3 | 0 |
| `E4-LS5-T4` | `implicit-merge-requirement` | 6 | 0 | 4 |
| `E4-LS5-T5` | `shallow-merge-misses-nested-conflict-trap` | 5 | 0 | 2 |
| `E4-LS5-T6` | `full-reconciliation-pipeline` | 8 | 1 | 4 |
| `E5-LS1-T4` | `implicit-filtering-for-briefing` | 5 | 0 | 1 |
| `E5-LS1-T5` | `outdated-authoritative-source-trap` | 2 | 0 | 4 |
| `E5-LS1-T6` | `multi-dimension-filter-rank` | 3 | 0 | 3 |
| `E5-LS2-T4` | `implicit-comparison-for-evaluation` | 8 | 0 | 0 |
| `E5-LS2-T5` | `cherry-pick-3-of-10-trap` | 1 | 0 | 1 |
| `E5-LS2-T6` | `multi-source-collect-detect-label-compare` | 2 | 0 | 5 |
| `E5-LS3-T4` | `implicit-fact-check` | 6 | 0 | 5 |
| `E5-LS3-T5` | `fake-real-mixed-citations` | 7 | 0 | 5 |
| `E5-LS3-T6` | `full-citation-audit` | 6 | 0 | 5 |
| `E5-LS4-T4` | `implicit-ceo-constraint` | 6 | 0 | 4 |
| `E5-LS4-T5` | `verbose-covers-everything-trap` | 6 | 0 | 4 |
| `E5-LS4-T6` | `hierarchical-series-summarization` | 6 | 0 | 4 |
| `E5-LS5-T4` | `implicit-contradiction-check-for-synthesis` | 10 | 0 | 3 |
| `E5-LS5-T5` | `false-contradiction-different-timeframes-trap` | 11 | 0 | 4 |
| `E5-LS5-T6` | `comprehensive-contradiction-audit` | 11 | 0 | 4 |
| `E6-LS1-T4` | `triage-for-meeting-prep` | 9 | 4 | 1 |
| `E6-LS1-T5` | `anger-not-urgent-trap` | 9 | 4 | 1 |
| `E6-LS1-T6` | `triage-then-draft-p0-replies` | 9 | 4 | 1 |
| `E6-LS2-T4` | `implicit-reply-selection` | 8 | 3 | 2 |
| `E6-LS2-T5` | `friendly-tone-unreasonable-request-trap` | 8 | 3 | 2 |
| `E6-LS2-T6` | `triage-context-cc-compose` | 8 | 3 | 2 |
| `E6-LS3-T4` | `implicit-tracking-for-standup` | 6 | 2 | 3 |
| `E6-LS3-T5` | `question-masquerading-as-action-trap` | 7 | 2 | 3 |
| `E6-LS3-T6` | `full-thread-extract-track-followup` | 6 | 2 | 3 |
| `E6-LS4-T4` | `implicit-scheduling-requirement` | 11 | 3 | 2 |
| `E6-LS4-T5` | `dst-boundary-trap` | 11 | 3 | 2 |
| `E6-LS4-T6` | `multi-day-optimization` | 11 | 3 | 2 |
| `E6-LS5-T4` | `implicit-extraction-from-meeting-notes` | 16 | 2 | 1 |
| `E6-LS5-T5` | `rhetorical-question-trap` | 16 | 2 | 1 |
| `E6-LS5-T6` | `full-thread-parse-and-summarize` | 16 | 2 | 1 |

## Interpretation boundary

This audit does not change the benchmark verifier. It changes how paired-run evidence is interpreted: functional, contract, and form effects are not collapsed into one causal claim.
