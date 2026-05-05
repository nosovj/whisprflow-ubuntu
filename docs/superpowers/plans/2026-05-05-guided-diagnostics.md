# Guided Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guided setup, test, calibration, summary, and config validation commands to `whisprflowctl`.

**Architecture:** Keep one Python CLI, but split diagnostics into pure functions for testability: config schema validation, PCM level measurement, signal analysis, and command rendering. Live commands use `parecord` only at the edges.

**Tech Stack:** Python 3.10, argparse, unittest, PulseAudio/PipeWire `parecord`, systemd user service.

---

### Task 1: Pure Validation And Analysis

**Files:**
- Modify: `whisprflowctl.py`
- Modify: `test_whisprflowctl.py`

- [x] **Step 1: Write failing tests for config validation**

Add tests that `mic_min_mean_abs="bad"` is rejected and `mic_min_mean_abs=220` is accepted.

- [x] **Step 2: Implement config schema validation**

Add a small schema for known numeric, boolean, and enum keys. Make `config set` reject invalid known-key values and add `config validate`.

- [x] **Step 3: Write failing tests for button and mic analysis**

Add synthetic level lists and assert verdicts plus recommended keys.

- [x] **Step 4: Implement analysis helpers**

Add `analyze_button_levels` and `analyze_mic_levels` returning verdict, measured stats, and recommendations.

### Task 2: CLI Commands

**Files:**
- Modify: `whisprflowctl.py`
- Modify: `test_whisprflowctl.py`

- [x] **Step 1: Write failing parser tests**

Assert `test button`, `test mic`, `calibrate`, `summary`, `setup wizard`, and `config validate` route correctly under mocks.

- [x] **Step 2: Implement live sampling**

Add `sample_parecord_levels(device, seconds, sample_rate, chunk_size)` that returns mean/peak chunks.

- [x] **Step 3: Implement commands**

Add human-readable output for `summary`, `test`, `calibrate`, and wizard. `calibrate --apply` saves recommendations and restarts the service.

- [x] **Step 4: Gate wizard phases**

Add Enter prompts before button and mic phases when stdin is interactive, plus `--no-prompt` for scripts.

- [x] **Step 5: Add level meter output**

Add `--meter` to `test button` and `test mic`, and enable it from the wizard so users see live level lines during timed capture.

### Task 3: Docs, Verification, Release

**Files:**
- Modify: `README.md`
- Modify: `test_packaging.py`
- Modify: `.github/workflows/ci.yml` if needed.

- [x] **Step 1: Document guided flow**

Add quick commands and examples to README.

- [x] **Step 2: Run verification**

Run unit tests, Xvfb tests, shell syntax, Python AST parse, secret scan, and local smoke commands.

- [x] **Step 3: Commit and push**

Commit changes, push main, tag `v0.3.0`, and watch CI.
