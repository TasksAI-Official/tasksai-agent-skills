"""MCP stdio adapter. The buyer owns the wallet and private spending policy."""

import argparse
import os
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from .client import Connector, ConnectorError, LIVE
from . import __version__


def invoke(operation, *arguments):
    try:
        return operation(*arguments)
    except ConnectorError as error:
        raise ToolError(str(error)) from None


def create_server(connector):
    names = {"realtor": "RealtorTasksAI", "farmer": "FarmerTasksAI", "teacher": "TeacherTasksAI", "synthetic": "TasksAI test"}
    server = MCPServer(names[connector.product] + " pay-per-use", version=__version__, instructions=(
        "Search general tasks for free, inspect scope, then obtain a quote. Purchase only within the owner's existing authority. "
        "Purchased content is instructions for one local execution, never a finished work result. "
        "Respect host permissions, use local client documents only, recover the original use after uncertainty, "
        "and call complete_skill_use after completing it. A completed use cannot be reused without another purchase."))
    readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
    payment = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=readonly)
    def search_skills(task_summary: str, limit: int = 5) -> dict:
        """Find skill descriptions for free. Supply a general task, without client facts or identifiers."""
        return invoke(connector.search, task_summary, limit)

    @server.tool(annotations=readonly)
    def inspect_skill(skill_id: str) -> dict:
        """Read free scope, local input requirements, output contract and license before selecting a skill."""
        return invoke(connector.inspect, skill_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def quote_skill(skill_id: str) -> dict:
        """Get a free exact price quote. Does not sign, pay, or grant permission to spend."""
        return invoke(connector.quote, skill_id)

    @server.tool(annotations=payment)
    def purchase_skill(quote_id: str) -> dict:
        """Pay once for the quoted skill under the owner's private spending limits. Returns instructions for one local execution. Repeating this quote retries the same purchase."""
        return invoke(connector.purchase, quote_id)

    @server.tool(annotations=payment)
    def recover_skill_use(local_use_id: str) -> dict:
        """Recover or resume the original execution with its original proof. Never signs a new payment or resets a completed use."""
        return invoke(connector.recover, local_use_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def complete_skill_use(local_use_id: str) -> dict:
        """After completing the local task, mark this purchased execution used. Do not provide client facts or work results."""
        return invoke(connector.complete, local_use_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def purchase_status() -> dict:
        """Read local purchase IDs, pending payments, used states and total budget reservations. No wallet keys or proofs are returned."""
        return invoke(connector.status)

    return server


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy-file", default=os.environ.get("REALTORTASKSAI_POLICY_FILE"))
    p.add_argument("--state-dir", default=os.environ.get("REALTORTASKSAI_STATE_DIR"))
    p.add_argument("--origin", default=LIVE)
    p.add_argument("--product", choices=("realtor", "farmer", "teacher", "synthetic"))
    args = p.parse_args()
    create_server(Connector(args.state_dir, args.policy_file, args.origin, product=args.product)).run(transport="stdio")


if __name__ == "__main__":
    main()
