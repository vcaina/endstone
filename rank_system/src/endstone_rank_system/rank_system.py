import json
from pathlib import Path

from endstone import Player
from endstone.event import (
    ActorDeathEvent,
    BlockBreakEvent,
    PlayerChatEvent,
    PlayerDeathEvent,
    PlayerJoinEvent,
    event_handler,
)
from endstone.form import ActionForm, MessageForm
from endstone.inventory import ItemStack
from endstone.plugin import Plugin
from endstone.scoreboard import Criteria


class RankSystem(Plugin):
    api_version = "0.5"
    name = "rank-system"

    NEWBIE_TAG = "\u00a77Newbie"
    _how_ranks_text = (
        "Earn ranks automatically:\n"
        "Mob Kills: Hunter (0), Slayer (20), Beastmaster (100)\n"
        "Player Kills: Fighter (0), Warrior (15), Champion (50)\n"
        "Ores Mined: Miner (0), Excavator (100), Prospector (500)\n"
        "Use /rank to choose which rank is displayed next to your name."
    )

    commands = {
        "rank": {
            "description": "Open the rank selection UI.",
            "usages": ["/rank"],
            "permissions": ["rank_system.command.rank"],
        },
        "rankup": {
            "description": "Promote to the next rank if eligible.",
            "usages": ["/rankup"],
            "permissions": ["rank_system.command.rankup"],
        },
        "resetranks": {
            "description": "Reset all stored rank data.",
            "usages": ["/resetranks"],
            "permissions": ["rank_system.command.resetranks"],
        },
    }

    permissions = {
        "rank_system.command.rank": {
            "description": "Allow using /rank to choose rank display.",
            "default": True,
        },
        "rank_system.command.rankup": {
            "description": "Allow using /rankup to manually upgrade rank.",
            "default": "op",
        },
        "rank_system.command.resetranks": {
            "description": "Allow resetting all rank data.",
            "default": "op",
        },
    }

    RANKS = {
        "mob_kills": [
            (0, "\u00a7aHunter"),
            (20, "\u00a79Slayer"),
            (100, "\u00a7dBeastmaster"),
        ],
        "player_kills": [
            (0, "\u00a7aFighter"),
            (15, "\u00a79Warrior"),
            (50, "\u00a7dChampion"),
        ],
        "ores_mined": [
            (0, "\u00a7aMiner"),
            (100, "\u00a79Excavator"),
            (500, "\u00a7dProspector"),
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
        "minecraft:deepslate_coal_ore",
        "minecraft:deepslate_iron_ore",
        "minecraft:deepslate_copper_ore",
        "minecraft:deepslate_gold_ore",
        "minecraft:deepslate_diamond_ore",
        "minecraft:deepslate_emerald_ore",
        "minecraft:deepslate_redstone_ore",
        "minecraft:deepslate_lapis_ore",
    }

    def __init__(self):
        super().__init__()
        # Use string UUIDs for persistence
        self._selected: dict[str, str] = {}
        # Store ranks for each stat separately
        self._ranks: dict[str, dict[str, str]] = {}
        self._data_file: Path | None = None

    def _uid(self, player: Player) -> str:
        """Return a consistent string identifier for the player."""
        return str(player.unique_id)

    def on_enable(self) -> None:
        sb = self.server.scoreboard
        self._data_file = Path(self.data_folder) / "ranks.json"
        if self._data_file.exists():
            try:
                with self._data_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._selected = {str(k): v for k, v in data.get("selected", {}).items()}
                self._ranks = {
                    str(k): {stat: name for stat, name in v.items()}
                    for k, v in data.get("ranks", {}).items()
                }
            except json.JSONDecodeError:
                self.logger.warning(
                    "Failed to parse %s, starting with empty rank data", self._data_file
                )
                self._selected = {}
                self._ranks = {}
        for obj, display in [
            ("mob_kills", "Mob Kills"),
            ("player_kills", "Player Kills"),
            ("ores_mined", "Ores Mined"),
        ]:
            if not sb.get_objective(obj):
                sb.add_objective(obj, Criteria.Type.DUMMY, display)

        self.register_events(self)

    def on_disable(self) -> None:
        if self._data_file is None:
            return
        data = {
            "selected": {str(k): v for k, v in self._selected.items()},
            "ranks": {str(k): v for k, v in self._ranks.items()},
        }
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        with self._data_file.open("w", encoding="utf-8") as f:
            json.dump(data, f)

    def _get_rank_name(self, obj_name: str, value: int) -> str:
        tiers = self.RANKS.get(obj_name, [])
        rank = tiers[0][1] if tiers else ""
        for threshold, name in tiers:
            if value >= threshold:
                rank = name
            else:
                break
        return rank

    def _update_stat(self, player: Player, stat: str) -> None:
        """Update the player's rank for the given statistic."""
        sb = self.server.scoreboard
        obj = sb.get_objective(stat)
        score = obj.get_score(player)
        rank_name = self._get_rank_name(stat, score.value)

        uid = self._uid(player)
        ranks = self._ranks.setdefault(uid, {})
        old_rank = ranks.get(stat)
        ranks[stat] = rank_name

        if old_rank != rank_name:
            self._apply_rank_benefits(player, rank_name, stat)
            self.server.broadcast_message(
                f"{player.name} has been promoted to {rank_name}!"
            )
            player.send_title("Rank Up!", f"You are now {rank_name}")

        # Update display name if this stat is currently selected
        if self._selected.get(uid) == stat:
            self._set_display_rank(player)

    def _set_display_rank(self, player: Player) -> None:
        """Refresh the player's name tag based on the selected stat."""
        uid = self._uid(player)
        stat = self._selected.get(uid, "mob_kills")

        sb = self.server.scoreboard
        score = sb.get_objective(stat).get_score(player).value
        rank_name = self.NEWBIE_TAG
        ranks = self._ranks.get(uid, {})
        if score > 0 and stat in ranks:
            rank_name = ranks[stat]

        player.name_tag = f"[{rank_name}\u00a7r] \u00a7f{player.name}"

    def _leaderboard_lines(self, stat: str) -> list[str]:
        """Return formatted lines for the top 5 players of a stat."""
        sb = self.server.scoreboard
        obj = sb.get_objective(stat)
        scores: list[tuple[Player, int]] = []
        for entry in sb.entries:
            if isinstance(entry, Player):
                val = obj.get_score(entry).value
                if val > 0:
                    scores.append((entry, val))

        scores.sort(key=lambda t: t[1], reverse=True)
        lines = []
        for i, (player, val) in enumerate(scores[:5], 1):
            uid = self._uid(player)
            selected = self._selected.get(uid, "mob_kills")
            prefix = self._ranks.get(uid, {}).get(selected, self.NEWBIE_TAG)
            lines.append(f"{i}. [{prefix}\u00a7r] {player.name} - {val}")

        if not lines:
            lines.append("No data yet.")
        return lines

    def _apply_rank_benefits(self, player: Player, rank_name: str, stat: str) -> None:
        """Give rewards for reaching a new rank."""
        reward = ""
        try:
            if stat == "mob_kills":
                if rank_name.endswith("Hunter"):
                    player.inventory.add_item(ItemStack("minecraft:bread", 32))
                    reward = "32x minecraft:bread"
                elif rank_name.endswith("Slayer"):
                    player.inventory.add_item(ItemStack("minecraft:cooked_beef", 32))
                    reward = "32x minecraft:cooked_beef"
                elif rank_name.endswith("Beastmaster"):
                    player.inventory.add_item(ItemStack("minecraft:golden_apple", 2))
                    reward = "2x minecraft:golden_apple"
            elif stat == "player_kills":
                if rank_name.endswith("Fighter"):
                    items = [
                        "minecraft:leather_helmet",
                        "minecraft:leather_chestplate",
                        "minecraft:leather_leggings",
                        "minecraft:leather_boots",
                    ]
                    reward = "a full set of Leather Armor"
                elif rank_name.endswith("Warrior"):
                    items = [
                        "minecraft:iron_helmet",
                        "minecraft:iron_chestplate",
                        "minecraft:iron_leggings",
                        "minecraft:iron_boots",
                    ]
                    reward = "a full set of Iron Armor"
                elif rank_name.endswith("Champion"):
                    items = [
                        "minecraft:diamond_helmet",
                        "minecraft:diamond_chestplate",
                        "minecraft:diamond_leggings",
                        "minecraft:diamond_boots",
                    ]
                    reward = "a full set of Diamond Armor"
                else:
                    items = []
                for item in items:
                    player.inventory.add_item(ItemStack(item))
            elif stat == "ores_mined":
                if rank_name.endswith("Miner"):
                    player.add_effect("minecraft:haste", 1000000, 0)
                    reward = "permanent Haste I"
                elif rank_name.endswith("Excavator"):
                    player.add_effect("minecraft:haste", 1000000, 1)
                    reward = "permanent Haste II"
                elif rank_name.endswith("Prospector"):
                    player.add_effect("minecraft:night_vision", 1000000, 0)
                    reward = "permanent Night Vision"
            if reward:
                player.send_message(
                    f"\u00a7a[RankSystem] You earned the [{rank_name}] rank and received {reward}!"
                )
        except Exception:
            self.logger.exception("Failed to apply rank reward")

    # Event handlers
    @event_handler
    def on_actor_death(self, event: ActorDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and isinstance(killer, Player) and not isinstance(event, PlayerDeathEvent):
            obj = self.server.scoreboard.get_objective("mob_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1
            self._update_stat(killer, "mob_kills")

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent) -> None:
        killer = event.damage_source.actor
        if killer and isinstance(killer, Player):
            obj = self.server.scoreboard.get_objective("player_kills")
            score = obj.get_score(killer)
            score.value = score.value + 1
            self._update_stat(killer, "player_kills")

    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        block_type = event.block.type.lower().split("[")[0]
        self.logger.info(f"Broke block: {event.block.type}")
        if block_type in self.ORES:
            obj = self.server.scoreboard.get_objective("ores_mined")
            score = obj.get_score(event.player)
            score.value = score.value + 1
            self._update_stat(event.player, "ores_mined")

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        player = event.player
        player.scoreboard = self.server.scoreboard
        uid = self._uid(player)
        if uid not in self._selected:
            self._selected[uid] = "mob_kills"
        self._set_display_rank(player)

        sb = self.server.scoreboard
        values = [
            sb.get_objective("mob_kills").get_score(player).value,
            sb.get_objective("player_kills").get_score(player).value,
            sb.get_objective("ores_mined").get_score(player).value,
        ]
        if all(v == 0 for v in values):
            player.send_message("\u00a76\u00a7l[SERVER] \u00a7r\u00a76To access ranks type /rank")

        ranks = self._ranks.setdefault(uid, {})
        for stat in self.RANKS.keys():
            if stat not in ranks:
                obj = self.server.scoreboard.get_objective(stat)
                if obj.get_score(player).value > 0:
                    self._update_stat(player, stat)

    @event_handler
    def on_player_chat(self, event: PlayerChatEvent) -> None:
        uid = self._uid(event.player)
        sb = self.server.scoreboard
        values = [
            sb.get_objective("mob_kills").get_score(event.player).value,
            sb.get_objective("player_kills").get_score(event.player).value,
            sb.get_objective("ores_mined").get_score(event.player).value,
        ]
        if all(v == 0 for v in values):
            rank = self.NEWBIE_TAG
        else:
            stat = self._selected.get(uid, "mob_kills")
            rank = self._ranks.get(uid, {}).get(stat, self.NEWBIE_TAG)
        original = event.message
        event.message = f"[{rank}\u00a7r] \u00a7f{event.player.name}: {original}"

    def on_command(self, sender, command, args):
        if not isinstance(sender, Player):
            return False

        player = sender

        if command.name == "rank":
            main = ActionForm("Rank Menu")
            main.add_button("Rank Display")
            main.add_button("Leaderboards")
            main.add_button("How Ranks Work")

            def main_handle(p, index):
                if index == 0:
                    sub = ActionForm("Select Rank")
                    sub.add_button("Mob Kills")
                    sub.add_button("Player Kills")
                    sub.add_button("Ores Mined")

                    def sub_handle(p2, idx):
                        if idx < 0 or idx > 2:
                            return
                        obj_name = ["mob_kills", "player_kills", "ores_mined"][idx]
                        self._selected[self._uid(p2)] = obj_name
                        self._set_display_rank(p2)
                        mapping = {
                            "mob_kills": "Mob Kill rank",
                            "player_kills": "Player Kill rank",
                            "ores_mined": "Ore Mining rank",
                        }
                        p2.send_message(
                            f"\u00a7a[RankSystem] {mapping[obj_name]} is now shown beside your name."
                        )

                    sub.on_submit = sub_handle
                    p.send_form(sub)
                elif index == 1:
                    board = ActionForm("Leaderboards")
                    board.add_button("Top Mob Killers")
                    board.add_button("Top Player Killers")
                    board.add_button("Top Ore Miners")

                    def board_handle(p2, idx):
                        if idx < 0 or idx > 2:
                            return
                        stat = ["mob_kills", "player_kills", "ores_mined"][idx]
                        title = [
                            "Top Mob Killers",
                            "Top Player Killers",
                            "Top Ore Miners",
                        ][idx]
                        lines = self._leaderboard_lines(stat)
                        text = "\n".join(lines)
                        form = MessageForm(title, text, "OK", "")
                        p2.send_form(form)

                    board.on_submit = board_handle
                    p.send_form(board)
                elif index == 2:
                    info = MessageForm(
                        "How Ranks Work",
                        self._how_ranks_text,
                        "OK",
                        "",
                    )
                    p.send_form(info)

            main.on_submit = main_handle
            player.send_form(main)
            return True


        if command.name == "rankup":
            if not player.has_permission("rank_system.command.rankup"):
                player.send_message("You do not have permission to use this command.")
                return True
            for stat in self.RANKS.keys():
                self._update_stat(player, stat)
            return True

        if command.name == "resetranks":
            if not player.has_permission("rank_system.command.resetranks"):
                player.send_message("You do not have permission to use this command.")
                return True
            sb = self.server.scoreboard

            # Clear all saved data
            self._ranks.clear()
            self._selected.clear()

            if self._data_file is not None:
                self._data_file.parent.mkdir(parents=True, exist_ok=True)
                with self._data_file.open("w", encoding="utf-8") as f:
                    json.dump({"selected": {}, "ranks": {}}, f)

            # Reset scoreboard entries for everyone
            for entry in sb.entries:
                sb.reset_scores(entry)

            # Refresh online player name tags
            for p in self.server.online_players:
                self._set_display_rank(p)

            player.send_message("All ranks have been reset.")
            return True

        return False
