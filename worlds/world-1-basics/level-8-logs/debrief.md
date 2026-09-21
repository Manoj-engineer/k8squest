# 🎓 Mission Debrief: Pod Logs Mystery

## What Happened

The PostgreSQL container needed the `POSTGRES_PASSWORD` environment variable to initialize, but it wasn't provided. The container started, failed immediately, and Kubernetes restarted it—eventually showing `Error` or `CrashLoopBackOff`. The failure was an application configuration problem, and the only reliable way to discover the missing setting was by checking the container logs.

## The Correct Mental Model

**Logs are your debugging superpower**. Kubernetes can report that a container is failing, but it cannot explain every application-specific configuration error. A container may:
- Start and print a useful error before exiting
- Fail due to a missing environment variable
- Restart and repeat until it enters CrashLoopBackOff
- Look healthy at the Kubernetes resource level while the application is unavailable

**Log locations in Kubernetes**:
- Container logs: Captured from stdout/stderr
- Access via: `kubectl logs`
- Stored temporarily on node
- Rotated when they get too large

## Commands You Mastered

```bash
# View current logs
kubectl logs <pod> -n <namespace>

# View previous container logs (after crash)
kubectl logs <pod> --previous -n <namespace>

# Follow logs in real-time
kubectl logs <pod> -f -n <namespace>

# Specific container in multi-container pod
kubectl logs <pod> -c <container> -n <namespace>

# Last N lines
kubectl logs <pod> --tail=50 -n <namespace>

# Logs since timestamp
kubectl logs <pod> --since=1h -n <namespace>
```

## What's Next

Next: Init containers that block pod startup!
