# Token Tactics

**Token Tactics** is a real-time, turn-based multiplayer board game engine written in Python. It features a text-based interface where players control tokens on a grid, managing Action Points (AP), health, and positioning to eliminate opponents.

The game supports a unique "Jury" mechanic: when a player is eliminated, they join the jury and can vote to grant bonus AP to remaining tokens, influencing the flow of the endgame.

## 🎮 Features

*   **Turn-Based Strategy:** Manage limited Action Points (AP) to move, shoot, heal, or upgrade.
*   **Dynamic Board:** Adjustable board sizes with automatic token placement.
*   **Jury System:** Eliminated players don't just watch; they vote to buff surviving tokens.
*   **Token Customization:** Upgrade range, life capacity, and capture enemy tokens.
*   **Reproducibility:** Deterministic gameplay using fixed random seeds for debugging and fair play.
*   **ASCII & Emoji Support:** Play with rich emoji graphics or standard ASCII characters for terminal compatibility.
*   **File-Driven Input:** Define game setup and commands via a simple text file (`commands.txt`).

## 📋 Prerequisites

*   Python 3.10+ (uses modern type hinting syntax like `tuple[int,int]`)
*   No external libraries required (uses only standard library modules).

## 🚀 Quick Start

1.  **Clone or Download** the repository.
2.  **Run the game:**
    ```bash
    python tt_game.py
    ```
    *(Note: Ensure the main script is named `tt_game.py` or adjust the command accordingly.)*

3.  **ASCII Mode:** If your terminal doesn't support emojis well, run:
    ```bash
    python tt_game.py --ascii
    ```

4.  **Edit Commands:** The game reads from `commands.txt`. Edit this file to change players, tokens, or issue commands. The game auto-reloads when the file changes.

## 🕹️ How to Play

### 1. Setup (`commands.txt`)

The game initializes based on the content of `commands.txt`. A typical setup looks like this:

```text
# Define Players
PLAYER Alice
PLAYER Bob

# Define Tokens (Symbol Owner)
TOKEN 🍎 Alice
TOKEN 🐬 Bob

# Game Parameters
RANDOM_SEED 42
BOARD_SIZE default
```

### 2. Core Mechanics

*   **Action Points (AP):** Every turn, living tokens gain `AP_PER_TURN` (default 1). Actions cost AP.
*   **Movement:** Tokens move 1 square in any direction (Chebyshev distance).
*   **Combat:** Shoot enemies within range to reduce their Life. If Life reaches 0, the token is KO'd but remains on the board.
*   **Elimination:** If a player has no living tokens, they are eliminated and join the **Jury**.

### 3. The Jury

Eliminated players enter the Jury. Each jury member can vote for one specific living token. At the start of every turn, tokens with jury votes receive **+1 extra AP**. This allows eliminated players to influence who wins.

## 📜 Command Reference

Commands are case-insensitive. Arguments are space-separated.

### Game Control

| Command             | Description                                                                                    |
|:--------------------|:-----------------------------------------------------------------------------------------------|
| `next_turn`         | Ends the current turn. Grants AP to all living tokens and jury-buffed tokens.                  |
| `help`              | Displays available commands.                                                                   |
| `BOARD_SIZE [size]` | Sets board dimensions (e.g., `BOARD_SIZE 10`). Resets game state. Use `default` for auto-size. |
| `RANDOM_SEED [num]` | Sets the RNG seed for reproducible token placement.                                            |

### Player & Token Setup

| Command                   | Description                                         |
|:--------------------------|:----------------------------------------------------|
| `PLAYER [name]`           | Adds a new player.                                  |
| `TOKEN [symbol] [player]` | Adds a token to a player. Symbol must be 1-2 chars. |

### Actions (Cost AP)

| Command                     | Cost  | Description                                                                                            |
|:----------------------------|:------|:-------------------------------------------------------------------------------------------------------|
| `move [token] [dx] [dy]`    | 1 AP  | Move token by dx, dy (must be adjacent).                                                               |
| `shoot [attacker] [target]` | 1 AP  | Deal 1 damage to target. Must be in range. Steals AP if target dies.                                   |
| `heal [token]`              | 2 AP  | Restore 1 Life to own token (up to cap).                                                               |
| `gift [from] [to] [amt]`    | 0 AP* | Transfer AP from one token to another. Must be in range. (*Configurable cost)                          |
| `gift_heart [from] [to]`    | 1 AP  | Transfer 1 Life from donor to receiver. Donor must survive. Revives jury members if receiver was KO'd. |
| `upgrade [token]`           | 5 AP  | Increase Range +1, Life Cap +1, and heal 1 Life.                                                       |
| `capture [hunter] [prey]`   | 5 AP  | Capture an adjacent KO enemy token. It joins your team with 1 Life.                                    |

### Jury Actions

| Command                 | Description                                                                                              |
|:------------------------|:---------------------------------------------------------------------------------------------------------|
| `vote [player] [token]` | An eliminated player votes for a token. That token gets +1 AP/turn. Use `vote [player] None` to abstain. |

### Configuration (Optional)

You can tweak balance by setting costs in `commands.txt`:
*   `MOVE_COST [int]`
*   `SHOOT_COST [int]`
*   `HEAL_SELF_COST [int]`
*   `UPGRADE_COST [int]`
*   `CAPTURE_COST [int]`
*   `GIFT_COST [int]`
*   `GIFT_HEART_COST [int]`
*   `AP_PER_TURN [int]`

## 🛠️ Development & Architecture

The code is structured using a Command Pattern for extensibility.

*   **`Game` Class:** Manages state (board, tokens, players, jury).
*   **`Command` Classes:** Abstract base class for all actions. Each command validates state and executes logic.
*   **`GameRunner`:** Handles file watching, parsing, and the main loop.
*   **`Palette`:** Defines visual representation (Emoji vs ASCII).

### Adding New Commands

1.  Create a new class inheriting from `Command`.
2.  Implement the `execute()` method.
3.  Register the command in `Game._COMMAND_REGISTRY`.

## 📝 License

This project is open-source. Feel free to modify and extend it for your own game nights or AI research projects.

---

*Created by Omar Cusma Fait*
