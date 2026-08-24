# Rule catalog 1.0

The catalog is the scoring and explanation source of truth. `repoinsight rules` prints the live metadata and `repoinsight explain RULE_ID` shows evidence, limits, and remediation. Heuristic rules report static indicators, not proof of a defect. Possible-secret findings are always labeled as suspected evidence.

| ID | Category | Severity | Default deduction | Title |
|---|---|---|---:|---|
| RI-MAINT-001 | maintainability | medium | 3 | High cyclomatic complexity |
| RI-MAINT-002 | maintainability | medium | 2 | Large function or method |
| RI-MAINT-003 | maintainability | medium | 3 | Large class |
| RI-MAINT-004 | maintainability | medium | 3 | Large Python module |
| RI-MAINT-005 | maintainability | low | 2 | Deeply nested control flow |
| RI-MAINT-006 | maintainability | medium | 3 | Duplicated-looking function structure |
| RI-MAINT-007 | maintainability | low | 1 | Possible unused private definition |
| RI-MAINT-008 | maintainability | info | 1 | TODO or FIXME marker |
| RI-MAINT-009 | maintainability | low | 1 | Import organization concern |
| RI-TEST-001 | testing | high | 25 | No discovered Python tests |
| RI-TEST-002 | testing | medium | 12 | Low test-to-source ratio |
| RI-TEST-003 | testing | low | 5 | Tests outside recognized roots |
| RI-TEST-004 | testing | medium | 8 | Test runner evidence missing |
| RI-TEST-005 | testing | medium | 8 | CI test invocation missing |
| RI-TEST-006 | testing | low | 4 | Coverage evidence missing |
| RI-DOC-001 | documentation | high | 20 | Root README missing |
| RI-DOC-002 | documentation | low | 5 | README content incomplete |
| RI-DOC-003 | documentation | medium | 8 | Low public docstring rate |
| RI-DOC-004 | documentation | low | 4 | Contribution guide missing |
| RI-DOC-005 | documentation | info | 2 | Release notes missing |
| RI-DOC-006 | documentation | low | 4 | Usage examples missing |
| RI-SEC-001 | security hygiene | high | 10 | Possible secret |
| RI-SEC-002 | security hygiene | medium | 5 | Dynamic code execution call |
| RI-SEC-003 | security hygiene | high | 8 | Insecure shell execution pattern |
| RI-SEC-004 | security hygiene | high | 8 | Unsafe deserialization pattern |
| RI-SEC-005 | security hygiene | medium | 6 | Risky temporary-file handling |
| RI-SEC-006 | security hygiene | low | 2 | Runtime dependency lacks an exact pin |
| RI-SEC-007 | security hygiene | high | 8 | TLS verification disabled |
| RI-REPO-001 | repository hygiene | medium | 10 | License metadata missing |
| RI-REPO-002 | repository hygiene | low | 5 | `.gitignore` missing |
| RI-REPO-003 | repository hygiene | medium | 8 | Dependency metadata missing |
| RI-REPO-004 | repository hygiene | low | 5 | Packaging configuration missing |
| RI-REPO-005 | repository hygiene | medium | 8 | CI configuration missing |
| RI-REPO-006 | repository hygiene | low | 3 | `.dockerignore` missing |
| RI-REPO-007 | repository hygiene | info | 3 | Issue and pull-request templates missing |
| RI-REPO-008 | repository hygiene | info | 2 | Community policies missing |
| RI-HIST-001 | maintenance | high | 15 | Stale reachable history |
| RI-HIST-002 | maintenance | low | 5 | Low recent commit activity |
| RI-HIST-003 | maintenance | low | 4 | Single-contributor history |
| RI-HIST-004 | maintenance | info | 0 | Remote history is partial |
| RI-HIST-005 | maintenance | info | 0 | Git history unavailable |

Per-rule caps are part of the live catalog and scoring trace. Rule IDs are stable throughout report contract 1.0. Threshold-backed defaults are documented in [Configuration](configuration.md).
