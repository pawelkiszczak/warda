"""The `systemone` decider against a stand-in `POST /v1/systemone` server (no model, no network)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from warda.bench import brama, run_brama
from warda.schema import ACTIONS

ITEMS = brama.load_items()
CASE = brama.decider_view(ITEMS[0], brama.load_policies(), brama.load_ids())


@pytest.fixture
def server():
    """Answers each question with weight 1, 2, 3, ... in the order its criteria arrive, plus one unknown key."""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append(body)
            answers = {}
            for key, q in body["questions"].items():
                probs = {a: i + 1.0 for i, a in enumerate(q["criteria"])} | {"other": 10.0}
                answers[key] = {"type": "choice", "probabilities": probs}
            data = json.dumps({"answers": answers}).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            data = json.dumps({"data": [{"id": "stand-in"}]}).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def test_asks_both_orders_and_renormalises_over_the_actions(server):
    url, seen = server
    decide, meta = run_brama.systemone_decider(url, None)
    canonical, reversed_ = decide(CASE)
    assert [list(b["questions"]["action"]["criteria"]) for b in seen] == [list(ACTIONS), list(ACTIONS[::-1])]
    assert seen[0]["state"] == brama.render_state(CASE)
    total = sum(range(1, len(ACTIONS) + 1))
    assert canonical == {a: (i + 1) / total for i, a in enumerate(ACTIONS)}
    assert reversed_ == {a: (len(ACTIONS) - i) / total for i, a in enumerate(ACTIONS)}
    assert meta["served"] == {"data": [{"id": "stand-in"}]}
    assert "question_key" not in meta


def test_question_key_is_sent_and_recorded(server):
    url, seen = server
    decide, meta = run_brama.systemone_decider(url, None, key="decision")
    decide(CASE)
    assert {k for b in seen for k in b["questions"]} == {"decision"}
    assert meta["question_key"] == "decision"


def test_request_model_overrides_the_model_field(server):
    url, seen = server
    decide, meta = run_brama.systemone_decider(url, None, request_model="stand-in")
    decide(CASE)
    assert {b["model"] for b in seen} == {"stand-in"}
    assert meta["request_model"] == "stand-in"
