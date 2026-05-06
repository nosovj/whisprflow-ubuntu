# Transcription Bias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add project/global dictionary hints to improve Whisper spelling of domain terms.

**Architecture:** Keep dictionary parsing inside `whisprflow.py`, because transcription request assembly already lives there. Mirror new config defaults in `whisprflowctl.py`, validate list fields there, and document usage in README.

**Tech Stack:** Python stdlib, `requests`, existing `unittest` tests.

---

### Task 1: Add Failing Runtime Tests

**Files:**
- Modify: `test_whisprflow.py`

- [ ] Add tests for `build_transcription_prompt`, markdown dictionary extraction, root-down context order, and provider request payloads.
- [ ] Run `timeout 45 .venv/bin/python -m unittest test_whisprflow.py` and confirm failures reference missing prompt helpers or missing request `prompt`.

### Task 2: Implement Runtime Prompt Building

**Files:**
- Modify: `whisprflow.py`

- [ ] Add config keys: `custom_terms`, `dictionary_files`, `context_roots`, `context_filenames`, `prompt_max_chars`.
- [ ] Add helpers for list normalization, term extraction, context file walking, dedupe, and cap enforcement.
- [ ] Add `prompt` to local OpenWhispr and OpenAI multipart payloads only when non-empty.
- [ ] Run `timeout 45 .venv/bin/python -m unittest test_whisprflow.py` and confirm pass.

### Task 3: Add CLI Validation And Packaging Tests

**Files:**
- Modify: `whisprflowctl.py`
- Modify: `test_whisprflowctl.py`
- Modify: `test_packaging.py`

- [ ] Validate list config fields as arrays of strings.
- [ ] Confirm default/example config drift test still passes.
- [ ] Run `timeout 45 .venv/bin/python -m unittest test_packaging.py test_whisprflowctl.py` and confirm pass.

### Task 4: Document And Verify

**Files:**
- Modify: `README.md`
- Modify: `config.example.json`
- Modify: `CHANGELOG.md`

- [ ] Document global dictionary and project dictionary sections.
- [ ] Add `v0.3.8` changelog entry.
- [ ] Run full unit tests, Xvfb tests, shell parse, compileall, and secret scan.
- [ ] Commit and push once checks pass.
