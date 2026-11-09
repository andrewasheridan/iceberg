---
name: ste100
description: Write in ASD-STE100 Simplified Technical English (STE). Use when you write or edit prose in this repo - README, CONTRIBUTING, docs and ADRs, case READMEs, docstrings, code comments, user-facing messages (CLI help, errors, logs), issue, commit and pull request bodies.
---

# ASD-STE100 Simplified Technical English

STE is a controlled language for technical text. Its purpose is text that is clear,
has only one possible meaning, and is easy to translate. This file summarizes the STE
writing rules. The authority is the ASD-STE100 specification (asd-ste100.org), which
contains the full rules and the dictionary of approved words.

## Where STE applies

| Applies | Does not apply |
|---|---|
| `README.md`, `CONTRIBUTING.md`, `docs/` (ADRs too) | Code identifiers (names of functions, variables, classes) |
| `cases/*/README.md` | Quoted output, error text from other tools |
| Docstrings and code comments, in `src/` and `tests/` | Conventional Commits header syntax (`feat(cli): ...`) |
| CLI help text, error and log messages | `CHANGELOG.md` (the release process makes it) |
| Issue, commit and PR bodies | Your chat replies to the user |

Technical names (`pyproject.toml`, `uv`, `pytest`, function names) are always permitted.
Put code names in backticks.

STE adds to the other style rules in `CONTRIBUTING.md`. It does not replace them. For
example, a docstring still starts with an imperative verb, and that verb is never
"Return".

## Words

- Use simple, common words. Use one word for one meaning, and use that word every time.
  Do not use synonyms for variety.
- Use a word only as one part of speech. For example, "test" can be a noun or a verb in
  general English. Choose the approved use, and do not change between the two in one text.
- Do not make clusters of more than three nouns. Write "the speed of the cache lookup",
  not "cache lookup speed limit value".
- Do not leave out articles (`a`, `an`, `the`) or "that" to make text shorter.

Common substitutions (guidance, not the official dictionary):

| Do not write | Write |
|---|---|
| utilize, leverage, employ | use |
| ensure, verify | make sure |
| prior to | before |
| subsequent to, following | after |
| in order to | to |
| perform, conduct | do |
| commence, initiate | start |
| terminate | stop |
| obtain, acquire | get |
| approximately | about |
| in the event that | if |
| numerous | many |
| sufficient | enough |
| require | must, is necessary |
| it is possible to | you can |

## Verbs

- Use only these forms: imperative ("Run the tests."), simple present ("The function
  returns a list."), simple past ("The test failed."), simple future ("The command will
  stop."), infinitive, and the past participle as an adjective ("the selected file").
- Do not use the "-ing" form, except in a technical name. Write "Before you start the
  server", not "Before starting the server".
- Use the active voice. In procedures (instructions), always use the active voice.
  In descriptive text, use the passive voice only when the agent is not known or not
  important.
- Do not use a modal verb such as "should", "could", or "would" for an instruction.
  Write a command: "Run `uv sync`." not "You should run `uv sync`."

## Sentences

- Procedural sentences (instructions): 20 words or fewer.
- Descriptive sentences (explanations): 25 words or fewer.
- Write about one topic in each sentence.
- Use a vertical list when there are many items or steps.
- Do not use semicolons. Make two sentences.

## Procedures (instructions)

- Write one instruction in each sentence, unless the user must do two actions at the
  same time.
- Start the instruction with the verb (imperative).
- Put a condition before the instruction: "If the check fails, read the log."
- Give each step a number.
- Put explanations and notes in a separate sentence, not in the step.

## Descriptive text

- Give the most important information first.
- Write about one topic in each paragraph.
- Write six sentences or fewer in each paragraph.

## Warnings and cautions

- Start with a short, clear command that tells the user what to do or not do.
- Then give the reason or the risk in one short sentence.

Example: "Do not delete `uv.lock`. Other users will get different package versions."

## Examples

Docstring, bad:

```python
def load(path: Path) -> Config:
    """Utilizes the provided path in order to perform loading of the configuration,
    ensuring that defaults are applied prior to validation."""
```

Docstring, good:

```python
def load(path: Path) -> Config:
    """Read the configuration from `path`.

    The function adds the default values before it validates the configuration.
    """
```

Commit body:

```
# Bad
Refactored the parsing logic since it was getting kind of hard to follow and
also it was utilizing a deprecated API, which should probably be fixed.

# Good
The parser used a deprecated API. This change replaces the API and moves each
step of the parser into a separate function.
```

## Review

When you finish prose, read it again and check each sentence against these rules:
length, one topic, active voice, no "-ing" forms, no modal instructions, approved words.
