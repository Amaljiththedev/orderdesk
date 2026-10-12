# OrderDesk

AI order intake for B2B suppliers: reads messy emailed and PDF orders, matches every line to the catalogue,
prices it, and only asks a person about the lines it is unsure of.

- Architecture: [docs/architecture.md](docs/architecture.md)
- Requirements and phases: [docs/PRD.md](docs/PRD.md)
- Decisions log: [docs/decisions.md](docs/decisions.md)

## Results (synthetic data)

All numbers come from generated orders; the data is synthetic.

- **Prompt injection:** 0 of 20 injected orders changed a price, product or quantity without a human check.
  The extraction model obeyed 2 of them (v1, before the code check); a rule-based detector now holds those
  orders for review, with 0 false positives on 300 normal orders. (`evals/injection_eval.py`, injection set v1)

## Run

```
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

API docs: http://localhost:8001/docs
