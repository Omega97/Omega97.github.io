import random


NUMBERS = ("0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣",
           "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣")
EMOTES = ["🟡", "🍕",
          "🟠", "🦊",
          "🔵", "🐬",
          "🟢", "🦖",
          "🟣", "⚔️",
          # "🔴", "🍎",
          ]
BLANK = "➕"
CORNER = "⏹️"


def build_board(size: int, start_from_one=False) -> str:
    """
    Shuffle emoji across the board.
    :param size: board size
    :param start_from_one: start side board count from 1 rather than 0
    :return: board representation
    """
    n_blanks = size ** 2 - len(EMOTES)
    assert n_blanks >= 0, 'Board size too small!'
    tiles = EMOTES + [BLANK] * n_blanks
    random.shuffle(tiles)

    board = CORNER
    for j in range(size):
        board += NUMBERS[(j+start_from_one) % len(NUMBERS)]
    board += '\n'
    for i in range(size):
        board += NUMBERS[(i+start_from_one) % len(NUMBERS)]
        for j in range(size):
            board += tiles[i * size + j]
        board += "\n"

    return board


def main(random_seed=0, size=10):
    random.seed(random_seed)
    print(build_board(size=size, start_from_one=True))


if __name__ == '__main__':
    main()
