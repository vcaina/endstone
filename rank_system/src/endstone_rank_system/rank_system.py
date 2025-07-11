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
from endstone.scoreboard import Criteria


class RankSystem(Plugin):
    api_version = "0.5"
    name = "rank-system"

    NEWBIE_TAG = "Newbie"

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

    RANKS = {
        "mob_kills": [
            (0, "Hunter"),
            (10, "Slayer"),
            (50, "Beastmaster"),
        ],
        "player_kills": [
            (0, "Fighter"),
            (10, "Warrior"),
            (30, "Champion"),
        ],
        "ores_mined": [
            (0, "Miner"),
            (50, "Excavator"),
            (150, "Prospector"),
        ],
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

    def __init__(self):
        super().__init__()
        self._selected: dict[str, str] = {}

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

    def _get_rank_name(self, obj_name: str, value: int) -> str:
        tiers = self.RANKS.get(obj_name, [])
        rank = tiers[0][1] if tiers else ""
        for threshold, name in tiers:
            if value >= threshold:
                rank = name
            else:
                break
        return rank

    def _update_player_rank(self, player) -> None:
        stat = self._selected.get(player.unique_id)
        if not stat:
            return
        sb = self.server.scoreboard
        values = [
            sb.get_objective("mob_kills").get_score(player).value,
            sb.get_objective("player_kills").get_score(player).value,
            sb.get_objective("ores_mined").get_score(player).value,
        ]
        if all(v == 0 for v in values):
            rank_name = self.NEWBIE_TAG
        else:
            obj = sb.get_objective(stat)
            score = obj.get_score(player)
            rank_name = self._get_rank_name(stat, score.value)
        player.name_tag = f"[{rank_name}] {player.name}"

    # Event handlers
    @event_handler
    def on_actor_death(self, event: ActorDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and killer.is_player and not isinstance(event, PlayerDeathEvent):
            obj = self.server.scoreboard.get_objective("mob_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1
            self._update_player_rank(killer)

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and killer.is_player:
            obj = self.server.scoreboard.get_objective("player_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1
            self._update_player_rank(killer)

    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        if event.block.type in self.ORES:
            obj = self.server.scoreboard.get_objective("ores_mined")
            score = obj.get_score(event.player)
            score.value = score.value + 1
            self._update_player_rank(event.player)

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        # Display mob_kills by default
        obj = self.server.scoreboard.get_objective("mob_kills")
        event.player.scoreboard = self.server.scoreboard
        self._selected[event.player.unique_id] = "mob_kills"
        self._update_player_rank(event.player)

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
            self._selected[p.unique_id] = obj_name
            p.scoreboard = sb
            self._update_player_rank(p)

        form.on_submit = handle
        form.show(player)
        return True
