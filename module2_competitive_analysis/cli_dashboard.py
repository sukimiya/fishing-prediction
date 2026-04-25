"""CLI dashboard using Rich for competitive analysis display."""

from datetime import date
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box

from module2_competitive_analysis.storage import Storage


console = Console()


def show_overview(storage: Storage):
    """Show the main overview table of all tracked apps."""
    snapshots = storage.get_all_latest_snapshots()

    if not snapshots:
        console.print("[yellow]No tracking data yet. Run 'track' first.[/yellow]")
        return

    table = Table(
        title=f" 竞品概览 — {date.today().isoformat()}",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("App", style="bold")
    table.add_column("版本", justify="center")
    table.add_column("评分", justify="center")
    table.add_column("评价数", justify="right")
    table.add_column("价格")
    table.add_column("快照数", justify="right")
    table.add_column("最近更新", justify="center")

    for s in snapshots:
        if not s.get("snapshot_date"):
            table.add_row(
                s["name"], "—", "—", "—", "—", "0", "—",
            )
            continue

        # Color-code rating
        rating = s.get("rating", 0) or 0
        if rating >= 4.5:
            rating_str = f"[green]{rating:.1f}[/green]"
        elif rating >= 3.5:
            rating_str = f"[yellow]{rating:.1f}[/yellow]"
        else:
            rating_str = f"[red]{rating:.1f}[/red]"

        snapshot_count = storage.get_snapshot_count(s["app_id"])

        table.add_row(
            s["name"],
            s.get("version", "—"),
            rating_str,
            str(s.get("rating_count", 0)),
            s.get("price_text", "—"),
            str(snapshot_count),
            s.get("snapshot_date", "—"),
        )

    console.print(table)


def show_app_detail(storage: Storage, app_id: str):
    """Show detailed history for a single app."""
    app = storage.get_app(app_id)
    if not app:
        console.print(f"[red]App not found: {app_id}[/red]")
        return

    snapshots = storage.get_snapshots(app_id, limit=30)

    console.print(f"\n[bold cyan] {app['name']}[/bold cyan]")
    console.print(f"  Store: {app['store']} | Apple ID: {app['apple_id']}")
    console.print(f"  Snapshots: {len(snapshots)}")

    if not snapshots:
        return

    # Rating history table
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("日期", justify="center")
    table.add_column("版本", justify="center")
    table.add_column("评分", justify="center")
    table.add_column("评价数", justify="right")
    table.add_column("更新说明")

    for s in snapshots[:20]:  # latest 20
        rating = s.get("rating", 0) or 0
        rating_str = (
            f"[green]{rating:.1f}[/green]" if rating >= 4.5
            else f"[yellow]{rating:.1f}[/yellow]" if rating >= 3.5
            else f"[red]{rating:.1f}[/red]"
        )
        notes = (s.get("update_notes", "") or "")[:80]
        table.add_row(
            s["snapshot_date"],
            s.get("version", "—"),
            rating_str,
            str(s.get("rating_count", 0)),
            notes,
        )

    console.print(table)


def show_diff(storage: Storage, since_date: Optional[str] = None):
    """Show what changed between snapshots."""
    from datetime import timedelta

    if not since_date:
        since_date = (date.today() - timedelta(days=7)).isoformat()

    apps = storage.get_apps()

    console.print(f"\n[bold cyan] 变更追踪 (since {since_date})[/bold cyan]\n")

    found = False
    for app in apps:
        snapshots = storage.get_snapshots(app["app_id"], limit=365)
        # Filter since date
        recent = [s for s in snapshots if s["snapshot_date"] >= since_date]
        if len(recent) < 2:
            continue

        # Compare latest two
        latest = recent[0]
        prev = recent[1]

        changes = []
        if latest["version"] != prev["version"]:
            changes.append(f"版本: {prev['version']} → [green]{latest['version']}[/green]")
        if latest["rating"] != prev["rating"]:
            delta = latest["rating"] - prev["rating"]
            color = "green" if delta > 0 else "red"
            changes.append(f"评分: {prev['rating']:.1f} → [{color}]{latest['rating']:.1f}[/{color}] ({delta:+.2f})")
        if latest["rating_count"] != prev["rating_count"]:
            delta = latest["rating_count"] - prev["rating_count"]
            changes.append(f"评价数: +{delta}")

        if changes:
            found = True
            console.print(f"[bold]{app['name']}[/bold]")
            for c in changes:
                console.print(f"  {c}")
            console.print()

    if not found:
        console.print("[yellow]No significant changes detected.[/yellow]")


def show_comparison(storage: Storage):
    """Show a feature comparison matrix across apps."""
    apps = storage.get_apps()
    if not apps:
        console.print("[yellow]No apps tracked.[/yellow]")
        return

    console.print("\n[bold cyan] 当前状态快照[/bold cyan]\n")

    for app in apps:
        latest = storage.get_latest_snapshot(app["app_id"])
        if not latest:
            continue

        info = (
            f"  [bold]{app['name']}[/bold]\n"
            f"  版本: {latest.get('version', '—')}\n"
            f"  评分: {latest.get('rating', '—')} ({latest.get('rating_count', 0)} 评价)\n"
            f"  大小: {latest.get('app_size_mb', '—')} MB\n"
            f"  价格: {latest.get('price_text', '—')}\n"
        )
        notes = latest.get("update_notes", "")
        if notes:
            info += f"  最近更新: {notes[:120]}"
        console.print(Panel(info, border_style="blue"))
