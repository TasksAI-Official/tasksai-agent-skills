# Installation and manual configuration

The guided [agent installation page](https://tasksai-agent-commerce-live-10437713249.us-central1.run.app/connect)
offers the existing standalone installer. PyPI is an additional installation
channel for the same free connection. No human subscription is required for free
agent search. Purchases use the buyer's USDC budget, not human TasksAI credits.

Use Python 3.11 or newer. In a dedicated virtual environment, run:

```sh
python -m pip install tasksai-agent-skills==0.3.2
tasksai-agent-skills setup --client manual --product all
tasksai-agent-skills doctor --product all --json
```

`setup` prints the saved configuration path, a free check command, and a separate
owner authorization command. With `--client codex`, `claude-desktop`, or `cursor`,
it adds named connections to that application's normal configuration. Existing
connections are retained and changed configuration files are backed up privately.
Run setup from the same installed environment when repeating it.

## Manual MCP configuration with uvx

Install `uv` from its official distribution if needed. The following JSON can be
used by clients accepting `mcpServers`; Codex uses its corresponding TOML format.
No private key or policy is embedded in this configuration.

```json
{
  "mcpServers": {
    "tasksai-realtor-pay-per-use": {
      "command": "uvx",
      "args": ["--from", "tasksai-agent-skills==0.3.2", "tasksai-agent-skills", "serve", "--product", "realtor"]
    },
    "tasksai-farmer-pay-per-use": {
      "command": "uvx",
      "args": ["--from", "tasksai-agent-skills==0.3.2", "tasksai-agent-skills", "serve", "--product", "farmer"]
    },
    "tasksai-teacher-pay-per-use": {
      "command": "uvx",
      "args": ["--from", "tasksai-agent-skills==0.3.2", "tasksai-agent-skills", "serve", "--product", "teacher"]
    }
  }
}
```

The default state directory is `~/.tasksai-agent-skills`. Existing legacy purchase
state is retained when detected. Supply an absolute `--state-dir` when you want
to select another private directory. Keep it outside the source repository and
shared or synchronized folders. Each server selects one product; the guided
`--product all` setup adds all three.

Check installation using `tasksai-agent-skills doctor --product all`. It verifies
free search and price quotes and makes no payments. If your application cannot
find `uvx` or Python, use its absolute executable path.
