#!/usr/bin/env python3
"""
Rich CLI for SAR Command Agent

Provides an enhanced command-line interface with:
- Formatted tables for agent status
- Progress display for pending tasks
- Color-coded specialist analyses
- Markdown rendering for responses
- Multi-turn conversation support
"""

import os
import sys
import json
import uuid
from typing import Optional, Dict, List, Any
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.live import Live
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

# Initialize Rich console
console = Console()


class SARCliInterface:
    """Enhanced CLI for SAR Command Agent with rich formatting."""
    
    # Command help mapping
    COMMANDS = {
        "ask": "Ask a question to the Command Agent",
        "upload": "Upload and analyze a file (image/PDF)",
        "mission create": "Interactive mission creation",
        "mission load": "Load mission from JSON file",
        "mission status": "Show current mission state",
        "status": "System-wide status (all agents)",
        "agents": "List all agents and their last output",
        "tasks": "Show pending/completed tasks",
        "streams": "List all Redis streams with message counts",
        "session new": "Start a new conversation session",
        "session history": "Show conversation history",
        "session": "Switch to an existing session by ID",
        "verbose": "Toggle verbose output mode",
        "help": "Show this help message",
        "exit": "Exit the CLI",
    }
    
    def __init__(self, agent):
        """
        Initialize CLI with a CommandAgent instance.
        
        Args:
            agent: CommandAgent instance for processing queries
        """
        self.agent = agent
        self.verbose = False
        self.session_id = str(uuid.uuid4())
        
        # Setup prompt with history
        history_file = os.path.expanduser("~/.sar_cli_history")
        self.prompt_session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
        )
    
    def print_header(self):
        """Print CLI header with welcome message."""
        header = Panel(
            "[bold cyan]SAR Command Agent[/bold cyan]\n"
            "[dim]Search and Rescue Multi-Agent System[/dim]\n\n"
            f"[green]Session:[/green] {self.session_id[:8]}...\n"
            "[dim]Type 'help' for available commands[/dim]",
            title="🔍 SAR CLI",
            border_style="blue",
            box=box.DOUBLE,
        )
        console.print(header)
        console.print()
    
    def print_help(self):
        """Print help table with all commands."""
        table = Table(title="Available Commands", box=box.ROUNDED)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        
        for cmd, desc in self.COMMANDS.items():
            table.add_row(cmd, desc)
        
        console.print(table)
        console.print()
    
    def print_status(self):
        """Print system status including agent info."""
        agent_status = self.agent.get_status()
        
        table = Table(title="System Status", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Agent Name", agent_status.get("name", "N/A"))
        table.add_row("Version", agent_status.get("version", "N/A"))
        table.add_row("Framework", agent_status.get("framework", "N/A"))
        table.add_row("Status", agent_status.get("status", "N/A"))
        table.add_row("Session ID", self.session_id[:8] + "...")
        table.add_row("Verbose Mode", "ON" if self.verbose else "OFF")
        table.add_row("Input Stream", agent_status.get("input_stream", "N/A"))
        table.add_row("Output Stream", agent_status.get("output_stream", "N/A"))
        
        console.print(table)
        console.print()
    
    def print_agents_status(self):
        """Print status of all specialist agents."""
        # Try to get Redis client from agent
        try:
            redis_client = self.agent.redis_client
            
            agents_info = [
                ("Weather", "weather.forecast.raw", "🌤️"),
                ("Health", "health.assessment.raw", "🏥"),
                ("History", "history.out.raw", "📚"),
                ("Photo Analysis", "photo.analysis.raw", "📷"),
                ("Path Analysis", "path.analysis.raw", "🗺️"),
                ("Interview", "interview.analysis.raw", "📝"),
                ("Logistics", "logistics.status.raw", "📦"),
            ]
            
            table = Table(title="Agent Status", box=box.ROUNDED)
            table.add_column("Agent", style="cyan")
            table.add_column("Stream", style="dim")
            table.add_column("Messages", justify="right", style="green")
            table.add_column("Last Activity", style="yellow")
            
            for name, stream, icon in agents_info:
                try:
                    # Get stream length
                    length = redis_client.xlen(stream)
                    
                    # Get last message time
                    last_msg = redis_client.xrevrange(stream, count=1)
                    if last_msg:
                        msg_id = last_msg[0][0]
                        if isinstance(msg_id, bytes):
                            msg_id = msg_id.decode('utf-8')
                        # Parse timestamp from message ID (format: timestamp-sequence)
                        ts = int(msg_id.split("-")[0]) / 1000
                        last_time = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    else:
                        last_time = "No messages"
                    
                    table.add_row(f"{icon} {name}", stream, str(length), last_time)
                except Exception as e:
                    table.add_row(f"{icon} {name}", stream, "Error", str(e)[:20])
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error fetching agent status: {e}[/red]")
        
        console.print()
    
    def print_streams(self):
        """Print all Redis streams with message counts."""
        try:
            redis_client = self.agent.redis_client
            
            # Common SAR streams
            streams = [
                "command.query.raw",
                "command.response.raw",
                "mission.new",
                "weather.forecast.raw",
                "weather.query.raw",
                "health.assessment.raw",
                "health.assess.raw",
                "history.in.raw",
                "history.out.raw",
                "photo.task.raw",
                "photo.analysis.raw",
                "path.query.raw",
                "path.analysis.raw",
                "interview.in.raw",
                "interview.analysis.raw",
                "logistics.query.raw",
                "logistics.status.raw",
                "field.observation.raw",
                "system.dead_letter",
            ]
            
            table = Table(title="Redis Streams", box=box.ROUNDED)
            table.add_column("Stream", style="cyan")
            table.add_column("Messages", justify="right", style="green")
            table.add_column("Groups", justify="right", style="yellow")
            
            for stream in streams:
                try:
                    length = redis_client.xlen(stream)
                    
                    # Try to get consumer groups
                    try:
                        groups = redis_client.xinfo_groups(stream)
                        group_count = len(groups)
                    except:
                        group_count = 0
                    
                    if length > 0:
                        table.add_row(stream, str(length), str(group_count))
                except:
                    pass  # Stream doesn't exist
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error fetching streams: {e}[/red]")
        
        console.print()
    
    def print_session_history(self):
        """Print conversation history for current session."""
        from .graph import get_session_history
        
        history = get_session_history(self.session_id)
        
        if not history:
            console.print("[yellow]No conversation history yet.[/yellow]\n")
            return
        
        console.print(Panel(f"Session: {self.session_id[:8]}...", title="Conversation History"))
        
        for i, msg in enumerate(history, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if role == "user":
                console.print(f"\n[bold cyan]You ({i}):[/bold cyan]")
                console.print(content[:500] + ("..." if len(content) > 500 else ""))
            else:
                console.print(f"\n[bold green]Assistant ({i}):[/bold green]")
                # Try to render as markdown
                try:
                    md = Markdown(content[:1000] + ("..." if len(content) > 1000 else ""))
                    console.print(md)
                except:
                    console.print(content[:1000])
        
        console.print()
    
    def ask_question(self, question: str):
        """Process a question and display the response."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing query...", total=None)
            
            try:
                response = self.agent.process_query(
                    question, 
                    session_id=self.session_id,
                    verbose=self.verbose
                )
                progress.update(task, description="Complete!")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return
        
        # Display response
        console.print()
        console.print(Panel(
            Markdown(response),
            title="[bold green]Response[/bold green]",
            border_style="green",
        ))
        console.print()
    
    def handle_upload(self, filepath: str):
        """Handle file upload for analysis."""
        import os
        
        if not os.path.exists(filepath):
            console.print(f"[red]File not found: {filepath}[/red]")
            return
        
        # Determine file type
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            file_type = "image"
            console.print(f"[cyan]Detected image file: {filepath}[/cyan]")
        elif ext == '.pdf':
            file_type = "pdf"
            console.print(f"[cyan]Detected PDF file: {filepath}[/cyan]")
        else:
            console.print(f"[yellow]Unknown file type: {ext}. Treating as generic upload.[/yellow]")
            file_type = "unknown"
        
        console.print("[yellow]Note: File upload requires API Gateway to be running.[/yellow]")
        console.print("[dim]Use: curl -X POST http://localhost:8080/upload/analyze -F 'files=@{filepath}'[/dim]")
        console.print()
    
    def new_session(self):
        """Start a new conversation session."""
        self.session_id = str(uuid.uuid4())
        console.print(f"[green]✓ New session started: {self.session_id[:8]}...[/green]\n")
    
    def switch_session(self, session_id: str):
        """Switch to an existing session."""
        self.session_id = session_id
        console.print(f"[green]✓ Switched to session: {self.session_id[:8]}...[/green]\n")
    
    def parse_command(self, user_input: str) -> tuple:
        """
        Parse user input into command and arguments.
        
        Returns:
            Tuple of (command, arguments)
        """
        parts = user_input.strip().split(maxsplit=1)
        if not parts:
            return None, None
        
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        return cmd, args
    
    def run(self):
        """Main CLI loop."""
        self.print_header()
        
        while True:
            try:
                # Get user input with rich prompt
                user_input = self.prompt_session.prompt(
                    "SAR> ",
                ).strip()
                
                if not user_input:
                    continue
                
                cmd, args = self.parse_command(user_input)
                
                # Handle commands
                if cmd in ['exit', 'quit', 'q']:
                    console.print("[dim]Goodbye![/dim]")
                    break
                
                elif cmd == 'help':
                    self.print_help()
                
                elif cmd == 'status':
                    self.print_status()
                
                elif cmd == 'agents':
                    self.print_agents_status()
                
                elif cmd == 'streams':
                    self.print_streams()
                
                elif cmd == 'history':
                    self.print_session_history()
                
                elif cmd == 'verbose':
                    self.verbose = not self.verbose
                    console.print(f"[cyan]Verbose mode: {'ON' if self.verbose else 'OFF'}[/cyan]\n")
                
                elif cmd == 'new':
                    self.new_session()
                
                elif cmd == 'session':
                    if args:
                        self.switch_session(args)
                    else:
                        console.print(f"[cyan]Current session: {self.session_id}[/cyan]\n")
                
                elif cmd == 'ask':
                    if args:
                        self.ask_question(args)
                    else:
                        console.print("[yellow]Usage: ask <question>[/yellow]\n")
                
                elif cmd == 'upload':
                    if args:
                        self.handle_upload(args)
                    else:
                        console.print("[yellow]Usage: upload <filepath>[/yellow]\n")
                
                elif cmd == 'tasks':
                    console.print("[yellow]Task tracking available via dispatch tools.[/yellow]")
                    console.print("[dim]Pending tasks are displayed during query processing.[/dim]\n")
                
                elif cmd == 'mission':
                    if args.startswith('create'):
                        console.print("[yellow]Mission creation wizard not yet implemented.[/yellow]\n")
                    elif args.startswith('load'):
                        filepath = args[5:].strip()
                        if filepath:
                            console.print(f"[yellow]Loading mission from: {filepath}[/yellow]")
                            console.print("[dim]Use API Gateway: POST /missions[/dim]\n")
                        else:
                            console.print("[yellow]Usage: mission load <filepath>[/yellow]\n")
                    elif args.startswith('status'):
                        console.print("[yellow]Mission status requires active mission.[/yellow]\n")
                    else:
                        console.print("[yellow]Mission commands: create, load <file>, status[/yellow]\n")
                
                else:
                    # Treat as a question
                    self.ask_question(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit.[/dim]")
            except EOFError:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")


class JsonIOInterface:
    """JSON I/O mode for frontend integration testing."""
    
    def __init__(self, agent):
        self.agent = agent
        self.session_id = str(uuid.uuid4())
    
    def run(self):
        """Run in JSON I/O mode - read JSON from stdin, write JSON to stdout."""
        import sys
        
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                
                question = request.get("question") or request.get("query")
                session_id = request.get("session_id", self.session_id)
                
                if not question:
                    response = {"error": "No question provided"}
                else:
                    result = self.agent.process_query(question, session_id=session_id)
                    response = {
                        "session_id": session_id,
                        "question": question,
                        "response": result,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                print(json.dumps({"error": f"Invalid JSON: {e}"}))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({"error": str(e)}))
                sys.stdout.flush()


def run_rich_cli(agent):
    """Run the rich CLI interface."""
    cli = SARCliInterface(agent)
    cli.run()


def run_json_io(agent):
    """Run in JSON I/O mode."""
    interface = JsonIOInterface(agent)
    interface.run()
