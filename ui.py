"""Minimal terminal UI — clean text, subtle colors, no chrome."""

import os
import sys
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn,
)

console = Console(highlight=False)


def clear():
    os.system("clear" if os.name != "nt" else "cls")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def header(text: str):
    console.print()
    console.rule(f"[bold magenta]{text}[/bold magenta]")
    console.print()

def dim(text: str):
    console.log(f"[dim]{text}[/dim]")

def info(text: str):
    console.log(f"{text}")

def success(text: str):
    console.print(f"[green]✓ {text}[/green]")

def error(text: str):
    console.print(f"[red]✗ {text}[/red]")

def warning(text: str):
    console.print(f"[yellow]! {text}[/yellow]")

def status_dot(label: str, ok: bool):
    dot = "[green]●[/green]" if ok else "[dim]○[/dim]"
    console.print(f"  {dot} {label}")

def newline():
    console.print()


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def prompt(label: str = "") -> str:
    if label:
        return Prompt.ask(label)
    return console.input("  > ").strip()

def confirm(label: str) -> bool:
    console.print(f"  {label} [dim](y/n)[/dim]")
    return console.input("  > ").strip().lower() in ("y", "yes", "")

def pick(items: list[str] | list[tuple[str, str]], label: str = "") -> int | None:
    if label:
        console.print()
        console.rule(f"[bold cyan]{label}[/bold cyan]")
        console.print()
        
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Idx", justify="right", style="cyan", no_wrap=True)
    table.add_column("Option", style="white")
    
    # Check if we have two-part tuples (name, extra_info) for a 3-column layout
    is_tuple = len(items) > 0 and isinstance(items[0], tuple)
    if is_tuple:
        table.add_column("Details", style="dim", justify="right")
    
    for i, item in enumerate(items, 1):
        if is_tuple:
            table.add_row(str(i), item[0], item[1])
        else:
            table.add_row(str(i), item)
        
    console.print(table)
    console.print()
    
    while True:
        choice = Prompt.ask(f"Select by index (or 'q' to quit)", default="q")
        if choice.lower() in ('q', 'quit', 'b', 'back'):
            return None
        
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(items):
                return idx - 1
        console.print("[red]Invalid index.[/red]")


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def make_progress(label: str = "Working") -> Progress:
    return Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

def make_download_progress() -> Progress:
    return Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

def make_grading_progress() -> Progress:
    return Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold magenta]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


# ---------------------------------------------------------------------------
# Legacy compat — these exist so old code doesn't break but do nothing fancy
# ---------------------------------------------------------------------------

def banner():
    console.print("\n  [bold]Brightspace Grading Automation[/bold]")

def nav(parts):
    pass

def menu(options, context=None):
    pass

def pause():
    console.input("\n  [dim]Press enter to continue...[/dim]")

def prompt_choices(label, choices):
    console.print(f"  {label}: {' / '.join(choices)}")
    while True:
        val = console.input("  > ").strip()
        for c in choices:
            if c.lower().startswith(val.lower()) and val:
                return c

def status_panel(title, items):
    console.print(f"\n  [bold]{title}[/bold]")
    for k, v in items.items():
        console.print(f"  [dim]{k}:[/dim] {v}")
    return ""

def duo_code_display(code: str):
    console.print()
    console.print(f"  [bold yellow]Duo code: {code}[/bold yellow]")
    console.print(f"  [dim]Match this in your Duo Mobile app[/dim]")
    console.print()
