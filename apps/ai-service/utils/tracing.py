from datetime import datetime, timezone


def _iso_ms():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}"[:3]


def trace_step(session_id: str, step_name: str, data: dict):
    print(f"[TRACE] {_iso_ms()} | session:{session_id} | step:{step_name} | {data}")


def trace_tool_call(session_id: str, tool_name: str, args: dict, result: str, duration_ms: float):
    print(f"[TRACE] {_iso_ms()} | session:{session_id} | step:{tool_name}_call | args={args} result={result} duration_ms={duration_ms}")


def trace_error(session_id: str, context: str, error: str):
    print(f"[TRACE] {_iso_ms()} | session:{session_id} | step:{context} | error={error}")
