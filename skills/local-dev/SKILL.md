---
name: local-dev
description: Run the local development environment for the TKD Registration Frontend repo, including Flask dev server and Stripe CLI webhook forwarding.
---

# Local Dev Environment Skill

This skill allows an agent (or developer) to start the local development environment for this repository. It automatically:
- Loads the `.env` file from the repository root.
- Ensures the user is logged into AWS and that `AWS_PROFILE` is set.
- Starts the Flask dev server on port `5001`.
- Starts the Stripe CLI listener forwarding webhooks to localhost:5001.

## Prerequisites
1. **AWS CLI** installed and configured.
2. **Stripe CLI** installed (`stripe` executable in `PATH`).
3. A `.env` file at the repository root.
4. `uv` package manager installed.

## Usage
Run the skill using Python:
```bash
uv run python skills/local-dev/scripts/run_dev.py
```
This script handles process orchestration, logs interleaving, and clean shutdown on termination (Ctrl+C).
