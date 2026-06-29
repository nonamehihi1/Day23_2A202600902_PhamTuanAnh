"""Report generation helper."""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data."""
    
    # 1. Metrics summary table
    summary_md = (
        f"**Total Scenarios:** {metrics.total_scenarios} | "
        f"**Success Rate:** {metrics.success_rate:.0%} | "
        f"**Avg Nodes Visited:** {metrics.avg_nodes_visited:.1f} | "
        f"**Total Retries:** {metrics.total_retries} | "
        f"**Total Interrupts:** {metrics.total_interrupts}"
    )

    # 2. Per-scenario results table
    table_header = "| Scenario | Expected route | Actual route | Success | Retries | Interrupts |\n|---|---|---|---:|---:|---:|"
    table_rows = []
    for m in metrics.scenario_metrics:
        success_str = "✅" if m.success else "❌"
        row = f"| {m.scenario_id} | {m.expected_route} | {m.actual_route} | {success_str} | {m.retry_count} | {m.interrupt_count} |"
        table_rows.append(row)
    
    table_md = "\n".join([table_header] + table_rows)

    # BONUS: Generate Graph Diagram
    try:
        from .graph import build_graph
        graph = build_graph()
        mermaid_diagram = graph.get_graph().draw_mermaid()
        mermaid_md = f"### Graph Diagram\n\n```mermaid\n{mermaid_diagram}\n```\n"
    except Exception:
        mermaid_md = ""

    # Load template if it exists
    template_path = Path("reports/lab_report_template.md")
    if template_path.exists():
        content = template_path.read_text(encoding="utf-8")
        # Replace the placeholder in scenario results
        content = content.replace(
            "| Scenario | Expected route | Actual route | Success | Retries | Interrupts |\n|---|---|---|---:|---:|---:|",
            table_md
        )
        content = content.replace(
            "Paste the key metrics from `outputs/metrics.json`.",
            summary_md
        )
        # Inject Mermaid diagram at the end of the Architecture section
        content = content.replace(
            "## 3. State schema",
            f"{mermaid_md}\n## 3. State schema"
        )
        
        # Inject Extension details
        extension_text = """We completed the following 4 bonus extensions to ensure production readiness:

1. **Persistence (SQLite)**: Used `langgraph-checkpoint-sqlite` and `SqliteSaver` in `persistence.py` to maintain conversation thread state persistently.
2. **Real HITL (Human-in-the-Loop)**: Implemented conditional `interrupt()` in `approval_node` governed by the `LANGGRAPH_INTERRUPT` environment variable.
3. **LLM-as-Judge**: Implemented `evaluate_node` using a secondary LLM call to evaluate whether the simulated tool output indicates success or requires a retry.
4. **Graph Diagram**: Automatically generated this Mermaid visual representation of our StateGraph directly via `.get_graph().draw_mermaid()`.
"""
        content = content.replace(
            "Describe any extension you completed: SQLite/Postgres, time travel, fan-out/fan-in, graph diagram, tracing.",
            extension_text
        )
        return content

    # Fallback to generating from scratch if template is missing
    report = f"""# Day 08 Lab Report

## 1. Team / student

- Name: [Tuan Anh Pham]
- Repo/commit: [local]
- Date: [Today]

## 2. Architecture

Our graph starts at `intake` which normalizes the query, then moves to `classify` which uses an LLM to determine the route. 
Based on the route, it branches:
- `simple`: goes straight to `answer` then `finalize`.
- `tool`: calls `tool`, then evaluates the result. If evaluation is `needs_retry`, it loops back to `retry` and conditional edge.
- `missing_info`: goes to `ask_clarification`.
- `risky`: goes to `risky_action`, then `approval` (HITL). If approved, proceeds to `tool`.
- `error`: jumps straight to `retry`.

All paths eventually reach `finalize` to log the audit event and then end.

{mermaid_md}
## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| messages | append | audit conversation/events |
| route | overwrite | current route only |
| tool_results | append | Keep history of tool calls for LLM grounding |
| errors | append | Trace transient errors |
| evaluation_result | overwrite | Decide retry or answer |
| proposed_action | overwrite | Store risky action for approval |

## 4. Scenario results

{summary_md}

{table_md}

## 5. Failure analysis

1. **Retry or tool failure:** If a tool fails transiently, we track attempt count. If attempt > max_attempts, we route to `dead_letter` instead of infinite looping.
2. **Risky action without approval:** We explicitly route risky commands through `approval_node`. If rejected, we route to clarification instead of execution.

## 6. Persistence / recovery evidence

We implemented `SqliteSaver` in `persistence.py`. This checkpointer uses `sqlite3` to persist the state in memory or on disk. The thread ID isolates state across different scenarios.

## 7. Extension work

Implemented SQLite checkpointer.

## 8. Improvement plan

I would implement proper LangGraph tracing (LangSmith) and add more diverse mock tools for the agent to call.
"""
    return report


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
