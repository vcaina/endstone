from __future__ import annotations

from endstone.event import (
    ActorDeathEvent,
    BlockBreakEvent,
    PlayerDeathEvent,
    PlayerJoinEvent,
    event_handler,
)
from endstone.form import ActionForm
from endstone.plugin import Plugin
from endstone.scoreboard import Criteria, DisplaySlot


class RankSystem(Plugin):
    api_version = "0.5"
    name = "rank-system"

    commands = {
        "rank": {
            "description": "Open the rank selection UI.",
            "usages": ["/rank"],
            "permissions": ["rank_system.command.rank"],
        }
    }

    permissions = {
        "rank_system.command.rank": {
            "description": "Allow using /rank to choose rank display.",
            "default": True,
        }
    }

    ORES = {
        "minecraft:coal_ore",
        "minecraft:iron_ore",
        "minecraft:copper_ore",
        "minecraft:gold_ore",
        "minecraft:diamond_ore",
        "minecraft:emerald_ore",
        "minecraft:redstone_ore",
        "minecraft:lapis_ore",
        "minecraft:nether_gold_ore",
        "minecraft:ancient_debris",
    }

    def on_enable(self) -> None:
        sb = self.server.scoreboard
        for obj, display in [
            ("mob_kills", "Mob Kills"),
            ("player_kills", "Player Kills"),
            ("ores_mined", "Ores Mined"),
        ]:
            if not sb.get_objective(obj):
                sb.add_objective(obj, Criteria.Type.DUMMY, display)

        self.register_events(self)

    # Event handlers
    @event_handler
    def on_actor_death(self, event: ActorDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and killer.is_player and not isinstance(event, PlayerDeathEvent):
            obj = self.server.scoreboard.get_objective("mob_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and killer.is_player:
            obj = self.server.scoreboard.get_objective("player_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1

    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        if event.block.type in self.ORES:
            obj = self.server.scoreboard.get_objective("ores_mined")
            score = obj.get_score(event.player)
            score.value = score.value + 1

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        # Display mob_kills by default
        obj = self.server.scoreboard.get_objective("mob_kills")
        obj.set_display(DisplaySlot.SIDEBAR)
        event.player.scoreboard = self.server.scoreboard

    def on_command(self, sender, command, args):
        if command.name != "rank" or not sender.is_player:
            return False

        player = sender
        sb = self.server.scoreboard
        form = ActionForm("Select Rank")
        form.add_button("Mob Kills")
        form.add_button("Player Kills")
        form.add_button("Ores Mined")

        def handle(p, index):
            obj_name = ["mob_kills", "player_kills", "ores_mined"][index]
            obj = sb.get_objective(obj_name)
            sb.clear_slot(DisplaySlot.SIDEBAR)
            obj.set_display(DisplaySlot.SIDEBAR)
            p.scoreboard = sb

        form.on_submit = handle
        form.show(player)
        return True
