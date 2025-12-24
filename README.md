# K8sQuest 🕹️⚙️
Learn Kubernetes by fixing it.

K8sQuest is a **local, game-based Kubernetes training platform** with an interactive GUI-like terminal interface. Each mission breaks something in Kubernetes. Your job is to fix it.

**50 progressive challenges across 5 worlds** - from beginner to advanced.

No cloud. No AWS. No costs.

## ✨ Features

- �📊 **Real-time Monitoring** - Watch Kubernetes resources update live with "check" command
- 💡 **Progressive Hints** - Unlocks gradually as you need help
- 📚 **Step-by-Step Guides** - Beginner-friendly walkthroughs when you need them
- � **Post-Mission Debriefs** - Learn WHY your fix worked with real-world examples
- �🎯 **Clear Mission Briefings** - Know difficulty, time estimate, and concepts
- 🏆 **XP & Progress System** - Track your learning journey and achievements
- 🎮 **Multi-Terminal Workflow** - Learn real-world debugging patterns
- 💾 **Auto-Save Progress** - Never lose your achievements
- 🔄 **Reset Levels** - Get stuck? Clean slate anytime

## 🛡️ Safety First

K8sQuest includes **comprehensive safety guards** (enabled by default):
- ✅ Prevents deletion of critical namespaces (kube-system, default, etc.)
- ✅ Blocks destructive cluster-wide operations
- ✅ Limits operations to `k8squest` namespace via RBAC
- ✅ Confirms risky operations before execution
- ✅ Safe for beginners - hard to break things!

[Learn more about safety guards →](docs/SAFETY.md)

## Requirements
- Docker Desktop (running)
- kubectl
- kind
- bash
- python3

## Quick Start
```bash
# One-time setup
./install.sh

# Start playing
./play.sh
```

## 🎮 How to Play

1. **Start the game** - Run `./play.sh` (keeps the game running)
2. **Read the mission briefing** - Understand what's broken  
3. **OPEN A NEW TERMINAL** ⚠️ - Keep the game running in the first terminal!
4. **Use kubectl to investigate** - Check pods, logs, and events in the NEW terminal
5. **Fix the issue** - Apply corrections using kubectl commands
6. **Return to game terminal** - Choose an action (check/validate/guide)
7. **Earn XP** - Complete missions to level up!

## 🎯 Available Commands During Play

- `check` - Monitor resource status in real-time (watch for changes!)
- `guide` - Show step-by-step solution walkthrough
- `hints` - Display progressive hints (unlocks more on each use)
- `solution` - View the solution.yaml file
- `validate` - Test if your solution works
- `skip` - Skip to the next level (no XP awarded)
- `quit` - Exit the game (progress is auto-saved)

## 🎓 Post-Mission Debriefs

After completing each mission, you'll get a detailed debrief explaining:
- ✅ What actually happened and why
- 🧠 The correct mental model for this concept
- 🚨 Real-world production incident examples
- 💼 Interview questions you can now answer
- 🔧 kubectl commands you mastered

**This is where the real learning happens!**

## 🔧 Reset Levels

Get stuck or want to retry? Reset individual levels:
```bash
python3 engine/reset.py level-1-pods
python3 engine/reset.py level-2-deployments
```

Or reset everything:
```bash
python3 engine/reset.py all
```

## 📚 Learning Path

### 🎯 World 1: Core Kubernetes Basics (Levels 1-10) 
**Difficulty**: Beginner | **Total XP**: 1,000  
Master the fundamentals of Kubernetes debugging and troubleshooting.

- ✅ Level 1: CrashLoopBackOff Challenge (100 XP)
- ✅ Level 2: Deployment Zero Replicas (100 XP)
- ✅ Level 3: ImagePullBackOff Mystery (100 XP)
- ✅ Level 4: Pending Pod Problem (100 XP)
- ✅ Level 5: Lost Connection - Labels & Selectors (100 XP)
- ✅ Level 6: Port Mismatch Mayhem (100 XP)
- ✅ Level 7: Sidecar Sabotage (100 XP)
- ✅ Level 8: Pod Logs Mystery (100 XP)
- ✅ Level 9: Init Container Gridlock (100 XP)
- ✅ Level 10: Namespace Confusion (100 XP)

### 🏆 World 2: Deployments & Scaling (Levels 11-20) 
**Difficulty**: Intermediate | **Total XP**: 1,350  
Master deployment strategies, scaling, and health checks.

- ✅ Rolling updates, rollbacks, HPA, liveness/readiness probes
- ✅ PodDisruptionBudgets, canary deployments, anti-affinity
- ✅ Resource management, pod lifecycle, and production patterns

### 🏆 World 3: Networking & Services (Levels 21-30) 
**Difficulty**: Intermediate | **Total XP**: 2,100  
Master service discovery, load balancing, and network policies.

- ✅ ClusterIP, NodePort, LoadBalancer services
- ✅ DNS resolution, Ingress controllers, NetworkPolicies
- ✅ Session affinity, cross-namespace communication, headless services

### 🏆 World 4: Storage & Stateful Apps (Levels 31-40) 
**Difficulty**: Advanced | **Total XP**: 2,600  
Master persistent storage, StatefulSets, and configuration management.

- ✅ PersistentVolumes, PVCs, access modes, StorageClasses
- ✅ StatefulSets, volume permissions, reclaim policies
- ✅ ConfigMaps, Secrets, and production storage patterns

### 🏆 World 5: Security & Production Ops (Levels 41-50) 
**Difficulty**: Advanced | **Total XP**: 3,150  
Production-ready Kubernetes: RBAC, security, resource management, and chaos engineering.

- ✅ RBAC (ServiceAccounts, Roles, RoleBindings)
- ✅ SecurityContext, Pod Security Standards (restricted)
- ✅ ResourceQuotas, NetworkPolicies, node scheduling
- ✅ Taints/Tolerations, PodDisruptionBudgets, PriorityClass
- ✅ **Level 50**: 🔥 **The Chaos Finale** - 9 simultaneous failures in a production scenario!

**Total Journey**: 50 Levels | 10,200 XP | Beginner → Kubernetes Master 🏆

📖 **Full Blueprint**: See [docs/50-CHALLENGE-BLUEPRINT.md](docs/50-CHALLENGE-BLUEPRINT.md) for detailed descriptions of all 50 challenges.


## 🛠️ Manual Play (Advanced)

If you prefer the old-school bash script:
```bash
./engine/start_game.sh
```

## 📖 Contributing

Want to add more missions? Check out [docs/contributing.md](docs/contributing.md)
