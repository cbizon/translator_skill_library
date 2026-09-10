# Translator Skill Library

Reusable agent skills for working with the Biomedical Data Translator.

## Included Skills

| Skill | Purpose |
| --- | --- |
| `translator-issue-triage` | Investigate `NCATSTranslator/Feedback` issues using live GitHub, ARS, TRAPI, and ARA evidence. |
| `translator-normalization-triage` | Trace odd identifier groupings, names, and semantic drift through Babel, NodeNorm, Translator answers, and UI presentation. |
| `translator-one-hop-questions` | Build, validate, run, and inspect one-hop TRAPI queries through Translator ARS. |
| `translator-set-input-queries` | Build, validate, run, and inspect set-input TRAPI queries against Answer Coalesce. |

Each directory under `skills/` is a self-contained
[Agent Skill](https://agentskills.io) with a required `SKILL.md` and any
supporting scripts or references.

## Requirements

- Git
- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for the isolated helper-script commands
- Network access to the Translator services used by a selected skill
- Authenticated [GitHub CLI](https://cli.github.com/) access for
  `translator-issue-triage`

The helper scripts use only the Python standard library. `jq` is useful for
manual inspection of collected TRAPI payloads but is not required by the
scripts.

## Clone

Keep the checkout in a stable location if you install with symbolic links:

```bash
git clone https://github.com/cbizon/translator_skill_library.git \
  "$HOME/src/translator_skill_library"

cd "$HOME/src/translator_skill_library"
```

## Install In Codex

Codex discovers personal skills under `$HOME/.agents/skills`. Link all four
skills into that directory:

```bash
mkdir -p "$HOME/.agents/skills"

for skill in \
  translator-issue-triage \
  translator-normalization-triage \
  translator-one-hop-questions \
  translator-set-input-queries
do
  ln -s "$PWD/skills/$skill" "$HOME/.agents/skills/$skill"
done
```

Codex normally detects skill changes automatically. Restart Codex if newly
installed skills do not appear. Use `/skills` or mention a skill explicitly,
for example:

```text
$translator-one-hop-questions
```

For a repository-scoped installation, place or link the skill directories
under `<repository>/.agents/skills/`.

See the official
[Codex skills documentation](https://developers.openai.com/codex/skills/).

## Install In Claude Code

Claude Code discovers personal skills under `$HOME/.claude/skills`. Link all
four skills into that directory:

```bash
mkdir -p "$HOME/.claude/skills"

for skill in \
  translator-issue-triage \
  translator-normalization-triage \
  translator-one-hop-questions \
  translator-set-input-queries
do
  ln -s "$PWD/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

Invoke a skill explicitly with its slash command, for example:

```text
/translator-one-hop-questions
```

For a repository-scoped installation, place or link the skill directories
under `<repository>/.claude/skills/`.

See the official
[Claude Code skills documentation](https://code.claude.com/docs/en/skills).

## Install In Both

From the repository root:

```bash
for target in "$HOME/.agents/skills" "$HOME/.claude/skills"
do
  mkdir -p "$target"
  for skill in \
    translator-issue-triage \
    translator-normalization-triage \
    translator-one-hop-questions \
    translator-set-input-queries
  do
    ln -s "$PWD/skills/$skill" "$target/$skill"
  done
done
```

The commands intentionally fail if a destination already exists rather than
silently replacing an installed skill. Remove or relocate the existing
destination only after checking whether it contains local changes.

## Update

When installed with symbolic links, updating the checkout updates both clients:

```bash
cd "$HOME/src/translator_skill_library"
git pull --ff-only
```

## Behavior And Permissions

- The query skills make live network requests and write result JSON to paths
  selected in their commands.
- `translator-normalization-triage` is read-only by default. It uses live
  NodeNorm, Name Resolver, ARS/TRAPI, source-record, and Babel concordance
  evidence as available.
- `translator-issue-triage` can post a GitHub comment and add justified
  assignees when invoked for normal triage. Ask for a `dry-run`, `draft`, or
  `read-only` investigation to prevent GitHub mutations.
- `agents/openai.yaml` supplies optional Codex UI metadata. Claude Code uses
  `SKILL.md`, `scripts/`, and `references/` and does not require that file.
