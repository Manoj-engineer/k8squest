#!/usr/bin/env python3
"""
K8sQuest - Interactive Kubernetes Learning Game
🎮 Now with Retro Gaming UI! 🎮
"""

import json
import os
import select
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

# Platform-specific imports for pagination
if os.name == 'nt':  # Windows
    import msvcrt
else:  # Unix/Linux/Mac
    import tty
    import termios

# Import retro UI components
try:
    from retro_ui import (
        celebrate_milestone,
        show_command_menu,
        show_game_complete,
        show_level_start,
        show_power_up_notification,
        show_retro_header,
        show_retro_welcome,
        show_victory,
        show_xp_bar,
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
    from safety import print_safety_info, validate_kubectl_command

    SAFETY_ENABLED = os.environ.get("K8SQUEST_SAFETY", "on").lower() != "off"
except ImportError:
    SAFETY_ENABLED = False
    print("⚠️  Warning: Safety guards module not found. Running without protection.")

# Web-mode / multi-user settings — injected by the engine pod at session creation.
# When running locally these are unset and the game behaves exactly as before.
K8SQUEST_NAMESPACE = os.environ.get("K8SQUEST_NAMESPACE", "k8squest")
K8SQUEST_WEB = os.environ.get("K8SQUEST_WEB", "").lower() in ("1", "true")
K8SQUEST_LEVEL = os.environ.get("K8SQUEST_LEVEL", "")
K8S_CLUSTER_TYPE = os.environ.get("K8S_CLUSTER_TYPE", "kind")

if not os.environ.get("KUBECONFIG"):
    home = os.path.expanduser("~")
    if K8S_CLUSTER_TYPE == "k3s":
        k3s_config = os.path.join(home, ".kube", "k3s-config")
        if os.path.exists(k3s_config):
            os.environ["KUBECONFIG"] = k3s_config

def get_expected_context():
    """Return the expected kubectl context name based on cluster type."""
    if K8S_CLUSTER_TYPE == "k3s":
        return "k3s-k8squest"
    return "kind-k8squest"

console = Console()


def wait_for_any_key():
    """Block until the user presses any single key (including space bar).
    Falls back to input() on platforms where raw-tty is unavailable."""
    if os.name == 'nt':  # Windows
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            # Skip null-prefix escape sequences (arrow/page keys)
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            return
    else:  # Unix / macOS
        import tty, termios, select
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:
            input()  # fallback (e.g. piped stdin)
            return
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            # Consume the rest of an escape sequence so it doesn't pollute input
            if ch == "\x1b" and select.select([sys.stdin], [], [], 0.05)[0]:
                sys.stdin.read(2)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            try:
                termios.tcflush(fd, termios.TCIFLUSH)
            except Exception:
                pass


class PaginatedDisplay:
    """Helper class for paginating long content like man pages"""

    def __init__(self, console, lines_per_page=None):
        self.console = console
        self.lines_per_page = lines_per_page or self._calculate_lines_per_page()

    def _calculate_lines_per_page(self):
        """Pick a sensible default based on terminal height"""
        default_height = 24
        try:
            size = getattr(self.console, "size", None)
            if size and getattr(size, "height", None):
                default_height = size.height
            elif hasattr(self.console, "height"):
                default_height = self.console.height
        except Exception:
            pass
        # Reserve space for title, borders, and navigation prompts
        return max(8, default_height - 8)

    def _get_keypress(self):
        """Read a single keypress (cross-platform) and return it"""
        if os.name == 'nt':  # Windows
            while True:
                ch = msvcrt.getwch()
                # Arrow/page keys emit a null prefix - skip them
                if ch in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    continue
                if ch == "\r":
                    return "\n"
                return ch
        else:  # Unix/Linux/Mac
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    # Arrow/Page keys send an escape sequence quickly; detect extra bytes
                    if select.select([sys.stdin], [], [], 0.01)[0]:
                        sys.stdin.read(2)
                        return ""
                    # Treat a lone ESC as a quick exit request
                    return 'q'
                # Convert carriage return to newline (Enter key in raw mode)
                if ch == "\r":
                    return "\n"
                return ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                try:
                    termios.tcflush(fd, termios.TCIFLUSH)
                except Exception:
                    pass

    @staticmethod
    def _build_code_block_states(lines):
        """Track whether each line is inside a fenced code block"""
        states = []
        inside_code = False
        for line in lines:
            states.append(inside_code)
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_code = not inside_code
        return states

    def _build_page_ranges(self, lines):
        """Create page ranges that avoid splitting fenced code blocks"""
        if not lines:
            return [(0, 0)]

        code_states = self._build_code_block_states(lines)
        ranges = []
        start = 0
        line_count = len(lines)

        while start < line_count:
            end = min(start + self.lines_per_page, line_count)
            # Avoid splitting inside a code block by extending to the closing fence
            while end < line_count and code_states[end - 1]:
                end += 1
            if end == start:  # Safety: ensure progress
                end = min(start + self.lines_per_page, line_count)
            ranges.append((start, end))
            start = end

        return ranges

    def _render_page(self, page_content, title, border_style, page_num=None, total_pages=None):
        # Use Rich's terminal controls so escape sequences don't leak into output.
        self.console.clear()

        if page_num is not None and total_pages is not None:
            page_indicator = f" [Page {page_num}/{total_pages}]"
        else:
            page_indicator = ""

        self.console.print(
            Panel(
                Markdown(page_content),
                title=f"[bold {border_style}]{title}{page_indicator}[/bold {border_style}]",
                border_style=border_style,
                box=box.DOUBLE,
            )
        )

    def _print_navigation_hint(self, page_index, total_pages):
        nav_parts = ["[dim]Navigation:[/dim]", "[cyan]Enter/Space[/cyan] next"]
        if page_index > 0:
            nav_parts.append("[cyan]b[/cyan] back")
        if total_pages > 1:
            nav_parts.append("[cyan]g[/cyan] go to start")
        nav_parts.append("[cyan]q[/cyan] skip debrief")
        if page_index == total_pages - 1:
            nav_parts.append("[cyan]Enter[/cyan] finishes")
        hint = " • ".join(nav_parts)
        self.console.print(hint)

    def display_paginated(self, content, title="Content", border_style="green", use_alt_buffer=False):
        """Display content with pagination like man pages
        
        Args:
            content: The content to display
            title: Title for the panel
            border_style: Color/style of the border
            use_alt_buffer: If True, use alternative screen buffer (content disappears after exit)
                          If False, content stays in terminal history (better for learning content)
        """
        lines = content.split('\n')
        page_ranges = self._build_page_ranges(lines)
        total_pages = len(page_ranges)

        if total_pages == 1:
            self._render_page(content, title, border_style)
            self.console.print()
            Prompt.ask("\n[dim]Press ENTER to continue[/dim]", default="")
            return

        # Optionally enter alternative screen buffer (like less/man pages)
        # For debriefs, we want content to stay visible in terminal history
        if use_alt_buffer:
            sys.stdout.write("\033[?1049h")  # Enable alternative buffer
            sys.stdout.flush()

        try:
            page_index = 0

            while True:
                start_idx, end_idx = page_ranges[page_index]
                page_content = '\n'.join(lines[start_idx:end_idx])
                self._render_page(page_content, title, border_style, page_index + 1, total_pages)
                self.console.print()
                self._print_navigation_hint(page_index, total_pages)

                key = self._get_keypress()
                if not key:
                    continue

                key_lower = key.lower()
                if key in ('\n', ' ', ''):
                    if page_index == total_pages - 1:
                        break
                    page_index = min(total_pages - 1, page_index + 1)
                elif key_lower == 'b' and page_index > 0:
                    page_index -= 1
                elif key_lower == 'g':
                    page_index = 0
                elif key_lower == 'q':
                    # Skip remaining pages
                    break
                else:
                    # Unrecognized input - ignore and wait again
                    continue
        finally:
            # Exit alternative screen buffer if it was enabled
            if use_alt_buffer:
                sys.stdout.write("\033[?1049l")  # Disable alternative buffer
                sys.stdout.flush()

        self.console.print()


class K8sQuest:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.progress_file = self.base_dir / "progress.json"
        self.progress = self.load_progress()

    def load_progress(self):
        """Load player progress from JSON file"""
        if self.progress_file.exists():
            with open(self.progress_file, "r", encoding='utf-8', errors='replace') as f:
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
            "player_name": "Padawan",
        }

    def save_progress(self):
        """Save player progress"""
        with open(self.progress_file, "w", encoding='utf-8') as f:
            json.dump(self.progress, indent=2, fp=f)

    def show_welcome(self):
        """Display welcome screen with retro gaming style"""
        if RETRO_UI_ENABLED:
            show_retro_welcome()
            time.sleep(1)

        console.clear()

        # Retro-style title
        title = """
    ╦╔═╔═╗╔═╗╔═╗ ╦ ╦╔═╗╔═╗╔╦╗
    ╠╩╗╠═╣╚═╗║═╬╗║ ║║╣ ╚═╗ ║
    ╩ ╩╚═╝╚═╝╚═╝╚╚═╝╚═╝╚═╝ ╩
        """

        welcome_panel = Panel(
            Text(title, style="bold cyan")
            + Text("\n🎮 Kubernetes Adventure Game 🎮\n", style="bold yellow")
            + Text("Contra-Style Learning | Arcade Action | Boss Battles", style="dim"),
            title="[bold magenta]⚔️  K8SQUEST  ⚔️[/bold magenta]",
            border_style="cyan",
            box=box.HEAVY,
        )

        console.print(welcome_panel)
        console.print()

        # Player stats in retro gaming style
        stats = Table(show_header=False, box=box.HEAVY, border_style="yellow")
        stats.add_column("Stat", style="cyan bold")
        stats.add_column("Value", style="yellow bold")
        stats.add_row("🎮 PLAYER", self.progress["player_name"])
        stats.add_row("💎 TOTAL XP", str(self.progress["total_xp"]))
        stats.add_row(
            "⭐ LEVELS CLEARED", f"{len(self.progress['completed_levels'])}/50"
        )

        # Calculate completion percentage
        completion = (len(self.progress["completed_levels"]) / 50) * 100
        progress_bar = "█" * int(completion / 5) + "░" * (20 - int(completion / 5))
        stats.add_row("📊 PROGRESS", f"[{progress_bar}] {completion:.0f}%")

        # Show current level if resuming
        if self.progress.get("current_level"):
            stats.add_row("🎯 CURRENT MISSION", self.progress["current_level"])

        # Add safety status with gaming flair
        safety_status = "🛡️  ACTIVE" if SAFETY_ENABLED else "⚠️  DISABLED"
        safety_color = "green" if SAFETY_ENABLED else "red"
        stats.add_row("🛡️  SHIELDS", f"[{safety_color}]{safety_status}[/{safety_color}]")

        console.print(
            Panel(
                stats,
                title="[bold yellow]⚡ PLAYER STATUS ⚡[/bold yellow]",
                border_style="yellow",
                box=box.HEAVY,
            )
        )

        # Show XP progress bar
        if RETRO_UI_ENABLED:
            console.print()
            console.print(show_xp_bar(self.progress["total_xp"], 10200))

        # Show safety reminder if enabled with gaming theme
        if SAFETY_ENABLED:
            console.print()
            console.print(
                Panel(
                    "[green]🛡️  DEFENSE SYSTEMS ONLINE[/green]\n"
                    "[dim]✓ Prevents cluster destruction\n"
                    "✓ Namespace protection active\n"
                    "✓ Safe mode engaged\n"
                    "Type 'safety info' for shield details[/dim]",
                    border_style="green",
                    box=box.HEAVY,
                    title="[bold green]🔰 SAFETY PROTOCOLS[/bold green]",
                )
            )
        console.print()

    def load_mission(self, level_path):
        """Load mission metadata"""
        mission_file = level_path / "mission.yaml"
        with open(mission_file, "r", encoding='utf-8', errors='replace') as f:
            return yaml.safe_load(f)

    def show_mission_briefing(self, mission, level_name):
        """Display mission briefing screen"""
        console.clear()

        briefing = f"""
# 🎯 {mission["name"]}

**Mission**: {mission["description"]}

**Objective**: {mission["objective"]}

**XP Reward**: {mission["xp"]} XP
        """

        console.print(
            Panel(
                Markdown(briefing),
                title=f"[bold cyan]Level: {level_name}[/bold cyan]",
                border_style="yellow",
                box=box.DOUBLE,
            )
        )
        console.print()

    def show_progressive_hints(self, level_path, hint_level=1, show_all=False):
        """Show hints progressively - unlock more as players struggle

        Args:
            level_path: Path to the level directory
            hint_level: Current hint level (1-3)
            show_all: If True, show all unlocked hints. If False, show only the current hint level.
        """
        hints_available = []

        for i in range(1, 4):
            hint_file = level_path / f"hint-{i}.txt"
            if hint_file.exists():
                hints_available.append((i, hint_file))

        if not hints_available:
            console.print("[yellow]No hints available for this level[/yellow]")
            return

        # Show header with progress
        console.print(
            Panel(
                f"[bold yellow]💡 Hints (Unlocked: {min(hint_level, len(hints_available))}/{len(hints_available)})[/bold yellow]",
                border_style="yellow",
            )
        )

        if show_all:
            # Show all unlocked hints
            for i, hint_file in hints_available:
                if i <= hint_level:
                    with open(hint_file, "r", encoding='utf-8', errors='replace') as f:
                        hint_content = f.read().strip()

                    hint_style = "cyan" if i == 1 else ("yellow" if i == 2 else "green")
                    console.print(
                        f"\n[bold {hint_style}]Hint {i}:[/bold {hint_style}] {hint_content}"
                    )
                else:
                    console.print(
                        f"\n[dim]Hint {i}: 🔒 Locked - try again to unlock[/dim]"
                    )
        else:
            # Show only the current hint level (newest unlocked hint)
            if hint_level <= len(hints_available):
                i, hint_file = hints_available[hint_level - 1]
                with open(hint_file, "r", encoding='utf-8', errors='replace') as f:
                    hint_content = f.read().strip()

                hint_style = (
                    "cyan"
                    if hint_level == 1
                    else ("yellow" if hint_level == 2 else "green")
                )
                console.print(
                    f"\n[bold {hint_style}]Hint {hint_level}:[/bold {hint_style}] {hint_content}"
                )

                # Show status of other hints
                for j in range(1, len(hints_available) + 1):
                    if j < hint_level:
                        console.print(
                            f"\n[dim]Hint {j}: ✅ Previously unlocked (type 'hints' to see all)[/dim]"
                        )
                    elif j > hint_level:
                        console.print(
                            f"\n[dim]Hint {j}: 🔒 Locked - try again to unlock[/dim]"
                        )
            else:
                console.print("\n[yellow]All hints have been unlocked![/yellow]")
                console.print("[dim]Type 'hints' again to see all hints[/dim]")

        console.print()
        return min(hint_level, len(hints_available))

    def show_debrief(self, level_path):
        """Show the post-mission debrief with learning explanations"""
        debrief_file = level_path / "debrief.md"

        if not debrief_file.exists():
            console.print("[yellow]No debrief available for this level[/yellow]")
            return

        with open(debrief_file, "r", encoding='utf-8', errors='replace') as f:
            debrief_content = f.read()

        # Use paginated display WITHOUT alternative buffer
        # This keeps the debrief visible in terminal history for reference
        paginator = PaginatedDisplay(console)
        paginator.display_paginated(
            debrief_content,
            title="🎓 Mission Debrief - What You Learned",
            border_style="green",
            use_alt_buffer=False  # Keep debrief in terminal history
        )

    def show_solution_file(self, level_path):
        """Display the solution.yaml file contents"""
        solution_file = level_path / "solution.yaml"

        if not solution_file.exists():
            console.print("[yellow]No solution file available for this level[/yellow]")
            return

        with open(solution_file, "r", encoding='utf-8', errors='replace') as f:
            solution_content = f.read()

        console.print(
            Panel(
                f"[cyan]{solution_content}[/cyan]",
                title="[bold green]📄 solution.yaml[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )
        console.print()

    def show_hints(self, level_name, level_path=None):
        """Show helpful hints based on the level - DEPRECATED, use show_progressive_hints"""
        hints = {
            "level-1-pods": [
                "Use `kubectl get pod nginx-broken -n k8squest` to check status",
                "Use `kubectl describe pod nginx-broken -n k8squest` to see events",
                "Use `kubectl logs nginx-broken -n k8squest` to check logs",
                "The pod has a bad command. Check what command is being run.",
                "Remember: You can't edit a running pod - delete and recreate it!",
            ],
            "level-2-deployments": [
                "Use `kubectl get deployment web -n k8squest` to check status",
                "Use `kubectl describe deployment web -n k8squest` for details",
                "Scale with `kubectl scale deployment web --replicas=N -n k8squest`",
                "Or edit with `kubectl edit deployment web -n k8squest`",
            ],
        }

        level_hints = hints.get(level_name, ["Explore with kubectl commands!"])

        hint_table = Table(
            title="💡 Helpful Commands", box=box.ROUNDED, border_style="blue"
        )
        hint_table.add_column("Hint", style="cyan")

        for hint in level_hints:
            hint_table.add_row(hint)

        console.print(hint_table)
        console.print()

        # Ask if they want to see the solution
        if level_path:
            if Confirm.ask(
                "[yellow]📄 Would you like to see the solution.yaml file?[/yellow]",
                default=False,
            ):
                console.print()
                self.show_solution_file(level_path)
                console.print(
                    "[dim]💡 Tip: You can use this as a reference to fix the issue[/dim]\n"
                )

    def get_resource_status(self, level_name):
        """Get current status of Kubernetes resources in k8squest namespace"""
        try:
            # Get common resource types
            resource_types = [
                "pods",
                "deployments",
                "services",
                "ingress",
                "pvc",
                "configmaps",
            ]
            status_parts = []

            for resource_type in resource_types:
                result = subprocess.run(
                    ["kubectl", "get", resource_type, "-n", K8SQUEST_NAMESPACE, "--no-headers"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.strip().split("\n")

                    for line in lines[:2]:  # Show up to 2 of each type
                        parts = line.split()
                        if len(parts) >= 2:
                            name = parts[0]
                            status = parts[1] if len(parts) > 1 else "?"

                            # Format based on resource type
                            if resource_type == "pods":
                                status_parts.append(f"Pod {name}: {status}")
                            elif resource_type == "deployments":
                                status_parts.append(f"Deploy {name}: {status}")
                            elif resource_type == "services":
                                svc_type = parts[1] if len(parts) > 1 else "?"
                                status_parts.append(f"Svc {name}: {svc_type}")
                            elif resource_type == "ingress":
                                hosts = parts[2] if len(parts) > 2 else "?"
                                status_parts.append(f"Ingress {name}: {hosts}")
                            elif resource_type == "pvc":
                                status_parts.append(f"PVC {name}: {status}")
                            elif resource_type == "configmaps":
                                status_parts.append(f"CM {name}")

                    # Limit total status parts to avoid clutter
                    if len(status_parts) >= 3:
                        break

            if status_parts:
                return " | ".join(status_parts[:3])
            else:
                return "No resources found"

        except subprocess.TimeoutExpired:
            return "Timeout"
        except Exception as e:
            return f"Checking..."

        return "Checking..."

    def show_terminal_instructions(self, level_name):
        """Show clear instructions about the kubectl terminal"""
        if K8SQUEST_WEB:
            # In web mode, the second terminal panel is already visible in the browser
            instructions = Panel(
                Text.from_markup(
                    "[bold cyan]🖥️  USE THE RIGHT TERMINAL PANEL[/bold cyan]\n\n"
                    "[cyan]The shell panel on the right is your kubectl workspace:[/cyan]\n"
                    f"1️⃣  Use kubectl commands targeting namespace [bold]{K8SQUEST_NAMESPACE}[/bold]\n"
                    "2️⃣  Fix the broken resources\n"
                    "3️⃣  Come back here and choose 'validate' or 'check'"
                ),
                title="[bold yellow]⚡ YOUR WORKSPACE[/bold yellow]",
                border_style="yellow",
                box=box.DOUBLE,
            )
        else:
            instructions = Panel(
                Text.from_markup(
                    "[bold yellow]📟 OPEN A NEW TERMINAL WINDOW[/bold yellow]\n\n"
                    "[cyan]While this game is running:[/cyan]\n"
                    "1️⃣  Open a NEW terminal window/tab\n"
                    "2️⃣  Use kubectl commands to fix the issue:\n"
                    "    • [dim]kubectl edit, scale, patch, etc.[/dim]\n"
                    "    • [dim]Or apply solution.yaml from level folder[/dim]\n"
                    "3️⃣  Come back here and choose 'validate' or 'check'\n\n"
                    "[dim]💡 Tip: Use Cmd+T (Mac) or Ctrl+Shift+T (Linux) to open a new tab[/dim]"
                ),
                title="[bold red]⚠️  IMPORTANT[/bold red]",
                border_style="red",
                box=box.DOUBLE,
            )
        console.print(instructions)
        console.print()

    def monitor_status(self, level_name, duration=10):
        """Monitor resource status in real-time"""
        console.print(
            f"\n[yellow]👀 Monitoring status for {duration} seconds...[/yellow]\n"
        )

        status_table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        status_table.add_column("Time", style="dim")
        status_table.add_column("Status", style="yellow")

        with Live(status_table, refresh_per_second=2, console=console) as live:
            for i in range(duration):
                status = self.get_resource_status(level_name)
                status_table.add_row(datetime.now().strftime("%H:%M:%S"), status)
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
            """,
        }

        guide = guides.get(level_name, "No guide available for this level.")

        console.print(
            Panel(
                Markdown(guide),
                title="[bold green]📚 Beginner's Guide[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            )
        )
        console.print()

    def deploy_mission(self, level_path, level_name):
        """Deploy the broken Kubernetes resources"""
        console.print("\n[yellow]🚀 Deploying mission environment...[/yellow]")

        # Pre-flight connectivity check with timeout
        check = subprocess.run(
            ["kubectl", "get", "nodes", "--request-timeout=5s"],
            capture_output=True, text=True,
        )
        if check.returncode != 0:
            console.print(f"\n[red]⚠️  Cannot connect to cluster:[/red]")
            console.print(f"[dim red]{check.stderr.strip()}[/dim red]")
            console.print(f"\n[yellow]💡 Make sure k3s is running, then in your other terminal run:[/yellow]")
            console.print(f"[dim]    export KUBECONFIG=\"$HOME/.kube/k3s-config\"[/dim]")
            console.print(f"[dim]    kubectl config use-context {get_expected_context()}[/dim]")
            return False

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Setting up namespace...", total=3)

            # Ensure namespace exists (idempotent, skip if already there)
            result = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input="apiVersion: v1\nkind: Namespace\nmetadata:\n  name: k8squest\n",
                capture_output=True, text=True,
            )
            
            # Check for namespace creation errors
            if result.returncode != 0:
                console.print(f"\n[red]⚠️  Failed to create namespace:[/red]")
                console.print(f"[dim red]{result.stderr}[/dim red]")
                console.print("[yellow]💡 Hint: Make sure your kubectl context is set correctly[/yellow]")
                console.print(f"[dim]Run: kubectl config use-context {get_expected_context()}[/dim]")
                return False

            # Clean up resources from previous level (without deleting the namespace)
            progress.update(task, description="Cleaning up previous level...")
            subprocess.run(
                ["kubectl", "delete", "all", "--all", "-n", K8SQUEST_NAMESPACE, "--ignore-not-found"],
                capture_output=True, text=True,
            )

            progress.update(task, description="Deploying broken resources...")
            progress.advance(task)

            # Check if level has a setup script (for levels needing history like rollback)
            setup_script = level_path / "setup.sh"
            if setup_script.exists():
                console.print("[yellow]Running level setup script...[/yellow]")
                result = subprocess.run(
                    ["bash", "setup.sh"],
                    cwd=str(level_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode != 0:
                    console.print(f"[red]Setup failed:[/red]")
                    console.print(f"[dim red]{result.stderr}[/dim red]")
                    if result.stdout:
                        console.print(f"[dim]{result.stdout}[/dim]")
                    return False
            else:
                # Apply broken config (without forcing namespace to respect YAML)
                result = subprocess.run(
                    ["kubectl", "apply", "-f", str(level_path / "broken.yaml")],
                    capture_output=True,
                    text=True,
                )
                # Show errors if deployment fails
                if result.returncode != 0:
                    console.print(f"[red]Deployment failed:[/red]")
                    console.print(f"[dim red]{result.stderr}[/dim red]")
                    return False

            progress.update(task, description="✅ Environment ready!")
            progress.advance(task)

        console.print("\n")
        console.print(
            Panel(
                Text(
                    "🔴 MISSION DEPLOYED WITH BUGS! 🔴",
                    style="bold red",
                    justify="center",
                )
                + Text(
                    "\n\nSomething is broken in the Kubernetes cluster.", style="yellow"
                )
                + Text("\nYour mission: Find and fix the issue!", style="cyan"),
                border_style="red",
                box=box.DOUBLE,
            )
        )
        console.print()
        return True  # Deployment successful

    def validate_mission(self, level_path, level_name):
        """Run validation script and show results"""
        console.print("\n[yellow]🔍 Validating your solution...[/yellow]\n")

        # Run validation script from the level directory with proper environment
        # Use relative name (not absolute path) so Windows/Git Bash doesn't mangle it
        result = subprocess.run(
            ["bash", "validate.sh"],
            cwd=str(level_path),  # CRITICAL: Run from level directory
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "NAMESPACE": K8SQUEST_NAMESPACE}  # inject namespace for validate.sh
        )

        # Always show output for debugging
        if result.stdout:
            console.print(f"[dim]{result.stdout}[/dim]")
        if result.stderr and result.returncode != 0:
            console.print(f"[dim red]Error output: {result.stderr}[/dim red]")

        if result.returncode == 0:
            # Success!
            console.print(
                Panel(
                    Text(
                        "✅ MISSION COMPLETE! ✅", style="bold green", justify="center"
                    )
                    + Text(f"\n\n{result.stdout}", style="green"),
                    border_style="green",
                    box=box.DOUBLE,
                )
            )
            return True
        else:
            # Failed
            console.print(
                Panel(
                    Text(
                        "❌ Not quite there yet...", style="bold red", justify="center"
                    )
                    + Text(f"\n\n{result.stdout}", style="red"),
                    border_style="red",
                    box=box.ROUNDED,
                )
            )
            return False

    def play_level(self, level_path, level_name):
        """Play a single level with retro gaming UI"""
        mission = self.load_mission(level_path)

        # Show retro level start screen
        if RETRO_UI_ENABLED:
            level_num = int(level_name.split("-")[1]) if "level-" in level_name else 0
            show_level_start(
                level_num,
                mission["name"],
                mission["xp"],
                mission.get("difficulty", "beginner"),
            )
            if K8SQUEST_WEB:
                try:
                    input()
                except EOFError:
                    return False
            else:
                wait_for_any_key()  # Wait for player to press any key (incl. space bar)

        # Show mission briefing with metadata
        console.clear()

        # Display retro-style header
        if RETRO_UI_ENABLED:
            console.print(
                show_retro_header(
                    mission["name"], mission["xp"], self.progress["total_xp"]
                )
            )
            console.print()

        # Display difficulty and time estimate with gaming flair
        difficulty_colors = {
            "beginner": "green",
            "intermediate": "yellow",
            "advanced": "red",
            "expert": "magenta",
        }
        diff_color = difficulty_colors.get(
            mission.get("difficulty", "beginner"), "cyan"
        )

        difficulty_icons = {
            "beginner": "⚡",
            "intermediate": "⚡⚡",
            "advanced": "⚡⚡⚡",
            "expert": "💀",
        }
        diff_icon = difficulty_icons.get(mission.get("difficulty", "beginner"), "⚡")

        metadata = f"[{diff_color}]{diff_icon}[/{diff_color}] {mission.get('difficulty', 'Unknown').upper()}"
        metadata += f"  |  ⏱️  ~{mission.get('expected_time', '?')}"
        if "concepts" in mission:
            metadata += f"  |  🎯 {', '.join(mission['concepts'])}"

        console.print(Panel(metadata, border_style=diff_color, box=box.HEAVY))
        console.print()

        self.show_mission_briefing(mission, level_name)

        # In web mode the backend already deployed the namespace + broken resources
        if not K8SQUEST_WEB:
            deployment_success = self.deploy_mission(level_path, level_name)
            if not deployment_success:
                console.print("\n[red]⚠️  Mission deployment failed![/red]")
                console.print("[yellow]This usually means:[/yellow]")
                console.print(f"  1. kubectl context is not set to '{get_expected_context()}'")
                console.print(f"  2. {K8S_CLUSTER_TYPE.capitalize()} cluster is not running")
                console.print("  3. Docker is not running")
                console.print()
                if Confirm.ask("Would you like to skip this level?", default=False):
                    return True
                else:
                    return False

        # Show terminal instructions prominently
        self.show_terminal_instructions(level_name)

        # Start with hint level 0 (no hints shown yet)
        current_hint_level = 0

        # Interactive loop with retro UI
        attempts = 0
        while True:
            console.print()

            # Show retro command menu
            if RETRO_UI_ENABLED:
                console.print(show_command_menu())
            else:
                console.print("=" * 60)
                console.print("[bold cyan]🎮 What would you like to do?[/bold cyan]")
                console.print("=" * 60)
                console.print(
                    "  [cyan]check[/cyan]     - 👁️  Monitor the resource status"
                )
                console.print("  [cyan]guide[/cyan]     - 📖 Step-by-step instructions")
                console.print("  [cyan]hints[/cyan]     - 💡 Helpful kubectl commands")
                console.print(
                    "  [cyan]solution[/cyan]  - 📄 View the solution.yaml file"
                )
                console.print("  [cyan]validate[/cyan]  - ✅ Test if you've fixed it")
                console.print("  [cyan]skip[/cyan]      - ⏭️  Skip this level")
                console.print("  [cyan]quit[/cyan]      - 🚪 Exit the game")
                console.print("=" * 60)

            console.print()

            try:
                action = Prompt.ask(
                    "⚔️  Choose your action",
                    choices=[
                        "check",
                        "guide",
                        "hints",
                        "solution",
                        "validate",
                        "restart",
                        "skip",
                        "quit",
                    ],
                    default="check",
                )
            except EOFError:
                console.print("\n[yellow]Session disconnected.[/yellow]")
                return False

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
                # Show only the newly unlocked hint (not all previous hints)
                self.show_progressive_hints(
                    level_path, current_hint_level, show_all=False
                )

            elif action == "solution":
                console.print("\n[yellow]📄 Showing solution file...[/yellow]\n")
                if RETRO_UI_ENABLED:
                    show_power_up_notification("solution")
                self.show_solution_file(level_path)
                console.print(
                    "[dim]💡 Use this as reference to fix the broken configuration[/dim]\n"
                )

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
                        console.print(
                            f"\n[bold yellow]🌟 +{xp_earned} XP! Total: {self.progress['total_xp']} XP[/bold yellow]"
                        )
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
                    
                    # Pause before asking about next challenge
                    console.print("\n[dim]Press Enter to continue...[/dim]")
                    input()

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
                        "Use 'check' to see real-time status! 👀",
                    ]
                    console.print(
                        f"\n[yellow]{encouragement[attempts % len(encouragement)]}[/yellow]\n"
                    )

                    if not Confirm.ask("Try again?", default=True):
                        return False

            elif action == "restart":
                if Confirm.ask(
                    "Restart this level?", default=True
                ):
                    return None

            elif action == "skip":
                if Confirm.ask(
                    "Skip this level? (No XP will be awarded)", default=False
                ):
                    return True

            elif action == "quit":
                console.print(
                    "\n[yellow]👋 Thanks for playing K8sQuest! Progress saved.[/yellow]\n"
                )
                sys.exit(0)

    def play_specific_level_by_name(self, level_name: str):
        """Web mode: jump directly to a level by its directory name (e.g. 'level-1-pods')."""
        import re
        base_dir = Path(__file__).parent.parent / "worlds"
        matches = list(base_dir.rglob(level_name))
        if not matches:
            console.print(f"[red]Level '{level_name}' not found.[/red]")
            sys.exit(1)
        level_path = matches[0]
        self.play_level(level_path, level_name)

    def play_specific_level(self):
        """Allow user to select and play a specific level"""
        import re

        # Get all worlds and their levels
        worlds = {}
        all_worlds = [
            "world-1-basics",
            "world-2-deployments",
            "world-3-networking",
            "world-4-storage",
            "world-5-security",
        ]

        def natural_sort_key(path):
            """Extract numbers from path for natural sorting"""
            parts = re.split(r"(\d+)", path.name)
            return [int(part) if part.isdigit() else part for part in parts]

        # Collect all levels from all worlds
        for world_name in all_worlds:
            world_path = self.base_dir / "worlds" / world_name
            if world_path.exists():
                levels = sorted(
                    [d for d in world_path.iterdir() if d.is_dir()],
                    key=natural_sort_key,
                )
                worlds[world_name] = levels

        # Display all levels organized by world
        console.clear()
        console.print(
            Panel("[bold cyan]Select a Level to Play[/bold cyan]", border_style="cyan")
        )
        console.print()

        level_choices = []
        display_list = []

        for world_name in all_worlds:
            if world_name not in worlds:
                continue

            world_display = (
                world_name.replace("world-", "World ").replace("-", " ").title()
            )
            console.print(f"\n[bold yellow]{world_display}[/bold yellow]")

            for level_path in worlds[world_name]:
                level_name = level_path.name
                # Check if completed
                status = (
                    "✅" if level_name in self.progress["completed_levels"] else "⭕"
                )

                # Load mission to get the name
                mission_file = level_path / "mission.yaml"
                if mission_file.exists():
                    with open(mission_file, "r", encoding='utf-8', errors='replace') as f:
                        mission = yaml.safe_load(f)
                        display_name = mission.get("name", level_name)
                else:
                    display_name = level_name

                level_num = len(level_choices) + 1
                level_choices.append((level_name, world_name, level_path))
                display_list.append(f"  [{level_num:2d}] {status} {display_name}")
                console.print(display_list[-1])

        console.print("\n[dim]Enter level number or 'q' to quit[/dim]\n")

        # Get user selection
        choice = Prompt.ask("Choose a level", default="q")

        if choice.lower() == "q":
            console.print("\n[yellow]Returning to menu...[/yellow]\n")
            return

        try:
            level_index = int(choice) - 1
            if 0 <= level_index < len(level_choices):
                level_name, world_name, level_path = level_choices[level_index]

                # Update progress to this level
                self.progress["current_level"] = level_name
                self.progress["current_world"] = world_name
                self.save_progress()

                # Play the same level if it gets reset
                while True:
                    result = self.play_level(level_path, level_name)
                    
                    if result is None:
                        continue  # Restart the same level
                    
                    if not result:
                        return False  # Player quit or stopped
                    
                    break

                # After playing, ask what to do next
                console.print("\n[cyan]What would you like to do?[/cyan]")
                console.print("  [1] Play another level", markup=False)
                console.print("  [2] Continue from here", markup=False)
                console.print("  [q] Quit", markup=False)
                console.print()

                next_choice = Prompt.ask(
                    "Your choice", choices=["1", "2", "q"], default="q"
                )

                if next_choice == "1":
                    self.play_specific_level()  # Recursive call to play another
                elif next_choice == "2":
                    # Continue from this world
                    all_worlds_list = [
                        "world-1-basics",
                        "world-2-deployments",
                        "world-3-networking",
                        "world-4-storage",
                        "world-5-security",
                    ]
                    start_world_index = all_worlds_list.index(world_name)
                    for world in all_worlds_list[start_world_index:]:
                        if not self.play_world(world):
                            break
            else:
                console.print("[red]Invalid level number[/red]")
                time.sleep(1)
                self.play_specific_level()
        except ValueError:
            console.print("[red]Please enter a valid number[/red]")
            time.sleep(1)
            self.play_specific_level()

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
            parts = re.split(r"(\d+)", path.name)
            return [int(part) if part.isdigit() else part for part in parts]

        levels = sorted(
            [d for d in world_path.iterdir() if d.is_dir()], key=natural_sort_key
        )

        # Find where to resume from
        start_index = 0
        if self.progress.get("current_level"):
            # Try to find the current level in the list
            for i, level_path in enumerate(levels):
                if level_path.name == self.progress["current_level"]:
                    # If the level is already completed, start from the next one
                    if (
                        self.progress["current_level"]
                        in self.progress["completed_levels"]
                    ):
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

            # Play the same level if it gets reset
            while True:
                result = self.play_level(level_path, level_name)
                
                if result is None:
                    continue  # Restart the same level
                
                if not result:
                    return False  # Player quit or stopped
                
                break

        # World complete!
        console.clear()
        console.print(
            Panel(
                Text("🎉 WORLD COMPLETE! 🎉", style="bold green", justify="center")
                + Text(
                    f"\n\nTotal XP: {self.progress['total_xp']}",
                    style="yellow",
                    justify="center",
                ),
                border_style="green",
                box=box.DOUBLE,
            )
        )
        time.sleep(2)

        return True  # World completed successfully


def main():
    game = K8sQuest()

    # Web mode: bypass all menus and jump straight to the requested level.
    # K8SQUEST_LEVEL is set by the backend when creating the engine pod.
    if K8SQUEST_WEB:
        if K8SQUEST_LEVEL:
            game.play_specific_level_by_name(K8SQUEST_LEVEL)
        else:
            console.print("[red]K8SQUEST_WEB is set but K8SQUEST_LEVEL is missing.[/red]")
            sys.exit(1)
        return

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
        "world-5-security",
    ]

    # Check if there's progress to resume
    has_progress = len(game.progress["completed_levels"]) > 0 or game.progress.get(
        "current_level"
    )

    if has_progress:
        current_level = game.progress.get("current_level", "None")
        current_world = game.progress.get("current_world", "world-1-basics")
        completed_count = len(game.progress["completed_levels"])

        console.print(
            Panel(
                f"[yellow]📍 Resume Point Detected[/yellow]\n\n"
                f"Current Level: [cyan]{current_level}[/cyan]\n"
                f"Completed: [green]{completed_count}[/green] levels\n"
                f"Total XP: [yellow]{game.progress['total_xp']}[/yellow]",
                title="[bold]Continue Your Journey[/bold]",
                border_style="yellow",
            )
        )
        console.print()

        # Offer three options
        console.print("[cyan]Choose an option:[/cyan]")
        console.print("  [1] Continue from where you left off", markup=False)
        console.print("  [2] Play a specific level", markup=False)
        console.print("  [3] Start from the beginning", markup=False)
        console.print("  [q] Quit", markup=False)
        console.print()

        choice = Prompt.ask("Your choice", choices=["1", "2", "3", "q"], default="1")

        if choice == "1":
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

        elif choice == "2":
            # Play specific level
            game.play_specific_level()

        elif choice == "3":
            game.progress["current_level"] = None
            game.progress["completed_levels"] = []
            game.progress["total_xp"] = 0
            game.save_progress()

            # Play all worlds from the beginning
            for world in all_worlds:
                if not game.play_world(world):
                    break  # Player quit
        else:
            console.print(f"\n[yellow]See you later, {game.progress['player_name']}![/yellow]\n")
    else:
        if Confirm.ask("Ready to start your training?", default=True):
            # Play all worlds from the beginning
            for world in all_worlds:
                if not game.play_world(world):
                    break  # Player quit
        else:
            console.print(f"\n[yellow]See you later, {game.progress['player_name']}![/yellow]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]👋 Game interrupted. Progress saved![/yellow]\n")
        sys.exit(0)
    except EOFError:
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)
