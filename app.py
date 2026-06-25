import json
import os
import random
import re
import string
import tempfile
import time
from contextlib import contextmanager
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


# ============================================================
# BABY SHOWER FAMILY FEUD
# Quickplay tournament + individual Fast Money championship
# ============================================================

st.set_page_config(page_title="Baby Shower Feud", layout="wide")

SESSIONS_DIR = "game_sessions"
HOSTS_FILE = "host_sessions.json"
DEFAULT_GAME_CODE = "default"
GAME_CODE_LENGTH = 4
FAST_MONEY_SECONDS = 45
FUZZY_THRESHOLD = 78


PRELOADED_TEAMS = [
    "Roses",
    "Peonies",
    "Tulips",
    "Hydrangeas",
    "Daisies",
    "Lilacs",
    "Ranunculus",
    "Wildflowers",
]


DEFAULT_MAIN_QUESTIONS = [
    {
        "question": "Name something parents always carry in a diaper bag.",
        "answers": [
            ["Diapers", 35],
            ["Wipes", 25],
            ["Bottle", 15],
            ["Snacks", 10],
            ["Extra clothes", 8],
            ["Pacifier", 7],
        ],
    }
]

DEFAULT_FAST_MONEY_QUESTIONS = [
    {
        "question": "Name something parents do while the baby is sleeping.",
        "answers": [["Sleep", 40], ["Clean", 25], ["Eat", 15], ["Shower", 10], ["Watch TV", 10]],
    },
    {
        "question": "Name a baby item people forget to pack.",
        "answers": [["Diapers", 35], ["Wipes", 25], ["Bottle", 20], ["Pacifier", 10], ["Extra clothes", 10]],
    },
    {
        "question": "Name something babies hate.",
        "answers": [["Bath time", 30], ["Diaper changes", 25], ["Car seat", 20], ["Loud noises", 15], ["Being put down", 10]],
    },
    {
        "question": "Name something exhausted parents drink a lot of.",
        "answers": [["Coffee", 50], ["Energy drinks", 20], ["Water", 12], ["Soda", 10], ["Tea", 8]],
    },
    {
        "question": "Name something babies wake up their parents for.",
        "answers": [["Feeding", 35], ["Diaper change", 25], ["Crying", 20], ["Teething", 10], ["Comfort", 10]],
    },
]


THEMES = {
    "Baby Girl / Purple": {
        "paper": "#F8F5F0",
        "cream": "#FFFAF8",
        "primary": "#6E5873",
        "secondary": "#A58BB7",
        "accent": "#EADFED",
        "border": "#D8C4DD",
        "highlight": "#E8C7D0",
        "sidebar": "#F2EAF4",
    },
    "Baby Boy / Blue": {
        "paper": "#F5F9FD",
        "cream": "#FFFFFF",
        "primary": "#355C7D",
        "secondary": "#5D8AA8",
        "accent": "#D8EAF8",
        "border": "#B8D5EA",
        "highlight": "#C8E5FF",
        "sidebar": "#E7F2FB",
    },
    "Sage Garden": {
        "paper": "#F7F7F0",
        "cream": "#FFFDF8",
        "primary": "#59684A",
        "secondary": "#7D8F68",
        "accent": "#E4EAD8",
        "border": "#C9D4B8",
        "highlight": "#DDEBCB",
        "sidebar": "#EEF3E6",
    },
    "Woodland Neutral": {
        "paper": "#F8F6F0",
        "cream": "#FFFDF8",
        "primary": "#5B4B3A",
        "secondary": "#8A765D",
        "accent": "#E7E2D5",
        "border": "#D2C7B8",
        "highlight": "#D7E5C8",
        "sidebar": "#F0EADF",
    },
    "Wildflower": {
        "paper": "#FFFDF8",
        "cream": "#FFFFFF",
        "primary": "#4D5A4B",
        "secondary": "#D29BB8",
        "accent": "#E8D7E4",
        "border": "#DCCBBF",
        "highlight": "#F4E5A4",
        "sidebar": "#F7EEF5",
    },
    "Sunflower": {
        "paper": "#FFF9E8",
        "cream": "#FFFFFF",
        "primary": "#6A4A1F",
        "secondary": "#C68B20",
        "accent": "#F8E6A8",
        "border": "#E6C66E",
        "highlight": "#FFE08A",
        "sidebar": "#FFF1C8",
    },
    "Custom": {
        "paper": "#F8F5F0",
        "cream": "#FFFAF8",
        "primary": "#6E5873",
        "secondary": "#A58BB7",
        "accent": "#EADFED",
        "border": "#D8C4DD",
        "highlight": "#E8C7D0",
        "sidebar": "#F2EAF4",
    },
}


def default_custom_theme():
    return THEMES["Custom"].copy()


def get_theme_colors(state):
    selected_theme = state.get("theme", "Baby Girl / Purple")
    if selected_theme == "Custom":
        custom = default_custom_theme()
        custom.update(state.get("custom_theme", {}) if isinstance(state.get("custom_theme"), dict) else {})
        return custom
    return THEMES.get(selected_theme, THEMES["Baby Girl / Purple"])


def default_state():
    return {
        "teams": {
            team: [] for team in PRELOADED_TEAMS
        },
        "locked": False,
        "matches": [],
        "current_match_index": 0,
        "active_teams": [],
        "round_winners": [],
        "round_bank": 0,
        "match_scores": {},
        "total_scores": {},
        "current_question_index": 0,
        "revealed": [],
        "strike": False,
        "steal_mode": False,
        "questions": DEFAULT_MAIN_QUESTIONS,
        "fast_money_questions": DEFAULT_FAST_MONEY_QUESTIONS,
        "google_sheet_url": "",
        "theme": "Baby Girl / Purple",
        "custom_theme": default_custom_theme(),
        "champion_team": "",
        "tournament_complete": False,
        "fast_money_started": False,
        "fast_money_start_time": 0,
        "fast_money_answers": {},
        "ended": False,
        "ended_reason": "",
        "ended_at": 0,
        "message": "Welcome to Baby Shower Family Feud!",
    }


def sanitize_game_code(raw_code):
    """Turn user-entered game codes into safe URL/file names."""
    raw_code = str(raw_code or "").strip().lower()
    safe_code = re.sub(r"[^a-z0-9_-]+", "-", raw_code).strip("-")
    return safe_code


def has_game_code_in_url():
    return bool(sanitize_game_code(st.query_params.get("game", "")))


def should_create_new_host_game():
    """Return True when a host needs a fresh unique game code.

    This prevents every host who opens ?view=host or ?view=host&game=default
    from landing in the same shared default session. Hosts can also force a new
    session with ?view=host&new=1 or the Start New Game button.
    """
    if st.query_params.get("view", "player") != "host":
        return False

    requested_code = sanitize_game_code(st.query_params.get("game", ""))
    wants_new_game = str(st.query_params.get("new", "")).lower() in {"1", "true", "yes"}

    return wants_new_game or not requested_code or requested_code == DEFAULT_GAME_CODE


def generate_game_code():
    """Create a short readable game code, avoiding existing session files."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(100):
        code = "".join(random.choice(alphabet) for _ in range(GAME_CODE_LENGTH))
        if not os.path.exists(os.path.join(SESSIONS_DIR, f"{code.lower()}.json")):
            return code.lower()
    return str(int(time.time()))


def generate_host_id():
    """Create an ID that follows one host/browser via the URL."""
    alphabet = string.ascii_lowercase + string.digits
    return "h" + "".join(random.choice(alphabet) for _ in range(10))


def get_host_id():
    return sanitize_game_code(st.query_params.get("host", ""))


def get_host_index_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, HOSTS_FILE)


def get_host_index_lock_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, HOSTS_FILE + ".lock")


@contextmanager
def host_index_lock():
    lock_path = get_host_index_lock_file()
    lock_handle = open(lock_path, "w", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        yield
    finally:
        try:
            try:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        finally:
            lock_handle.close()


def load_host_index_unlocked():
    index_file = get_host_index_file()
    if not os.path.exists(index_file):
        return {}
    try:
        with open(index_file, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_host_index_unlocked(index):
    index_file = get_host_index_file()
    directory = os.path.dirname(index_file) or "."
    fd, temp_path = tempfile.mkstemp(prefix="hosts_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(index, file, indent=2)
        os.replace(temp_path, index_file)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def get_state_file_for_code(game_code):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{sanitize_game_code(game_code)}.json")


def end_game_session(game_code, reason="A new game session was started by this host."):
    """Mark an existing session ended so old player links stop the game."""
    safe_code = sanitize_game_code(game_code)
    if not safe_code:
        return

    state_file = get_state_file_for_code(safe_code)
    if not os.path.exists(state_file):
        return

    lock_path = os.path.join(SESSIONS_DIR, f"{safe_code}.lock")
    lock_handle = open(lock_path, "w", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass

        try:
            with open(state_file, "r", encoding="utf-8") as file:
                old_state = json.load(file)
        except Exception:
            old_state = default_state()

        old_state = migrate_state(old_state)
        old_state["ended"] = True
        old_state["ended_reason"] = reason
        old_state["ended_at"] = int(time.time())
        old_state["fast_money_started"] = False
        old_state["message"] = reason

        directory = os.path.dirname(state_file) or "."
        fd, temp_path = tempfile.mkstemp(prefix="state_", suffix=".tmp", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(old_state, file, indent=2)
            os.replace(temp_path, state_file)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    finally:
        try:
            try:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        finally:
            lock_handle.close()


def register_active_game_for_host(host_id, new_game_code):
    """Save this host's active game and end their previous one."""
    safe_host = sanitize_game_code(host_id)
    safe_game = sanitize_game_code(new_game_code)
    if not safe_host or not safe_game:
        return

    with host_index_lock():
        index = load_host_index_unlocked()
        previous_game = index.get(safe_host, {}).get("active_game")

        if previous_game and previous_game != safe_game:
            end_game_session(previous_game)

        index[safe_host] = {
            "active_game": safe_game,
            "updated_at": int(time.time()),
        }
        save_host_index_unlocked(index)


def create_new_host_session():
    """Create a new host-owned game and mark the host's previous game ended."""
    host_id = get_host_id() or generate_host_id()
    new_code = generate_game_code()
    register_active_game_for_host(host_id, new_code)

    st.query_params.clear()
    st.query_params["view"] = "host"
    st.query_params["game"] = new_code
    st.query_params["host"] = host_id


def get_game_code():
    """Return a safe game/session code from the URL.

    Example URLs:
    ?view=host&game=a7k4
    ?view=player&game=a7k4
    """
    return sanitize_game_code(st.query_params.get("game", DEFAULT_GAME_CODE)) or DEFAULT_GAME_CODE


def get_state_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{get_game_code()}.json")


def get_lock_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{get_game_code()}.lock")


@contextmanager
def state_file_lock():
    """Cross-session lock for safer simultaneous reads/writes on Streamlit Cloud.

    Uses Python stdlib only, so there is no extra requirements.txt dependency.
    Streamlit Cloud runs on Linux, where fcntl is available. If fcntl is not
    available, the app still runs, but without process-level locking.
    """
    lock_path = get_lock_file()
    lock_handle = open(lock_path, "w", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        yield
    finally:
        try:
            try:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        finally:
            lock_handle.close()


def write_state_unlocked(state):
    state_file = get_state_file()
    directory = os.path.dirname(state_file) or "."
    os.makedirs(directory, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix="state_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
        os.replace(temp_path, state_file)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def save_state(state):
    with state_file_lock():
        write_state_unlocked(state)


def migrate_state(state):
    base = default_state()
    for key, value in base.items():
        if key not in state:
            state[key] = value

    if not isinstance(state.get("teams"), dict):
        state["teams"] = {}
    if not isinstance(state.get("matches"), list):
        state["matches"] = []
    if not isinstance(state.get("round_winners"), list):
        state["round_winners"] = []
    if not isinstance(state.get("match_scores"), dict):
        state["match_scores"] = {}
    if not isinstance(state.get("total_scores"), dict):
        state["total_scores"] = {}
    if not isinstance(state.get("fast_money_answers"), dict):
        state["fast_money_answers"] = {}
    if not state.get("questions"):
        state["questions"] = DEFAULT_MAIN_QUESTIONS
    if not state.get("fast_money_questions"):
        state["fast_money_questions"] = DEFAULT_FAST_MONEY_QUESTIONS


    # Ensure preloaded teams always exist
    for team in PRELOADED_TEAMS:
        state["teams"].setdefault(team, [])

    if state.get("theme") not in THEMES:
        state["theme"] = "Baby Girl / Purple"
    if not isinstance(state.get("custom_theme"), dict):
        state["custom_theme"] = default_custom_theme()

    return state


def load_state():
    state_file = get_state_file()

    with state_file_lock():
        if not os.path.exists(state_file):
            state = default_state()
            write_state_unlocked(state)
            return state

        try:
            with open(state_file, "r", encoding="utf-8") as file:
                state = json.load(file)
        except Exception:
            state = default_state()

        state = migrate_state(state)
        write_state_unlocked(state)
        return state


initial_view = st.query_params.get("view", "player")

# If the host opens the host page without a real game code, create one automatically
# and put it in the URL. If this same host/browser already had an active game,
# the previous game is marked ended so old player links cannot keep playing.
# Players must have a game code to join a session.
if should_create_new_host_game():
    create_new_host_session()
    st.rerun()

# If a host has a game code but no host ID, add one so future new sessions can
# end this host's previous game. This preserves the current game code.
if st.query_params.get("view", "player") == "host" and has_game_code_in_url() and not get_host_id():
    st.query_params["host"] = generate_host_id()
    register_active_game_for_host(st.query_params["host"], get_game_code())
    st.rerun()

state = load_state()


# -----------------------------
# Styling
# -----------------------------

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Cormorant+Garamond:wght@500;600;700&display=swap');

:root {
    --paper: #F8F5F0;
    --cream: #FFFAF8;
    --plum: #6E5873;
    --lavender: #A58BB7;
    --soft-lavender: #EADFED;
    --border-lavender: #D8C4DD;
    --dusty-rose: #A58BB7;
    --blush-pink: #E8C7D0;
    --sage: #7D8F68;
}

html, body, .stApp {
    background: var(--paper) !important;
    color: var(--plum) !important;
    font-family: 'Cormorant Garamond', serif !important;
}

* {
    color: var(--plum);
}

.main-title {
    font-family: 'Playfair Display', serif;
    font-size: clamp(42px, 8vw, 84px);
    line-height: 1;
    text-align: center;
    font-weight: 800;
    color: var(--plum) !important;
    margin-top: 10px;
    margin-bottom: 4px;
    letter-spacing: 1px;

    max-width: 100%;
    white-space: nowrap;

}

.subtitle {
    text-align: center;
    font-size: 24px;
    color: var(--lavender) !important;
    margin-bottom: 28px;
    letter-spacing: 0.5px;
}

.question-card {
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 28px;
    padding: 28px;
    margin: 20px 0 24px 0;
    font-size: clamp(26px, 4vw, 40px);
    font-weight: 700;
    text-align: center;
    color: var(--plum) !important;
    box-shadow: 0 10px 30px rgba(110, 88, 115, 0.10);
}

.answer-tile {
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 22px;
    padding: 18px 22px;
    margin-bottom: 14px;
    color: var(--plum) !important;
    font-size: clamp(22px, 3.5vw, 30px);
    font-weight: 700;
    display: flex;
    justify-content: space-between;
    gap: 20px;
    box-shadow: 0 6px 18px rgba(110, 88, 115, 0.08);
}

.answer-hidden {
    color: var(--blush-pink) !important;
    text-align: center;
    justify-content: center;
    font-weight: 700;
}

.score-card, .bracket-card, .info-card {
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 22px;
    padding: 18px;
    margin-bottom: 12px;
    box-shadow: 0 6px 18px rgba(110, 88, 115, 0.08);
    color: var(--plum) !important;
}

.score-number {
    font-family: 'Playfair Display', serif;
    font-size: 42px;
    font-weight: 800;
    color: var(--dusty-rose) !important;
}

.message {
    text-align: center;
    font-size: 24px;
    font-weight: 700;
    color: var(--dusty-rose) !important;
    margin: 18px 0;
}

.small-note {
    font-size: 18px;
    color: var(--lavender) !important;
}

.stButton button {
    background: var(--soft-lavender) !important;
    color: var(--plum) !important;
    border: 1px solid var(--border-lavender) !important;
    border-radius: 14px !important;
    font-family: 'Cormorant Garamond', serif !important;
    font-size: 18px !important;
    font-weight: 700 !important;
}

.stButton button:hover {
    border-color: var(--dusty-rose) !important;
    color: var(--lavender) !important;
}

section[data-testid="stSidebar"] {
    background: #F2EAF4 !important;
}

section[data-testid="stSidebar"] * {
    color: var(--plum) !important;
}

input, textarea, select {
    color: var(--plum) !important;
    background: #FFFFFF !important;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div,
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
    background: #FFFFFF !important;
    color: var(--plum) !important;
}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: var(--lavender) !important;
    opacity: 1 !important;
}


/* Force any Streamlit default white foreground text to blush pink */
.stAlert,
.stAlert *,
[data-testid="stNotification"],
[data-testid="stNotification"] *,
[data-testid="stToast"],
[data-testid="stToast"] *,
button[kind="primary"],
button[kind="primary"] *,
.st-emotion-cache-1kyxreq,
.st-emotion-cache-1kyxreq * {
    color: var(--blush-pink) !important;
}

/* Keep typed input areas white and readable */
[contenteditable="true"],
[role="textbox"] {
    background: #FFFFFF !important;
    color: var(--plum) !important;
}

[data-testid="stMetricValue"] {
    color: var(--dusty-rose) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# Apply the selected theme after the base CSS so it overrides the default colors.
active_theme = get_theme_colors(state)
st.markdown(
    f"""
<style>
:root {{
    --paper: {active_theme["paper"]};
    --cream: {active_theme["cream"]};
    --plum: {active_theme["primary"]};
    --lavender: {active_theme["secondary"]};
    --soft-lavender: {active_theme["accent"]};
    --border-lavender: {active_theme["border"]};
    --dusty-rose: {active_theme["secondary"]};
    --blush-pink: {active_theme["highlight"]};
    --sage: {active_theme["secondary"]};
}}

section[data-testid="stSidebar"] {{
    background: {active_theme["sidebar"]} !important;
}}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# Utility functions
# -----------------------------

def normalize(text):
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum() or ch.isspace()).strip()


def similarity(a, b):
    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return 0

    if fuzz is not None:
        return fuzz.ratio(a, b)

    return int(SequenceMatcher(None, a, b).ratio() * 100)


def load_questions_from_csv(csv_url):
    df = pd.read_csv(csv_url)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"game_type", "question", "answer", "points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    df["game_type"] = df["game_type"].astype(str).str.strip().str.lower()

    main_df = df[df["game_type"] == "main"].copy()
    fast_df = df[df["game_type"] == "fast_money"].copy()

    def build_questions(source_df):
        questions = []
        for question_text, group in source_df.groupby("question", sort=False):
            answers = []
            for _, row in group.iterrows():
                try:
                    points = int(row["points"])
                except Exception:
                    points = 0
                answers.append([str(row["answer"]), points])
            questions.append({"question": str(question_text), "answers": answers})
        return questions

    main_questions = build_questions(main_df)
    fast_money_questions = build_questions(fast_df)

    if not main_questions:
        raise ValueError("No main questions found. Use game_type = main.")
    if len(fast_money_questions) < 5:
        raise ValueError("Fast Money needs at least 5 questions with game_type = fast_money.")

    return main_questions, fast_money_questions[:5]


def build_initial_matches(team_names):
    names = list(team_names)
    matches = []
    for i in range(0, len(names), 2):
        if i + 1 < len(names):
            matches.append([names[i], names[i + 1]])
        else:
            matches.append([names[i], "BYE"])
    return matches


def set_active_match_from_index():
    if not state["matches"]:
        state["active_teams"] = []
        return

    index = state.get("current_match_index", 0)
    if index >= len(state["matches"]):
        state["active_teams"] = []
        return

    match = state["matches"][index]
    state["active_teams"] = match

    for team in match:
        if team != "BYE":
            state["match_scores"].setdefault(team, 0)
            state["total_scores"].setdefault(team, 0)


def reset_question_state():
    state["revealed"] = []
    state["round_bank"] = 0
    state["strike"] = False
    state["steal_mode"] = False


def current_question():
    questions = state.get("questions", DEFAULT_MAIN_QUESTIONS)
    index = state.get("current_question_index", 0)
    if not questions:
        return DEFAULT_MAIN_QUESTIONS[0]
    return questions[index % len(questions)]


def award_bank(team):
    points = state.get("round_bank", 0)
    state["match_scores"][team] = state["match_scores"].get(team, 0) + points
    state["total_scores"][team] = state["total_scores"].get(team, 0) + points
    state["message"] = f"{team} wins {points} points!"
    state["round_bank"] = 0


def end_match_and_advance():
    active = [t for t in state.get("active_teams", []) if t != "BYE"]

    if not active:
        state["message"] = "No active match."
        return

    if len(active) == 1:
        winner = active[0]
    else:
        team_a, team_b = active[0], active[1]
        score_a = state["match_scores"].get(team_a, 0)
        score_b = state["match_scores"].get(team_b, 0)

        if score_a == score_b:
            state["message"] = "Tie game! Award a tiebreaker point or manually award the bank before advancing."
            return

        winner = team_a if score_a > score_b else team_b

    state.setdefault("round_winners", []).append(winner)
    state["message"] = f"{winner} advances!"

    state["current_match_index"] += 1
    reset_question_state()
    state["current_question_index"] += 1

    if state["current_match_index"] >= len(state["matches"]):
        winners = state.get("round_winners", [])

        if len(winners) == 1:
            state["champion_team"] = winners[0]
            state["tournament_complete"] = True
            state["message"] = f"{winners[0]} wins the tournament! Fast Money is ready."
            state["matches"] = []
            state["active_teams"] = []
        else:
            state["matches"] = build_initial_matches(winners)
            state["round_winners"] = []
            state["current_match_index"] = 0
            state["match_scores"] = {}
            set_active_match_from_index()
    else:
        set_active_match_from_index()


def score_fast_money_answers(answer_list):
    total = 0
    results = []
    fm_questions = state.get("fast_money_questions", DEFAULT_FAST_MONEY_QUESTIONS)[:5]

    for idx, typed_answer in enumerate(answer_list):
        typed_answer = str(typed_answer).strip()
        question_result = {
            "question": fm_questions[idx]["question"] if idx < len(fm_questions) else "",
            "typed": typed_answer,
            "matched": "",
            "points": 0,
            "similarity": 0,
        }

        if idx < len(fm_questions) and typed_answer:
            best = None
            for correct_answer, points in fm_questions[idx]["answers"]:
                score = similarity(typed_answer, correct_answer)
                if best is None or score > best["similarity"]:
                    best = {"matched": correct_answer, "points": int(points), "similarity": score}

            if best and best["similarity"] >= FUZZY_THRESHOLD:
                question_result.update(best)
                total += best["points"]
            elif best:
                question_result.update({"matched": best["matched"], "points": 0, "similarity": best["similarity"]})

        results.append(question_result)

    return total, results


def timer_remaining():
    if not state.get("fast_money_started"):
        return FAST_MONEY_SECONDS

    elapsed = int(time.time() - int(state.get("fast_money_start_time", 0)))
    return max(0, FAST_MONEY_SECONDS - elapsed)


def render_header():
    st.markdown('<div class="main-title">Baby Shower Family Feud</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Baby Shower Tournament Edition</div>', unsafe_allow_html=True)


def render_answer_board():
    q = current_question()
    st.markdown(f'<div class="question-card">{q["question"]}</div>', unsafe_allow_html=True)

    for idx, (answer, points) in enumerate(q["answers"]):
        if idx in state.get("revealed", []):
            st.markdown(
                f'<div class="answer-tile"><span>{idx + 1}. {answer}</span><span>{points}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<div class="answer-tile answer-hidden">{idx + 1}</div>', unsafe_allow_html=True)


def render_scoreboard():
    teams = [t for t in state.get("active_teams", []) if t != "BYE"]
    if not teams:
        return

    cols = st.columns(len(teams) + 1)

    for idx, team in enumerate(teams):
        cols[idx].markdown(
            f"""
            <div class="score-card">
                <div>{team}</div>
                <div class="score-number">{state["match_scores"].get(team, 0)}</div>
                <div class="small-note">match points</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    cols[-1].markdown(
        f"""
        <div class="score-card">
            <div>Round Bank</div>
            <div class="score-number">{state.get("round_bank", 0)}</div>
            <div class="small-note">{'STEAL!' if state.get("steal_mode") else 'current question'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bracket():
    st.subheader("Tournament Bracket")

    if not state.get("locked"):
        st.info("Bracket appears after the host locks teams.")
        return

    if state.get("tournament_complete"):
        st.success(f"Champion Team: {state.get('champion_team')}")
        return

    if not state.get("matches"):
        st.info("No active matches.")
        return

    for idx, match in enumerate(state["matches"]):
        label = "Current Match" if idx == state.get("current_match_index", 0) else f"Match {idx + 1}"
        team_a = match[0] if len(match) > 0 else ""
        team_b = match[1] if len(match) > 1 else ""
        st.markdown(
            f"""
            <div class="bracket-card">
                <strong>{label}</strong><br>
                {team_a} vs {team_b}
            </div>
            """,
            unsafe_allow_html=True,
        )


render_header()

view = st.query_params.get("view", "player")
page = st.query_params.get("page", "main")
game_code = get_game_code()
has_game_code = has_game_code_in_url()

if view == "host":
    host_id = get_host_id()
    host_url = f"?view=host&game={game_code}&host={host_id}" if host_id else f"?view=host&game={game_code}"
    player_url = f"?view=player&game={game_code}"
    st.markdown(
        f'''
        <div class="info-card">
            <strong>Game Code:</strong> {game_code.upper()}<br>
            <span class="small-note">Share this player link: <code>{player_url}</code></span><br>
            <span class="small-note">Host link: <code>{host_url}</code></span>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    st.caption("Starting a new session will automatically end this host's previous game session.")
    if st.button("Start New Game Session"):
        create_new_host_session()
        st.rerun()

elif not has_game_code:
    ended_notice = st.session_state.pop("ended_session_notice", "")
    if ended_notice:
        st.warning(ended_notice)

    st.markdown(
        '<div class="info-card">Enter the game code from your host to join.</div>',
        unsafe_allow_html=True,
    )
    entered_code = st.text_input("Game code")
    if st.button("Join Game"):
        safe_code = sanitize_game_code(entered_code)
        if not safe_code:
            st.error("Enter a game code.")
        else:
            st.query_params["view"] = "player"
            st.query_params["game"] = safe_code
            st.rerun()
    st.stop()
else:
    st.markdown(
        f'<div class="info-card"><strong>Game Code:</strong> {game_code.upper()}</div>',
        unsafe_allow_html=True,
    )

if state.get("ended"):
    ended_reason = state.get("ended_reason") or "This game session has ended because the host started a new session."

    if view == "player":
        st.session_state["ended_session_notice"] = ended_reason
        st.query_params.clear()
        st.query_params["view"] = "player"
        st.rerun()

    st.warning(ended_reason)
    if view == "host":
        if st.button("Create Another New Session"):
            create_new_host_session()
            st.rerun()
    st.stop()

if page == "bracket":
    render_bracket()
    st.stop()


# -----------------------------
# Player View
# -----------------------------

if view == "player":
    st_autorefresh(interval=1000, key="player_refresh")

    if not state.get("locked"):
        st.markdown('<div class="info-card">Create or join a team before the host locks the game.</div>', unsafe_allow_html=True)

        player_name = st.text_input("Your name")
        existing_teams = list(state.get("teams", {}).keys())
        team_choice = st.selectbox("Join a team", existing_teams + ["Create new team"])
        new_team_name = ""

        if team_choice == "Create new team":
            new_team_name = st.text_input("New team name")

        if st.button("Sign In"):
            name = player_name.strip()
            team = new_team_name.strip() if team_choice == "Create new team" else team_choice

            if not name:
                st.error("Enter your name.")
            elif not team:
                st.error("Enter or select a team name.")
            else:
                state = load_state()  # reload latest session state before changing shared data
                state["teams"].setdefault(team, [])
                if name not in state["teams"][team]:
                    state["teams"][team].append(name)
                save_state(state)
                st.success(f"You are signed in as {name} on {team}.")
                st.rerun()

        if state.get("teams"):
            st.subheader("Signed-In Teams")
            for team, players in state["teams"].items():
                st.markdown(
                    f'<div class="info-card"><strong>{team}</strong><br>{", ".join(players) if players else "No players yet"}</div>',
                    unsafe_allow_html=True,
                )

    else:
        st.success("Teams are locked. Game is in progress!")
        render_scoreboard()
        render_answer_board()

        if state.get("strike"):
            st.markdown('<div class="message">Strike! The other team may steal.</div>', unsafe_allow_html=True)

        if state.get("message"):
            st.markdown(f'<div class="message">{state["message"]}</div>', unsafe_allow_html=True)

    if state.get("champion_team"):
        st.divider()
        st.header("Fast Money: Individual Championship")

        champion = state["champion_team"]
        st.markdown(
            f'<div class="info-card">Only players on <strong>{champion}</strong> are eligible. Everyone on the winning team answers at the same time.</div>',
            unsafe_allow_html=True,
        )

        eligible_players = state.get("teams", {}).get(champion, [])
        player = st.selectbox("Sign in as", [""] + eligible_players)

        if not state.get("fast_money_started"):
            st.info("Waiting for the host to start the Fast Money timer.")
        else:
            remaining = timer_remaining()
            st.metric("Time Remaining", f"{remaining}s")
            st.progress(remaining / FAST_MONEY_SECONDS)

            already_submitted = player in state.get("fast_money_answers", {})

            if not player:
                st.warning("Select your name to begin.")
            elif already_submitted:
                score = state["fast_money_answers"][player]["score"]
                st.success(f"Submitted! Your score: {score}")
            elif remaining <= 0:
                st.error("Time is up.")
            else:
                answers = []
                for idx, fm_q in enumerate(state.get("fast_money_questions", DEFAULT_FAST_MONEY_QUESTIONS)[:5]):
                    answers.append(st.text_input(f"{idx + 1}. {fm_q['question']}", key=f"fm_answer_{idx}_{player}"))

                if st.button("Submit Fast Money Answers"):
                    score, results = score_fast_money_answers(answers)
                    state = load_state()  # reload so simultaneous submissions do not overwrite each other
                    state.setdefault("fast_money_answers", {})[player] = {
                        "team": champion,
                        "score": score,
                        "answers": answers,
                        "results": results,
                    }
                    save_state(state)
                    st.success(f"Submitted! Your score: {score}")
                    st.rerun()

        if state.get("fast_money_answers"):
            st.subheader("Fast Money Leaderboard")
            leaderboard = sorted(
                state["fast_money_answers"].items(),
                key=lambda item: item[1].get("score", 0),
                reverse=True,
            )
            for rank, (player_name, data) in enumerate(leaderboard, start=1):
                st.markdown(
                    f'<div class="score-card"><strong>#{rank} {player_name}</strong><br>{data.get("score", 0)} points</div>',
                    unsafe_allow_html=True,
                )


# -----------------------------
# Host View
# -----------------------------

if view == "host":
    st.sidebar.header("Host Controls")

    with st.sidebar.expander("Appearance", expanded=True):
        theme_names = list(THEMES.keys())
        current_theme_name = state.get("theme", "Baby Girl / Purple")
        if current_theme_name not in theme_names:
            current_theme_name = "Baby Girl / Purple"

        selected_theme = st.selectbox(
            "Color Theme",
            theme_names,
            index=theme_names.index(current_theme_name),
        )

        theme_changed = selected_theme != state.get("theme")
        state["theme"] = selected_theme

        if selected_theme == "Custom":
            st.caption("Choose your own colors for this game session.")
            custom_theme = default_custom_theme()
            custom_theme.update(state.get("custom_theme", {}) if isinstance(state.get("custom_theme"), dict) else {})

            custom_theme["paper"] = st.color_picker("Page Background", custom_theme["paper"])
            custom_theme["cream"] = st.color_picker("Card Background", custom_theme["cream"])
            custom_theme["primary"] = st.color_picker("Primary Text / Header", custom_theme["primary"])
            custom_theme["secondary"] = st.color_picker("Secondary Accent", custom_theme["secondary"])
            custom_theme["accent"] = st.color_picker("Button / Soft Accent", custom_theme["accent"])
            custom_theme["border"] = st.color_picker("Borders", custom_theme["border"])
            custom_theme["highlight"] = st.color_picker("Highlight / Hidden Answers", custom_theme["highlight"])
            custom_theme["sidebar"] = st.color_picker("Sidebar Background", custom_theme["sidebar"])

            if custom_theme != state.get("custom_theme"):
                state["custom_theme"] = custom_theme
                theme_changed = True

        st.markdown(
            f'<div class="info-card"><strong>Preview:</strong><br>'
            f'<span style="color:{get_theme_colors(state)["primary"]};">Primary</span> • '
            f'<span style="color:{get_theme_colors(state)["secondary"]};">Accent</span></div>',
            unsafe_allow_html=True,
        )

        if theme_changed:
            save_state(state)
            st.rerun()

    with st.sidebar.expander("Google Sheet Questions", expanded=True):
        csv_url = st.text_input("Published CSV URL", value=state.get("google_sheet_url", ""))
        if st.button("Load Questions"):
            try:
                main_qs, fast_qs = load_questions_from_csv(csv_url)
                state["questions"] = main_qs
                state["fast_money_questions"] = fast_qs
                state["google_sheet_url"] = csv_url
                state["current_question_index"] = 0
                reset_question_state()
                save_state(state)
                st.success(f"Loaded {len(main_qs)} main questions and {len(fast_qs)} Fast Money questions.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not load questions: {error}")

    with st.sidebar.expander("Teams + Bracket", expanded=True):
        st.write(f"Teams signed up: {len(state.get('teams', {}))}")

        if not state.get("locked"):
            if st.button("Lock Teams + Build Bracket"):
                if len(state.get("teams", {})) < 2:
                    st.error("You need at least 2 teams to play.")
                else:
                    state["locked"] = True
                    state["matches"] = build_initial_matches(list(state["teams"].keys()))
                    state["current_match_index"] = 0
                    state["round_winners"] = []
                    state["match_scores"] = {}
                    state["total_scores"] = {team: 0 for team in state["teams"]}
                    state["tournament_complete"] = False
                    state["champion_team"] = ""
                    state["fast_money_started"] = False
                    state["fast_money_answers"] = {}
                    set_active_match_from_index()
                    save_state(state)
                    st.rerun()
        else:
            if st.button("Unlock Teams"):
                state["locked"] = False
                save_state(state)
                st.rerun()

    render_bracket()

    if state.get("locked") and not state.get("tournament_complete"):
        render_scoreboard()
        render_answer_board()

        q = current_question()

        st.sidebar.subheader("Reveal Answers")
        for idx, (answer, points) in enumerate(q["answers"]):
            if st.sidebar.button(f"Reveal {idx + 1}: {answer} ({points})"):
                if idx not in state["revealed"]:
                    state["revealed"].append(idx)
                    state["round_bank"] += int(points)
                    state["message"] = f"{answer} is on the board!"
                    save_state(state)
                    st.rerun()

        active = [t for t in state.get("active_teams", []) if t != "BYE"]

        st.sidebar.subheader("Award / Steal")
        if active:
            for team in active:
                if st.sidebar.button(f"Award Bank to {team}"):
                    award_bank(team)
                    save_state(state)
                    st.rerun()

        if st.sidebar.button("1 Strike → Enable Steal"):
            state["strike"] = True
            state["steal_mode"] = True
            state["message"] = "Strike! The other team gets one chance to steal."
            save_state(state)
            st.rerun()

        st.sidebar.subheader("Match Flow")
        if st.sidebar.button("End Match / Auto-Advance Winner"):
            end_match_and_advance()
            save_state(state)
            st.rerun()

        if st.sidebar.button("Reset Current Question"):
            reset_question_state()
            save_state(state)
            st.rerun()

    if state.get("tournament_complete"):
        st.success(f"Tournament Champion Team: {state.get('champion_team')}")
        st.header("Fast Money Individual Championship")

        if not state.get("fast_money_started"):
            if st.button("Start Fast Money Timer"):
                state["fast_money_started"] = True
                state["fast_money_start_time"] = int(time.time())
                state["fast_money_answers"] = {}
                save_state(state)
                st.rerun()
        else:
            remaining = timer_remaining()
            st.metric("Fast Money Time Remaining", f"{remaining}s")
            st.progress(remaining / FAST_MONEY_SECONDS)

            if st.button("Restart Fast Money Timer"):
                state["fast_money_start_time"] = int(time.time())
                state["fast_money_answers"] = {}
                save_state(state)
                st.rerun()

        if state.get("fast_money_answers"):
            st.subheader("Leaderboard")
            leaderboard = sorted(
                state["fast_money_answers"].items(),
                key=lambda item: item[1].get("score", 0),
                reverse=True,
            )

            for rank, (player_name, data) in enumerate(leaderboard, start=1):
                st.markdown(
                    f"""
                    <div class="score-card">
                        <strong>#{rank} {player_name}</strong><br>
                        {data.get("score", 0)} points
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander(f"See {player_name}'s answer matches"):
                    for result in data.get("results", []):
                        st.write(
                            f"{result.get('question')}: typed '{result.get('typed')}' → matched '{result.get('matched')}' "
                            f"({result.get('similarity')}%) = {result.get('points')} pts"
                        )

    st.sidebar.divider()
    if st.sidebar.button("Reset Entire Game"):
        fresh = default_state()
        save_state(fresh)
        st.rerun()
