"""The Round 7 hint crossword (/round7hint2): the puzzle in crossword.js
has to be one a person can actually finish. Every square crosses two
real entries, every entry has a clue and every clue an entry, and the
answers the league asked for sit where they asked. Offline, like the
rest of the suite; the page's behaviour in a browser is checked by hand
(README, Round 7 hint crossword)."""
import base64
import json
import re
import unittest

from support import ROOT

SITE = ROOT / "site"
SIZE = 15


def read(name):
    return (SITE / name).read_text(encoding="utf-8")


def puzzle():
    """The grid (15 strings, "#" for black) and the clues, read straight
    out of crossword.js the way the page reads them."""
    js = read("crossword.js")
    encoded = re.search(r'var SOLUTION = "([A-Za-z0-9+/=]+)";', js).group(1)
    flat = base64.b64decode(encoded).decode("utf-8")[::-1]
    rows = [flat[r * SIZE:(r + 1) * SIZE] for r in range(SIZE)]
    clues = {}
    for direction in ("across", "down"):
        block = re.search(direction + r": \{(.*?)\n    \}", js, re.S).group(1)
        clues[direction] = {int(n): json.loads('"' + text + '"')
                            for n, text in re.findall(r'(\d+): "((?:[^"\\]|\\.)*)"', block)}
    return flat, rows, clues


def entries(rows):
    """Numbered entries, numbered the way crossword.js numbers them."""
    def white(r, c):
        return 0 <= r < SIZE and 0 <= c < SIZE and rows[r][c] != "#"
    out = {"across": {}, "down": {}}
    n = 0
    for r in range(SIZE):
        for c in range(SIZE):
            if not white(r, c):
                continue
            a = not white(r, c - 1) and white(r, c + 1)
            d = not white(r - 1, c) and white(r + 1, c)
            if not (a or d):
                continue
            n += 1
            for direction, go, dr, dc in (("across", a, 0, 1), ("down", d, 1, 0)):
                if go:
                    word, rr, cc = "", r, c
                    while white(rr, cc):
                        word += rows[rr][cc]
                        rr, cc = rr + dr, cc + dc
                    out[direction][n] = word
    return out


class Puzzle(unittest.TestCase):
    def setUp(self):
        self.flat, self.rows, self.clues = puzzle()
        self.entries = entries(self.rows)

    def test_grid_is_fifteen_by_fifteen_of_letters_digits_and_blocks(self):
        self.assertEqual(len(self.flat), SIZE * SIZE)
        self.assertRegex(self.flat, r"^[A-Z0-9#]+$")

    def test_every_entry_has_a_clue_and_every_clue_an_entry(self):
        for direction in ("across", "down"):
            with self.subTest(direction):
                self.assertEqual(sorted(self.entries[direction]), sorted(self.clues[direction]))
                for n, text in self.clues[direction].items():
                    self.assertTrue(text.strip(), f"{n} {direction} has an empty clue")

    def test_every_square_belongs_to_an_across_and_a_down_of_three_or_more(self):
        # an unchecked square, or a two-letter slot, can't be solved fairly
        for r in range(SIZE):
            for c in range(SIZE):
                if self.rows[r][c] == "#":
                    continue
                left = right = c
                while left > 0 and self.rows[r][left - 1] != "#":
                    left -= 1
                while right < SIZE - 1 and self.rows[r][right + 1] != "#":
                    right += 1
                top = bottom = r
                while top > 0 and self.rows[top - 1][c] != "#":
                    top -= 1
                while bottom < SIZE - 1 and self.rows[bottom + 1][c] != "#":
                    bottom += 1
                with self.subTest(square=(r + 1, c + 1)):
                    self.assertGreaterEqual(right - left + 1, 3)
                    self.assertGreaterEqual(bottom - top + 1, 3)

    def test_black_squares_are_symmetric_and_the_white_ones_connected(self):
        for r in range(SIZE):
            for c in range(SIZE):
                self.assertEqual(self.rows[r][c] == "#", self.rows[SIZE - 1 - r][SIZE - 1 - c] == "#", (r, c))
        whites = {(r, c) for r in range(SIZE) for c in range(SIZE) if self.rows[r][c] != "#"}
        seen, todo = set(), [next(iter(whites))]
        while todo:
            r, c = todo.pop()
            if (r, c) in seen or (r, c) not in whites:
                continue
            seen.add((r, c))
            todo += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
        self.assertEqual(seen, whites)

    def test_no_answer_is_used_twice(self):
        answers = list(self.entries["across"].values()) + list(self.entries["down"].values())
        self.assertEqual(len(answers), len(set(answers)))

    def test_the_answers_the_league_asked_for_are_where_they_asked(self):
        self.assertEqual(self.entries["across"][4], "L4LM")
        self.assertEqual(self.clues["across"][4], "Kunj conglomerate")
        self.assertEqual(self.entries["down"][5], "4NONBLONDES")
        # GONG and SOLO cross 4NONBLONDES at its O's
        self.assertEqual(self.rows[2][4:8], "GONG")
        self.assertEqual(self.rows[6][4:8], "SOLO")


class Page(unittest.TestCase):
    def test_members_only_page_loads_the_puzzle_between_account_and_app(self):
        html = read("round7hint2.html")
        self.assertIn('<body class="gated" data-page="crossword">', html)
        srcs = re.findall(r'<script src="([^"]+)"', html)
        self.assertLess(srcs.index("auth.js"), srcs.index("account.js"))
        self.assertLess(srcs.index("account.js"), srcs.index("crossword.js"))
        self.assertLess(srcs.index("crossword.js"), srcs.index("app.js"))
        self.assertIn("PFML.ready.then(boot)", read("crossword.js"))

    def test_app_js_fills_the_header_on_the_crossword_page(self):
        boot = read("app.js").split("function boot() {", 1)[1].split("\n  }\n", 1)[0]
        branch = boot.split('page === "crossword"', 1)[1].split("}", 1)[0]
        self.assertIn('renderNav(index, "crossword")', branch)

    def test_every_element_the_code_looks_up_exists_on_the_page(self):
        html = read("round7hint2.html")
        for el_id in sorted(set(re.findall(r'\$\("(\w+)"\)', read("crossword.js")))):
            with self.subTest(el_id):
                self.assertIn(f'id="{el_id}"', html)

    def test_panels_shown_and_hidden_with_the_hidden_attribute_really_hide(self):
        # The emoji search lesson (CLAUDE.md): a rule that sets display
        # beats [hidden] unless [hidden] is restated for that class.
        css = re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S)
        for cls in ("xw-menu", "xw-paused"):
            with self.subTest(cls):
                self.assertRegex(css, r"\." + cls + r"\s*\{[^}]*display:\s*flex")
                self.assertRegex(css, r"\." + cls + r"\[hidden\]\s*\{\s*display:\s*none")


if __name__ == "__main__":
    unittest.main()
