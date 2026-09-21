#!/bin/bash

echo "🔍 Checking pod status and stability..."

POD_STATUS=$(kubectl get pod database-app -n k8squest -o jsonpath='{.status.phase}' 2>/dev/null)
READY=$(kubectl get pod database-app -n k8squest -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)
RESTART_COUNT=$(kubectl get pod database-app -n k8squest -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null)
PASSWORD_SET=$(kubectl get pod database-app -n k8squest -o jsonpath='{.spec.containers[0].env[?(@.name=="POSTGRES_PASSWORD")].value}' 2>/dev/null)

echo "   Pod Phase: $POD_STATUS"
echo "   Ready: $READY"
echo "   Restarts: $RESTART_COUNT"
echo "   PostgreSQL password configured: $([[ -n "$PASSWORD_SET" ]] && echo yes || echo no)"

if [[ "$POD_STATUS" == "Running" ]] && [[ "$READY" == "true" ]] && [[ "$RESTART_COUNT" -eq 0 ]] && [[ -n "$PASSWORD_SET" ]]; then
    echo "✅ Pod is running without restarts"
    exit 0
else
    echo "❌ Pod is not stable - Status: $POD_STATUS, Restarts: $RESTART_COUNT"
    echo "💡 Hint: Check logs with 'kubectl logs database-app -n k8squest'"
    echo "💡 Look for the PostgreSQL error about missing POSTGRES_PASSWORD"
    exit 1
fi
