# Ronin coding-agent skills

This directory contains the skills that let a coding agent work against Ronin's
real CLI and API contracts:

- `ronin-core`: project validation, planning, submission, lifecycle inspection,
  cancellation and evidence collection.
- `ronin-data-engineering`: bounded connector discovery, previews, plans,
  checkpoint health and durable ingestion workflows.
- `ronin-machine-learning`: ML Studio, PipelineIR, artifact identity,
  checkpoints, model promotion and qualification boundaries.

Each skill is an independent bundle with a `SKILL.md`, an OpenAI agent
interface descriptor, references and any helper scripts. The instructions
keep read-only discovery ahead of mutations, require command compatibility
checks, and separate local success from release qualification.

## Discover and validate

From the repository root:

```text
python -m studio_cli.entrypoint skills list
python -m studio_cli.entrypoint skills validate
```

Use `RONIN_AGENT_SKILLS_DIR` or `--root` when the skills live outside the
checkout. Validation only reads metadata and parses helper Python scripts; it
does not invoke the Ronin CLI or execute a skill.

## Package for an agent runtime

```text
python -m studio_cli.entrypoint skills package --output .tmp-agent-skills-dist
```

The generated archives are deterministic and contain only the selected skill's
files. Install the resulting `skill.zip` files in the agent runtime's skill
directory according to that runtime's installation mechanism.

The source skills are intentionally kept in the repository so their contracts
can be reviewed and updated with the Ronin CLI/API in the same change.
