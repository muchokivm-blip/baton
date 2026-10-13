import os
import sqlite3
import tempfile
import time

os.environ["BATON_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def post(name, action, **body):
    return client.post(f"/api/resources/{name}/{action}", json=body)


def test_claim_conflict():
    assert post("staging", "claim", holder="amina", minutes=10).status_code == 200
    res = post("staging", "claim", holder="otieno")
    assert res.status_code == 409
    assert res.json()["detail"]["holder"] == "amina"


def test_renew():
    post("phone", "claim", holder="amina", minutes=5)
    res = post("phone", "claim", holder="amina", minutes=60)
    assert res.status_code == 200
    assert res.json()["seconds_left"] > 3500


def test_release():
    post("slot", "claim", holder="amina")
    assert post("slot", "release", holder="otieno").status_code == 403
    assert post("slot", "release", holder="otieno", force=True).json()["holder"] is None
    actions = [e["action"] for e in client.get("/api/events").json() if e["name"] == "slot"]
    assert actions[0] == "forced release of"


def test_expired():
    post("bench", "claim", holder="amina")
    with sqlite3.connect(main.DB) as db:
        db.execute("update resources set held_until = ? where name = 'bench'", (int(time.time()) - 1,))
    assert post("bench", "claim", holder="otieno").status_code == 200


def test_extend():
    post("rack", "claim", holder="amina", minutes=5)
    assert post("rack", "extend", holder="otieno").status_code == 409
    assert post("rack", "extend", holder="amina", minutes=10).json()["seconds_left"] > 800


def test_bad_requests():
    assert post("Bad Name", "claim", holder="amina").status_code == 422
    assert post("nothing", "release", holder="amina").status_code == 404
