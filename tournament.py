"""
Double-elimination tournament logic for One Piece TCG Bot.
"""

import json
import math
import os
import random
from dataclasses import dataclass, field, asdict
from typing import Optional

DATA_FILE        = "data/tournament.json"
GLOBAL_LB_FILE   = "data/global_leaderboard.json"


@dataclass
class Match:
    match_id: int
    player1: Optional[str]  # Discord user ID (str) or None = BYE
    player2: Optional[str]
    winner: Optional[str] = None
    loser: Optional[str] = None
    bracket: str = "winners"  # "winners" | "losers" | "grand_finals"
    round_num: int = 1
    # Where winners / losers go next
    winner_goes_to: Optional[int] = None   # match_id
    loser_goes_to: Optional[int] = None    # match_id


@dataclass
class Tournament:
    state: str = "idle"  # idle | registration | ongoing | finished
    participants: list = field(default_factory=list)   # list of user IDs (str)
    matches: dict = field(default_factory=dict)        # match_id -> Match dict
    next_match_id: int = 1
    leaderboard: list = field(default_factory=list)    # ordered list of user IDs (1st=best)
    player_names: dict = field(default_factory=dict)   # user_id -> display_name


# --- persistence ------------------------------------------------------------

def _load() -> Tournament:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        t = Tournament(**{k: v for k, v in data.items() if k != "matches"})
        t.matches = {int(k): Match(**v) for k, v in data.get("matches", {}).items()}
        return t
    return Tournament()


def _save(t: Tournament):
    os.makedirs("data", exist_ok=True)
    data = asdict(t)
    data["matches"] = {k: asdict(v) for k, v in t.matches.items()}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get() -> Tournament:
    return _load()


# --- registration ------------------------------------------------------------

def open_registration() -> str:
    t = _load()
    if t.state not in ("idle", "finished"):
        return "error:already_open"
    t.state = "registration"
    t.participants = []
    t.matches = {}
    t.next_match_id = 1
    t.leaderboard = []
    t.player_names = {}
    _save(t)
    return "ok"


def register_player(user_id: str, display_name: str) -> str:
    t = _load()
    if t.state != "registration":
        return "error:not_open"
    if user_id in t.participants:
        return "error:already_registered"
    t.participants.append(user_id)
    t.player_names[user_id] = display_name
    _save(t)
    return "ok"


def unregister_player(user_id: str) -> str:
    t = _load()
    if t.state != "registration":
        return "error:not_open"
    if user_id not in t.participants:
        return "error:not_registered"
    t.participants.remove(user_id)
    t.player_names.pop(user_id, None)
    _save(t)
    return "ok"


# --- bracket building --------------------------------------------------------

def _next_power_of_two(n: int) -> int:
    return 1 if n <= 1 else 2 ** math.ceil(math.log2(n))


def start_tournament() -> str:
    t = _load()
    if t.state != "registration":
        return "error:wrong_state"
    if len(t.participants) < 2:
        return "error:not_enough_players"
    if len(t.participants) % 2 != 0:
        return "error:odd_players"

    random.shuffle(t.participants)
    _build_double_elim(t)
    t.state = "ongoing"
    _save(t)
    return "ok"


def _seed_players(players: list) -> list:
    """
    Distribute BYEs so that no two BYEs ever face each other.
    Strategy: real matches fill the first pairs, BYE matches (1 real + 1 BYE)
    fill the remaining pairs at the end.
    e.g. 6 players → size 8 → pairs: [P1vP2, P3vP4, P5vBYE, P6vBYE]
    """
    n = len(players)
    size = _next_power_of_two(n)
    byes = size - n
    num_pairs = size // 2

    seeded: list = []
    p_idx = 0
    real_pairs = num_pairs - byes   # pairs with two real players

    for i in range(num_pairs):
        seeded.append(players[p_idx]); p_idx += 1
        if i < real_pairs:
            seeded.append(players[p_idx]); p_idx += 1
        else:
            seeded.append(None)     # BYE always faces a real player

    return seeded


def _build_double_elim(t: Tournament):
    """
    Build a full double-elimination bracket.
    Players are seeded randomly into the winners bracket.
    BYEs are automatically advanced.
    """
    players = _seed_players(list(t.participants))
    size = len(players)

    t.matches = {}
    t.next_match_id = 1

    # -- Winners bracket ------------------------------------------------------
    # Round 1 matches
    w_rounds: list[list[int]] = []   # list of rounds, each round = list of match_ids
    r1_ids = []
    for i in range(0, size, 2):
        mid = t.next_match_id
        t.next_match_id += 1
        m = Match(match_id=mid, player1=players[i], player2=players[i + 1],
                  bracket="winners", round_num=1)
        t.matches[mid] = m
        r1_ids.append(mid)
    w_rounds.append(r1_ids)

    # Subsequent winners rounds
    prev_round = r1_ids
    round_num = 2
    while len(prev_round) > 1:
        curr_round = []
        for i in range(0, len(prev_round), 2):
            mid = t.next_match_id
            t.next_match_id += 1
            m = Match(match_id=mid, player1=None, player2=None,
                      bracket="winners", round_num=round_num)
            t.matches[mid] = m
            curr_round.append(mid)
            # Wire previous matches → this match
            t.matches[prev_round[i]].winner_goes_to = mid
            t.matches[prev_round[i + 1]].winner_goes_to = mid
        w_rounds.append(curr_round)
        prev_round = curr_round
        round_num += 1

    winners_final_id = w_rounds[-1][0]

    # -- Losers bracket -------------------------------------------------------
    # Losers bracket has 2*(size-1)-1 matches total, structured in pairs of rounds.
    # Round L1: losers from W round 1 (size/2 players → size/4 matches)
    # Then alternating: "drop-in" from next winners round, then internal losers round
    l_rounds: list[list[int]] = []
    l_round_num = 1

    # L-Round 1: losers from W round 1 fight each other
    l1_losers_count = len(w_rounds[0])  # == size/2
    l1_ids = []
    for i in range(0, l1_losers_count, 2):
        mid = t.next_match_id
        t.next_match_id += 1
        m = Match(match_id=mid, player1=None, player2=None,
                  bracket="losers", round_num=l_round_num)
        t.matches[mid] = m
        l1_ids.append(mid)
        # W-round-1 losers go here
        t.matches[w_rounds[0][i]].loser_goes_to = mid
        t.matches[w_rounds[0][i + 1]].loser_goes_to = mid
    l_rounds.append(l1_ids)
    l_round_num += 1

    # For each subsequent winners round (except the final), drop losers into losers bracket
    for w_round_idx in range(1, len(w_rounds) - 1):
        w_round = w_rounds[w_round_idx]
        prev_l_round = l_rounds[-1]

        # "Drop-in" round: pair W-round losers with L-round survivors
        dropin_ids = []
        for i, l_mid in enumerate(prev_l_round):
            mid = t.next_match_id
            t.next_match_id += 1
            m = Match(match_id=mid, player1=None, player2=None,
                      bracket="losers", round_num=l_round_num)
            t.matches[mid] = m
            dropin_ids.append(mid)
            t.matches[l_mid].winner_goes_to = mid
            if i < len(w_round):
                t.matches[w_round[i]].loser_goes_to = mid
        l_rounds.append(dropin_ids)
        l_round_num += 1

        # Internal losers round (if more than 1 match)
        if len(dropin_ids) > 1:
            internal_ids = []
            for i in range(0, len(dropin_ids), 2):
                mid = t.next_match_id
                t.next_match_id += 1
                m = Match(match_id=mid, player1=None, player2=None,
                          bracket="losers", round_num=l_round_num)
                t.matches[mid] = m
                internal_ids.append(mid)
                t.matches[dropin_ids[i]].winner_goes_to = mid
                t.matches[dropin_ids[i + 1]].winner_goes_to = mid
            l_rounds.append(internal_ids)
            l_round_num += 1
            prev_l_round = internal_ids
        else:
            prev_l_round = dropin_ids

    # Losers final: last remaining losers match feeds grand finals
    losers_final_id = l_rounds[-1][0] if len(l_rounds[-1]) == 1 else None
    if losers_final_id is None:
        # Create it from last two
        last = l_rounds[-1]
        mid = t.next_match_id
        t.next_match_id += 1
        m = Match(match_id=mid, player1=None, player2=None,
                  bracket="losers", round_num=l_round_num)
        t.matches[mid] = m
        for lm in last:
            t.matches[lm].winner_goes_to = mid
        losers_final_id = mid
        l_round_num += 1

    # -- Grand Finals ---------------------------------------------------------
    gf_id = t.next_match_id
    t.next_match_id += 1
    gf = Match(match_id=gf_id, player1=None, player2=None,
               bracket="grand_finals", round_num=1)
    t.matches[gf_id] = gf
    t.matches[winners_final_id].winner_goes_to = gf_id
    t.matches[losers_final_id].winner_goes_to = gf_id

    # -- Auto-advance BYEs ----------------------------------------------------
    _auto_advance(t)


# --- sentinel for BYE slots --------------------------------------------------
# None  = slot not yet filled (waiting for a previous match result)
# __BYE__ = slot filled by a bye (no real player; should auto-advance opponent)

BYE_SENTINEL = "__BYE__"


def _fill_slot(match: Match, value: Optional[str]):
    """Fill the first empty slot of a match with value (player_id or BYE_SENTINEL)."""
    if match.player1 is None:
        match.player1 = value
    else:
        match.player2 = value


def _auto_advance(t: Tournament):
    """Propagate BYEs and double-BYEs until no more automatic advances are possible."""
    changed = True
    while changed:
        changed = False
        for m in list(t.matches.values()):
            if m.winner is not None:
                continue
            p1, p2 = m.player1, m.player2

            # Real player vs BYE sentinel → real player wins
            if p1 == BYE_SENTINEL and p2 is not None and p2 != BYE_SENTINEL:
                _resolve_match(t, m.match_id, winner_id=p2)
                changed = True
            elif p2 == BYE_SENTINEL and p1 is not None and p1 != BYE_SENTINEL:
                _resolve_match(t, m.match_id, winner_id=p1)
                changed = True
            # Real player vs empty slot (one side is None, other is a real player)
            elif p1 is None and p2 is not None and p2 != BYE_SENTINEL:
                _resolve_match(t, m.match_id, winner_id=p2)
                changed = True
            elif p2 is None and p1 is not None and p1 != BYE_SENTINEL:
                _resolve_match(t, m.match_id, winner_id=p1)
                changed = True
            # Both BYE → propagate BYE forward, this match is a ghost
            elif p1 == BYE_SENTINEL and p2 == BYE_SENTINEL:
                m.winner = BYE_SENTINEL
                m.loser  = BYE_SENTINEL
                if m.winner_goes_to:
                    _fill_slot(t.matches[m.winner_goes_to], BYE_SENTINEL)
                if m.loser_goes_to:
                    _fill_slot(t.matches[m.loser_goes_to], BYE_SENTINEL)
                changed = True


# --- match resolution --------------------------------------------------------

def _resolve_match(t: Tournament, match_id: int, winner_id: str):
    m = t.matches[match_id]
    # Determine loser (may be BYE_SENTINEL or None → both mean "no real loser")
    raw_loser = m.player2 if winner_id == m.player1 else m.player1
    loser_id  = raw_loser if (raw_loser and raw_loser != BYE_SENTINEL) else None
    m.winner  = winner_id
    m.loser   = raw_loser

    # Move winner forward
    if m.winner_goes_to:
        _fill_slot(t.matches[m.winner_goes_to], winner_id)

    # Move loser forward or eliminate
    if m.loser_goes_to:
        # Route BYE_SENTINEL or None as BYE_SENTINEL so the next match can auto-advance
        _fill_slot(t.matches[m.loser_goes_to], loser_id if loser_id else BYE_SENTINEL)
    elif loser_id is not None:
        # No further match → eliminated
        if loser_id not in t.leaderboard:
            t.leaderboard.insert(0, loser_id)

    # Check if grand finals just finished (winner must be a real player)
    if m.bracket == "grand_finals" and m.winner_goes_to is None and winner_id != BYE_SENTINEL:
        if winner_id not in t.leaderboard:
            t.leaderboard.insert(0, winner_id)
        if loser_id and loser_id not in t.leaderboard:
            t.leaderboard.insert(1, loser_id)
        t.state = "finished"
        _record_tournament_win(winner_id, t.player_names.get(winner_id, winner_id))


def report_score(match_id: int, winner_id: str) -> str:
    t = _load()
    if t.state != "ongoing":
        return "error:not_ongoing"
    if match_id not in t.matches:
        return "error:invalid_match"
    m = t.matches[match_id]
    if m.winner is not None:
        return "error:already_played"
    if winner_id not in (m.player1, m.player2) or winner_id == BYE_SENTINEL:
        return "error:invalid_winner"
    _resolve_match(t, match_id, winner_id)
    _save(t)
    return "finished" if t.state == "finished" else "ok"


# --- helpers -----------------------------------------------------------------

def get_pending_matches(t: Optional[Tournament] = None) -> list[Match]:
    if t is None:
        t = _load()
    return [m for m in t.matches.values()
            if m.winner is None
            and m.player1 is not None and m.player1 != BYE_SENTINEL
            and m.player2 is not None and m.player2 != BYE_SENTINEL]


def get_match_by_players(user1: str, user2: str) -> Optional[Match]:
    t = _load()
    for m in t.matches.values():
        if m.winner is None and {m.player1, m.player2} == {user1, user2}:
            return m
    return None


# --- global leaderboard (inter-tournois) -------------------------------------

def _load_global_lb() -> dict:
    """Returns {user_id: {"name": str, "wins": int}}"""
    os.makedirs("data", exist_ok=True)
    if os.path.exists(GLOBAL_LB_FILE):
        with open(GLOBAL_LB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_global_lb(lb: dict):
    os.makedirs("data", exist_ok=True)
    with open(GLOBAL_LB_FILE, "w", encoding="utf-8") as f:
        json.dump(lb, f, ensure_ascii=False, indent=2)


def _record_tournament_win(user_id: str, display_name: str):
    """Called when a tournament finishes — increments the winner's count."""
    lb = _load_global_lb()
    if user_id not in lb:
        lb[user_id] = {"name": display_name, "wins": 0}
    lb[user_id]["wins"] += 1
    lb[user_id]["name"] = display_name   # update name in case it changed
    _save_global_lb(lb)


def get_global_leaderboard() -> list[dict]:
    """Returns a sorted list of {"user_id", "name", "wins"} descending by wins."""
    lb = _load_global_lb()
    entries = [{"user_id": uid, "name": v["name"], "wins": v["wins"]}
               for uid, v in lb.items()]
    entries.sort(key=lambda e: e["wins"], reverse=True)
    return entries
