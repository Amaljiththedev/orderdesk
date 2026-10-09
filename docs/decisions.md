# Decisions

Dated notes: what was chosen, what was ruled out, and why. Newest first.

## 2026-10-09 — Resolve agent stays a suggestion

**Decision:** Resolve agent: v1 85.7% precise (guessed brands and pack sizes despite the prompt). Moved those
rules into code; v1b 93.8%, fixed/broke 1/0. Kept as a suggestion below the auto-approve threshold
(confidence 0.45). Net gain on generated data is small; held-out orders will show if it earns its token cost.
**Why:** Auto-approve target is 99% precision; the agent is below it, and prompt rules alone were not followed.
**Ruled out:** Letting agent picks auto-approve; relying on the prompt for brand and pack rules.
**Revisit when:** resolve_eval on held-out orders shows ~99% precision of picks, or token cost per line drops.

## YYYY-MM-DD — title

**Decision:**
**Why:**
**Ruled out:**
**Revisit when:**
