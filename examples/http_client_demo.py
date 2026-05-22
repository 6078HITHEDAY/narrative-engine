"""HTTP API 客户端 demo — 演示如何从外部进程调用 narrative-engine 服务。

启动服务（另开一个终端）:
    narrative-engine serve --story stories/seaside_town --port 8000

然后运行:
    python examples/http_client_demo.py [base_url]

base_url 默认 http://localhost:8000。
"""

from __future__ import annotations

import json
import sys

import httpx


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "http://localhost:8000"

    with httpx.Client(base_url=base, timeout=60) as client:
        health = client.get("/health")
        print(f"[GET /health] {health.status_code} {health.json()}")
        print()

        info = client.get("/story")
        print(f"[GET /story] {info.status_code}")
        print(json.dumps(info.json(), ensure_ascii=False, indent=2))
        print()

        payload = {
            "state": {
                "player": {"name": "player", "inventory": ["a key"]},
                "world": {"area": "market", "time": "afternoon"},
            },
            "kind": "description",
            "context": "刚到达市场",
        }
        resp = client.post("/tell", json=payload)
        print(f"[POST /tell] {resp.status_code}")
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
        print()

        print("[POST /tell stream=True] (SSE)")
        stream_payload = {**payload, "stream": True}
        with client.stream("POST", "/tell", json=stream_payload) as stream:
            for line in stream.iter_lines():
                if line:
                    print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
