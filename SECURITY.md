# Security Policy

## Supported versions

Only the latest tagged release on `main` is supported. We don't backport fixes.

| Version | Supported |
|---|---|
| latest `main` / latest tag | Yes |
| older tags | No |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Email the maintainer directly with:

- A description of the issue
- Steps to reproduce
- The affected version (commit SHA or tag)
- Your assessment of impact

You should get an acknowledgement within 72 hours. We aim to ship a fix or mitigation within 14 days for high-severity issues.

If we agree the report is valid, we will:

1. Confirm the issue and scope.
2. Prepare a patch on a private branch.
3. Coordinate a release date with you.
4. Credit you in the release notes (unless you prefer to stay anonymous).

## Scope

In scope:

- The ingester service (`ingester/`)
- The database schema and migrations (`db/`)
- The Grafana provisioning and dashboard JSON (`grafana/`)
- The nginx reverse proxy config (`nginx/`)
- The Docker Compose topology and `.env.example`

Out of scope:

- Vulnerabilities in upstream dependencies (Postgres, Grafana, Python libs) — please report those upstream. We will pick up patched versions promptly.
- Issues that require an attacker who already has shell access on the host or admin access to Grafana.
- Anything that depends on the operator running the stack with weak credentials they were warned about in `.env.example`.

## Secrets handling

- `.env` is gitignored. Only `.env.example` is committed, and it contains placeholders.
- Grafana admin password is set from `.env` at boot. Anonymous viewers cannot edit.
- Postgres is not exposed to the internet — only the compose network reaches it.
- nginx is the only public-facing container.

If you find a committed secret in the git history, please report it as a vulnerability so we can rotate and rewrite history.
