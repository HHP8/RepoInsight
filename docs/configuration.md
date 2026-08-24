# Configuration

RepoInsight loads built-in defaults, then a discovered repository-root `.repoinsight.toml` or explicit `--config` file, then CLI overrides. Unknown keys and invalid types fail closed. For remote sources, clone safety limits come from defaults and CLI because repository configuration is unavailable until after acquisition.

## Keys and defaults

| Key | Default | Purpose |
|---|---:|---|
| `analysis.exclude` | `[]` | Git-style excluded paths |
| `analysis.respect_gitignore` | `true` | Apply root Git ignore rules |
| `analysis.max_file_bytes` | `1048576` | Per-file byte bound |
| `analysis.max_files` | `20000` | Inventory file-count bound |
| `analysis.max_source_bytes` | `104857600` | Aggregate source-byte bound |
| `analysis.timeout_seconds` | `120` | Overall analysis deadline |
| `git.remote_history_depth` | `500` | Bounded remote history |
| `git.clone_timeout_seconds` | `60` | Clone process timeout |
| `scoring.weights.maintainability` | `25` | Category weight |
| `scoring.weights.testing` | `25` | Category weight |
| `scoring.weights.documentation` | `15` | Category weight |
| `scoring.weights.security_hygiene` | `15` | Category weight |
| `scoring.weights.repository_hygiene` | `10` | Category weight |
| `scoring.weights.maintenance` | `10` | Category weight |
| `rules.enabled` | `[]` | Explicitly enabled rule IDs |
| `rules.disabled` | `[]` | Explicitly disabled rule IDs |
| `thresholds.complexity` | `15` | Complexity boundary |
| `thresholds.function_loc` | `75` | Large-function boundary |
| `thresholds.class_loc` | `500` | Large-class boundary |
| `thresholds.module_loc` | `1000` | Large-module boundary |
| `thresholds.nesting_depth` | `5` | Nesting boundary |
| `thresholds.duplicate_statements` | `8` | Duplicate-structure minimum |
| `thresholds.test_ratio_medium` | `0.10` | Lowest test/source ratio band |
| `thresholds.test_ratio_low` | `0.25` | Higher test/source ratio band |
| `thresholds.public_docstring_rate` | `0.50` | Public docstring boundary |
| `thresholds.stale_days` | `365` | Stale-history age |
| `thresholds.activity_window_days` | `180` | Recent-activity window |
| `thresholds.activity_min_commits` | `2` | Minimum recent commits |
| `thresholds.single_contributor_min_age_days` | `180` | Single-contributor age guard |
| `output.format` | `all` | `json`, `html`, or `all` |
| `output.directory` | `repoinsight-report` | Default output directory |
| `ci.fail_under` | `0` | CI score threshold |

Example:

```toml
[analysis]
exclude = ["generated/", "vendor/"]
max_file_bytes = 2097152

[rules]
disabled = ["RI-MAINT-008"]

[ci]
fail_under = 80
```

The configuration fingerprint covers analysis, Git, scoring, rules, thresholds, and CI settings. Output format and directory are intentionally excluded because they do not change analysis results.
