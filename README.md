# TasksAI Agent Skills

Free local MCP connector for **RealtorTasksAI, FarmerTasksAI and TeacherTasksAI**.
Search skill descriptions and inspect exact prices for free. When its owner has
enabled purchasing, an agent can pay the **5-cent pilot price for one use of one
skill**, receive the instructions, and perform the task in the buyer's workspace.

<!-- mcp-name: io.github.TasksAI-Official/tasksai-agent-skills -->

The API delivers **skill instructions**, not a completed document or other work
result. The buyer's own agent creates the work. Another execution requires
another purchase; purchasing instructions does not grant ownership or reusable
access to the skill catalog.

## Install

Requires Python 3.11 or newer and an application supporting local MCP tools.
The [guided website installation](https://tasksai-agent-commerce-live-10437713249.us-central1.run.app/connect)
supports Codex, Claude Desktop, Cursor, and manual configuration. This agent
connection is separate from the human TasksAI subscription installation.

For developers, create a separate environment, then install the published package:

```sh
python3 -m venv .venv
# Mac or Linux:
.venv/bin/python -m pip install tasksai-agent-skills==0.3.1
.venv/bin/tasksai-agent-skills setup --client codex --product all
.venv/bin/tasksai-agent-skills doctor --product all
```

On Windows PowerShell, replace the last three commands with:

```powershell
.venv\Scripts\python.exe -m pip install tasksai-agent-skills==0.3.1
.venv\Scripts\tasksai-agent-skills.exe setup --client codex --product all
.venv\Scripts\tasksai-agent-skills.exe doctor --product all
```

Choose `--client claude-desktop`, `--client cursor`, or `--client manual` for
another application. `--product all` installs three separately named connections
sharing one purchase ledger and spending budget. Existing human connections are
preserved. Restart the application after setup.

If you already use `uv`, you can run one MCP server directly:

```sh
uvx --from tasksai-agent-skills==0.3.1 tasksai-agent-skills serve --product realtor
```

Replace `realtor` with `farmer` or `teacher` to select another catalog. The
registry listing lets the installer choose this product. See
[manual configuration](docs/installation.md) for all three connections.

## First free search

After setup, ask your agent:

> Search RealtorTasksAI for an open-house lead follow-up skill. Show me its scope
> and exact price. Do not purchase anything.

Search and quote tools need no wallet, account, or spending permission. Supply
only a general task description; keep client, student, farm, and transaction
details in your workspace.

## Enable purchases only when you choose

The package includes **no wallet, private key, merchant credentials, funds, or
permission to spend**. A wallet owner must provide a funded **Base-network USDC**
wallet file and set a total budget. Setup prints the authorization command.
See [purchasing and recovery](docs/purchasing.md) before enabling payments.

Each purchase obtains instructions for one execution. The agent should complete
that execution locally and call `complete_skill_use`. Recovery resumes the
original purchase; it does not grant another use. One new execution requires a
new purchase. The exact quote controls the amount paid.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_skills` | Find descriptions for a general task; free |
| `inspect_skill` | Read scope, local requirements, output contract and terms; free |
| `quote_skill` | Obtain an exact, short-lived price quote; free |
| `purchase_skill` | Purchase instructions within the owner's private spending limits |
| `recover_skill_use` | Resume the original purchase after an interrupted response |
| `complete_skill_use` | Mark that execution completed |
| `purchase_status` | Read local purchase states and reserved budget |

## See what the agent creates

[Three recorded demonstrations](https://tasksai-agent-commerce-live-10437713249.us-central1.run.app/demos)
show free discovery, a real five-cent payment, instruction delivery, and the
buyer's agent creating a Word document or Excel workbook. These are fictional
operator-funded demonstrations, not customer testimonials.

## What is public

This repository and the PyPI package contain only the connector, documentation,
configuration examples, and tests. **Paid skill instructions remain behind the
existing x402 purchase wall.** The MIT license covers this connector software;
it does not license the separately purchased instruction content. Once delivered,
plaintext cannot be made impossible to copy; the single-use terms and agent
instructions govern its permitted use.

For development and release checks, see [development](docs/development.md).
Report connector defects through the repository's Issues page. Do not post
wallet files, private keys, payment proofs, paid instructions, or client data.
