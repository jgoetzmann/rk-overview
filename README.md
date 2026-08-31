# rk-overview

The human-maintained explainer for the rk project (quantization-aware Runge-Kutta search).
The companion repo rk-findings carries the authoritative, machine-generated numbers; this site
carries the narrative: what the project is, how the system is built, every design decision and
what the build did to it, run-level charts, and a frozen snapshot of the findings site.

Site: https://jgoetzmann.github.io/rk-overview/

Regenerate after editing tools/pages_text.py or to refresh the snapshot:

    ..\rk-harness\.venv\Scripts\python.exe tools\generate.py

DESIGN.md is the original pre-build decision record, kept verbatim; the design-decisions page
annotates it against the as-built system.
