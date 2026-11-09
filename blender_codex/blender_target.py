"""Resolve the actual official socket in THIS Blender; never probe another PID."""
import sys


def target_environment(addons, modules=None):
    modules = sys.modules if modules is None else modules
    candidates = []
    for name, addon in addons.items():
        if name != "blender_mcp_addon" and not name.endswith(".mcp"):
            continue
        module = modules.get(name)
        server = getattr(module, "mcp_to_blender_server", None)
        listener = getattr(getattr(server, "_state", None), "sock", None)
        if listener is not None:
            host, port = listener.getsockname()[:2]
            # A wildcard listener in this process is reached over loopback.
            if host == "0.0.0.0":
                host = "127.0.0.1"
            if host not in ("127.0.0.1", "localhost") or type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError("The official Blender MCP listener must use a local IPv4 address and valid port.")
            candidates.append({"BLENDER_MCP_HOST": host, "BLENDER_MCP_PORT": str(port)})
    if len(candidates) != 1:
        raise ValueError("Start exactly one official Blender Lab MCP server in this Blender instance before connecting. No other Blender listener will be selected automatically.")
    return candidates[0]
