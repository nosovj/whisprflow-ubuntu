# GitHub Project Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve GitHub-first install and project documentation without adding distro packaging.

**Architecture:** Keep runtime unchanged. Add one explicit installer flow flag, one changelog, README polish, and packaging tests that lock the behavior.

**Tech Stack:** Bash installer, Python `unittest`, Markdown docs, GitHub Actions.

---

### Task 1: Installer Setup Flag

**Files:**
- Modify: `install.sh`
- Modify: `test_packaging.py`

- [ ] **Step 1: Write failing packaging test**

Add assertions in `test_packaging.py` that `install.sh` contains `--setup`, `RUN_SETUP`, and `setup wizard`.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m unittest test_packaging.PackagingTests`

Expected: fails because installer lacks `--setup`.

- [ ] **Step 3: Implement flag**

Add `RUN_SETUP=0`, parse `--setup`, document it in help, and run:

```bash
"$ROOT/.venv/bin/python" "$ROOT/whisprflowctl.py" setup wizard
```

after service files are installed and before optional service restart.

- [ ] **Step 4: Run packaging tests**

Run: `.venv/bin/python -m unittest test_packaging.PackagingTests`

Expected: pass.

### Task 2: GitHub Docs

**Files:**
- Create: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `test_packaging.py`

- [ ] **Step 1: Write failing docs tests**

Assert README mentions `CHANGELOG.md`, `./install.sh --setup`, `whisprflowctl test sources --prep-seconds 3`, and `configured button source stayed flat`.

Assert changelog exists and mentions `v0.3.0`, `v0.3.1`, `v0.3.2`, `v0.3.3`, and `v0.3.4`.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m unittest test_packaging.PackagingTests`

Expected: fails because changelog/docs are missing.

- [ ] **Step 3: Update docs**

Add `CHANGELOG.md`, update install section with `--setup`, add a changelog link, and add flat-source troubleshooting language.

- [ ] **Step 4: Run packaging tests**

Run: `.venv/bin/python -m unittest test_packaging.PackagingTests`

Expected: pass.

### Task 3: Full Verification And Release

**Files:**
- No new functional files.

- [ ] **Step 1: Run full local verification**

Run:

```bash
timeout 45 .venv/bin/python -m unittest test_whisprflow.py test_packaging.py test_whisprflowctl.py
timeout 45 xvfb-run -a .venv/bin/python -m unittest test_whisprflow.py test_packaging.py test_whisprflowctl.py
bash -n run.sh autostart.sh install.sh scripts/list-audio-devices.sh
.venv/bin/python -c "import ast; [ast.parse(open(p).read()) for p in ('whisprflow.py','hud.py','whisprflowctl.py')]"
gh workflow view CI --repo nosovj/whisprflow-ubuntu
git diff --check
```

Expected: tests/syntax/diff pass. Use the repository CI workflow for the canonical secret scan so the regex stays centralized in one file.

- [ ] **Step 2: Commit and tag**

Run:

```bash
git add .
git commit -m "Improve GitHub onboarding docs"
git push origin main
git tag v0.3.5
git push origin v0.3.5
```

- [ ] **Step 3: Verify CI**

Run: `gh run list --repo nosovj/whisprflow-ubuntu --limit 4`

Expected: `main` and `v0.3.5` CI runs complete successfully.
