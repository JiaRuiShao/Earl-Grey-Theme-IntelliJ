"""Minimal LSP client: runs Eclipse JDT LS headless and dumps semantic tokens + diagnostics."""
import json
import os
import subprocess
import sys
import threading
import time
import glob
import queue

JDTLS = sys.argv[1]
PROJECT = sys.argv[2]
SOURCE = sys.argv[3]
OUT = sys.argv[4]

launcher = glob.glob(os.path.join(JDTLS, "plugins", "org.eclipse.equinox.launcher_*.jar"))[0]
data_dir = os.path.join(os.path.dirname(OUT), "jdtls-data")
cmd = [
    "java",
    "-Declipse.application=org.eclipse.jdt.ls.core.id1",
    "-Dosgi.bundles.defaultStartLevel=4",
    "-Declipse.product=org.eclipse.jdt.ls.core.product",
    "-Dlog.level=ALL",
    "-Xmx1G",
    "--add-modules=ALL-SYSTEM",
    "--add-opens", "java.base/java.util=ALL-UNNAMED",
    "--add-opens", "java.base/java.lang=ALL-UNNAMED",
    "-jar", launcher,
    "-configuration", os.path.join(JDTLS, "config_linux"),
    "-data", data_dir,
]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(OUT + ".stderr", "w"))

inbox = queue.Queue()


def reader():
    f = proc.stdout
    while True:
        headers = {}
        while True:
            line = f.readline()
            if not line:
                return
            line = line.decode("utf-8", "replace").strip()
            if not line:
                if headers:
                    break
                continue
            if ":" not in line or not line.lower().startswith("content-"):
                sys.stderr.write("[stdout noise] " + line + "\n")
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
        body = f.read(int(headers["content-length"]))
        inbox.put(json.loads(body))


threading.Thread(target=reader, daemon=True).start()
next_id = [0]


def send(msg):
    data = json.dumps(msg).encode("utf-8")
    proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
    proc.stdin.flush()


def request(method, params, timeout=300):
    next_id[0] += 1
    rid = next_id[0]
    send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    return wait_for(lambda m: m.get("id") == rid and "method" not in m, timeout)


def notify(method, params):
    send({"jsonrpc": "2.0", "method": method, "params": params})


diagnostics = {}
statuses = []


def handle(m):
    # answer server->client requests so the server never blocks
    if "method" in m and "id" in m:
        result = None
        if m["method"] == "workspace/configuration":
            result = [None for _ in m["params"]["items"]]
        send({"jsonrpc": "2.0", "id": m["id"], "result": result})
    elif m.get("method") == "textDocument/publishDiagnostics":
        diagnostics[m["params"]["uri"]] = m["params"]["diagnostics"]
    elif m.get("method") == "language/status":
        statuses.append(m["params"])


def wait_for(pred, timeout):
    end = time.time() + timeout
    sys.stderr.write("waiting...\n")
    while time.time() < end:
        try:
            m = inbox.get(timeout=1)
        except queue.Empty:
            continue
        handle(m)
        if pred(m):
            return m
    raise TimeoutError("timed out")


root_uri = "file://" + os.path.abspath(PROJECT)
init = request("initialize", {
    "processId": os.getpid(),
    "rootUri": root_uri,
    "workspaceFolders": [{"uri": root_uri, "name": "sample"}],
    "capabilities": {
        "workspace": {"configuration": True, "workspaceFolders": True},
        "textDocument": {
            "publishDiagnostics": {"tagSupport": {"valueSet": [1, 2]}},
            "semanticTokens": {
                "requests": {"full": True, "range": True},
                "tokenTypes": [], "tokenModifiers": [], "formats": ["relative"],
                "multilineTokenSupport": False, "overlappingTokenSupport": False,
            },
        },
    },
    "initializationOptions": {
        "settings": {"java": {"autobuild": {"enabled": True}}},
        "extendedClientCapabilities": {"classFileContentsSupport": True},
    },
}, timeout=300)
legend = init["result"]["capabilities"]["semanticTokensProvider"]["legend"]
notify("initialized", {})

# wait until the project import finishes
try:
    wait_for(lambda m: m.get("method") == "language/status" and m["params"].get("type") == "ServiceReady", 600)
except TimeoutError:
    pass

uri = "file://" + os.path.abspath(SOURCE)
text = open(SOURCE, encoding="utf-8").read()
notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "java", "version": 1, "text": text}})

# give the reconciler time to publish diagnostics
deadline = time.time() + 120
while time.time() < deadline and uri not in diagnostics:
    try:
        handle(inbox.get(timeout=1))
    except queue.Empty:
        pass
time.sleep(5)
while not inbox.empty():
    handle(inbox.get())

tokens = request("textDocument/semanticTokens/full", {"textDocument": {"uri": uri}})["result"]
json.dump({"legend": legend, "data": tokens["data"], "diagnostics": diagnostics.get(uri, []), "statuses": statuses[-5:]},
          open(OUT, "w"), indent=1)
print("tokens:", len(tokens["data"]) // 5, "diagnostics:", len(diagnostics.get(uri, [])))
try:
    request("shutdown", None, timeout=30)
    notify("exit", None)
except Exception:
    pass
proc.kill()
