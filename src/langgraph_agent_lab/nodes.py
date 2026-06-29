"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
from pydantic import BaseModel, Field

from .state import AgentState, make_event, Route
from .llm import get_llm
from langgraph.types import interrupt

# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────

class RouteClassification(BaseModel):
    route: Route = Field(description="Classified route based on the query: risky, tool, missing_info, error, simple")

def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM."""
    query = state.get("query", "")
    llm = get_llm()
    structured_llm = llm.with_structured_output(RouteClassification)
    
    prompt = f"""Classify the user query into one of these intents:
- risky: Actions with side effects (refunds, deletions, sending emails, cancellations)
- tool: Information lookups (order status, tracking, search queries)
- missing_info: Vague/incomplete queries lacking actionable context
- error: System failures (timeouts, crashes, service unavailable)
- simple: General questions answerable without tools or actions
Priority: risky > tool > missing_info > error > simple.

You must output a valid JSON object with exactly one key "route".
Example: {{"route": "simple"}}

Query: {query}"""

    try:
        result = structured_llm.invoke(prompt)
        route_str = result.route.value if hasattr(result.route, 'value') else str(result.route)
    except Exception:
        # Fallback for models that fail structured output and return raw string
        res = llm.invoke(prompt)
        txt = str(res.content).lower()
        if "risky" in txt: route_str = "risky"
        elif "tool" in txt: route_str = "tool"
        elif "missing" in txt: route_str = "missing_info"
        elif "error" in txt: route_str = "error"
        else: route_str = "simple"
    
    risk_level = "high" if route_str == "risky" else "low"
    
    return {
        "route": route_str,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"Classified as {route_str}")]
    }

def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call."""
    attempt = state.get("attempt", 0)
    route = state.get("route", "")
    
    if route == "error" and attempt < 2:
        result = "ERROR: simulated transient tool failure"
    else:
        result = "SUCCESS: mock tool execution completed normally"
        
    return {
        "tool_results": [result],
        "events": [make_event("tool", "executed", result)]
    }

def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate."""
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""
    
    # BONUS: LLM-as-judge for tool evaluation
    llm = get_llm()
    prompt = f"""You are an evaluator for a support agent.
Check if the tool execution was successful or if it encountered an error that requires a retry.
Respond with EXACTLY ONE WORD: either "success" or "needs_retry".

Tool output: {latest_result}
"""
    
    try:
        response = llm.invoke(prompt)
        text = str(response.content).lower().strip()
        evaluation = "needs_retry" if "retry" in text or "error" in text else "success"
    except Exception:
        # Fallback to heuristic
        evaluation = "needs_retry" if "ERROR" in latest_result else "success"
        
    return {
        "evaluation_result": evaluation,
        "events": [make_event("evaluate", "completed", f"Evaluated as {evaluation} (LLM-as-judge)")]
    }

def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval", {})
    
    llm = get_llm()
    
    context = []
    if tool_results:
        context.append(f"Tool results: {tool_results}")
    if approval:
        context.append(f"Approval status: {approval}")
        
    context_str = "\n".join(context)
    
    prompt = f"""You are a helpful support ticket agent. Answer the user's query based ONLY on the provided context if available.
User Query: {query}

Context:
{context_str}

If there is no context, provide a general helpful answer."""
    
    response = llm.invoke(prompt)
    answer = response.content if hasattr(response, 'content') else str(response)
    
    return {
        "final_answer": answer,
        "events": [make_event("answer", "generated", "Final answer generated")]
    }

def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    question = f"Could you please provide more details? Your request '{query}' is too vague."
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("ask_clarification", "requested", "Asked for clarification")]
    }

def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    proposed_action = f"Executing risky action for: {query}"
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "prepared", "Risky action prepared for approval")]
    }

def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step."""
    if os.getenv("LANGGRAPH_INTERRUPT") == "true":
        decision = interrupt("Requires approval")
        if isinstance(decision, dict):
            approved = decision.get("approved", False)
        else:
            approved = bool(decision)
    else:
        approved = True
        
    approval = {
        "approved": approved,
        "reviewer": "mock-reviewer",
        "comment": "Mock auto-approved" if approved else "Mock auto-rejected"
    }
    
    return {
        "approval": approval,
        "events": [make_event("approval", "decision_made", f"Approved: {approved}")]
    }

def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt."""
    attempt = state.get("attempt", 0)
    new_attempt = attempt + 1
    error_msg = f"Retry attempt {new_attempt} after failure"
    return {
        "attempt": new_attempt,
        "errors": [error_msg],
        "events": [make_event("retry_or_fallback", "retrying", error_msg)]
    }

def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    answer = "We are unable to process your request at this time due to repeated system failures."
    return {
        "final_answer": answer,
        "events": [make_event("dead_letter", "failed", "Max retries exceeded")]
    }

def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")]
    }
