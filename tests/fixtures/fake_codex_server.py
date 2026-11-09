"""Deterministic JSONL app-server peer. No credentials, network, or Blender."""
import json
import os
import sys
import time

mode = sys.argv[1]
thread_id = "thread-test"
turn_number = 0
turn_id = None
initialized = False


def emit(message):
    print(json.dumps(message), flush=True)


def response(request, result):
    emit({"id": request["id"], "result": result})


def notify(method, **params):
    emit({"method": method, "params": dict(threadId=thread_id, **params)})


def complete():
    notify("turn/completed", turn={"id": turn_id, "status": "completed", "error": None})


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        if mode == "bad-response":
            emit({"id": request["id"], "result": {}, "error": {"code": -1}})
            continue
        if mode == "unknown-response":
            emit({"id": 9999, "result": {}})
            continue
        if mode == "malformed":
            print("not-json", flush=True)
            continue
        if mode == "invalid-shape":
            emit([])
            continue
        if mode == "timeout":
            continue
        if mode == "eof":
            print("fixture failed intentionally", file=sys.stderr, flush=True)
            break
        if mode == "flood-stderr":
            sys.stderr.write("diagnostic " * 100000)
            sys.stderr.flush()
        response(request, {})
    elif method == "initialized":
        initialized = True
    elif method == "account/read":
        assert initialized
        assert request["params"] == {"refreshToken": False}
        response(request, {"account": None if mode == "logged-out" else {"type": "chatgpt"},
                           "requiresOpenaiAuth": True})
    elif method == "thread/start":
        params = request["params"]
        assert params["approvalPolicy"] == "never"
        assert params["sandbox"] == "danger-full-access"
        assert "approvalsReviewer" not in params
        assert "LIVE scene" in params["developerInstructions"]
        assert "ambiguous" in params["developerInstructions"]
        # Notification races the response, as allowed by the real transport.
        notify("thread/started", thread={"id": "wrong-notification-thread"})
        response(request, {"thread": {"id": thread_id}})
    elif method == "model/list":
        response(request, {"data": [{"id": "fake-model", "model": "fake-provider-model", "displayName": "Fake model",
                           "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [
                               {"reasoningEffort": "medium", "description": "Medium"}, {"reasoningEffort": "high", "description": "High"}],
                           "isDefault": True, "inputModalities": ["text", "image"]},
                           {"id": "fake-text-model", "model": "provider-text-model", "displayName": "Text model",
                            "defaultReasoningEffort": "low", "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
                            "inputModalities": ["text"]}], "nextCursor": None})
    elif method == "thread/resume":
        assert request["params"]["threadId"] == thread_id
        assert request["params"]["excludeTurns"] is True
        assert request["params"]["approvalPolicy"] == "never"
        assert request["params"]["sandbox"] == "danger-full-access"
        if mode == "history-fresh-prompt":
            assert "CURRENT_PROMPT_FROM_DISK" in request["params"]["developerInstructions"]
        response(request, {"thread": {"id": thread_id, "turns": []}})
    elif method == "thread/turns/list":
        assert request["params"]["threadId"] == thread_id
        assert request["params"]["itemsView"] == "full"
        assert request["params"]["sortDirection"] == "asc"
        page = request["params"].get("cursor")
        if not page:
            response(request, {"data": [{"id": "old-turn-1", "status": "inProgress" if mode == "history-active" else "completed", "itemsView": "full", "items": [
                {"id": "user-old", "type": "userMessage", "content": [{"type": "text", "text": "Old question"}]},
                {"id": "agent-old", "type": "agentMessage", "text": "Old answer"}]}], "nextCursor": "page-2"})
        else:
            assert page == "page-2"
            response(request, {"data": [{"id": "old-turn-2", "status": "completed", "itemsView": "full", "items": [
                {"id": "tool-old", "type": "mcpToolCall", "tool": "execute_blender_code", "arguments": {"code": "result = {}"}, "status": "completed", "result": {"content": [{"type": "text", "text": "actual persisted result"}]}, "error": None}]}], "nextCursor": None})
    elif method == "thread/name/set":
        assert request["params"]["threadId"] == thread_id
        assert request["params"]["name"] == "Renamed chat"
        response(request, {})
    elif method == "turn/start":
        assert request["params"]["threadId"] == thread_id
        inputs = request["params"]["input"]
        assert len(inputs) == (5 if mode == "images" else 3 if mode == "text-attachment" else 2)
        if mode == "images":
            assert [item["type"] for item in inputs] == ["text", "text", "localImage", "localImage", "localImage"]
            assert all(os.path.isabs(item["path"]) and os.path.isfile(item["path"]) for item in inputs[2:])
        turn_number += 1
        turn_id = "turn-" + str(turn_number)
        notify("turn/started", turn={"id": turn_id})
        if mode == "rpc-error":
            emit({"id": request["id"], "error": {"code": -1, "message": "fixture denied"}})
            continue
        if mode == "interrupt-race":
            time.sleep(0.15)
        if mode != "early-completion":
            response(request, {"turn": {"id": turn_id}})
        if mode in ("configuration", "text-attachment"):
            notify("item/completed", turnId=turn_id,
                   item={"type": "agentMessage", "id": "params-" + turn_id, "text": json.dumps(request["params"])})
            complete()
            continue
        if mode == "rich":
            for item_id, tool in (("tool-1", "get_screenshot_of_area_as_image"), ("tool-2", "execute_blender_code")):
                item = {"id": item_id, "type": "mcpToolCall", "server": "blender", "tool": tool,
                        "arguments": {"area_ui_type": "VIEW_3D"} if item_id == "tool-1" else {"code": "import bpy\\nresult = {}"}, "status": "inProgress"}
                notify("item/started", turnId=turn_id, item=item)
                notify("item/mcpToolCall/progress", turnId=turn_id, itemId=item_id, message="Reading live scene")
                item.update(status="completed", result={"content": ([{"type": "image", "mimeType": "image/png", "data":
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII="}]
                    if item_id == "tool-1" else [{"type": "text", "text": "{\"status\":\"ok\"}"}])}, error=None)
                notify("item/completed", turnId=turn_id, item=item)
            complete()
            continue
        if mode == "questions":
            emit({"id": 701, "method": "item/tool/requestUserInput", "params": {"threadId": thread_id, "turnId": turn_id,
                  "itemId": "question-item", "isBlocking": True,
                  "questions": [{"id": "color", "header": "Color", "question": "Which color?", "options": [{"label": "Blue", "description": "Use blue"}]}]}})
            continue
        if mode == "images":
            notify("item/completed", turnId=turn_id,
                   item={"type": "agentMessage", "id": "image-echo", "text": json.dumps(inputs)})
            complete()
            continue
        # An unrelated thread must never leak text into the UI.
        emit({"method": "item/agentMessage/delta", "params": {
            "threadId": "other", "turnId": turn_id, "itemId": "other", "delta": "BAD"}})
        if mode == "retry":
            notify("error", turnId=turn_id, error={"message": "Retrying"}, willRetry=True)
        elif mode == "resolved":
            emit({"id": "server-approval", "method": "item/commandExecution/requestApproval",
                  "params": {"threadId": thread_id, "turnId": turn_id, "command": "example"}})
            notify("serverRequest/resolved", requestId="server-approval")
            complete()
        elif mode.startswith("elicit-"):
            variant = mode.removeprefix("elicit-")
            schema = {"type": "object", "properties": {}}
            if variant == "fields":
                schema["properties"] = {"nested": {"type": "object", "properties": {}}}
            if variant == "form-values":
                schema.update(properties={"name": {"type": "string", "minLength": 1}, "count": {"type": "integer", "minimum": 1}}, required=["name", "count"])
            params = {"threadId": thread_id, "turnId": turn_id, "serverName": "blender",
                      "message": "Allow this Blender operation?", "mode": "form", "requestedSchema": schema}
            if variant == "url":
                params.update(mode="url", url="https://example.test", elicitationId="id")
                del params["requestedSchema"]
            if variant == "invalid":
                params["requestedSchema"] = {}
            emit({"id": "server-approval", "method": "mcpServer/elicitation/request", "params": params})
        elif mode in ("approval", "permissions", "legacy", "unknown", "approval-stop"):
            method_name = {"approval": "item/commandExecution/requestApproval",
                           "permissions": "item/permissions/requestApproval",
                           "legacy": "execCommandApproval", "unknown": "future/request",
                           "approval-stop": "item/commandExecution/requestApproval"}[mode]
            emit({"id": "server-approval", "method": method_name,
                  "params": {"threadId": thread_id, "turnId": turn_id,
                             "command": "example", "permissions": {"network": {"enabled": True}}}})
        elif mode not in ("interrupt-race", "idle"):
            notify("item/agentMessage/delta", turnId=turn_id, itemId="item-1", delta="Hallo ")
            notify("item/agentMessage/delta", turnId=turn_id, itemId="item-1", delta="Blender 🧊")
            notify("item/completed", turnId=turn_id,
                   item={"type": "agentMessage", "id": "item-1", "text": "Hallo Blender 🧊"})
            notify("item/completed", turnId=turn_id,
                   item={"type": "agentMessage", "id": "item-2", "text": "Unstreamed final"})
            complete()
        if mode == "early-completion":
            time.sleep(0.05)
            response(request, {"turn": {"id": turn_id}})
    elif method == "turn/interrupt":
        assert request["params"] == {"threadId": thread_id, "turnId": turn_id}
        response(request, {})
        complete()
    elif request.get("id") == 701:
        assert request["result"] == {"answers": {"color": {"answers": ["Blue"]}}}
        complete()
    elif request.get("id") == "server-approval":
        if mode.startswith("elicit-"):
            result = request["result"]
            variant = mode.removeprefix("elicit-")
            if variant in ("fields", "url", "invalid"):
                assert result == {"action": "cancel"}, result
            elif variant == "form-values":
                assert result == {"action": "accept", "content": {"name": "Cube", "count": 2}}, result
            elif variant == "accept":
                assert result == {"action": "accept", "content": {}}, result
            else:
                assert result == {"action": "decline"}, result
        elif mode == "unknown":
            assert request["error"]["code"] == -32601
        elif mode == "permissions":
            assert request["result"]["scope"] == "turn"
        elif mode == "legacy":
            assert request["result"]["decision"] in ("approved", {"denied": {"rejection": "User declined"}})
        else:
            assert request["result"]["decision"] in ("accept", "decline")
        if mode != "approval-stop":
            complete()
    else:
        raise AssertionError(request)
