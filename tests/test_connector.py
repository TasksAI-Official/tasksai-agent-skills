from argparse import Namespace
import json
import os
import time
import tomllib

import httpx
import pytest

from realtortasksai_connector.client import Connector, LIVE, private_json
from realtortasksai_connector.onboarding import authorize, setup


@pytest.mark.parametrize("client", ["codex", "claude-desktop", "cursor", "manual"])
def test_setup_preserves_human_configuration_and_does_not_enable_spending(tmp_path, client):
    config = tmp_path / ("config.toml" if client == "codex" else "config.json")
    original = ('model = "existing"\n[mcp_servers.human]\nurl = "https://example.invalid/mcp"\n'
                if client == "codex" else json.dumps({"mcpServers": {"human": {"url": "https://example.invalid/mcp"}},
                                                     "preference": "keep"}))
    config.write_text(original)
    args = Namespace(client=client, product="all", config_file=str(config), state_dir=str(tmp_path / "private"))
    setup(args)
    first = config.read_text()
    values = tomllib.loads(first) if client == "codex" else json.loads(first)
    servers = values["mcp_servers" if client == "codex" else "mcpServers"]
    assert servers["human"] == {"url": "https://example.invalid/mcp"}
    assert len(servers) == 4
    for product in ("realtor", "farmer", "teacher"):
        arguments = servers[f"tasksai-{product}-pay-per-use"]["args"]
        assert arguments[arguments.index("--product") + 1] == product
        assert arguments[arguments.index("--state-dir") + 1] == str(tmp_path / "private")
        assert arguments[arguments.index("--policy-file") + 1] == str(tmp_path / "private/policy.json")
    setup(args)
    assert config.read_text() == first
    assert len(list(tmp_path.glob("config.*.tasksai-backup-*"))) == 1
    assert not (tmp_path / "private/policy.json").exists()


def test_conflicting_connection_is_not_replaced(tmp_path):
    config = tmp_path / "config.json"
    original = json.dumps({"mcpServers": {"tasksai-realtor-pay-per-use": {"command": "existing"}}})
    config.write_text(original)
    with pytest.raises(ValueError, match="different connection"):
        setup(Namespace(client="manual", product="realtor", config_file=str(config), state_dir=str(tmp_path / "state")))
    assert config.read_text() == original


def test_default_mode_refuses_purchase_before_any_network_request(tmp_path):
    requests = []
    def transport(request):
        requests.append(request)
        raise AssertionError("A purchase without owner authority must not contact the network")
    connector = Connector(tmp_path / "state", client=httpx.Client(transport=httpx.MockTransport(transport)))
    with pytest.raises(ValueError, match="Discovery-only"):
        connector.purchase("not-authorized")
    assert requests == []
    assert connector.status()["uses"] == []
    assert connector.status()["reserved_usdc"] == "0.000000"


def test_search_transmits_only_general_task_and_selected_product(tmp_path):
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"matches": []})
    connector = Connector(tmp_path / "state", product="teacher", client=httpx.Client(transport=httpx.MockTransport(transport)))
    assert connector.search("plan equivalent fractions lesson") == {"matches": []}
    assert requests[0].url == LIVE + "/v1/agent/search"
    assert json.loads(requests[0].content) == {"product_id": "teacher", "task_summary": "plan equivalent fractions lesson", "limit": 5}
    with pytest.raises(ValueError, match="client identifiers"):
        connector.search("plan lesson for person@example.invalid")
    assert len(requests) == 1


def test_owner_authorization_keeps_key_out_of_policy_and_does_not_pay(tmp_path):
    from eth_account import Account
    account = Account.create()
    wallet = tmp_path / "private-wallet.json"
    wallet.write_text(json.dumps({"private_key": account.key.hex()}))
    wallet.chmod(0o600)
    directory = tmp_path / "state"
    authorize(Namespace(state_dir=str(directory), wallet_file=str(wallet), max_per_purchase_usdc="0.05",
                        max_total_usdc="0.15", expires_hours=1, skill=["teacher-write-daily-lesson-plans"]))
    policy = (directory / "policy.json").read_text()
    assert account.key.hex() not in policy and "private_key" not in policy
    value = json.loads(policy)
    assert value["max_total_usdc"] == "0.150000"
    assert value["allowed_skill_ids"] == ["teacher-write-daily-lesson-plans"]
    assert value["expires_at"] > time.time()
    assert Connector(directory, str(directory / "policy.json")).status()["uses"] == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode-bit check; Windows uses account ACLs")
def test_world_readable_wallet_is_rejected(tmp_path):
    wallet = tmp_path / "private-wallet.json"
    wallet.write_text("{}")
    wallet.chmod(0o644)
    with pytest.raises(ValueError, match="readable only"):
        private_json(wallet)


def test_registry_metadata_matches_package_and_readme():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    server = json.loads((root / "server.json").read_text())
    assert metadata["version"] == server["version"] == server["packages"][0]["version"]
    assert metadata["name"] == server["packages"][0]["identifier"]
    assert f"mcp-name: {server['name']} -->" in (root / "README.md").read_text()
    assert len(server["description"]) <= 100
    assert server["packages"][0]["packageArguments"][0]["value"] == "serve"
