import time
import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage


class ToolErrorHandler(AgentMiddleware):
    def _make_error(self, request, exc):
        tool_name = request.tool.name if request.tool else "unknown"
        print(f"[ERROR] tool:{tool_name} | {exc}")
        return ToolMessage(
            content=json.dumps(
                {"success": False, "error": str(exc)}, ensure_ascii=False
            ),
            tool_call_id=request.tool_call["id"],
        )

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as e:
            return self._make_error(request, e)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as e:
            return self._make_error(request, e)


class ContextSummarizer(AgentMiddleware):
    def __init__(self, llm, token_limit=8000):
        super().__init__()
        self.llm = llm
        self.token_limit = token_limit

    def before_model(self, state, runtime):
        messages = state.get("messages", [])
        total_chars = 0
        for m in messages:
            content = getattr(m, "content", "")
            if isinstance(content, str):
                total_chars += len(content)
        if total_chars // 4 <= self.token_limit:
            return None
        cutoff = len(messages) // 2
        old_msgs = messages[:cutoff]
        recent_msgs = messages[cutoff:]
        summary_lines = []
        for m in old_msgs:
            summary_lines.append(f"{type(m).__name__}: {str(m.content)[:200]}")
        summary_text = "\n".join(summary_lines)
        resp = self.llm.invoke(
            [HumanMessage(content=f"Summarize the conversation:\n{summary_text}")]
        )
        summary_msg = SystemMessage(content=f"Context summary: {resp.content}")
        return {"messages": [summary_msg] + list(recent_msgs)}


class AgentStepTracker(AgentMiddleware):
    def before_agent(self, state, runtime):
        steps = list(state.get("intermediate_steps", []))
        steps.append(
            {
                "step": "agent_step",
                "agent": "planner",
                "status": "running",
                "timestamp": time.time(),
            }
        )
        return {"intermediate_steps": steps}

    def after_agent(self, state, runtime):
        steps = list(state.get("intermediate_steps", []))
        if steps and steps[-1].get("status") == "running":
            steps[-1] = {**steps[-1], "status": "done"}
        return {"intermediate_steps": steps}


AUDIT_FORBIDDEN_KEYWORDS = ["裸体", "色情", "暴力", "血腥", "武器"]


class AuditMiddleware(AgentMiddleware):
    def after_tool_call(self, request, result, runtime):
        content = str(result)
        for kw in AUDIT_FORBIDDEN_KEYWORDS:
            if kw in content:
                raise ValueError(f"audit_blocked: keyword={kw}")
        return None
