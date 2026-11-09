"""App-server peer for the direct dynamic-tool wire protocol, without MCP."""
import json
import sys

def emit(value):
    print(json.dumps(value), flush=True)

def notify(method, **params):
    emit({"method": method, "params": {"threadId": "native-thread", **params}})

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        assert request["params"]["capabilities"]["experimentalApi"] is True
        emit({"id": request["id"], "result": {}})
    elif method == "initialized":
        pass
    elif method == "account/read":
        emit({"id": request["id"], "result": {"account": {"type": "chatgpt"}}})
    elif method == "model/list":
        emit({"id": request["id"], "result": {"data": []}})
    elif method == "thread/start":
        specs = request["params"]["dynamicTools"]
        assert len(specs) == 1 and specs[0]["name"] == "image_to_3d"
        assert specs[0]["type"] == "function"
        emit({"id": request["id"], "result": {"thread": {"id": "native-thread"}}})
    elif method == "turn/start":
        emit({"id": request["id"], "result": {"turn": {"id": "native-turn"}}})
        notify("turn/started", turn={"id": "native-turn"})
        notify("item/started", turnId="native-turn", item={"id": "native-call", "type": "dynamicToolCall",
               "tool": "image_to_3d", "status": "inProgress", "arguments": {"task_id": "existing-1"}})
        emit({"id": "native-rpc", "method": "item/tool/call", "params": {"threadId": "native-thread",
              "turnId": "native-turn", "callId": "native-call", "tool": "image_to_3d",
              "arguments": {"task_id": "existing-1"}}})
        notify("item/agentMessage/delta", turnId="native-turn", itemId="msg", delta="Transport stays responsive")
    elif request.get("id") == "native-rpc":
        result = request["result"]
        content = result["contentItems"][0]
        assert content["type"] == "inputText"
        assert json.loads(content["text"])["task_id"] == "existing-1"
        notify("item/completed", turnId="native-turn", item={"id": "native-call", "type": "dynamicToolCall",
               "tool": "image_to_3d", "status": "completed", **result})
        notify("turn/completed", turn={"id": "native-turn", "status": "completed"})
    elif method == "turn/interrupt":
        emit({"id": request["id"], "result": {}})
        notify("turn/completed", turn={"id": "native-turn", "status": "interrupted"})
    else:
        raise AssertionError(request)
