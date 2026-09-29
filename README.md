# OrderDesk

AI order intake for B2B suppliers: reads messy emailed and PDF orders, matches every line to the catalogue,
prices it, and only asks a person about the lines it is unsure of.

- Architecture: [docs/architecture.md](docs/architecture.md)
- Requirements and phases: [docs/PRD.md](docs/PRD.md)
- Decisions log: [docs/decisions.md](docs/decisions.md)

## Run

```
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

API docs: http://localhost:8001/docs
