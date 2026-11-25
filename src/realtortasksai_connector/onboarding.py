"""Install the separate agent connection and configure owner-controlled purchasing."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time
import tomllib
import httpx

from .client import Connector, LIVE, atomic, private_json
from .server import create_server
from . import __version__ as VERSION

PRODUCTS = ("realtor", "farmer", "teacher")
CLIENTS = ("codex", "claude-desktop", "cursor", "manual")


def state_directory(value=None):
    if value:
        return Path(value).expanduser().absolute()
    legacy = Path.home() / ".realtortasksai-connector"
    if (legacy / "purchases.sqlite3").is_file():
        return legacy
    return Path.home() / ".tasksai-agent-skills"


def write_private(path, content):
    """Replace one owner file atomically, without leaving a readable temporary copy."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".tasksai-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configuration_path(client):
    if client == "codex":
        return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    if client == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Claude/claude_desktop_config.json"
    raise ValueError("Choose Codex, Cursor or a manual configuration on this operating system")


def connections(product, directory):
    selected = PRODUCTS if product == "all" else (product,)
    return {
        f"tasksai-{name}-pay-per-use": {
            "command": sys.executable,
            "args": ["-m", "realtortasksai_connector", "serve", "--product", name,
                     "--state-dir", str(directory), "--policy-file", str(directory / "policy.json")],
        }
        for name in selected
    }


def command_text(arguments):
    if os.name == "nt":
        return "& " + " ".join("'" + value.replace("'", "''") + "'" for value in arguments)
    return shlex.join(arguments)


def setup(args):
    directory = state_directory(args.state_dir)
    # Construct the existing connector before touching the host configuration.
    Connector(directory)
    client = args.client
    if client is None and sys.stdin.isatty():
        print("Choose your agent application\n1. Codex\n2. Claude Desktop\n3. Cursor\n4. Save a configuration file")
        choice = input("Application [1-4]: ").strip()
        if choice not in ("1", "2", "3", "4"):
            raise ValueError("Choose one of the four applications")
        client = CLIENTS[int(choice) - 1]
    client = client or "manual"
    path = Path(args.config_file).expanduser().absolute() if args.config_file else (
        directory / "agent-connections.json" if client == "manual" else configuration_path(client)
    )
    path = path.resolve()
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    additions = connections(args.product, directory)
    if client == "codex":
        parsed = tomllib.loads(original)
        existing = parsed.get("mcp_servers", {})
        blocks = []
        for name, value in additions.items():
            if name in existing:
                if any(existing[name].get(k) != v for k, v in value.items()):
                    raise ValueError(f"{name} already has a different connection. Review that connection before replacing it")
                continue
            blocks.append(f"[mcp_servers.{name}]\ncommand = {json.dumps(value['command'])}\nargs = {json.dumps(value['args'])}\n")
        content = original.rstrip() + "\n\n" + "\n".join(blocks) if blocks else original
        tomllib.loads(content)
    else:
        parsed = json.loads(original) if original else {}
        if not isinstance(parsed, dict) or not isinstance(parsed.get("mcpServers", {}), dict):
            raise ValueError("The agent configuration must contain a JSON object with mcpServers")
        existing = parsed.setdefault("mcpServers", {})
        for name, value in additions.items():
            if name in existing and any(existing[name].get(k) != v for k, v in value.items()):
                raise ValueError(f"{name} already has a different connection. Review that connection before replacing it")
            existing.setdefault(name, value)
        content = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    if content != original:
        if original:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            write_private(path.with_name(path.name + ".tasksai-backup-" + stamp), original)
        write_private(path, content)
    print(f"Added {len(additions)} TasksAI agent connections to {path}")
    print("Free search and price quotes are ready. Restart your agent application to load its connections.")
    base = [sys.executable, "-m", "realtortasksai_connector"]
    print("Check this installation")
    print(command_text(base + ["doctor", "--product", args.product, "--state-dir", str(directory)]))
    print("The wallet owner can configure purchasing with an explicit budget")
    print(command_text(base + ["authorize", "--state-dir", str(directory)]))


def authorize(args):
    directory = state_directory(args.state_dir)
    connector = Connector(directory)
    wallet_file = args.wallet_file
    total_limit = args.max_total_usdc
    if sys.stdin.isatty():
        wallet_file = wallet_file or input("Full path of your private buyer-wallet JSON file: ").strip()
        total_limit = total_limit or input("Maximum total USDC budget for this ledger: ").strip()
    if not wallet_file or not total_limit:
        raise ValueError("The wallet owner must supply --wallet-file and --max-total-usdc")
    wallet = Path(wallet_file).expanduser().absolute()
    from eth_account import Account
    address = Account.from_key(private_json(wallet)["private_key"]).address
    per_purchase = atomic(args.max_per_purchase_usdc)
    total = atomic(total_limit)
    if per_purchase > total or args.expires_hours <= 0:
        raise ValueError("Choose a positive expiry and a total budget at least as large as the per-use limit")
    reserved = int(Decimal(connector.status()["reserved_usdc"]) * 1000000)
    if total < reserved:
        raise ValueError("The total budget is smaller than the payments already reserved in this ledger")
    policy = {"enabled": True, "origin": LIVE, "wallet_file": str(wallet),
              "max_per_purchase_usdc": str(Decimal(per_purchase).scaleb(-6)),
              "max_total_usdc": str(Decimal(total).scaleb(-6)),
              "expires_at": int(time.time() + args.expires_hours * 3600)}
    if args.skill:
        policy["allowed_skill_ids"] = args.skill
    path = directory / "policy.json"
    write_private(path, json.dumps(policy, indent=2) + "\n")
    print(f"Purchases enabled for wallet {address}")
    print(f"Per-use limit {policy['max_per_purchase_usdc']} USDC. Total ledger budget {policy['max_total_usdc']} USDC.")
    print("The budget includes all payments already reserved in this purchase ledger.")


def doctor(args):
    directory = state_directory(args.state_dir)
    policy = directory / "policy.json"
    selected = PRODUCTS if args.product == "all" else (args.product,)
    reports = []
    for product in selected:
        connector = Connector(directory, str(policy) if policy.is_file() else None, product=product)
        response = connector.client.get(LIVE + "/v1/agent/catalog", params={"product_id": product, "limit": 1})
        response.raise_for_status()
        catalog = response.json()
        skill = catalog["skills"][0]["skill_id"]
        quote = connector.quote(skill)
        reports.append({"product": product, "available_skills": catalog["total"],
                        "quoted_usdc": quote["offer"]["price"]["amount"], "payment_made": False})
        connector.client.close()
    result = {"connector_version": VERSION, "checks": reports, "payment_made": False}
    if args.json:
        print(json.dumps(result))
    else:
        for report in reports:
            print(f"{report['product']}: {report['available_skills']} skills available; live quote {report['quoted_usdc']} USDC per use")
        print("Connection checks passed. No payment was made.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="action", required=True)
    install = commands.add_parser("setup", help="Add separate pay-per-use connections to an agent application")
    install.add_argument("--client", choices=CLIENTS)
    install.add_argument("--product", choices=("all",) + PRODUCTS, default="all")
    install.add_argument("--config-file")
    install.add_argument("--state-dir")
    install.set_defaults(run=setup)
    check = commands.add_parser("doctor", help="Test free catalog access and exact price quotes")
    check.add_argument("--product", choices=("all",) + PRODUCTS, default="all")
    check.add_argument("--state-dir")
    check.add_argument("--json", action="store_true")
    check.set_defaults(run=doctor)
    permission = commands.add_parser("authorize", help="Set the wallet owner's purchasing limits")
    permission.add_argument("--wallet-file")
    permission.add_argument("--max-per-purchase-usdc", default="0.05")
    permission.add_argument("--max-total-usdc")
    permission.add_argument("--expires-hours", type=float, default=24)
    permission.add_argument("--skill", action="append")
    permission.add_argument("--state-dir")
    permission.set_defaults(run=authorize)
    disable = commands.add_parser("disable-purchases", help="Disable new purchases while keeping receipt history")
    disable.add_argument("--state-dir")
    serve = commands.add_parser("serve", help="Start the local MCP connection")
    serve.add_argument("--product", choices=PRODUCTS, default="realtor")
    serve.add_argument("--state-dir")
    serve.add_argument("--policy-file")
    args = parser.parse_args()
    try:
        if args.action == "serve":
            directory = state_directory(args.state_dir)
            policy = args.policy_file or str(directory / "policy.json")
            create_server(Connector(directory, policy, product=args.product)).run(transport="stdio")
        elif args.action == "disable-purchases":
            path = state_directory(args.state_dir) / "policy.json"
            policy = private_json(path)
            policy["enabled"] = False
            write_private(path, json.dumps(policy, indent=2) + "\n")
            print("New purchases disabled. Existing purchase records are retained.")
        else:
            args.run(args)
    except (ValueError, OSError, KeyError, ArithmeticError, httpx.HTTPError) as error:
        parser.exit(1, f"TasksAI setup needs attention. {error}\n")
