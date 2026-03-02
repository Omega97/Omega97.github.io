"""
===== Token Tactics Game =====
Real-time token-based multiplayer board game.
"""
import random
import sys
import os
import time
import hashlib
import inspect
from typing import Dict, List, Tuple, Iterator
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# === BOARD ===
@dataclass
class Palette:
    """Default palette using emoji representations."""
    NUMBERS: Tuple[str, ...] = (
        "0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣",
        "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"
    )
    BLANK_TILE: str = "➗"
    RANGE_TILE: str = "➕"
    CORNER_TILE: str = "⏹️"
    ENERGY: str = "⚡️"
    HEART: str = "❤️"
    BLACK_HEART: str = "🖤"


@dataclass
class AsciiPalette(Palette):
    """ASCII-compatible palette for systems that don't support emojis."""
    # Numbers: each instance gets its own copy, which avoids surprises in the future.
    NUMBERS: Tuple[str, ...] = field(
        default_factory=lambda: tuple(["  "] * 10)
    )
    BLANK_TILE: str = "# "
    RANGE_TILE: str = "+ "
    CORNER_TILE: str = " "
    ENERGY: str = "⚡ "
    HEART: str = "❤ "
    BLACK_HEART: str = "X "


# === Default Params ===
DEFAULT_MINIMUM_BOARD_SIZE = 5
DEFAULT_RANDOM_SEED = 0
DEFAULT_LIFE_CAP = 3
DEFAULT_ACTION_RANGE = 2
DEFAULT_GIFT_HEART_COST = 1
DEFAULT_HEAL_SELF_COST = 2
DEFAULT_UPGRADE_COST = 5
DEFAULT_CAPTURE_COST = 5


FIRST_FILE_CONTENT = "# Players\nPLAYER Alice\nPLAYER Bob\nPLAYER Charlie\n\n"\
                     "# Tokens\nTOKEN 🍎 Alice\nTOKEN 🐬 Bob\nTOKEN 🦊 Charlie\n\n"\
                     "# Parameters\nRANDOM_SEED 123456789\nBOARD_SIZE default\n\n"\
                     "# === Game ON! ===\n\n"\
                     "# Day 1\nnext_turn\nhelp\n"


# === EXCEPTIONS ===
class GameError(ValueError): pass
class TokenError(GameError): pass
class PlayerError(GameError): pass
class APError(GameError): pass
class RangeError(GameError): pass
class InvalidMoveError(GameError): pass
class BoardSizeError(GameError): pass


def chebyshev_distance(pos1, pos2):
    """Chebyshev distance (max(dx, dy)) - king-move style in chess"""
    x1, y1 = pos1
    x2, y2 = pos2
    dx = abs(x1 - x2)
    dy = abs(y1 - y2)
    return max(dx, dy)


@dataclass
class Token:
    owner: str
    position: tuple[int,int] | None
    life: int
    life_cap: int
    range: int
    ap: int


# ===== Commands =====


class Command(ABC):
    def __init__(self, game: 'Game', player: str | None = None):
        self.game = game
        self.player = player

    @abstractmethod
    def execute(self) -> str:
        pass


class NextTurnCommand(Command):
    def execute(self) -> str:
        """
        Gives 1 AP to all live tokens.
        Then, every token voted by the jury gets also +1 AP.
        """
        game = self.game
        palette = self.game.palette

        if not self.game.tokens:
            raise TokenError("No tokens on board.")
        game.force_board_size_set()

        # update turn counter
        game.turn_counter += 1

        alive_count = 0
        jury_bonus_count = 0

        # 1) +1 AP to every living token
        for token, info in game.iter_token_items():
            if game.get_life(token) >= 1:
                game.increase_ap(token, amount=1)
                alive_count += 1

        # 2) +1 extra AP to each jury representative token
        for player, jury_token in game.iter_jury_items():
            if jury_token in game.tokens:
                if game.get_life(jury_token) >= 1:
                    game.increase_ap(jury_token, amount=1)
                    jury_bonus_count += 1

        summary = f"[{game.turn_counter}] Gave +1 {palette.ENERGY} to {alive_count} living token"
        if alive_count != 1:
            summary += "s"

        if jury_bonus_count > 0:
            summary += f" + extra {jury_bonus_count} {palette.ENERGY} from jury"

        return summary


class MoveCommand(Command):
    def __init__(self, game: 'Game', token: str, dx: int, dy: int, player: str | None = None):
        super().__init__(game, player)
        self.token = token
        self.dx = dx
        self.dy = dy

    def execute(self) -> str:
        """
        move [dx] [dy]
        Move the token by one square to the target position.
        Cost: 1 AP
        """
        game = self.game
        token = self.token
        dx = self.dx
        dy = self.dy
        board_size = game.get_board_size()
        palette = self.game.palette

        game.check_tokens_exist(token)
        game.check_has_ap(token, 1)

        # Calculate target position from current position + direction
        info = game.get_token_info(token)
        curr_x, curr_y = info.position
        x = curr_x + dx
        y = curr_y + dy
        new_position = (x, y)

        # Check if token is alive
        # Tokens with 0 HP remain on the board but cannot take actions
        if info.life <= 0:
            raise InvalidMoveError("Error: Token has 0 HP and cannot move")

        # Check board boundaries
        if not (0 <= x < board_size and 0 <= y < board_size):
            raise InvalidMoveError("Target position is out of bounds")

        # Check distance (must be exactly 1 square away, Chebyshev distance)
        # This allows horizontal, vertical, and diagonal moves
        if chebyshev_distance(new_position, info.position) != 1:
            raise RangeError("Target position must be adjacent (1 square away)")

        # Check collision (target tile must be empty)
        # get_tile returns the token name if occupied, or BLANK_TILE if empty
        if game.get_tile(x, y) not in (palette.BLANK_TILE, palette.RANGE_TILE):
            raise InvalidMoveError("Target position is occupied by another token")

        # Execute Move
        info.position = new_position
        game.spend_ap(token, 1)

        # Update priority
        game.update_priority(game.get_owner(token))

        return f"{token} moved to ({x}, {y}) (-1 {palette.ENERGY})"


class GiftCommand(Command):
    def __init__(self, game: 'Game', token_1: str, token_2: str, n_points: int = 1, player: str | None = None):
        super().__init__(game, player)
        self.token_1 = token_1
        self.token_2 = token_2
        self.n_points = n_points

    def execute(self) -> str:
        """
        gift [token_1] [token_2]
        Gift 1 AP from token_1 to token_2
        Cost: 1 AP from token_1
        """
        game = self.game
        token_1 = self.token_1
        token_2 = self.token_2
        n_points = self.n_points
        palette = self.game.palette

        game.check_tokens_exist(token_1, token_2)
        game.check_has_ap(token_1, n_points)
        game.check_range(token_1, token_2)

        # Execute gift
        game.spend_ap(token_1, n_points)
        game.increase_ap(token_2, n_points)

        # Update priority
        game.update_priority(game.get_owner(token_1))

        return f"{token_1} → {token_2} : gifted {n_points} {palette.ENERGY}"


class ShootCommand(Command):
    def __init__(self, game: 'Game', token_1: str, token_2: str, player: str | None = None):
        super().__init__(game, player)
        self.token_1 = token_1
        self.token_2 = token_2

    def execute(self) -> str:
        """
        shoot [token_1] [token_2]
        Shoot at token_2 → -1 life.
        If you kill a token, you steal their AP.
        Cost: 1 AP
        """
        game = self.game
        token_1 = self.token_1
        token_2 = self.token_2

        game.check_tokens_exist(token_1, token_2)
        game.check_has_ap(token_1, 1)
        game.check_has_life(token_2)
        game.check_range(token_1, token_2)

        # Execute shoot
        game.spend_ap(token_1, amount=1)
        game.decrease_life(token_2, amount=1)
        target_owner = game.get_owner(token_2)

        # Update priority
        game.update_priority(game.get_owner(token_1))

        # Check elimination to steal AP
        life = game.get_life(token_2)
        if life == 0:
            stolen = game.get_ap(token_2)
            game.transfer_ap(token_2, token_1, stolen)

        # Report
        msg = (f"{token_1} shot at {token_2}!  "
               f"{target_owner}'s {token_2} now has {life} life {game.get_lifebar(token_2)}")
        if game.is_player_eliminated(target_owner):
            game.add_to_jury(target_owner)
            msg += f" → {target_owner} eliminated and sent to jury!"

        return msg


class HealCommand(Command):
    def __init__(self, game: 'Game', token: str, player: str | None = None):
        super().__init__(game, player)
        self.token = token

    def execute(self) -> str:
        """
        heal [token]
        Heal own token +1 life (up to life_cap)
        Cost: 2 AP
        """
        game = self.game
        token = self.token

        game.check_tokens_exist(token)
        game.check_has_ap(token, game.heal_self_cost)
        game.check_life_cap(token)

        # Execute heal
        game.spend_ap(token, game.heal_self_cost)
        game.increase_life(token)

        # Update priority
        game.update_priority(game.get_owner(token))

        return f"{token} healed +1 💚 {game.get_lifebar(token)}"


class UpgradeCommand(Command):
    def __init__(self, game: 'Game', token: str, player: str | None = None):
        super().__init__(game, player)
        self.token = token

    def execute(self) -> str:
        """
        upgrade [token]
        Target token gets:
        - range increased by +1
        - life-cap increased by +1
        - healed by +1 heart
        Cost: 5 AP
        """
        game = self.game
        token = self.token

        game.check_tokens_exist(token)
        game.check_has_ap(token, game.upgrade_cost)

        # Execute upgrade
        game.spend_ap(token, game.upgrade_cost)
        game.increase_life_cap(token)
        game.increase_life(token)
        game.increase_range(token)

        # Update priority
        game.update_priority(game.get_owner(token))

        # Report
        new_cap = game.get_life_cap(token)
        new_range = game.get_range(token)
        msg = (f"{token} upgraded! "
               f"New life cap: {new_cap} {game.get_lifebar(token)}, "
               f"range: {new_range} {'🏹' * new_range}")

        return msg


class GiftHeartCommand(Command):
    def __init__(self, game: 'Game', token_1: str, token_2: str, n_hearts: int = 1, player: str | None = None):
        super().__init__(game, player)
        self.token_1 = token_1
        self.token_2 = token_2
        self.n_hearts = n_hearts

    def execute(self) -> str:
        """
        gift_hear [token_1] [token_2]
        Gift 1 heart from token_1 to token_2.
        token_1 can't remain without hears.
        token_2 must be in range of token_1.
        If token_2's owner was in jury → bring them back.
        Cost: 1 AP
        """
        game = self.game
        token_1 = self.token_1
        token_2 = self.token_2
        n_hearts = self.n_hearts

        game.check_tokens_exist(token_1, token_2)
        game.check_has_ap(token_1, game.gift_heart_cost)
        game.check_range(token_1, token_2)
        game.check_has_life(token_1, amount=n_hearts+1)
        game.check_life_cap(token_2, extra_hearts=+n_hearts)

        # Execute gift heart
        game.spend_ap(token_1, game.gift_heart_cost)
        game.decrease_life(token_1, n_hearts)
        game.increase_life(token_2, n_hearts)

        # Check if we revive someone from jury
        target_owner = game.get_owner(token_2)
        msg = f"{token_1} → {token_2} : gifted 1 {game.palette.HEART}"
        if target_owner in game.jury:
            game.remove_from_jury(target_owner)
            msg += f" → {target_owner} revived from jury!"

        # Update priority
        game.update_priority(game.get_owner(token_1))

        # Check if donor died from this action
        donor_owner = game.get_owner(token_1)
        if game.get_life(token_1) == 0 and game.is_player_eliminated(donor_owner):
            msg += f" → {donor_owner} sacrificed last heart"

        return msg


class CaptureCommand(Command):
    def __init__(self, game: 'Game', token_1: str, token_2: str, player: str | None = None):
        super().__init__(game, player)
        self.token_1 = token_1
        self.token_2 = token_2

    def execute(self) -> str:
        """
        capture [token_1] [token_2]
        Capture a KO enemy token and add it to your own pieces.
        The captured token gets +1 heart.
        Requires token_1 in contact with token_2 (distance=1).
        Cost: 5 AP
        """
        game = self.game
        token_1 = self.token_1
        token_2 = self.token_2

        game.check_tokens_exist(token_1, token_2)
        game.check_has_ap(token_1, game.capture_cost)
        game.check_range(token_1, token_2, distance=1)

        # Check if token_2 belongs to a different player
        owner_1 = game.get_owner(token_1)
        owner_2 = game.get_owner(token_2)
        if owner_1 == owner_2:
            raise InvalidMoveError(f"Cannot capture your own token ({token_2})")

        # Check if target token has 0 life
        if game.get_life(token_2) > 0:
            raise InvalidMoveError(f"Cannot capture {token_2} - it still has {game.get_life(token_2)} life")

        # Execute capture
        game.spend_ap(token_1, game.capture_cost)

        # Remove token from old owner's player list
        if token_2 in game.get_player_tokens(owner_2):
            game.remove_token_from_player(owner_2, token_2)

        # Add token to new owner's player list
        game.get_player_tokens(owner_1).append(token_2)

        # Update token ownership
        game.set_owner(token_2, owner_1)

        # Restore 1 life to the captured token (so it becomes usable)
        game.set_life(token_2, 1)

        # Update priority
        game.update_priority(game.get_owner(token_1))

        msg = (f"{token_1} captured {token_2} from {owner_2}! "
               f"{token_2} now belongs to {owner_1} and has been restored to 1 {game.palette.HEART}")

        # Check if the old owner is now eliminated (if they have no tokens left)
        if game.is_player_eliminated(owner_2):
            # If they're not already in jury, add them
            if owner_2 not in game.jury:
                # Find a representative token (could be the captured one or any other)
                game.set_jury_vote(owner_2, token_2)
                msg += f" → {owner_2} has no tokens left and joins the jury!"

        return msg


class VoteCommand(Command):
    def __init__(self, game: 'Game', player: str, token: str | None = None):
        super().__init__(game, player)
        self.token = token

    def execute(self) -> str:
        """
        vote [token]
        You become part of the jury as soon as you vote for a live tank to support.
        Vote for adding an extra AP to target token each turn.
        None for no vote (cancels previous vote)
        """
        game = self.game
        player = self.player
        token = self.token

        if not game.is_player_eliminated(player):
            raise InvalidMoveError(f"Player {player} has not been eliminated yet")

        if token is not None:
            game.check_tokens_exist(token)
            if not game.get_life(token):
                raise InvalidMoveError(f"You may only vote for a live token (not {token})")
            game.set_jury_vote(player, token)
            msg = f"{player} is now voting for {token}"
        else:
            msg = f"{player} isn't voting for anyone"

        # Update priority
        game.update_priority(player)

        return msg


class HelpCommand(Command):
    def execute(self) -> str:
        """
        help
        Help message.
        """
        game = self.game

        msg = "\nTank Tactics\n"
        for command, method in game.COMMAND_REGISTRY.items():
            msg += f'\n{command}'
            msg += method.__doc__ if method.__doc__ else '\n'
        msg += "\nUse the input file 'commands.txt' to create a game-state.\n"
        return msg


# ===== Super-Commands =====


class AddPlayerCommand(Command):
    def execute(self) -> str:
        """
        PLAYER [name]
        Add a new player to dict of player: tokens
        """
        game = self.game
        player = self.player

        if player in game.get_players():
            raise PlayerError(f"Player '{player}' already exists")

        game.add_player(player)
        game.set_random_seed()

        return f"Added player '{player}'"


class AddTokenCommand(Command):
    def __init__(self, game: 'Game', token: str, owner: str, player: str | None = None):
        super().__init__(game, player)
        self.token = token
        self.owner = owner

    def execute(self) -> str:
        """
        TOKEN [token] [player]
        Add a token to a player.
        """
        game = self.game
        token = self.token
        owner = self.owner

        # Check valid for duplicate token names
        assert type(token) is str
        if not 1 <= len(token) <= 2:
            raise TokenError(f"Token {token} must be one character long")
        if token in game.get_tokens():
            raise TokenError(f"Token '{token}' already exists")

        # Check for owner
        if owner not in game.get_players():
            raise PlayerError(f'Player "{owner}" not found')

        # Add token to player
        game.add_token_to_player(owner, token)

        # Initialize tokens
        game.set_token(token, owner)

        # Init position
        if game.get_board_size() is not None:
            game.set_random_token_position(token)

        msg = f"Added {token} to {owner}"
        position = game.get_position(token)
        if position is not None:
            msg += f" at {position}"
        return msg


class SetBoardSizeCommand(Command):
    def __init__(self, game: 'Game', size: int | str = None, player: str | None = None):
        super().__init__(game, player)
        self.size = size

    def execute(self) -> str:
        """
        BOARD_SIZE [size/"default"]
        Change the board size. WARNING: This resets the game state!
        """
        game = self.game
        size = self.size

        if game.board_size_locked:
            raise BoardSizeError(f'Board size locked at {game.board_size}')

        default_size = game.get_default_board_size()
        if size is None or type(size) is str:
            size = default_size
        area = size ** 2
        if area <= len(game.tokens) or size < game.minimum_board_size:
            raise BoardSizeError(f'Board too small! {size}')

        # Set board size
        game.board_size = size
        game.board_size_locked = True

        # Reset random seed & restart tokens
        random.seed(game.random_seed)
        game.init_tokens()

        msg = f"Board size set to {size}x{size}"
        if game.board_size == default_size:
            msg += " (default)"
        msg += " - tokens repositioned, RNG reset"
        return msg


class SetRandomSeedCommand(Command):
    def __init__(self, game: 'Game', seed: int = None, player: str | None = None):
        super().__init__(game, player)
        self.seed = seed

    def execute(self) -> str:
        return self.game.set_random_seed(self.seed)


class SetUpgradeCostCommand(Command):
    def __init__(self, game: 'Game', cost: int, player: str | None = None):
        super().__init__(game, player)
        self.cost = cost

    def execute(self) -> str:
        """
        UPGRADE_COST [cost]
        Change the AP cost for upgrading a token.
        """
        game = self.game
        cost = self.cost

        if cost < 1:
            raise RangeError("Upgrade cost must be at least 1")
        game.upgrade_cost = cost
        return f"Upgrade cost set to {cost} AP"


class SetHealSelfCostCommand(Command):
    def __init__(self, game: 'Game', cost: int, player: str | None = None):
        super().__init__(game, player)
        self.cost = cost

    def execute(self) -> str:
        """
        HEAL_SELF_COST [cost]
        Change the AP cost for healing own token.
        """
        game = self.game
        cost = self.cost

        if cost < 1:
            raise RangeError("Heal cost must be at least 1")

        game.heal_self_cost = cost
        return f"Heal self cost set to {cost} AP"


class SetGiftHeartCostCommand(Command):
    def __init__(self, game: 'Game', cost: int, player: str | None = None):
        super().__init__(game, player)
        self.cost = cost

    def execute(self) -> str:
        """
        GIFT_HEART_COST [cost]
        Change the AP cost for gifting a heart.
        """
        game = self.game
        cost = self.cost

        if cost < 1:
            raise RangeError("Gift heart cost must be at least 1")

        game.gift_heart_cost = cost
        return f"Gift heart cost set to {cost} AP"


# ===== Game class =====


class Game:

    def __init__(self,
                 palette=Palette(),
                 random_seed=DEFAULT_RANDOM_SEED,
                 life_cap=DEFAULT_LIFE_CAP,
                 action_range=DEFAULT_ACTION_RANGE,
                 minimum_board_size=DEFAULT_MINIMUM_BOARD_SIZE,
                 heal_self_cost=DEFAULT_HEAL_SELF_COST,
                 gift_heart_cost=DEFAULT_GIFT_HEART_COST,
                 upgrade_cost=DEFAULT_UPGRADE_COST,
                 capture_cost=DEFAULT_CAPTURE_COST):
        """
        Actions cost AP (action points).
        Player may shoot each other, gift AP, heal, and upgrade their tokens.
        When a token loses all the live, it remains on the field.
        A player with no live tokens is part of the jury. When all players receive AP,
        each tank that has a vote from the jury receives one more AP.
        """
        self.palette = palette
        self.life_cap = life_cap
        self.action_range = action_range
        self.minimum_board_size = minimum_board_size
        self.heal_self_cost = heal_self_cost
        self.gift_heart_cost = gift_heart_cost
        self.upgrade_cost = upgrade_cost
        self.capture_cost = capture_cost
        self.players: Dict[str: List[str]] = dict()  # dict of name: tokens with all the players
        self.tokens: Dict[str: Token] = dict()  # dict of token: Token
        self.jury: Dict[str: str] = dict()  # dict of player: token
        self.board_size = None
        self.random_seed = None
        self.priority = None  # Player names ranked from high to low priority
        self.turn_counter = None
        self.board_size_locked = False

        self.set_random_seed(random_seed)
        self.init_tokens()

    def iter_player_items(self) -> Iterator[tuple[str, list]]:
        """Deterministically iterate over player.items()"""
        for player in sorted(self.players):
            tokens = self.get_player_tokens(player)
            yield player, tokens

    def iter_token_items(self) -> Iterator[tuple[str, Token]]:
        """Deterministically iterate over tokens.items()"""
        for token in sorted(self.tokens):
            items = self.get_token_info(token)
            yield token, items

    def iter_jury_items(self) -> Iterator[tuple[str, tuple]]:
        """Deterministically iterate over jury.items()"""
        for player in sorted(self.jury):
            tokens = self.jury[player]
            yield player, tokens

    def init_tokens(self):
        """
        Set the initial values of the tokens.
        Initialization is the same regardless of the order of players/tokens.
        """
        self.turn_counter = 0
        self.tokens = dict()

        for player, tokens in self.iter_player_items():
            for token in sorted(tokens):
                self.set_token(token, player)

        # If board is ready then init positions too
        if self.board_size is not None:
            self.set_random_token_position(*sorted(self.tokens))

    def force_board_size_set(self):
        """
        Use this to make sure that the boar size is set,
        but without committing to one.
        """
        if self.board_size is None:
            self.board_size = self.get_default_board_size()

    def repr(self):
        self.force_board_size_set()
        out = self.get_board_tiles_repr()
        out += self.get_player_life_repr()
        return out

    def __str__(self):
        return self.repr()

    # ===== Getters =====

    def get_players(self) -> Dict[str, List[str]]:
        return self.players

    def get_tokens(self) -> Dict[str, Token]:
        return self.tokens

    def get_board_size(self) -> int:
        return self.board_size

    def get_token_info(self, token: str) -> Token:
        return self.tokens[token]

    def get_player_tokens(self, player: str) -> List[str]:
        return self.players[player]

    def get_life(self, token):
        return self.get_token_info(token).life

    def get_life_cap(self, token):
        return self.get_token_info(token).life_cap

    def get_ap(self, token):
        return self.get_token_info(token).ap

    def get_position(self, token):
        return self.get_token_info(token).position

    def get_range(self, token):
        return self.get_token_info(token).range

    def get_owner(self, token):
        return self.get_token_info(token).owner

    def get_default_board_size(self, k=0.4) -> int:
        """
        Recommended board size.
        Keeps the density of tokens inversely proportional to the action radius.
        """
        action_diameter = 2 * self.action_range + 1
        token_area = action_diameter ** 2
        total_token_area = token_area * len(self.tokens)
        board_area = total_token_area * k
        board_size = int(board_area ** 0.5)
        return max(board_size, self.minimum_board_size)

    def get_tile(self, x, y):
        """
        Returns a token if present in that position.
        If position is empty but within range of any of the player's tokens,
        returns RANGE_TILE. Otherwise returns BLANK_TILE.
        """
        pos = (x, y)

        # First check if there's a token at this position
        for token, items in self.iter_token_items():
            if items.position == pos:
                return token

        # Color differently tiles close to live tokens
        for token, info in self.iter_token_items():
            if self.get_life(token) > 0:
                # Check only tokens owned by the specified player that are alive
                token_pos = info.position
                distance = chebyshev_distance((x, y), token_pos)
                if 0 < distance <= info.range:
                    return self.palette.RANGE_TILE

        return self.palette.BLANK_TILE

    def get_lifebar(self, token: str):
        red = self.get_token_info(token).life
        black = self.get_token_info(token).life_cap - red
        return f'[{self.palette.HEART * red}{self.palette.BLACK_HEART * black}]'

    def get_board_tiles_repr(self, offset=6):
        turn_bar = f'\nTurn {self.turn_counter}'
        out = f'{turn_bar:{self.board_size * 2 + 2 + offset}}'
        out += 'Priority & Votes'
        out += '\n'
        number_chars = [f"{c}" for c in self.palette.NUMBERS]
        n_numbers = len(number_chars)

        for j in reversed(range(self.board_size)):
            # Numbers
            out += number_chars[j % n_numbers]

            # Tiles
            for i in range(self.board_size):
                out += self.get_tile(i, j)
            rev_j = self.board_size - j - 1

            if rev_j < len(self.priority):
                # Priority tab
                player = self.priority[rev_j]
                out += " " * offset + f"- {player}"

                # Jury Vote
                if player in self.jury:
                    out += f' -> {self.jury[player]}'

            out += '\n'

        out += self.palette.CORNER_TILE
        for i in range(self.board_size):
            out += number_chars[i % n_numbers]
        out += '\n'
        return out

    def get_player_life_repr(self, name_length=10):
        out = ''
        for player, tokens in self.iter_player_items():
            if not self.is_player_eliminated(player):
                for i, token in enumerate(tokens):
                    if i == 0:
                        out += f'\n {player:{name_length-1}}'
                    else:
                        out += " " * name_length
                    life_bar = self.get_lifebar(token)
                    ap = self.get_ap(token)
                    energy_bar = f"{self.palette.ENERGY * ap} "
                    bar = f' {token} {life_bar}{energy_bar}'
                    out += f"{bar}\n"
        out += '\n'
        return out

    def get_jury_repr(self):
        """Jury (display vote if voted, otw just display user)"""
        out = ''
        if not self.tokens:
            return out
        for player, token in self.iter_player_items():
            if self.is_player_eliminated(player):
                out += f'\n{player:>7} -> '
                if player in self.jury:
                    out += f'{self.jury[player]}'
                else:
                    out += f'no vote'
        out += '\n'
        return out

    def get_priority_repr(self):
        return '\nPriority: ' + ", ".join(self.priority) if self.tokens else ''

    # ===== Setters =====

    def set_token(self, token, owner):
        self.tokens[token] = Token(
            owner=owner,
            position=None,
            ap=0,
            life=self.life_cap,
            life_cap=self.life_cap,
            range=self.action_range,
        )

    def set_owner(self, token, player):
        self.get_token_info(token).owner = player

    def set_life(self, token, amount: int):
        self.get_token_info(token).life = amount

    def set_random_token_position(self, *tokens):
        positions = [(i, j) for i in range(self.board_size) for j in range(self.board_size)]
        existing_positions = {info.position for token, info in self.iter_token_items()}
        available_positions = [p for p in positions if p not in existing_positions]

        if not len(available_positions):
            raise BoardSizeError("Not enough space on board for new tokens")

        random.shuffle(available_positions)

        msg = 'New token positions: '
        for token in tokens:
            position = available_positions.pop()
            self.get_token_info(token).position = position
            msg += f" {token} -> {position} "

        return msg

    def set_jury_vote(self, player, token: str | None):
        self.jury[player] = token

    def set_random_seed(self, seed: int = None):
        """
        RANDOM_SEED [seed]
        Set the random seed for reproducibility.
        """
        if seed is None:
            msg = "Random seed cannot be None"
        elif seed == self.random_seed:
            msg = f"Random seed was already {seed}"
        else:
            # Overwrite random seed
            self.random_seed = seed
            random.seed(seed)
            msg = f"Random seed set to {seed}"

        # Reset priority
        self.priority = sorted(self.players)
        random.shuffle(self.priority)

        return msg

    # ===== Exceptions =====

    def check_tokens_exist(self, *tokens):
        """Raise exception if any of the tokens don't exist."""
        self.force_board_size_set()
        for token in tokens:
            if token not in self.tokens:
                raise TokenError(token)

    def check_has_ap(self, token, cost):
        """Verify that token has enough AP to pay the cost."""
        if self.get_ap(token) < cost:
            raise APError(f"{token} AP: {self.get_ap(token)} < {cost}")

    def check_has_life(self, token, amount=1):
        """Verify that token has enough AP to pay the cost."""
        if self.get_life(token) < amount:
            raise GameError(f"{token} life: {self.get_life(token)} < {amount}")

    def check_life_cap(self, token, extra_hearts=1):
        """
        Verify that the token can receive the extra hearts.
        """
        if extra_hearts < 0:
            raise ValueError("Extra hearts amount can't be negative.")
        if self.get_life(token) + extra_hearts > self.get_life_cap(token):
            raise InvalidMoveError(f"{token} cannot receive any more hearts (did you mean 'gift_heart'?)")

    def check_range(self, token_1, token_2, distance=None):
        """
        Check if token_2 is within token_1's range.
        If `distance` is provided, it overrides token_1's natural range.
        """
        d = self.distance(token_1, token_2)
        r = distance if distance is not None else self.get_range(token_1)
        if d > r:
            raise RangeError(f"{token_2} is too far from {token_1} ({d} > {r})")

    # ===== Helper methods =====

    def add_player(self, player: str):
        self.players[player] = []

    def add_token_to_player(self, player, token):
        self.players[player].append(token)

    def remove_token_from_player(self, player, token):
        self.players[player].remove(token)

    def increase_life(self, token, amount=1):
        """Increase or decrease token life."""
        if amount < 0:
            raise ValueError("Amount can't be negative.")
        self.check_life_cap(token, extra_hearts=amount)
        self.get_token_info(token).life += amount

    def decrease_life(self, token, amount=1):
        """Increase or decrease token life."""
        if amount < 0:
            raise ValueError("Amount can't be negative.")
        self.check_has_life(token, amount=amount)
        self.get_token_info(token).life -= amount

    def increase_life_cap(self, token, amount=1):
        self.get_token_info(token).life_cap += amount

    def increase_range(self, token, amount=1):
        self.get_token_info(token).range += amount

    def increase_ap(self, token, amount):
        if amount < 0:
            raise ValueError('amount must be positive')
        self.get_token_info(token).ap += amount

    def spend_ap(self, token, amount):
        if amount < 0:
            raise ValueError('amount must be positive')
        self.check_has_ap(token, cost=amount)
        self.get_token_info(token).ap -= amount

    def transfer_ap(self, token_1, token_2, amount):
        """Transfer AP from token_1 to token_2"""
        self.spend_ap(token_1, amount)
        self.increase_ap(token_2, amount)

    def distance(self, token_1, token_2) -> float:
        """Chebyshev distance (max(dx, dy)) - king-move style in chess."""
        self.check_tokens_exist(token_1, token_2)
        pos1 = self.get_token_info(token_1).position
        pos2 = self.get_token_info(token_2).position
        return chebyshev_distance(pos1, pos2)

    def is_in_range(self, token_1, token_2) -> bool:
        """Check if token_2 is within token_1's current range."""
        if token_1 not in self.tokens or token_2 not in self.tokens:
            return False
        return self.distance(token_1, token_2) <= self.get_range(token_1)

    def is_player_eliminated(self, player) -> bool:
        """Returns True if player has no living tokens left."""
        for token, info in self.iter_token_items():
            if info.owner == player and info.life > 0:
                return False
        return True

    def update_priority(self, player):
        """
        When a player performs an action, they fall
        to the bottom of the priority list.
        """
        i = self.priority.index(player)
        self.priority.pop(i)
        self.priority.append(player)

    def add_to_jury(self, player):
        self.set_jury_vote(player, None)

    def remove_from_jury(self, player):
        del self.jury[player]

    # ===== List of all commands =====
    COMMAND_REGISTRY = {
        "next_turn": NextTurnCommand,
        "move": MoveCommand,
        "gift": GiftCommand,
        "shoot": ShootCommand,
        "heal": HealCommand,
        "gift_heart": GiftHeartCommand,
        "upgrade": UpgradeCommand,
        "capture": CaptureCommand,
        "vote": VoteCommand,
        "help": HelpCommand,
        "PLAYER": AddPlayerCommand,
        "TOKEN": AddTokenCommand,
        "RANDOM_SEED": SetRandomSeedCommand,
        "BOARD_SIZE": SetBoardSizeCommand,
        "UPGRADE_COST": SetUpgradeCostCommand,
        "HEAL_SELF_COST": SetHealSelfCostCommand,
        "GIFT_HEART_COST": SetGiftHeartCostCommand,
    }


def convert_args(raw_args, params):
    """Try to match the parameter's type."""
    converted_args = []
    for raw, param in zip(raw_args, params):
        if param.annotation in (int, float):
            converted_args.append(param.annotation(raw))
        else:
            try:
                converted_args.append(int(raw))
            except ValueError:
                converted_args.append(raw)
    return converted_args


def execute_text_command(game: Game, line: str) -> str:
    """Execute command line on game using Command Pattern."""
    line = line.strip()
    if not line or line.startswith("#"):
        return line

    parts = line.split()
    command_key = parts[0]
    raw_args = parts[1:]

    if command_key not in Game.COMMAND_REGISTRY:
        raise GameError(f"Unknown command: {command_key}")

    # Get the Command Class
    command_class = Game.COMMAND_REGISTRY[command_key]

    # Prepare arguments for the Command Constructor
    # We inspect the Command class __init__ to map args, similar to previous logic
    # Note: 'game' is always passed first, 'player' is optional keyword or positional
    sig = inspect.signature(command_class.__init__)
    params = [p for p in sig.parameters.values() if p.name not in ('self', 'game')]
    converted_args = convert_args(raw_args, params)

    # Instantiate Command with game instance
    # Note: We assume 'player' is handled via kwargs if needed, or passed as part of args
    # For simplicity in this hook, we pass game + converted args.
    # If 'player' context is needed, it should be injected here.
    command_instance = command_class(game, *converted_args)

    # Execute
    return command_instance.execute()


def run_commands_from_file(game: Game, filepath: str) -> tuple[str, list]:
    """
    Run all the commands in the file.
    """
    game_state = game.repr()
    report = []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                result = execute_text_command(game, line)
                game_state = game.repr()
                report.append(result)
            except Exception as e:
                report.append(f"❌ Error: {e}")
                break
    return game_state, report


def get_file_hash(filepath):
    """Compute MD5 hash of file contents."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def display_game_state(input_file, output_file, palette):
    """Display console output and save game state."""
    # Create fresh game instance
    game = Game(palette=palette)
    game_state, report = run_commands_from_file(game, input_file)
    messages = [s for s in report if s.strip() and not s.startswith('#')]
    last_report = messages[-1] if len(messages) else "(nothing to report)"
    msg = f"🔄 Auto-watch mode started (Press Ctrl+C to quit).\n"
    msg += last_report + '\n'
    msg += game_state

    # Save game state
    output = str(game)
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
    except IOError as e:
        msg += f"\n⚠️ Failed to save state to {output_file}: {e}\n"

    # Display message
    clear_screen()
    print(msg)


def create_input_file(input_file):
    """Create an input file and write 'help' command inside."""
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(FIRST_FILE_CONTENT)
        return True
    except IOError as e:
        print(f"⚠️ Failed to create input file {input_file}: {e}")
        return False


def main(period=0.5, ascii_mode=False):

    # Choose emoji palette
    if not ascii_mode:
        palette = Palette()
    else:
        palette = AsciiPalette()

    # Set default file paths
    input_file = "commands.txt"
    output_file = "game_state.txt"

    # Override with command line arguments if provided
    if len(sys.argv) >= 2:
        input_file = sys.argv[1]
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]

    # Validate input file exists
    if not os.path.exists(input_file):
        create_input_file(input_file)

    # Track previous file hash
    prev_file_hash = get_file_hash(input_file)

    # --- INITIAL DISPLAY ---
    display_game_state(input_file, output_file, palette=palette)

    try:
        while True:
            time.sleep(period)

            # Check if file still exists
            if not os.path.exists(input_file):
                print(f"⚠️  Warning: '{input_file}' no longer exists! ")
                continue

            # Compute current file hash
            current_file_hash = get_file_hash(input_file)

            # Check if file hash changed
            if current_file_hash != prev_file_hash:
                display_game_state(input_file, output_file, palette=palette)

                # Update previous file hash
                prev_file_hash = current_file_hash

    except KeyboardInterrupt:
        clear_screen()
        print("👋 Exiting.")


if __name__ == '__main__':
    main(ascii_mode=False)
