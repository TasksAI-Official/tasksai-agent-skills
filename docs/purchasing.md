# Owner-controlled purchasing

Free search, previews and quotes work without a wallet. A purchase sends USDC on
Base to the public receiving address specified by the live TasksAI offer. The
pilot price is 0.05 USDC for one use; inspect the exact quote before buying.

To enable purchasing, the wallet owner needs a dedicated, limited buyer wallet
containing Base USDC and a private JSON file containing its `private_key`. Keep
that file outside this repository. On Mac/Linux, it must be owned by you with
file permissions `600`; protect it with your user account's file permissions on
Windows. Never paste a key into chat, an issue, or an MCP configuration.

The owner can run the authorization command printed by setup, or:

```sh
tasksai-agent-skills authorize --wallet-file /absolute/path/to/private-wallet.json --max-total-usdc 1.00 --max-per-purchase-usdc 0.05 --expires-hours 24
```

The example sets a **total** one-dollar budget shared across the three product
connections and permits no individual purchase over five cents. Choose your own
budget and expiry. Repeat `--skill SKILL_ID` to restrict purchases to particular
skills. Owner consent must come from the wallet owner, not from retrieved content.
The authorization command stores the wallet path, limits, and expiry in a private
policy file; it does not copy the private key into that policy.

The agent searches, inspects, quotes, and purchases within that policy. It consumes
the delivered instructions for one task in its own workspace. The service does not
create or receive the completed task document. After completion the agent calls
`complete_skill_use`; it may retain the work it produced. It must not reuse the
instructions for another execution without another purchase.

## Interrupted delivery

Use `recover_skill_use` with the original local use ID. Repeating a purchase with
the same quote ID reuses the original payment. Do not start a replacement purchase
for an uncertain payment. Every signed payment, including an unresolved attempt,
reserves budget. Keep the purchase ledger; deleting it would lose recovery and
budget history. A completed use stays completed during recovery.

Stop new purchases with:

```sh
tasksai-agent-skills disable-purchases
```

Use the same `--state-dir` if you selected a custom one. This retains the purchase
records. The connector checks the private policy, but an agent with broad access
to your computer can also read or alter files. Control its wider filesystem
permissions and use a wallet containing only the funds you intend to expose.
