# Refactor Mixins to Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `SchedulerService` and `RecorderService` to use composition via handler classes instead of deep mixin inheritance, while maintaining the public API and ensuring all tests pass.

**Architecture:** Logic from mixins will be moved to specialized handler classes in `handlers/` subdirectories. The main service classes will instantiate these handlers, pass required shared state (locks, registries, etc.) to them, and delegate method calls to maintain backward compatibility for tests and external callers.

**Tech Stack:** Python 3.13, FastAPI, threading, subprocess.

---

### Task 1: Refactor RecorderService Handlers

**Files:**
- Create: `app/services/recorder/handlers/__init__.py`
- Create: `app/services/recorder/handlers/dependency.py`
- Create: `app/services/recorder/handlers/paths.py`
- Create: `app/services/recorder/handlers/probe.py`
- Modify: `app/services/recorder/service.py`
- Modify: `app/services/recorder/__init__.py`

- [ ] **Step 1: Create `handlers/dependency.py`**
- [ ] **Step 2: Create `handlers/paths.py`**
- [ ] **Step 3: Create `handlers/probe.py`**
- [ ] **Step 4: Update `RecorderService` to use handlers**

### Task 2: Refactor SchedulerService Handlers

**Files:**
- Create: `app/services/scheduler/handlers/__init__.py`
- Create: `app/services/scheduler/handlers/capture.py`
- Create: `app/services/scheduler/handlers/probe.py`
- Create: `app/services/scheduler/handlers/commands.py`
- Create: `app/services/scheduler/handlers/recovery.py`
- Modify: `app/services/scheduler/service.py`

- [ ] **Step 1: Create `handlers/capture.py`**
- [ ] **Step 2: Create `handlers/probe.py`**
- [ ] **Step 3: Create `handlers/commands.py`**
- [ ] **Step 4: Create `handlers/recovery.py`**
- [ ] **Step 5: Update `SchedulerService` to use handlers**

### Task 3: Verification and Cleanup

- [ ] **Step 1: Run Ruff**
- [ ] **Step 2: Run Tests**
- [ ] **Step 3: Delete old mixin files**
