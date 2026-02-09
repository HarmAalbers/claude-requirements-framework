# Claude Code Frozen Process Diagnostics

Quick reference for diagnosing frozen Claude Code CLI instances.

## Quick Diagnostic Commands

### 1. List All Claude Processes
```bash
ps aux | grep -E "claude" | grep -v grep
```

### 2. Get Working Directory for Each Process
```bash
ps aux | grep -E "node|claude" | grep -v grep | awk '{print $2}' | while read pid; do
  cmd=$(ps -p $pid -o args= 2>/dev/null | head -c 60)
  cwd=$(lsof -p $pid 2>/dev/null | grep cwd | awk '{print $NF}')
  if [ -n "$cwd" ]; then
    printf "%-8s %-60s %s\n" "$pid" "$cmd" "$cwd"
  fi
done
```

### 3. Check for Zombie Children
```bash
ps -eo pid,ppid,state,args | awk '$2 == <PID> {print}'
```
- `<defunct>` = zombie process (parent didn't reap it)

### 4. Get Memory Details
```bash
vmmap -summary <PID> 2>/dev/null | head -40
```
Key metrics:
- **Physical footprint (peak)**: Max memory ever used
- **JS VM Gigacage**: V8 JavaScript heap size

### 5. Get Real-time CPU/Memory
```bash
top -l 1 -pid <PID> 2>/dev/null | tail -2
```

## Freeze Types

### Type 1: CPU-Bound Freeze (Infinite Loop)
**Symptoms:**
- CPU at 100%+ constantly
- State: `R+` (Running)
- Memory may grow unbounded

**Causes:**
- Infinite recursion in code analysis
- Streaming operation that never completes
- Context accumulation without bounds

### Type 2: Deadlock Freeze (Waiting Forever)
**Symptoms:**
- CPU at 0%
- State: `S` (Sleeping)
- Zombie children (`<defunct>`)

**Causes:**
- MCP server crashed, Claude waiting for response
- File lock contention in hooks
- Pipe/socket waiting for data that never comes

## Common Root Causes

### 1. MCP Server Crashes
- Check for `<defunct>` zombie children
- Serena, memory, sentry MCP servers may crash unexpectedly
- No timeout protection on MCP calls

### 2. Hook Contention
- Rapid tool calls → many hook invocations
- File locks on `sessions.json` can deadlock
- Check: `~/.claude/hooks/` for custom hooks

### 3. Memory Explosion
- Large files read into context
- Circular dependencies in code analysis
- V8 garbage collection failures
- Peak memory > 10GB usually indicates a bug

### 4. Registry File Issues
- Atomic rename failures: `*.tmp → *.json`
- Missing directories in `.git/requirements/sessions/`
- Check: `ls -la ~/.claude/sessions.json`

## Session Registry
```bash
cat ~/.claude/sessions.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{k}: pid={v.get(\"pid\")}, project={v.get(\"project_dir\",\"?\")[-40:]}') for k,v in d.get('sessions',{}).items()]"
```

## Log Locations
- Requirements log: `~/.claude/requirements.log`
- Debug logs: `~/.claude/debug/`
- Session metrics: `.git/requirements/sessions/<session-id>.json`

## Kill Commands
```bash
# Graceful kill
kill <PID>

# Force kill (if unresponsive)
kill -9 <PID>
```

## Prevention Tips
1. Avoid reading very large files (>10MB) into context
2. Be cautious with rapid parallel tool execution
3. Monitor memory during long analysis tasks
4. Check MCP server health if session becomes unresponsive
