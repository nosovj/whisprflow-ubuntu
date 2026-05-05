# Management CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `whisprflowctl` as the first useful feature batch for install, config, device, service, log, model, and OpenWhispr management.

**Architecture:** Add one standalone Python CLI that wraps existing repo scripts and system tools. Install it by symlink through `install.sh`, document common commands in `README.md`, and cover behavior with unit and packaging tests.

**Tech Stack:** Python 3.10, argparse, unittest, bash installer, GitHub Actions with Xvfb.

---

### Task 1: CLI Command Surface

**Files:**
- Create: `whisprflowctl.py`
- Create: `test_whisprflowctl.py`

- [x] **Step 1: Add config tests**

```python
code = whisprflowctl.main(["config", "set", "streaming_phrases", "false"])
self.assertEqual(code, 0)
self.assertFalse(self.read_config()["streaming_phrases"])
```

- [x] **Step 2: Implement config commands**

```python
def cmd_config(args):
    cfg = load_config(merged=args.action == "show")
    if args.action == "set":
        cfg = load_config(merged=False)
        cfg[args.key] = parse_value(args.value)
        save_config(cfg)
        return 0
```

- [x] **Step 3: Add command-wrapper tests**

```python
run.assert_called_once_with(["systemctl", "--user", "restart", "whisprflow.service"], check=False)
```

- [x] **Step 4: Implement setup, doctor, devices, service, logs, model, and openwhispr commands**

```python
sub.add_parser("doctor", help="check install health").set_defaults(func=cmd_doctor)
```

### Task 2: Packaging And Docs

**Files:**
- Modify: `install.sh`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `test_packaging.py`

- [x] **Step 1: Install CLI symlink**

```bash
mkdir -p "$BIN_DIR"
ln -sf "$ROOT/whisprflowctl.py" "$BIN_DIR/whisprflowctl"
```

- [x] **Step 2: Document useful commands**

```bash
whisprflowctl doctor
whisprflowctl config show
whisprflowctl service restart
whisprflowctl logs -n 120
```

- [x] **Step 3: Add CLI tests to CI**

```yaml
run: timeout 60s xvfb-run -a python -m unittest test_whisprflow.py test_packaging.py test_whisprflowctl.py
```

### Task 3: Verification And Release

**Files:**
- Verify all changed files.

- [x] **Step 1: Run unit tests**

```bash
timeout 20 /home/joe/whisprflow-ubuntu/.venv/bin/python -m unittest test_whisprflow.py test_packaging.py test_whisprflowctl.py
```

- [x] **Step 2: Run Xvfb tests**

```bash
timeout 20 xvfb-run -a /home/joe/whisprflow-ubuntu/.venv/bin/python -m unittest test_whisprflow.py test_packaging.py test_whisprflowctl.py
```

- [x] **Step 3: Run syntax and secret checks**

```bash
bash -n run.sh autostart.sh install.sh scripts/list-audio-devices.sh
/home/joe/whisprflow-ubuntu/.venv/bin/python -c "import ast; [ast.parse(open(p).read()) for p in ('whisprflow.py','hud.py','whisprflowctl.py')]"
Run the same secret scan pattern from `.github/workflows/ci.yml`.
```

- [x] **Step 4: Commit, push, tag**

```bash
git add .
git commit -m "Add whisprflowctl management CLI"
git push origin main
git tag v0.2.0
git push origin v0.2.0
```
