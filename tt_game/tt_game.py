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
from typing import Dict


# === BOARD ===
NUMBERS = ("0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣")
BLANK_TILE = "➗"
RANGE_TILE = "➕"
CORNER_TILE = "⏹️"

# === ASCII BOARD ===
NUMBERS_ASCII = [" "] * 10
# NUMBERS_ASCII = ("⓪", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨")
BLANK_TILE_ASCII = "#"
RANGE_TILE_ASCII = "+"
CORNER_TILE_ASCII = " "

# === Default Params ===
DEFAULT_BOARD_SIZE = 10
DEFAULT_RANDOM_SEED = 0
DEFAULT_LIFE_CAP = 3
DEFAULT_ACTION_RANGE = 2
DEFAULT_MINIMUM_BOARD_SIZE = 5
DEFAULT_GIFT_HEART_COST = 1
DEFAULT_HEAL_SELF_COST = 2
DEFAULT_CAPTURE_COST = 4
DEFAULT_UPGRADE_COST = 5


# === EXCEPTIONS ===
class GameError(ValueError): pass
class TokenError(GameError): pass
class PlayerError(GameError): pass
class APError(GameError): pass
class RangeError(GameError): pass
class InvalidMoveError(GameError): pass
class BoardSizeError(GameError): pass


class Game:

    def __init__(self, players: Dict[str, list] = None,
                 board_size=None,
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
        self.players = players if players else dict()  # dict of name: tokens with all the players
        self.tokens: Dict[str: dict] = dict()  # dict of token: owner, position, life, AP
        self.jury: Dict[str: str] = dict()  # dict of player: token
        self.board_size = board_size
        self.life_cap = life_cap
        self.action_range = action_range
        self.minimum_board_size = minimum_board_size
        self.heal_self_cost = heal_self_cost
        self.gift_heart_cost = gift_heart_cost
        self.upgrade_cost = upgrade_cost
        self.capture_cost = capture_cost
        self.random_seed = None
        self.priority = None  # Player names ranked from high to low priority
        self.turn_counter = None
        self.board_size_locked = False

        self.set_random_seed(random_seed)
        if self.board_size is not None:
            self.init_tokens()

    def _iter_player_items(self):
        """Deterministically iterate over player.items()"""
        for player in sorted(self.players):
            tokens = self.players[player]
            yield player, tokens

    def iter_token_items(self):
        """Deterministically iterate over tokens.items()"""
        for token in sorted(self.tokens):
            items = self.tokens[token]
            yield token, items

    def _iter_jury_items(self):
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

        for player, tokens in self._iter_player_items():
            for token in sorted(tokens):
                self.tokens[token] = {
                    "owner": player,
                    "position": None,
                    "AP": 0,
                    "life": self.life_cap,
                    "life_cap": self.life_cap,
                    "range": self.action_range,
                }

        # If board is ready then init positions too
        if self.board_size is not None:
            self.set_random_token_position(*sorted(self.tokens))

    def force_board_size_set(self):
        """
        Use this to make sure that the boar size is set,
        but without committing to one.
        """
        if self.board_size is None:
            self.set_board_size_command(lock_board_size=False)

    def repr(self, ascii_mode=False):
        self.force_board_size_set()
        out = self.get_board_tiles_repr(ascii_mode)
        out += self.get_player_life_repr()
        out += self.get_jury_repr()
        out += self.get_priority()
        return out

    def __str__(self):
        return self.repr(ascii_mode=False)

    # === Exceptions ===

    def check_tokens_exist(self, *tokens):
        """Raise exception if any of the tokens don't exist."""
        self.force_board_size_set()
        for token in tokens:
            if token not in self.tokens:
                raise TokenError(token)

    def check_has_ap(self, token, cost):
        """Verify that token has enough AP to pay the cost."""
        if self.tokens[token]["AP"] < cost:
            raise APError(f"{token} AP: {self.get_ap(token)} < {cost}")

    def check_range(self, token_1, token_2, distance=None):
        """
        Check if token_2 is within token_1's range.
        If `distance` is provided, it overrides token_1's natural range.
        """
        d = self.distance(token_1, token_2)
        r = distance if distance is not None else self.tokens[token_1]["range"]
        if d > r:
            raise RangeError(f"{token_2} is too far from {token_1} ({d} > {r})")

    def check_life_cap(self, token, extra_hearts=1):
        """
        Verify that the token's harts will stay within the bounds
        after extra_hearts are applied.
        """
        if self.get_life(token) + extra_hearts > self.tokens[token]["life_cap"]:
            raise InvalidMoveError(f"{token} cannot receive any more hearts")
        elif self.get_life(token) + extra_hearts < 0:
            raise InvalidMoveError(f"{token} does not have enough hearts")

    # === Getters ===

    def get_life(self, token):
        return self.tokens[token]['life']

    def get_ap(self, token):
        return self.tokens[token]['AP']

    def get_position(self, token):
        return self.tokens[token]['position']

    def get_range(self, token):
        return self.tokens[token]['range']

    def get_owner(self, token):
        return self.tokens[token]['owner']

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
        for token, info in self.iter_token_items():
            if info["position"] == pos:
                return token

        # Color differently tiles close to live tokens
        for token, info in self.iter_token_items():
            if self.get_life(token) > 0:
                # Check only tokens owned by the specified player that are alive
                token_pos = info["position"]
                # Chebyshev distance
                distance = max(abs(x - token_pos[0]), abs(y - token_pos[1]))
                if 0 < distance <= info["range"]:
                    return RANGE_TILE

        return BLANK_TILE

    def get_lifebar(self, token: str):
        info = self.tokens[token]
        red = info["life"]
        black = info["life_cap"] - info["life"]
        return f'[{"❤️" * red}{"🖤" * black}]'

    def get_board_tiles_repr(self, ascii_mode=False):
        out = f'\nTurn {self.turn_counter}\n'
        if ascii_mode:
            number_chars = [f" {c}" for c in NUMBERS_ASCII]
        else:
            number_chars = NUMBERS
        n_numbers = len(number_chars)
        for j in reversed(range(self.board_size)):
            out += number_chars[j % n_numbers]
            for i in range(self.board_size):
                out += self.get_tile(i, j)
            out += '\n'
        out += CORNER_TILE_ASCII if ascii_mode else CORNER_TILE
        for i in range(self.board_size):
            out += number_chars[i % n_numbers]
        out += '\n'
        return out

    def get_player_life_repr(self, name_length=8, bar_length=16):
        out = ''
        for player, tokens in self._iter_player_items():
            if not self.is_player_eliminated(player):
                out += f'\n{player:{name_length}}'
                for token in tokens:
                    life_bar = self.get_lifebar(token)
                    ap = self.get_ap(token)
                    energy_bar = f"{"⚡️" * ap} "
                    bar = f' {token} {life_bar} {energy_bar}'
                    out += f"{bar:{bar_length}}"
        out += '\n'
        return out

    def get_jury_repr(self):
        """Jury (display vote if voted, otw just display user)"""
        out = ''
        if not self.tokens:
            return out
        for player, token in self._iter_player_items():
            if self.is_player_eliminated(player):
                if player in self.jury:
                    out += f'\n{player:>7} -> {self.jury[player]}'
                else:
                    out += f'\n{player:>7} -> no vote'
        out += '\n'
        return out

    def get_priority(self):
        return '\nPriority: ' + ", ".join(self.priority) if self.tokens else ''

    # === Setters ===

    def set_owner(self, token, player):
        self.tokens[token]['owner'] = player

    def set_life(self, token, amount: int):
        self.tokens[token]["life"] = amount

    def set_random_seed(self, seed: int = None):
        """
        RANDOM_SEED [seed]
        Set the random seed for reproducibility.
        Usage: set_random_seed(42)
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

    def set_random_token_position(self, *tokens):
        positions = [(i, j) for i in range(self.board_size) for j in range(self.board_size)]
        existing_positions = {info["position"] for token, info in self.iter_token_items()}
        available_positions = [p for p in positions if p not in existing_positions]

        if not len(available_positions):
            raise BoardSizeError("Not enough space on board for new tokens")

        random.shuffle(available_positions)

        msg = 'New token positions: '
        for token in tokens:
            position = available_positions.pop()
            self.tokens[token]['position'] = position
            msg += f" {token} -> {position} "

        return msg

    # === Helper methods ===

    def increase_life(self, token, amount=1):
        self.check_life_cap(token, extra_hearts=amount)
        self.tokens[token]['life'] += amount

    def increase_life_cap(self, token, amount=1):
        self.tokens[token]['life_cap'] += amount

    def increase_range(self, token, amount=1):
        self.tokens[token]['range'] += amount

    def increase_ap(self, token, amount):
        if amount < 0:
            raise ValueError('amount must be positive')
        self.tokens[token]['AP'] += amount

    def spend_ap(self, token, amount):
        if amount < 0:
            raise ValueError('amount must be positive')
        self.check_has_ap(token, cost=amount)
        self.tokens[token]['AP'] -= amount

    def transfer_ap(self, token_1, token_2, amount):
        """Transfer AP from token_1 to token_2"""
        self.spend_ap(token_1, amount)
        self.increase_ap(token_2, amount)

    def distance(self, token_1, token_2) -> float:
        """Chebyshev distance (max(dx, dy)) - king-move style in chess"""
        self.check_tokens_exist(token_1, token_2)
        x1, y1 = self.tokens[token_1]["position"]
        x2, y2 = self.tokens[token_2]["position"]
        return max(abs(x1 - x2), abs(y1 - y2))

    def is_in_range(self, token_1, token_2) -> bool:
        """Check if token_2 is within token_1's current range"""
        if token_1 not in self.tokens or token_2 not in self.tokens:
            return False
        return self.distance(token_1, token_2) <= self.tokens[token_1]["range"]

    def is_player_eliminated(self, player) -> bool:
        """Returns True if player has no living tokens left"""
        for token, info in self.iter_token_items():
            if info["owner"] == player and info["life"] > 0:
                return False
        return True

    def update_priority(self, player):
        i = self.priority.index(player)
        self.priority.pop(i)
        self.priority.append(player)

    # === Commands ===

    def give_ap_to_all_command(self) -> str:
        """
        Gives 1 AP to all live tokens.
        Then, every token voted by the jury gets also +1 AP.
        """
        if not self.tokens:
            raise TokenError("No tokens on board.")
        self.force_board_size_set()

        # update turn counter
        self.turn_counter += 1

        alive_count = 0
        jury_bonus_count = 0

        # 1) +1 AP to every living token
        for token, info in self.iter_token_items():
            if info["life"] >= 1:
                info["AP"] += 1
                alive_count += 1

        # 2) +1 extra AP to each jury representative token
        for player, jury_token in self._iter_jury_items():
            if jury_token in self.tokens:
                token_info = self.tokens[jury_token]
                if token_info["life"] >= 1:
                    token_info["AP"] += 1
                    jury_bonus_count += 1

        summary = f"[{self.turn_counter}] Gave +1 ⚡️ to {alive_count} living token"
        if alive_count != 1:
            summary += "s"

        if jury_bonus_count > 0:
            summary += f" + extra {jury_bonus_count} ⚡️ from jury"

        return summary

    def move_command(self, token: str, dx: int, dy: int):
        """
        move [dx] [dy]
        Move the token by one square to the target position.
        Cost: 1 AP
        """
        self.check_tokens_exist(token)
        self.check_has_ap(token, 1)

        # Calculate target position from current position + direction
        info = self.tokens[token]
        curr_x, curr_y = info["position"]
        x = curr_x + dx
        y = curr_y + dy

        # Check if token is alive
        # Tokens with 0 HP remain on the board but cannot take actions
        if info["life"] <= 0:
            raise InvalidMoveError("Error: Token has 0 HP and cannot move")

        curr_x, curr_y = info["position"]

        # Check board boundaries
        if not (0 <= x < self.board_size and 0 <= y < self.board_size):
            raise InvalidMoveError("Target position is out of bounds")

        # Check distance (must be exactly 1 square away, Chebyshev distance)
        # This allows horizontal, vertical, and diagonal moves
        if max(abs(x - curr_x), abs(y - curr_y)) != 1:
            raise RangeError("Target position must be adjacent (1 square away)")

        # Check collision (target tile must be empty)
        # get_tile returns the token name if occupied, or BLANK_TILE if empty
        if self.get_tile(x, y) not in (BLANK_TILE, RANGE_TILE):
            raise InvalidMoveError("Target position is occupied by another token")

        # Execute Move
        info["position"] = (x, y)
        self.spend_ap(token, 1)

        # Update priority
        self.update_priority(self.get_owner(token))

        return f"{token} moved to ({x}, {y}) (-1 ⚡️)"

    def gift_command(self, token_1: str, token_2: str, n_points=1) -> str:
        """
        gift [token_1] [token_2]
        Gift 1 AP from token_1 to token_2
        Cost: 1 AP from token_1
        """
        self.check_tokens_exist(token_1, token_2)
        self.check_has_ap(token_1, n_points)
        self.check_range(token_1, token_2)

        # Execute gift
        self.spend_ap(token_1, n_points)
        self.increase_ap(token_2, n_points)

        # Update priority
        self.update_priority(self.get_owner(token_1))

        return f"{token_1} → {token_2} : gifted {n_points} ⚡️"

    def shoot_command(self, token_1: str, token_2: str) -> str:
        """
        shoot [token_1] [token_2]
        Shoot at token_2 → -1 life.
        If you kill a token, you steal their AP.
        Cost: 1 AP
        """
        self.check_tokens_exist(token_1, token_2)
        self.check_has_ap(token_1, 1)
        self.check_range(token_1, token_2)

        # Execute shoot
        self.spend_ap(token_1, 1)
        self.tokens[token_2]["life"] -= 1
        target_owner = self.tokens[token_2]["owner"]

        # Update priority
        self.update_priority(self.get_owner(token_1))

        # Check elimination to steal AP
        life = self.get_life(token_2)
        if life == 0:
            stolen = self.get_ap(token_2)
            self.transfer_ap(token_2, token_1, stolen)

        # Report
        msg = (f"{token_1} shot at {token_2}!  "
               f"{target_owner}'s {token_2} now has {life} life {self.get_lifebar(token_2)}")
        if self.is_player_eliminated(target_owner):
            # No need to populate the jury
            msg += f" → {target_owner} eliminated and sent to jury!"

        return msg

    def heal_self_command(self, token: str) -> str:
        """
        heal [token]
        Heal own token +1 life (up to life_cap)
        Cost: 2 AP
        """
        self.check_tokens_exist(token)
        self.check_has_ap(token, self.heal_self_cost)
        self.check_life_cap(token)

        # Execute heal
        self.spend_ap(token, self.heal_self_cost)
        self.tokens[token]["life"] += 1

        # Update priority
        self.update_priority(self.get_owner(token))

        return f"{token} healed +1 💚 {self.get_lifebar(token)}"

    def upgrade_token_command(self, token: str) -> str:
        """
        upgrade [token]
        Target token gets:
        - range increased by +1
        - life-cap increased by +1
        - healed by +1 heart
        Cost: 5 AP
        """
        self.check_tokens_exist(token)
        self.check_has_ap(token, self.upgrade_cost)

        # Execute upgrade
        self.spend_ap(token, self.upgrade_cost)
        self.increase_life_cap(token)
        self.increase_life(token)
        self.increase_range(token)

        # Update priority
        self.update_priority(self.get_owner(token))

        # Report
        new_cap = self.tokens[token]["life_cap"]
        new_range = self.tokens[token]["range"]
        msg = (f"{token} upgraded! "
               f"New life cap: {new_cap} {self.get_lifebar(token)}, "
               f"range: {new_range} {'🏹' * new_range}")

        return msg

    def gift_heart_command(self, token_1: str, token_2: str) -> str:
        """
        gift_hear [token_1] [token_2]
        Gift 1 heart (life) from token_1 to token_2 (they must be in contact)
        If token_2's owner was in jury → bring them back
        Cost: 2 AP
        """
        self.check_tokens_exist(token_1, token_2)
        self.check_has_ap(token_1, self.gift_heart_cost)
        self.check_range(token_1, token_2, distance=1)
        self.check_life_cap(token_1, extra_hearts=-1)
        self.check_life_cap(token_2, extra_hearts=+1)

        # Execute gift heart
        self.spend_ap(token_1, self.gift_heart_cost)
        self.tokens[token_1]["life"] -= 1
        self.tokens[token_2]["life"] += 1

        target_owner = self.tokens[token_2]["owner"]
        msg = f"{token_1} → {token_2} : gifted 1 ❤️"

        # Check if we revive someone from jury
        if target_owner in self.jury:
            del self.jury[target_owner]
            msg += f" → {target_owner} revived from jury!"

        # Check if donor died from this action
        donor_owner = self.tokens[token_1]["owner"]
        if self.tokens[token_1]["life"] == 0 and self.is_player_eliminated(donor_owner):
            msg += f" → {donor_owner} eliminated (sacrificed last heart)"

        # Update priority
        self.update_priority(self.get_owner(token_1))

        return msg

    def capture_command(self, token_1: str, token_2: str) -> str:
        """
        capture [token_1] [token_2]
        Capture a KO enemy token and add it to your own pieces.
        Requires token_1 in contact with token_2 (distance=1).
        Cost: 5 AP
        """
        self.check_tokens_exist(token_1, token_2)
        self.check_has_ap(token_1, self.capture_cost)
        self.check_range(token_1, token_2, distance=1)

        # Check if token_2 belongs to a different player
        owner_1 = self.get_owner(token_1)
        owner_2 = self.get_owner(token_2)
        if owner_1 == owner_2:
            raise InvalidMoveError(f"Cannot capture your own token ({token_2})")

        # Check if target token has 0 life
        if self.get_life(token_2) > 0:
            raise InvalidMoveError(f"Cannot capture {token_2} - it still has {self.get_life(token_2)} life")

        # Execute capture
        self.spend_ap(token_1, self.capture_cost)

        # Remove token from old owner's player list
        if token_2 in self.players[owner_2]:
            self.players[owner_2].remove(token_2)

        # Add token to new owner's player list
        self.players[owner_1].append(token_2)

        # Update token ownership
        self.set_owner(token_2, owner_1)

        # Optional: Restore 1 life to the captured token (so it becomes usable)
        self.set_life(token_2, 1)

        msg = (f"{token_1} captured {token_2} from {owner_2}! "
               f"{token_2} now belongs to {owner_1} and has been restored to 1 ❤️")

        # Check if the old owner is now eliminated (if they have no tokens left)
        if self.is_player_eliminated(owner_2):
            # If they're not already in jury, add them
            if owner_2 not in self.jury:
                # Find a representative token (could be the captured one or any other)
                self.jury[owner_2] = token_2
                msg += f" → {owner_2} has no tokens left and joins the jury!"

        # Update priority
        self.update_priority(self.get_owner(token_1))

        return msg

    def jury_vote_command(self, player: str, token: str = None):
        """
        vote [token]
        You become part of the jury as soon as you vote for a live tank to support.
        Vote for adding an extra AP to target token each turn.
        None for no vote (cancels previous vote)
        """
        if not self.is_player_eliminated(player):
            raise InvalidMoveError(f"Player {player} has not been eliminated yet")
        self.check_tokens_exist(token)
        if not self.tokens[token]["life"]:
            raise InvalidMoveError(f"You may only vote for a live token (not {token})")
        if token is not None:
            self.jury[player] = token
            msg = f"{player} is now voting for {token}"
        else:
            msg = f"{player} isn't voting for anyone"

        # Update priority
        self.update_priority(player)

        return msg

    def help_message_command(self):
        """
        help
        Help message.
        """
        msg = "\nTank Tactics\n"
        for command, method in self.COMMANDS.items():
            msg += f'\n{command}'
            msg += method.__doc__ if method.__doc__ else '\n'
        msg += "\nUse the input file 'commands.txt' to create a game-state.\n"
        return msg

    # === Super-commands ===

    def add_player_command(self, player_name: str):
        """
        PLAYER [name]
        Add a new player to dict of player: tokens
        """
        if player_name in self.players:
            raise PlayerError(f"Player '{player_name}' already exists")

        self.players[player_name] = []

        self.set_random_seed()

        return f"Added player '{player_name}'"

    def add_token_command(self, token: str, owner: str):
        """
        TOKEN [token] [player]
        Add a token to a player.
        """
        # Check valid for duplicate token names
        assert type(token) is str
        if not 1 <= len(token) <= 2:
            raise TokenError(f"Token {token} must be one character long")
        if token in self.tokens:
            raise TokenError(f"Token '{token}' already exists")

        # Check for owner
        if owner not in self.players:
            raise PlayerError(f'Player "{owner}" not found')

        # Add player
        self.players[owner].append(token)

        # Initialize tokens
        self.tokens[token] = {
            "owner": owner,
            "position": None,
            "AP": 0,
            "life": self.life_cap,
            "life_cap": self.life_cap,
            "range": self.action_range,
        }

        # Init position
        if self.board_size is not None:
            self.set_random_token_position(token)

        msg = f"Added {token} to {owner}"
        position = self.get_position(token)
        if position is not None:
            msg += f" at {position}"
        return msg

    def set_board_size_command(self, size: int | str = None, lock_board_size=True):
        """
        BOARD_SIZE [size/"default"]
        Change the board size. WARNING: This resets the game state!
        """
        if self.board_size_locked:
            raise BoardSizeError(f'Board size locked at {self.board_size}')

        default_size = self.get_default_board_size()
        if size is None or type(size) is str:
            size = default_size
        if size ** 2 <= len(self.tokens) or size < self.minimum_board_size:
            raise BoardSizeError(f'Board too small! {size}')

        # Set board size
        self.board_size = size
        self.board_size_locked = lock_board_size

        # Reset random seed & restart tokens
        random.seed(self.random_seed)
        self.init_tokens()

        msg = f"Board size set to {size}x{size}"
        if self.board_size == default_size:
            msg += " (default)"
        msg += " - tokens repositioned, RNG reset"
        return msg

    def set_upgrade_cost_command(self, cost: int):
        """
        UPGRADE_COST [cost]
        Change the AP cost for upgrading a token.
        Usage: set_upgrade_cost(3)
        """
        if cost < 1:
            raise RangeError("Upgrade cost must be at least 1")
        self.upgrade_cost = cost
        return f"Upgrade cost set to {cost} AP"

    def set_heal_self_cost_command(self, cost: int):
        """
        HEAL_SELF_COST [cost]
        Change the AP cost for healing own token.
        Usage: set_heal_self_cost(2)
        """
        if cost < 1:
            raise RangeError("Heal cost must be at least 1")

        self.heal_self_cost = cost
        return f"Heal self cost set to {cost} AP"

    def set_gift_heart_cost_command(self, cost: int):
        """
        GIFT_HEART_COST [cost]
        Change the AP cost for gifting a heart.
        Usage: set_gift_heart_cost(2)
        """
        if cost < 1:
            raise RangeError("Gift heart cost must be at least 1")

        self.gift_heart_cost = cost
        return f"Gift heart cost set to {cost} AP"

    # List of all commands
    COMMANDS = {"next_turn": give_ap_to_all_command,
                "move": move_command,
                "gift": gift_command,
                "shoot": shoot_command,
                "heal": heal_self_command,
                "upgrade": upgrade_token_command,
                "gift_heart": gift_heart_command,
                "capture": capture_command,
                "vote": jury_vote_command,
                "help": help_message_command,
                "PLAYER": add_player_command,
                "TOKEN": add_token_command,
                "RANDOM_SEED": set_random_seed,
                "BOARD_SIZE": set_board_size_command,
                "UPGRADE_COST": set_upgrade_cost_command,
                "HEAL_SELF_COST": set_heal_self_cost_command,
                "GIFT_HEART_COST": set_gift_heart_cost_command,
                }


def execute_text_command(game: Game, line: str) -> str:
    """Execute command line on game."""
    line = line.strip()
    if not line or line.startswith("#"):
        return line

    parts = line.split()
    command = parts[0]
    raw_args = parts[1:]

    if command not in Game.COMMANDS:
        raise GameError(f"Unknown command: {command}")

    # Inspect method signature
    command_method = Game.COMMANDS[command]
    sig = inspect.signature(command_method)
    params = list(sig.parameters.values())

    # Remove 'self'
    params = [p for p in params if p.name != "self"]

    # Convert arguments automatically
    converted_args = []
    for raw, param in zip(raw_args, params):
        if param.annotation in (int, float):
            converted_args.append(param.annotation(raw))
        else:
            # default: keep as string (emoji tokens etc.)
            try:
                converted_args.append(int(raw))
            except ValueError:
                converted_args.append(raw)

    # Call dynamically
    args = [game] + converted_args
    result = command_method(*args)

    return result


def run_commands_from_file(game: Game, filepath: str, ascii_mode=False) -> tuple[str, list]:
    """
    Run all the commands in the file.
    """
    game_state = game.repr(ascii_mode=ascii_mode)
    report = []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                result = execute_text_command(game, line)
                game_state = game.repr(ascii_mode=ascii_mode)
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


def display_game_state(input_file, output_file, ascii_mode=False):
    """Display console output and save game state."""
    # Clear screen before updating display
    msg = f"🔄 Auto-watch mode started (Press Ctrl+C to quit).\n"

    # Create fresh game instance
    game = Game()
    game_state, report = run_commands_from_file(game, input_file, ascii_mode=ascii_mode)
    messages = [s for s in report if s.strip() and not s.startswith('#')]
    last_report = messages[-1] if len(messages) else "(nothing to report)"
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


def first_file_content():
    return ("# Players\nPLAYER Alice\nPLAYER Bob\nPLAYER Charlie\n\n"
            "# Tokens\nTOKEN 🍎 Alice\nTOKEN 🐬 Bob\nTOKEN 🦊 Charlie\n\n"
            "# Parameters\nRANDOM_SEED 123456789\nBOARD_SIZE default\n\n"
            "# === Game ON! ===\n\n"
            "# Day 1\nnext_turn\nhelp")


def create_input_file(input_file):
    """Create an input file and write 'help' command inside."""
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(first_file_content())
        return True
    except IOError as e:
        print(f"⚠️ Failed to create input file {input_file}: {e}")
        return False


def main(period=0.5, ascii_mode=True):

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
    display_game_state(input_file, output_file, ascii_mode=ascii_mode)

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
                display_game_state(input_file, output_file, ascii_mode=ascii_mode)

                # Update previous file hash
                prev_file_hash = current_file_hash

    except KeyboardInterrupt:
        clear_screen()
        print("👋 Exiting.")


if __name__ == '__main__':
    main()
