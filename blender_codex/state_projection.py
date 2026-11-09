"""Bounded, explicitly partial UI previews; original session/history is untouched."""
import json


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _preview(value, depth=0):
    if depth > 10:
        return "[Preview nesting limit; see full detail resource]"
    if isinstance(value, str):
        return value if len(value) <= 8192 else value[:8192] + "\n[Preview truncated; full detail is in the resource when available]"
    if isinstance(value, list):
        result = [_preview(x, depth + 1) for x in value[:64]]
        if len(value) > 64:
            result.append({"preview_omitted_entries": len(value) - 64})
        return result
    if isinstance(value, dict):
        result = {key: _preview(item, depth + 1) for key, item in list(value.items())[:64]}
        if len(value) > 64:
            result["preview_omitted_fields"] = len(value) - 64
        return result
    return value


def bounded_state(state, resources, limit):
    """Keep JSON under limit, exposing full large details via authorized handles.

    The returned metadata declares every preview/window reduction. No original
    transcript/result is overwritten; no filesystem paths are accepted here.
    """
    result = dict(state)
    artifacts = list(state.get("artifacts", []))
    stats = {"truncated": False, "large_previews": 0, "omitted_messages": 0,
             "omitted_tool_calls": 0, "omitted_threads": 0, "warnings": []}

    def detail(name, body, key):
        try:
            descriptor = resources.add(name, "application/json" if name.endswith(".json") else "text/plain", body, key=("ui-detail", key))
            if not any(entry.get("id") == descriptor["id"] for entry in artifacts):
                artifacts.append(descriptor)
            return descriptor["id"]
        except (ValueError, OSError):
            if not stats["warnings"]:
                stats["warnings"].append("Some full preview resources exceed the local cache limit; the original session/history was not altered.")
            return None

    tools = []
    for row in state.get("tool_calls", []):
        raw = _bytes(row)
        if len(raw) <= 128 * 1024:
            tools.append(row)
            continue
        stats["truncated"] = True
        stats["large_previews"] += 1
        view = _preview(row)
        handle = detail("tool-details.json", raw, row.get("id")) if row.get("status") != "running" else None
        view["projection"] = {"truncated": True, "original_bytes": len(raw), "detail_resource_id": handle}
        if handle:
            view["resource_ids"] = list(dict.fromkeys(view.get("resource_ids", []) + [handle]))
            content = view.get("content")
            view["content"] = (content if isinstance(content, list) else []) + [{"type": "resource", "resource_id": handle, "name": "tool-details.json"}]
        tools.append(view)
    messages = []
    for row in state.get("messages", []):
        if len(_bytes(row)) <= 128 * 1024:
            messages.append(row)
            continue
        stats["truncated"] = True
        stats["large_previews"] += 1
        view = _preview(row)
        raw_text = row.get("text", "")
        handle = detail("message-detail.txt", raw_text.encode("utf-8"), row.get("id")) if isinstance(raw_text, str) else None
        view["projection"] = {"truncated": True, "detail_resource_id": handle}
        if handle:
            for field in ("resource_ids", "attachments"):
                view[field] = list(dict.fromkeys(view.get(field, []) + [handle]))
        messages.append(view)
    result.update(messages=messages, tool_calls=tools, artifacts=artifacts)

    # A long but otherwise ordinary transcript also needs a bounded window.
    # Drop oldest entries only in the VIEW, preserving real IDs/order in retained
    # items and reporting omissions. The authoritative history stays complete.
    if len(_bytes(result)) > limit:
        for key in ("models", "context", "settings", "goal", "activity", "error", "status"):
            if key in result:
                result[key] = _preview(result[key])
        while len(_bytes(result)) > limit:
            choices = [key for key in ("messages", "tool_calls", "threads") if len(result.get(key, [])) > 1]
            if not choices:
                break
            key = max(choices, key=lambda name: len(_bytes(result[name])))
            values = result[key]
            drop = max(1, len(values) // 4)
            result[key] = values[drop:] if key != "threads" else values[:-drop]
            stats["omitted_" + key] += drop
            stats["truncated"] = True
        # Resource catalog retains all IDs referenced by the visible window.
        if len(_bytes(result)) > limit:
            needed = set()
            for row in result.get("messages", []) + result.get("tool_calls", []) + result.get("attachments", []):
                if isinstance(row, dict):
                    needed.update(x for x in row.get("resource_ids", []) if isinstance(x, str))
                    if isinstance(row.get("id"), str):
                        needed.add(row["id"])
            result["artifacts"] = [entry for entry in artifacts if entry.get("id") in needed]
            stats["truncated"] = True
    result["state_projection"] = stats
    if len(_bytes(result)) > limit:
        # Last-resort metadata-only view: retain control state and an explicit
        # warning, rather than allowing a snapshot size to kill the UI timer.
        for key in tuple(result):
            if key not in ("messages", "tool_calls", "artifacts", "attachments", "threads"):
                result[key] = _preview(result[key])
        stats["omitted_messages"] += len(result.get("messages", []))
        stats["omitted_tool_calls"] += len(result.get("tool_calls", []))
        result.update(messages=[], tool_calls=[], artifacts=[], attachments=[], threads=result.get("threads", [])[:20])
        stats["truncated"] = True
        stats["warnings"].append("Large transcript view reduced to metadata; chat history and connection remain available.")
        result["state_projection"] = stats
    # Keep a final small reserve for projection metadata without enlarging 4 MiB.
    if len(_bytes(result)) > limit:
        result = {key: _preview(state.get(key)) for key in ("ready", "busy", "status", "error", "thread_id", "active_thread_id", "history_error", "permission_mode")}
        result.update(messages=[], tool_calls=[], artifacts=[], attachments=[], threads=[], state_projection=stats)
    return result
