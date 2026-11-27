# TasksAI Agent Skills 0.3.2

Corrects the installation, purchasing and development documentation links on
PyPI by pointing them to the public repository. Connector behavior is unchanged
from version 0.3.1.

The free connector is available as a standalone public developer repository,
Python package, and official MCP Registry entry. It connects compatible local
agents to the RealtorTasksAI, FarmerTasksAI and TeacherTasksAI catalogs.

Search, previews and exact price quotes are free. Purchases start disabled. A
wallet owner can supply a Base USDC wallet and choose a shared total spending
budget, per-purchase limit and expiry. The five-cent pilot price buys instructions
for one execution by the buyer's own agent.

This release adds public packaging and documentation to the previously released
0.3.0 connector behavior. Paid skill instructions, merchant credentials, wallets
and customer records are not included. The connector software's MIT license does
not license the paid skill content.

The release process requires successful fresh-installation checks for the exact
published files on Mac, Windows and Linux using Python 3.11 and 3.14. Checks start
all three MCP connections, exercise free discovery and quotes, confirm purchases
are blocked without owner authority, and verify unpaid package requests return
HTTP 402 without instructions. Release checks make no paid purchases.

[Guided installation](https://tasksai-agent-commerce-live-10437713249.us-central1.run.app/connect)
and [three demonstrations](https://tasksai-agent-commerce-live-10437713249.us-central1.run.app/demos)
remain available at the existing public service address.
