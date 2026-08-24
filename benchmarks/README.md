# Benchmark

The benchmark deterministically generates 100 Python modules of 1,000 lines each, then runs the same in-memory `AnalyzeService` pipeline used by the CLI. It excludes network cloning and report-file writes. The fixture lives in a disposable temporary directory and is removed when the command exits.

```console
python -m benchmarks.run_benchmark
python -m benchmarks.run_benchmark --enforce-target
```

The second command fails if analysis takes 30 seconds or longer. Routine tests only verify deterministic fixture generation; the target runs only through this command or the manual benchmark workflow.

Results are environment-specific and are not a universal performance guarantee. Recorded evidence includes interpreter, platform, processor string, logical CPU count, exact line count, elapsed wall time, target, and report completeness.
