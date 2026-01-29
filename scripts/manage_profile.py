#!/usr/bin/env python3
"""Manage PaperPulse profile - followed authors, interests, etc."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.table import Table
from paperpulse import profile

console = Console()


def show_authors():
    """Display all followed authors."""
    authors = profile.get_followed_authors()
    if not authors:
        console.print("[yellow]No authors followed yet.[/yellow]")
        return

    console.print(f"\n[bold]👥 Followed Authors ({len(authors)}):[/bold]")
    for i, author in enumerate(authors, 1):
        console.print(f"  {i}. {author}")


def add_author(name: str):
    """Add a new author to follow."""
    if profile.add_followed_author(name):
        console.print(f"[green]✓ Added: {name}[/green]")
    else:
        console.print(f"[yellow]Already following: {name}[/yellow]")


def remove_author(name: str):
    """Remove an author from the list."""
    if profile.remove_followed_author(name):
        console.print(f"[green]✓ Removed: {name}[/green]")
    else:
        console.print(f"[yellow]Not found: {name}[/yellow]")


def interactive_menu():
    """Interactive profile management."""
    while True:
        console.print("\n[bold cyan]📚 PaperPulse Profile Manager[/bold cyan]")
        console.print("  1. Show followed authors")
        console.print("  2. Add author")
        console.print("  3. Remove author")
        console.print("  4. Show profile path")
        console.print("  5. Exit")

        try:
            choice = input("\nChoice: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            show_authors()
        elif choice == "2":
            name = input("Author name: ").strip()
            if name:
                add_author(name)
        elif choice == "3":
            show_authors()
            name = input("Author name to remove: ").strip()
            if name:
                remove_author(name)
        elif choice == "4":
            console.print(f"\nProfile: {profile.get_profile_path()}")
        elif choice == "5":
            break
        else:
            console.print("[red]Invalid choice[/red]")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Manage PaperPulse profile")
    parser.add_argument("command", nargs="?", choices=["list", "add", "remove"],
                       help="Command to run")
    parser.add_argument("name", nargs="?", help="Author name (for add/remove)")

    args = parser.parse_args()

    if args.command == "list":
        show_authors()
    elif args.command == "add" and args.name:
        add_author(args.name)
    elif args.command == "remove" and args.name:
        remove_author(args.name)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
