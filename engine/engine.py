#!/usr/bin/env python3
"""
K8sQuest - Interactive Kubernetes Learning Game
🎮 Now with Retro Gaming UI! 🎮
"""

import os
import sys
import json
import yaml
import subprocess
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.layout import Layout
from rich.text import Text
from rich.markdown import Markdown
from rich.live import Live
from rich.align import Align
from rich import box
from datetime import datetime

# Import retro UI components
try:
    from retro_ui import (
        show_retro_welcome, show_level_start, show_victory,
        show_command_menu, show_power_up_notification,
        show_retro_header, show_xp_bar, show_world_entry,
        show_game_complete, celebrate_milestone
    )
    RETRO_UI_ENABLED = True
except ImportError:
    RETRO_UI_ENABLED = False
    print("ℹ️  Retro UI not available, using standard interface")

# Import player name generator
try:
    from player_name import get_player_name
except ImportError:
    def get_player_name(console, current_name=None):
        from rich.prompt import Prompt
        return Prompt.ask("Enter your name", default="K8s Explorer")

# Import safety guards
try:
    from safety import validate_kubectl_command, print_safety_info
    SAFETY_ENABLED = os.environ.get("K8SQUEST_SAFETY", "on").lower() != "off"
except ImportError:
    SAFETY_ENABLED = False
    print("⚠️  Warning: Safety guards module not found. Running without protection.")

console = Console()

class K8sQuest:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.progress_file = self.base_dir / "progress.json"
        self.progress = self.load_progress()
        
    def load_progress(self):
        """Load player progress from JSON file"""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                progress = json.load(f)
                # Ensure current_level exists for resume functionality
                if "current_level" not in progress:
                    progress["current_level"] = None
                return progress
        return {
            "total_xp": 0,
            "completed_levels": [],
            "current_world": "world-1-basics",
            "current_level": None,
            "player_name": "Padawan"
        }
    
    def save_progress(self):
        """Save player progress"""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, indent=2, fp=f)
    
    def show_welcome(self):
        """Display welcome screen with retro gaming style"""
        if RETRO_UI_ENABLED:
            show_retro_welcome()
            time.sleep(1)
        
        console.clear()
        
        # Retro-style title
        title = """
    ╦╔═╔═╗╔═╗ ╦ ╦╔═╗╔═╗╔╦╗
    ╠╩╗╚═╗║═╬╗║ ║║╣ ╚═╗ ║ 
    ╩ ╩╚═╝╚═╝╚╚═╝╚═╝╚═╝ ╩ 
        """
        
        welcome_panel = Panel(
            Text(title, style="bold cyan") + 
            Text("\n🎮 Kubernetes Adventure Game 🎮\n", style="bold yellow") +
            Text("Contra-Style Learning | Arcade Action | Boss Battles", style="dim"),
            title="[bold magenta]⚔️  K8SQUEST  ⚔️[/bold magenta]",
            border_style="cyan",
            box=box.HEAVY
        )
        
        console.print(welcome_panel)
        console.print()
        
        # Player stats in retro gaming style
        stats = Table(show_header=False, box=box.HEAVY, border_style="yellow")
        stats.add_column("Stat", style="cyan bold")
        stats.add_column("Value", style="yellow bold")
        stats.add_row("🎮 PLAYER", self.progress["player_name"])
        stats.add_row("💎 TOTAL XP", str(self.progress["total_xp"]))
        stats.add_row("⭐ LEVELS CLEARED", f"{len(self.progress['completed_levels'])}/50")
        
        # Calculate completion percentage
        completion = (len(self.progress['completed_levels']) / 50) * 100
        progress_bar = "█" * int(completion / 5) + "░" * (20 - int(completion / 5))
        stats.add_row("📊 PROGRESS", f"[{progress_bar}] {completion:.0f}%")
        
        # Show current level if resuming
        if self.progress.get("current_level"):
            stats.add_row("🎯 CURRENT MISSION", self.progress["current_level"])
        
        # Add safety status with gaming flair
        safety_status = "🛡️  ACTIVE" if SAFETY_ENABLED else "⚠️  DISABLED"
        safety_color = "green" if SAFETY_ENABLED else "red"
        stats.add_row("🛡️  SHIELDS", f"[{safety_color}]{safety_status}[/{safety_color}]")
        
        console.print(Panel(stats, title="[bold yellow]⚡ PLAYER STATUS ⚡[/bold yellow]", border_style="yellow", box=box.HEAVY))
        
        # Show XP progress bar
        if RETRO_UI_ENABLED:
            console.print()
            console.print(show_xp_bar(self.progress["total_xp"], 10200))
        
        # Show safety reminder if enabled with gaming theme
        if SAFETY_ENABLED:
            console.print()
            console.print(Panel(
                "[green]🛡️  DEFENSE SYSTEMS ONLINE[/green]\n"
                "[dim]✓ Prevents cluster destruction\n"
                "✓ Namespace protection active\n"
                "✓ Safe mode engaged\n"
                "Type 'safety info' for shield details[/dim]",
                border_style="green",
                box=box.HEAVY,
                title="[bold green]🔰 SAFETY PROTOCOLS[/bold green]"
            ))
        console.print()
    
    def load_mission(self, level_path):
        """Load mission metadata"""
        mission_file = level_path / "mission.yaml"
        with open(mission_file, 'r') as f:
            return yaml.safe_load(f)
    
    def show_mission_briefing(self, mission, level_name):
        """Display mission briefing screen"""
        console.clear()
        
        briefing = f"""
# 🎯 {mission['name']}

**Mission**: {mission['description']}

**Objective**: {mission['objective']}

**XP Reward**: {mission['xp']} XP
        """
        
        console.print(Panel(
            Markdown(briefing),
            title=f"[bold cyan]Level: {level_name}[/bold cyan]",
            border_style="yellow",
            box=box.DOUBLE
        ))
        console.print()
    
    def show_progressive_hints(self, level_path, hint_level=1):
        """Show hints progressively - unlock more as players struggle"""
        hints_available = []
        
        for i in range(1, 4):
            hint_file = level_path / f"hint-{i}.txt"
            if hint_file.exists():
                hints_available.append((i, hint_file))
        
        if not hints_available:
            console.print("[yellow]No hints available for this level[/yellow]")
            return
        
        # Show hints up to the current level
        console.print(Panel(
            f"[bold yellow]💡 Hints (Unlocked: {min(hint_level, len(hints_available))}/{len(hints_available)})[/bold yellow]",
            border_style="yellow"
        ))
        
        for i, hint_file in hints_available:
            if i <= hint_level:
                with open(hint_file, 'r') as f:
                    hint_content = f.read().strip()
                
                hint_style = "cyan" if i == 1 else ("yellow" if i == 2 else "green")
                console.print(f"\n[bold {hint_style}]Hint {i}:[/bold {hint_style}] {hint_content}")
            else:
                console.print(f"\n[dim]Hint {i}: 🔒 Locked - try again to unlock[/dim]")
        
        console.print()
        return min(hint_level, len(hints_available))
    
    def show_debrief(self, level_path):
        """Show the post-mission debrief with learning explanations"""
        debrief_file = level_path / "debrief.md"
        
        if not debrief_file.exists():
            console.print("[yellow]No debrief available for this level[/yellow]")
            return
        
        with open(debrief_file, 'r') as f:
            debrief_content = f.read()
        
        console.clear()
        console.print(Panel(
            Markdown(debrief_content),
            title="[bold green]🎓 Mission Debrief - What You Learned[/bold green]",
            border_style="green",
            box=box.DOUBLE
        ))
        console.print()
        
        Prompt.ask("\n[dim]Press ENTER to continue[/dim]", default="")
    
    def show_solution_file(self, level_path):
        """Display the solution.yaml file contents"""
        solution_file = level_path / "solution.yaml"
        
        if not solution_file.exists():
            console.print("[yellow]No solution file available for this level[/yellow]")
            return
        
        with open(solution_file, 'r') as f:
            solution_content = f.read()
        
        console.print(Panel(
            f"[cyan]{solution_content}[/cyan]",
            title="[bold green]📄 solution.yaml[/bold green]",
            border_style="green",
            box=box.ROUNDED
        ))
        console.print()
    
    def show_hints(self, level_name, level_path=None):
        """Show helpful hints based on the level - DEPRECATED, use show_progressive_hints"""
        hints = {
            "level-1-pods": [
                "Use `kubectl get pod nginx-broken -n k8squest` to check status",
                "Use `kubectl describe pod nginx-broken -n k8squest` to see events",
                "Use `kubectl logs nginx-broken -n k8squest` to check logs",
                "The pod has a bad command. Check what command is being run.",
                "Remember: You can't edit a running pod - delete and recreate it!"
            ],
            "level-2-deployments": [
                "Use `kubectl get deployment web -n k8squest` to check status",
                "Use `kubectl describe deployment web -n k8squest` for details",
                "Scale with `kubectl scale deployment web --replicas=N -n k8squest`",
                "Or edit with `kubectl edit deployment web -n k8squest`"
            ]
        }
        
        level_hints = hints.get(level_name, ["Explore with kubectl commands!"])
        
        hint_table = Table(title="💡 Helpful Commands", box=box.ROUNDED, border_style="blue")
        hint_table.add_column("Hint", style="cyan")
        
        for hint in level_hints:
            hint_table.add_row(hint)
        
        console.print(hint_table)
        console.print()
        
        # Ask if they want to see the solution
        if level_path:
            if Confirm.ask("[yellow]📄 Would you like to see the solution.yaml file?[/yellow]", default=False):
                console.print()
                self.show_solution_file(level_path)
                console.print("[dim]💡 Tip: You can use this as a reference to fix the issue[/dim]\n")
    
    def get_resource_status(self, level_name):
        """Get current status of the Kubernetes resource"""
        try:
            if "pod" in level_name:
                result = subprocess.run(
                    ["kubectl", "get", "pod", "nginx-broken", "-n", "k8squest", 
                     "-o", "jsonpath={.status.phase}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return result.stdout.strip() or "Unknown"
            elif "deployment" in level_name:
                result = subprocess.run(
                    ["kubectl", "get", "deployment", "web", "-n", "k8squest",
                     "-o", "jsonpath={.status.readyReplicas}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                ready = result.stdout.strip() or "0"
                return f"{ready} replicas ready"
        except:
            return "Unknown"
        return "Unknown"
    
    def show_terminal_instructions(self, level_name):
        """Show clear instructions about opening another terminal"""
        instructions = Panel(
            Text.from_markup(
                "[bold yellow]📟 OPEN A NEW TERMINAL WINDOW[/bold yellow]\n\n"
                "[cyan]While this game is running:[/cyan]\n"
                "1️⃣  Open a NEW terminal window/tab\n"
                "2️⃣  Navigate to this directory\n"
                f"3️⃣  Use kubectl commands to fix the issue\n"
                "4️⃣  Come back here and choose 'validate' or 'check'\n\n"
                "[dim]💡 Tip: Use Cmd+T (Mac) or Ctrl+Shift+T (Linux) to open a new tab[/dim]"
            ),
            title="[bold red]⚠️  IMPORTANT[/bold red]",
            border_style="red",
            box=box.DOUBLE
        )
        console.print(instructions)
        console.print()
    
    def monitor_status(self, level_name, duration=10):
        """Monitor resource status in real-time"""
        console.print(f"\n[yellow]👀 Monitoring status for {duration} seconds...[/yellow]\n")
        
        status_table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        status_table.add_column("Time", style="dim")
        status_table.add_column("Status", style="yellow")
        
        with Live(status_table, refresh_per_second=2, console=console) as live:
            for i in range(duration):
                status = self.get_resource_status(level_name)
                status_table.add_row(
                    datetime.now().strftime("%H:%M:%S"),
                    status
                )
                time.sleep(1)
        
        console.print()
    
    def show_step_by_step_guide(self, level_name):
        """Show detailed step-by-step guide for beginners"""
        guides = {
            "level-1-pods": """
# 🎓 Step-by-Step Guide: Fix the Crashing Pod

## What's Wrong?
The pod has a bad command `nginxzz` that doesn't exist.

## How to Fix It:

### Step 1: Check what's wrong
```bash
kubectl get pod nginx-broken -n k8squest
kubectl describe pod nginx-broken -n k8squest
```

### Step 2: View the solution
Look at the file: `worlds/world-1-basics/level-1-pods/solution.yaml`

### Step 3: Delete the broken pod
```bash
kubectl delete pod nginx-broken -n k8squest
```

### Step 4: Apply the fix
```bash
kubectl apply -n k8squest -f worlds/world-1-basics/level-1-pods/solution.yaml
```

### Step 5: Verify it's working
```bash
kubectl get pod nginx-broken -n k8squest
```
Look for "Running" status!
            """,
            "level-2-deployments": """
# 🎓 Step-by-Step Guide: Fix the Deployment

## What's Wrong?
The deployment has 0 replicas, so no pods are running.

## How to Fix It:

### Step 1: Check the deployment
```bash
kubectl get deployment web -n k8squest
```

### Step 2: Scale up the replicas
```bash
kubectl scale deployment web --replicas=2 -n k8squest
```

### Step 3: Verify it's working
```bash
kubectl get deployment web -n k8squest
kubectl get pods -n k8squest
```
Look for "2/2" ready replicas!
            """
        }
        
        guide = guides.get(level_name, "No guide available for this level.")
        
        console.print(Panel(
            Markdown(guide),
            title="[bold green]📚 Beginner's Guide[/bold green]",
            border_style="green",
            box=box.ROUNDED
        ))
        console.print()
    
    def deploy_mission(self, level_path, level_name):
        """Deploy the broken Kubernetes resources"""
        console.print("\n[yellow]🚀 Deploying mission environment...[/yellow]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Setting up namespace...", total=3)
            
            # Delete and recreate namespace
            subprocess.run(
                ["kubectl", "delete", "namespace", "k8squest", "--ignore-not-found"],
                capture_output=True
            )
            progress.advance(task)
            
            subprocess.run(
                ["kubectl", "create", "namespace", "k8squest"],
                capture_output=True
            )
            progress.update(task, description="Deploying broken resources...")
            progress.advance(task)
            
            # Apply broken config (without forcing namespace to respect YAML)
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(level_path / "broken.yaml")],
                capture_output=True,
                text=True
            )
            # Log errors for debugging (optional)
            if result.returncode != 0:
                console.print(f"[dim red]Warning: {result.stderr}[/dim red]")
            
            progress.update(task, description="✅ Environment ready!")
            progress.advance(task)
        
        console.print("\n")
        console.print(Panel(
            Text("🔴 MISSION DEPLOYED WITH BUGS! 🔴", style="bold red", justify="center") +
            Text("\n\nSomething is broken in the Kubernetes cluster.", style="yellow") +
            Text("\nYour mission: Find and fix the issue!", style="cyan"),
            border_style="red",
            box=box.DOUBLE
        ))
        console.print()
    
    def validate_mission(self, level_path, level_name):
        """Run validation script and show results"""
        console.print("\n[yellow]🔍 Validating your solution...[/yellow]\n")
        
        validate_script = level_path / "validate.sh"
        result = subprocess.run(
            ["bash", str(validate_script)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Success!
            console.print(Panel(
                Text("✅ MISSION COMPLETE! ✅", style="bold green", justify="center") +
                Text(f"\n\n{result.stdout}", style="green"),
                border_style="green",
                box=box.DOUBLE
            ))
            return True
        else:
            # Failed
            console.print(Panel(
                Text("❌ Not quite there yet...", style="bold red", justify="center") +
                Text(f"\n\n{result.stdout}", style="red"),
                border_style="red",
                box=box.ROUNDED
            ))
            return False
    
    def play_level(self, level_path, level_name):
        """Play a single level with retro gaming UI"""
        mission = self.load_mission(level_path)
        
        # Show retro level start screen
        if RETRO_UI_ENABLED:
            level_num = int(level_name.split('-')[1]) if 'level-' in level_name else 0
            show_level_start(level_num, mission['name'], mission['xp'], mission.get('difficulty', 'beginner'))
            input()  # Wait for player to press any key
        
        # Show mission briefing with metadata
        console.clear()
        
        # Display retro-style header
        if RETRO_UI_ENABLED:
            console.print(show_retro_header(mission['name'], mission['xp'], self.progress["total_xp"]))
            console.print()
        
        # Display difficulty and time estimate with gaming flair
        difficulty_colors = {
            "beginner": "green",
            "intermediate": "yellow",
            "advanced": "red",
            "expert": "magenta"
        }
        diff_color = difficulty_colors.get(mission.get('difficulty', 'beginner'), 'cyan')
        
        difficulty_icons = {
            "beginner": "⚡",
            "intermediate": "⚡⚡",
            "advanced": "⚡⚡⚡",
            "expert": "💀"
        }
        diff_icon = difficulty_icons.get(mission.get('difficulty', 'beginner'), '⚡')
        
        metadata = f"[{diff_color}]{diff_icon}[/{diff_color}] {mission.get('difficulty', 'Unknown').upper()}"
        metadata += f"  |  ⏱️  ~{mission.get('expected_time', '?')}"
        if 'concepts' in mission:
            metadata += f"  |  🎯 {', '.join(mission['concepts'])}"
        
        console.print(Panel(metadata, border_style=diff_color, box=box.HEAVY))
        console.print()
        
        self.show_mission_briefing(mission, level_name)
        
        # Deploy the mission
        self.deploy_mission(level_path, level_name)
        
        # Show terminal instructions prominently
        self.show_terminal_instructions(level_name)
        
        # Start with hint level 1
        current_hint_level = 1
        console.print()
        self.show_progressive_hints(level_path, current_hint_level)
        
        # Interactive loop with retro UI
        attempts = 0
        while True:
            console.print()
            
            # Show retro command menu
            if RETRO_UI_ENABLED:
                console.print(show_command_menu())
            else:
                console.print("="*60)
                console.print("[bold cyan]🎮 What would you like to do?[/bold cyan]")
                console.print("="*60)
                console.print("  [cyan]check[/cyan]     - 👁️  Monitor the resource status")
                console.print("  [cyan]guide[/cyan]     - 📖 Step-by-step instructions")
                console.print("  [cyan]hints[/cyan]     - 💡 Helpful kubectl commands")
                console.print("  [cyan]solution[/cyan]  - 📄 View the solution.yaml file")
                console.print("  [cyan]validate[/cyan]  - ✅ Test if you've fixed it")
                console.print("  [cyan]skip[/cyan]      - ⏭️  Skip this level")
                console.print("  [cyan]quit[/cyan]      - 🚪 Exit the game")
                console.print("="*60)
            
            console.print()
            
            action = Prompt.ask(
                "⚔️  Choose your action",
                choices=["check", "guide", "hints", "solution", "validate", "skip", "quit"],
                default="check"
            )
            
            if action == "check":
                # Real-time status monitoring
                self.monitor_status(level_name, duration=10)
                
            elif action == "guide":
                if RETRO_UI_ENABLED:
                    show_power_up_notification("guide")
                self.show_step_by_step_guide(level_name)
                
            elif action == "hints":
                # Unlock next hint level
                current_hint_level += 1
                if RETRO_UI_ENABLED:
                    show_power_up_notification("hint")
                console.print()
                self.show_progressive_hints(level_path, current_hint_level)
            
            elif action == "solution":
                console.print("\n[yellow]📄 Showing solution file...[/yellow]\n")
                if RETRO_UI_ENABLED:
                    show_power_up_notification("solution")
                self.show_solution_file(level_path)
                console.print("[dim]💡 Use this as reference to fix the broken configuration[/dim]\n")
                
            elif action == "validate":
                attempts += 1
                console.print(f"\n[dim]⚔️  ATTEMPT #{attempts}[/dim]")
                
                if self.validate_mission(level_path, level_name):
                    # Victory with retro UI!
                    if RETRO_UI_ENABLED:
                        xp_earned = mission["xp"]
                        self.progress["total_xp"] += xp_earned
                        show_victory(xp_earned, self.progress["total_xp"])
                    else:
                        # Standard success animation
                        console.print("\n")
                        for i in range(3):
                            console.print("⭐ " * 20)
                            time.sleep(0.2)
                        
                        # Award XP
                        xp_earned = mission["xp"]
                        self.progress["total_xp"] += xp_earned
                    
                    if level_name not in self.progress["completed_levels"]:
                        self.progress["completed_levels"].append(level_name)
                    self.save_progress()
                    
                    if not RETRO_UI_ENABLED:
                        console.print(f"\n[bold yellow]🌟 +{xp_earned} XP! Total: {self.progress['total_xp']} XP[/bold yellow]")
                    console.print(f"[dim]⚡ Cleared in {attempts} attempt(s)[/dim]\n")
                    
                    # Check for milestones
                    if RETRO_UI_ENABLED:
                        completed_count = len(self.progress["completed_levels"])
                        if completed_count == 10:
                            celebrate_milestone("world_complete")
                        elif completed_count == 25:
                            celebrate_milestone("halfway")
                        elif completed_count == 49:
                            celebrate_milestone("final_boss")
                        elif completed_count == 50:
                            show_game_complete()
                    
                    # Show debrief - THE LEARNING MOMENT!
                    self.show_debrief(level_path)
                    
                    if Confirm.ask("Ready for the next challenge?", default=True):
                        return True
                    else:
                        return False
                else:
                    # Unlock next hint on failure
                    current_hint_level = min(current_hint_level + 1, 3)
                    encouragement = [
                        "Don't give up! You're learning! 💪",
                        "Every mistake teaches you something! 🧠",
                        "Try the 'guide' option for step-by-step help! 📚",
                        "Use 'check' to see real-time status! 👀"
                    ]
                    console.print(f"\n[yellow]{encouragement[attempts % len(encouragement)]}[/yellow]\n")
                    
                    if not Confirm.ask("Try again?", default=True):
                        return False
                        
            elif action == "skip":
                if Confirm.ask("Skip this level? (No XP will be awarded)", default=False):
                    return True
                    
            elif action == "quit":
                console.print("\n[yellow]👋 Thanks for playing K8sQuest! Progress saved.[/yellow]\n")
                sys.exit(0)
    
    def play_world(self, world_name):
        """Play all levels in a world"""
        world_path = self.base_dir / "worlds" / world_name
        
        if not world_path.exists():
            console.print(f"[red]Error: World '{world_name}' not found[/red]")
            return False
        
        # Get all level directories with natural sorting (level-1, level-2, ..., level-10)
        import re
        def natural_sort_key(path):
            """Extract numbers from path for natural sorting"""
            parts = re.split(r'(\d+)', path.name)
            return [int(part) if part.isdigit() else part for part in parts]
        
        levels = sorted([d for d in world_path.iterdir() if d.is_dir()], key=natural_sort_key)
        
        # Find where to resume from
        start_index = 0
        if self.progress.get("current_level"):
            # Try to find the current level in the list
            for i, level_path in enumerate(levels):
                if level_path.name == self.progress["current_level"]:
                    # If the level is already completed, start from the next one
                    if self.progress["current_level"] in self.progress["completed_levels"]:
                        start_index = i + 1
                    else:
                        start_index = i
                    break
        
        # Play levels starting from resume point
        for level_path in levels[start_index:]:
            level_name = level_path.name
            
            # Save current level before playing
            self.progress["current_level"] = level_name
            self.progress["current_world"] = world_name
            self.save_progress()
            
            if not self.play_level(level_path, level_name):
                return False  # Player quit or stopped
        
        # World complete!
        console.clear()
        console.print(Panel(
            Text("🎉 WORLD COMPLETE! 🎉", style="bold green", justify="center") +
            Text(f"\n\nTotal XP: {self.progress['total_xp']}", style="yellow", justify="center"),
            border_style="green",
            box=box.DOUBLE
        ))
        time.sleep(2)
        
        return True  # World completed successfully

def main():
    game = K8sQuest()
    
    # First time setup - get player name
    if game.progress["player_name"] == "Padawan":
        console.print()
        game.progress["player_name"] = get_player_name(console)
        game.save_progress()
        console.print(f"\n[green]✨ Welcome, {game.progress['player_name']}![/green]\n")
        time.sleep(1)
    
    game.show_welcome()
    
    # All 5 worlds in order
    all_worlds = [
        "world-1-basics",
        "world-2-deployments",
        "world-3-networking",
        "world-4-storage",
        "world-5-security"
    ]
    
    # Check if there's progress to resume
    has_progress = len(game.progress["completed_levels"]) > 0 or game.progress.get("current_level")
    
    if has_progress:
        current_level = game.progress.get("current_level", "None")
        current_world = game.progress.get("current_world", "world-1-basics")
        completed_count = len(game.progress["completed_levels"])
        
        console.print(Panel(
            f"[yellow]📍 Resume Point Detected[/yellow]\n\n"
            f"Current Level: [cyan]{current_level}[/cyan]\n"
            f"Completed: [green]{completed_count}[/green] levels\n"
            f"Total XP: [yellow]{game.progress['total_xp']}[/yellow]",
            title="[bold]Continue Your Journey[/bold]",
            border_style="yellow"
        ))
        console.print()
        
        if Confirm.ask("Continue from where you left off?", default=True):
            # Find which world to start from
            start_world_index = 0
            for i, world in enumerate(all_worlds):
                if world == current_world:
                    start_world_index = i
                    break
            
            # Play from current world through to the end
            for world in all_worlds[start_world_index:]:
                if not game.play_world(world):
                    break  # Player quit
                    
        elif Confirm.ask("Start from the beginning instead?", default=False):
            game.progress["current_level"] = None
            game.progress["completed_levels"] = []
            game.progress["total_xp"] = 0
            game.save_progress()
            
            # Play all worlds from the beginning
            for world in all_worlds:
                if not game.play_world(world):
                    break  # Player quit
        else:
            console.print("\n[yellow]See you later, Padawan![/yellow]\n")
    else:
        if Confirm.ask("Ready to start your training?", default=True):
            # Play all worlds from the beginning
            for world in all_worlds:
                if not game.play_world(world):
                    break  # Player quit
        else:
            console.print("\n[yellow]See you later, Padawan![/yellow]\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]👋 Game interrupted. Progress saved![/yellow]\n")
        sys.exit(0)
