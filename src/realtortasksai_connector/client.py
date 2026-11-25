"""Durable buyer state. The model cannot change the owner's spending policy."""

import base64
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from uuid import uuid4
import httpx

LIVE = "https://tasksai-agent-commerce-live-10437713249.us-central1.run.app"
TEST = "https://tasksai-agent-commerce-10437713249.us-central1.run.app"
RECIPIENT = "0x89caab53754691f245fe20823b5c92dbd450a0ca"
ASSETS = {"eip155:8453": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e"}


class ConnectorError(ValueError):
    """A controlled connector message that is safe to show to its owner and agent."""


def canonical(value):
    def check(v):
        if type(v) is int and abs(v) > 9007199254740991:
            raise ConnectorError("Unsafe canonical integer")
        if v is None or type(v) in (str, int, bool):
            return
        if type(v) is list:
            for x in v:
                check(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for x in v.values():
                check(x)
            return
        raise ConnectorError("Invalid canonical JSON")
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def private_json(path):
    p = Path(path)
    if not p.is_absolute() or p.is_symlink():
        raise ConnectorError("Use an absolute, private owner-controlled file")
    info = p.stat()
    if os.name != "nt" and (stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid()):
        raise ConnectorError("Owner policy and wallet files must be readable only by their owner")
    return json.loads(p.read_text())


def atomic(value):
    d = Decimal(str(value)) * 1000000
    if not d.is_finite() or d <= 0 or d != d.to_integral_value():
        raise ConnectorError("Spending limits must be positive, exact USDC amounts")
    return int(d)


class Connector:
    def __init__(self, state_dir=None, policy_file=None, origin=LIVE, client=None, clock=time.time, *, product=None):
        if origin not in (LIVE, TEST):
            raise ConnectorError("This connector only contacts the published TasksAI services")
        self.origin, self.clock = origin, clock
        self.product = product or ("realtor" if origin == LIVE else "synthetic")
        allowed = {"realtor", "farmer", "teacher"} if origin == LIVE else {"synthetic"}
        if self.product not in allowed:
            raise ConnectorError("Choose a published product for this service")
        self.network = "eip155:8453" if origin == LIVE else "eip155:84532"
        self.policy_file = policy_file
        self.client = client or httpx.Client(timeout=120, follow_redirects=False, trust_env=False)
        directory = Path(state_dir or Path.home() / ".realtortasksai-connector").expanduser().absolute()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or (os.name != "nt" and (directory.stat().st_mode & 0o077)):
            raise ConnectorError("The connector state directory must be private to its owner")
        self.path = directory / "purchases.sqlite3"
        if self.path.is_symlink():
            raise ConnectorError("Refusing a linked state file")
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600) if not self.path.exists() else None
        if fd is not None:
            os.close(fd)
        if os.name != "nt" and self.path.stat().st_mode & 0o077:
            raise ConnectorError("The purchase state file must be private")
        with self.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, at INTEGER NOT NULL, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS uses(id TEXT PRIMARY KEY, quote_id TEXT UNIQUE NOT NULL, origin TEXT NOT NULL,
                    wallet TEXT NOT NULL, amount INTEGER NOT NULL, state TEXT NOT NULL, proof TEXT NOT NULL,
                    quote TEXT NOT NULL, delivery TEXT, created_at INTEGER NOT NULL);''')

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def search(self, task_summary, limit=5):
        if not isinstance(task_summary, str) or not 3 <= len(task_summary) <= 300 or not 1 <= limit <= 20:
            raise ConnectorError("Search with a short general task description")
        if re.search(r"@|\b\d{3}[-. ]\d{3}[-. ]\d{4}\b|\b\d+\s+\w+\s+(street|st|road|rd|avenue|ave)\b", task_summary, re.I):
            raise ConnectorError("Do not send client identifiers, addresses or contact details")
        r = self.client.post(self.origin + "/v1/agent/search", json={"product_id": self.product,
            "task_summary": task_summary, "limit": limit})
        r.raise_for_status()
        return r.json()

    def _skill(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,119}", sid):
            raise ConnectorError("Choose a skill ID from the catalog")
        if self.origin == LIVE and not sid.replace("-", "_").startswith(self.product + "_"):
            raise ConnectorError("Skill belongs to a different product")
        return self.origin + "/v1/agent/skills/" + sid

    def inspect(self, skill_id):
        r = self.client.get(self._skill(skill_id))
        r.raise_for_status()
        return r.json()

    def _quote(self, sid):
        preview = self.inspect(sid)
        url = self._skill(sid) + "/package"
        r = self.client.get(url)
        if r.status_code != 402:
            raise ConnectorError("No active payment quote; no spending attempted")
        q = json.loads(base64.b64decode(r.headers["payment-required"], validate=True))
        if q["x402Version"] != 2 or q["resource"]["url"] != url or len(q["accepts"]) != 1:
            raise ConnectorError("Unsupported payment challenge")
        req = q["accepts"][0]
        extra = req["extra"]
        match = [p for p in preview["packages"] if p["offer"]["offer_id"] == extra.get("offerId")]
        if len(match) != 1:
            raise ConnectorError("Offer changed; request a new free quote")
        offer, manifest = match[0]["offer"], match[0]["preview"]
        expected_extra = {"name": "USD Coin" if self.network == "eip155:8453" else "USDC", "version": "2",
            "offerId": offer["offer_id"], "payloadSha256": offer["payload_sha256"],
            "termsRevision": "single-use-v1", "licensedExecutions": 1}
        if (req["scheme"] != "exact" or req["network"] != self.network
            or req["asset"].lower() != ASSETS[self.network] or offer["network"] != self.network
            or offer["asset"].lower() != ASSETS[self.network]
            or req["payTo"].lower() != offer["pay_to"].lower()
            or (self.origin == LIVE and req["payTo"].lower() != RECIPIENT)
            or req["amount"] != offer["price"]["atomic_amount"]
            or not re.fullmatch(r"[1-9][0-9]{0,15}", req["amount"])
            or offer["price"]["currency"] != "USDC" or offer["price"]["asset_decimals"] != 6
            or atomic(offer["price"]["amount"]) != int(req["amount"])
            or extra != expected_extra or offer["terms_revision"] != "single-use-v1" or offer["withdrawn"]
            or offer["purchase_url"] != url or manifest["execution_mode"] != "buyer_workspace"
            or manifest["product_id"] != self.product
            or manifest["license_revision"] != "single-use-v1" or manifest["license_text"] != offer["terms"]
            or not re.fullmatch(r"[a-f0-9]{64}", offer["payload_sha256"])
            or type(req["maxTimeoutSeconds"]) is not int or not 1 <= req["maxTimeoutSeconds"] <= 300):
            raise ConnectorError("Quote does not match this merchant, package or single-use rail")
        return {"skill_id": sid, "offer": offer, "challenge": q}

    def quote(self, skill_id):
        q = self._quote(skill_id)
        qid = str(uuid4())
        with self.db() as c:
            c.execute("INSERT INTO quotes VALUES(?,?,?)", (qid, int(self.clock()), json.dumps(q)))
        return {"quote_id": qid, "skill_id": skill_id, "offer": q["offer"],
            "expires_in_seconds": 120, "payment_made": False,
            "next_step": "Purchase only if the owner's private spending policy permits this exact quote."}

    def _policy(self):
        if not self.policy_file or not Path(self.policy_file).is_file():
            raise ConnectorError("Discovery-only mode. The owner must configure a private spending policy first.")
        p = private_json(self.policy_file)
        if p.get("enabled") is not True or p.get("origin") != self.origin:
            raise ConnectorError("Owner spending permission is disabled or for another service")
        if type(p.get("expires_at")) is not int or p["expires_at"] <= self.clock():
            raise ConnectorError("Owner spending permission has expired")
        atomic(p["max_per_purchase_usdc"])
        atomic(p["max_total_usdc"])
        return p

    def _reserve(self, quote_id):
        # An existing use can always recover the original payment without new signing authority.
        with self.db() as c:
            existing = c.execute("SELECT * FROM uses WHERE quote_id=?", (quote_id,)).fetchone()
        if existing:
            if existing["origin"] != self.origin:
                raise ConnectorError("Original purchase belongs to another service")
            return dict(existing)
        p = self._policy()
        with self.db() as c:
            row = c.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
        if not row or int(self.clock()) - row["at"] > 120:
            raise ConnectorError("Free quote expired; inspect a fresh quote before purchasing")
        q = json.loads(row["value"])
        if self._quote(q["skill_id"]) != q:
            raise ConnectorError("Offer changed; inspect a fresh free quote before purchasing")
        if p.get("allowed_skill_ids") is not None and q["skill_id"] not in p["allowed_skill_ids"]:
            raise ConnectorError("Skill is outside the owner's spending permission")
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        account = Account.from_key(private_json(p["wallet_file"])["private_key"])
        amount = int(q["offer"]["price"]["atomic_amount"])
        if amount > atomic(p["max_per_purchase_usdc"]):
            raise ConnectorError("Price exceeds the owner's per-purchase limit")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute("SELECT * FROM uses WHERE quote_id=?", (quote_id,)).fetchone()
            if existing:
                return dict(existing)
            # Count every signed proof, including unresolved/error cases. Never silently release a reservation.
            spent = c.execute("SELECT COALESCE(SUM(amount),0) FROM uses WHERE origin=?", (self.origin,)).fetchone()[0]
            if spent + amount > atomic(p["max_total_usdc"]):
                raise ConnectorError("Purchase exceeds the owner's total spending limit")
            req = q["challenge"]["accepts"][0]
            auth = {"from": account.address, "to": req["payTo"], "value": req["amount"],
                "validAfter": "0", "validBefore": str(int(self.clock()) + req["maxTimeoutSeconds"]),
                "nonce": "0x" + secrets.token_hex(32)}
            typed = {"types": {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
                "TransferWithAuthorization": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}]},
                "primaryType": "TransferWithAuthorization", "domain": {"name": req["extra"]["name"], "version": "2",
                    "chainId": int(self.network.split(":")[1]), "verifyingContract": req["asset"]},
                "message": {**auth, "value": amount, "validAfter": 0, "validBefore": int(auth["validBefore"]),
                    "nonce": bytes.fromhex(auth["nonce"][2:])}}
            signature = "0x" + account.sign_message(encode_typed_data(full_message=typed)).signature.hex().removeprefix("0x")
            proof = base64.b64encode(canonical({"x402Version": 2, "accepted": req,
                "resource": q["challenge"]["resource"], "payload": {"signature": signature, "authorization": auth}})).decode()
            uid = str(uuid4())
            c.execute("INSERT INTO uses VALUES(?,?,?,?,?,?,?,?,?,?)", (uid, quote_id, self.origin, account.address,
                amount, "pending", proof, json.dumps(q), None, int(self.clock())))
            return dict(c.execute("SELECT * FROM uses WHERE id=?", (uid,)).fetchone())

    def _validated(self, data, row):
        p, receipt, use = data["package"], data["receipt"], data["usage_authorization"]
        if "receipt" in p:
            raise ConnectorError("Delivery does not match the package contract: receipts belong outside the package")
        q = json.loads(row["quote"])
        offer = q["offer"]
        identity = hashlib.sha256(canonical({k: v for k, v in p.items() if k not in ("payload_sha256", "receipt")})).hexdigest()
        if (identity != offer["payload_sha256"] or p["payload_sha256"] != identity
            or p["skill_id"] != q["skill_id"] or p["product_id"] != self.product
            or p["license_revision"] != "single-use-v1" or p["license_text"] != offer["terms"]
            or p["execution_mode"] != "buyer_workspace" or p["canonicalization"] != "tasksai-json-v1"
            or receipt["offer_id"] != offer["offer_id"] or receipt["payload_sha256"] != identity
            or receipt["atomic_amount"] != str(row["amount"]) or receipt["payer"].lower() != row["wallet"].lower()
            or receipt["currency"] != "USDC" or receipt["asset_decimals"] != 6
            or receipt["network"] != self.network or receipt["asset"].lower() != ASSETS[self.network]
            or use["purchase_id"] != receipt["purchase_id"] or use["skill_id"] != q["skill_id"]
            or use["use_id"] != row["id"] or use["licensed_executions"] != 1 or use["policy_revision"] != "single-use-v1"):
            raise ConnectorError("Delivery does not match the exact purchased package and use")
        return data

    def _view(self, row):
        if row["state"] == "used":
            return {"local_use_id": row["id"], "state": "used", "instructions": "This use is completed. Purchase a new use for another execution."}
        if not row["delivery"]:
            return {"local_use_id": row["id"], "state": "pending", "message": "Retry this original use; never authorize a replacement payment."}
        data = self._validated(json.loads(row["delivery"]), row)
        return {"local_use_id": row["id"], "state": row["state"], "package": data["package"],
            "receipt": data["receipt"], "usage_authorization": data["usage_authorization"],
            "next_step": "Perform only this execution locally. Then call complete_skill_use. Recovery does not grant another use."}

    def _deliver(self, row):
        if row["state"] == "used" or row["delivery"]:
            return self._view(row)
        q = json.loads(row["quote"])
        try:
            r = self.client.get(q["offer"]["purchase_url"], headers={"PAYMENT-SIGNATURE": row["proof"], "X-TasksAI-Use-Id": row["id"]})
        except httpx.HTTPError:
            return self._view(row)
        if r.status_code != 200:
            return {**self._view(row), "http_status": r.status_code,
                "retry_after_seconds": r.headers.get("retry-after"),
                "message": "Original purchase retained. Retry recover_skill_use with the same local use ID. No new proof was signed."}
        data = self._validated(r.json(), row)
        with self.db() as c:
            # A concurrent completion must never be reset by a slower delivery retry.
            c.execute("UPDATE uses SET delivery=COALESCE(delivery,?),state=CASE WHEN state='used' THEN 'used' ELSE 'in_progress' END WHERE id=?",
                (json.dumps(data), row["id"]))
            row = dict(c.execute("SELECT * FROM uses WHERE id=?", (row["id"],)).fetchone())
        return self._view(row)

    def purchase(self, quote_id):
        return self._deliver(self._reserve(quote_id))

    def recover(self, local_use_id):
        with self.db() as c:
            row = c.execute("SELECT * FROM uses WHERE id=? AND origin=?", (local_use_id, self.origin)).fetchone()
        if not row:
            raise ConnectorError("Unknown local use ID")
        return self._deliver(dict(row))

    def complete(self, local_use_id):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM uses WHERE id=? AND origin=?", (local_use_id, self.origin)).fetchone()
            if not row or not row["delivery"]:
                raise ConnectorError("Only a delivered original execution can be marked completed")
            c.execute("UPDATE uses SET state='used' WHERE id=?", (local_use_id,))
        return {"local_use_id": local_use_id, "state": "used", "message": "Retain the work result. Another execution requires another purchase."}

    def status(self):
        with self.db() as c:
            rows = c.execute("SELECT id,quote_id,amount,state,created_at FROM uses WHERE origin=? ORDER BY created_at DESC", (self.origin,)).fetchall()
        try:
            self._policy()
            configured = True
        except (ValueError, OSError, KeyError, ArithmeticError):
            configured = False
        return {"origin": self.origin, "spending_configured": configured,
            "reserved_usdc": str(Decimal(sum(r["amount"] for r in rows)).scaleb(-6)),
            "uses": [dict(r) for r in rows], "note": "All signed payments count toward the budget, including unresolved payments. No task documents are stored or sent."}
