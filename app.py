import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import json
import os
import random
import time
import tempfile
from difflib import SequenceMatcher
from filelock import FileLock

st.set_page_config(page_title="Baby in Bloom Feud", layout="wide")

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

DEFAULT_GAME_CODE = "default"

DEFAULT_QUESTIONS = [
    {
        "question": "Name something parents always carry in a diaper bag.",
        "answers": [["Diapers", 35], ["Wipes", 25], ["Bottle", 15], ["Snacks", 10], ["Extra clothes", 8], ["Pacifier", 7]],
        "type": "main",
    },
    {
        "question": "Fast Money: Name something a baby needs every day.",
        "answers": [["Diapers", 35], ["Milk", 30], ["Sleep", 18], ["Love", 10], ["Clothes", 7]],
        "type": "fast_money",
    },
]

APP_TITLE = "🌸 Baby in Bloom Feud 🌸"
FAST_MONEY_SECONDS = 25
FUZZY_MATCH_THRESHOLD = 0.78


def sanitize_game_code(game_code):
    safe_code = "".join(ch for ch in str(game_code).strip().lower() if ch.isalnum() or ch in ("-", "_"))
    return safe_code or DEFAULT_GAME_CODE


def get_game_code():
    return sanitize_game_code(st.query_params.get("game", DEFAULT_GAME_CODE))


def get_state_file(game_code=None):
    code = sanitize_game_code(game_code or get_game_code())
    return os.path.join(SESSIONS_DIR, f"{code}.json")


def get_lock_file(game_code=None):
    return get_state_file(game_code) + ".lock"


def session_url_params(view="player", page="game"):
    game_code = get_game_code()
    return f"?view={view}&page={page}&game={game_code}"


def default_state():
    return {
        "locked": False,
        "teams": [],
        "scores": {},
        "questions": DEFAULT_QUESTIONS,
        "google_sheet_url": "",
        "match_index": 0,
        "match_question_number": 1,
        "current_question_index": 0,
        "revealed": [],
        "round_bank": 0,
        "strikes": 0,
        "buzzed": "",
        "message": "Teams may sign up on their phones.",
        "bracket_round": 1,
        "bracket_matches": [],
        "match_winners": [],
        "champion": "",
        "mode": "signup",
        "fast_money_teams": [],
        "fast_money_active_team": "",
        "fast_money_active_player": "Player 1",
        "fast_money_started_at": None,
        "fast_money_submissions": {},
        "fast_money_scores": {},
    }


def atomic_write_json(path, data):
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def save_state(state, game_code=None):
    state_file = get_state_file(game_code)
    lock_file = get_lock_file(game_code)
    with FileLock(lock_file):
        atomic_write_json(state_file, state)


def load_state(game_code=None):
    state_file = get_state_file(game_code)
    lock_file = get_lock_file(game_code)

    with FileLock(lock_file):
        if not os.path.exists(state_file):
            atomic_write_json(state_file, default_state())

        with open(state_file, "r") as f:
            state = json.load(f)

        fresh = default_state()
        changed = False
        for key, value in fresh.items():
            if key not in state:
                state[key] = value
                changed = True

        if changed:
            atomic_write_json(state_file, state)

        return state


def update_state(mutator, game_code=None):
    """
    Safely reloads the latest state, applies changes, saves, and returns the updated state.
    Use this for actions where multiple users may click at the same time.
    """
    state_file = get_state_file(game_code)
    lock_file = get_lock_file(game_code)

    with FileLock(lock_file):
        if not os.path.exists(state_file):
            state = default_state()
        else:
            with open(state_file, "r") as f:
                state = json.load(f)

        fresh = default_state()
        for key, value in fresh.items():
            if key not in state:
                state[key] = value

        mutator(state)
        atomic_write_json(state_file, state)
        return state


def reset_main_round(state):
    state["revealed"] = []
    state["round_bank"] = 0
    state["strikes"] = 0
    state["buzzed"] = ""


def normalize_text(text):
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum() or ch.isspace()).strip()


def similarity(a, b):
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def score_answer(user_answer, answer_bank):
    best_answer = ""
    best_points = 0
    best_score = 0
    for official, points in answer_bank:
        sim = similarity(user_answer, official)
        if sim > best_score:
            best_score = sim
            best_answer = official
            best_points = int(points)
    if best_score >= FUZZY_MATCH_THRESHOLD:
        return best_points, best_answer, best_score
    return 0, "No match", best_score


def load_questions_from_google_sheet(csv_url):
    df = pd.read_csv(csv_url)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"question", "answer", "points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}. Required: question, answer, points. Optional: type, category")

    if "type" not in df.columns:
        df["type"] = "main"

    questions = []
    group_cols = ["type", "question"]
    for (qtype, question_text), group in df.groupby(group_cols, sort=False):
        answers = []
        for _, row in group.iterrows():
            if pd.notna(row["answer"]):
                answers.append([str(row["answer"]).strip(), int(row["points"])])
        if answers:
            questions.append({
                "type": str(qtype).strip().lower(),
                "question": str(question_text).strip(),
                "answers": answers,
            })
    return questions


def main_questions(state):
    return [q for q in state.get("questions", DEFAULT_QUESTIONS) if q.get("type", "main") == "main"]


def fast_money_questions(state):
    return [q for q in state.get("questions", DEFAULT_QUESTIONS) if q.get("type") == "fast_money"]


def build_bracket(teams):
    shuffled = teams[:]
    random.shuffle(shuffled)
    matches = []
    for i in range(0, len(shuffled), 2):
        if i + 1 < len(shuffled):
            matches.append({"team_a": shuffled[i], "team_b": shuffled[i + 1], "winner": ""})
        else:
            matches.append({"team_a": shuffled[i], "team_b": "BYE", "winner": shuffled[i]})
    return matches


def start_tournament(state):
    state["locked"] = True
    state["mode"] = "main"
    state["bracket_round"] = 1
    state["bracket_matches"] = build_bracket(state["teams"])
    state["match_index"] = 0
    state["match_question_number"] = 1
    state["current_question_index"] = 0
    state["match_winners"] = [m["winner"] for m in state["bracket_matches"] if m["winner"]]
    state["champion"] = ""
    reset_main_round(state)
    state["message"] = "Tournament locked. Round 1 started."


def current_match(state):
    matches = state.get("bracket_matches", [])
    if not matches:
        return None
    idx = min(state.get("match_index", 0), len(matches) - 1)
    return matches[idx]


def current_main_question(state):
    qs = main_questions(state)
    if not qs:
        return DEFAULT_QUESTIONS[0]
    return qs[state.get("current_question_index", 0) % len(qs)]


def current_fast_money_question(state):
    qs = fast_money_questions(state)
    if not qs:
        return DEFAULT_QUESTIONS[1]
    idx = 0
    if state["fast_money_active_player"] == "Player 2" and len(qs) > 1:
        idx = 1
    return qs[idx % len(qs)]


def advance_to_next_match_or_round(state):
    matches = state["bracket_matches"]
    if state["match_index"] + 1 < len(matches):
        state["match_index"] += 1
        state["match_question_number"] = 1
        state["current_question_index"] += 1
        reset_main_round(state)
        state["message"] = "Next match started."
        return

    winners = [m["winner"] for m in matches if m["winner"] and m["winner"] != "BYE"]
    if len(winners) <= 2:
        state["fast_money_teams"] = winners
        state["fast_money_active_team"] = winners[0] if winners else ""
        state["mode"] = "fast_money"
        state["message"] = "Final two teams advanced to Fast Money!"
        state["fast_money_scores"] = {team: 0 for team in winners}
        state["fast_money_submissions"] = {}
        state["fast_money_started_at"] = None
        return

    state["bracket_round"] += 1
    state["bracket_matches"] = build_bracket(winners)
    state["match_index"] = 0
    state["match_question_number"] = 1
    state["current_question_index"] += 1
    reset_main_round(state)
    state["message"] = f"Bracket Round {state['bracket_round']} started."


def render_css():
    st.markdown("""
    <style>
    .stApp { background: radial-gradient(circle at top, #fff6fa 0%, #f8d9e4 45%, #eeb2c9 100%); }
    .title { text-align:center; font-size:58px; font-weight:900; color:#fff; text-shadow:3px 3px 0 #7b2348, 6px 6px 14px rgba(0,0,0,.25); margin-bottom:8px; }
    .subtitle { text-align:center; font-size:22px; color:#7b2348; font-weight:800; margin-bottom:22px; }
    .board { background:linear-gradient(180deg,#9d3260,#52122f); color:white; border:8px solid #ffd5e4; border-radius:34px; padding:26px; font-size:34px; font-weight:900; text-align:center; box-shadow:0 12px 28px rgba(80,20,50,.35); margin:18px 0; }
    .answer-revealed { background:linear-gradient(180deg,#fff8fb,#f7c7d9); color:#5c1435; border:5px solid #7b2348; border-radius:22px; padding:18px; font-size:26px; font-weight:900; margin:10px 0; display:flex; justify-content:space-between; }
    .answer-hidden { background:linear-gradient(180deg,#7b2348,#3e0d25); color:#ffd5e4; border:5px solid #ffd5e4; border-radius:22px; padding:18px; font-size:30px; font-weight:900; text-align:center; margin:10px 0; }
    .card { background:#fff8fb; border:4px solid #7b2348; border-radius:24px; padding:18px; color:#5c1435; font-size:22px; font-weight:900; text-align:center; box-shadow:0 6px 16px rgba(80,20,50,.18); }
    .bracket { background:#fff8fb; border:3px solid #c8658d; border-radius:18px; padding:14px; color:#5c1435; font-weight:800; margin:8px 0; }
    .message { text-align:center; color:#5c1435; font-size:26px; font-weight:900; margin-top:16px; }
    .small-link-box { background:#fff8fb; border:2px solid #c8658d; border-radius:14px; padding:10px; color:#5c1435; font-weight:700; margin-bottom:12px; }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown(f'<div class="title">{APP_TITLE}</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Tournament Edition</div>', unsafe_allow_html=True)


def render_session_info(view):
    game_code = get_game_code()
    st.sidebar.markdown("---")
    st.sidebar.subheader("Game Session")
    st.sidebar.write(f"**Game code:** `{game_code}`")

    new_code = st.sidebar.text_input("Switch/create game code", value=game_code)
    if st.sidebar.button("Open Game Session"):
        safe_code = sanitize_game_code(new_code)
        st.query_params["game"] = safe_code
        st.query_params["view"] = view
        st.query_params["page"] = st.query_params.get("page", "game")
        st.rerun()

    host_link = session_url_params(view="host")
    player_link = session_url_params(view="player")
    bracket_link = session_url_params(view=view, page="bracket")

    st.sidebar.markdown(
        f"""
        <div class="small-link-box">
        Host link: <code>{host_link}</code><br><br>
        Player link: <code>{player_link}</code><br><br>
        Bracket link: <code>{bracket_link}</code>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bracket(state):
    st.subheader("🏆 Bracket")
    matches = state.get("bracket_matches", [])
    if not matches:
        st.info("Bracket will appear after the host locks the game.")
        return
    cols = st.columns(min(4, max(1, len(matches))))
    for i, m in enumerate(matches):
        winner_line = f"<br><b>Winner:</b> {m['winner']}" if m.get("winner") else ""
        active = " ⭐ Current Match" if i == state.get("match_index", 0) and state.get("mode") == "main" else ""
        cols[i % len(cols)].markdown(
            f'<div class="bracket">Round {state.get("bracket_round", 1)} — Match {i+1}{active}<br>{m["team_a"]} vs {m["team_b"]}{winner_line}</div>',
            unsafe_allow_html=True,
        )


def render_signup(state, view):
    st.markdown('<div class="board">Team Sign-Up</div>', unsafe_allow_html=True)
    if state["locked"]:
        st.warning("Team sign-up is locked.")
    else:
        if view == "player":
            team_name = st.text_input("Create your team name")
            if st.button("Register Team"):
                name = team_name.strip()

                def register_team(latest_state):
                    if name and name not in latest_state["teams"] and len(latest_state["teams"]) < 8 and not latest_state["locked"]:
                        latest_state["teams"].append(name)
                        latest_state["scores"][name] = 0
                        latest_state["message"] = f"{name} joined the game!"

                latest = load_state()
                if not name:
                    st.error("Enter a team name.")
                elif latest["locked"]:
                    st.error("Sign-up is locked.")
                elif name in latest["teams"]:
                    st.error("That team name is already taken.")
                elif len(latest["teams"]) >= 8:
                    st.error("Team limit reached. Ask the host to start the game.")
                else:
                    update_state(register_team)
                    st.rerun()
        else:
            st.info("Guests can sign up from the player link. Lock the game when 6–8 teams have signed up.")

    st.subheader(f"Registered Teams: {len(state['teams'])}/8")
    if state["teams"]:
        for t in state["teams"]:
            st.write(f"• {t}")
    else:
        st.write("No teams yet.")


def render_main_game(state):
    match = current_match(state)
    q = current_main_question(state)
    if not match:
        st.info("Waiting for host to lock game and create bracket.")
        return

    left, right = match["team_a"], match["team_b"]
    score_cols = st.columns(3)
    score_cols[0].markdown(f'<div class="card">{left}<br>{state["scores"].get(left, 0)}</div>', unsafe_allow_html=True)
    score_cols[1].markdown(f'<div class="card">Match Q {state["match_question_number"]}/3<br>Bank: {state["round_bank"]}</div>', unsafe_allow_html=True)
    score_cols[2].markdown(f'<div class="card">{right}<br>{state["scores"].get(right, 0)}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="board">{q["question"]}</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (answer, points) in enumerate(q["answers"]):
        if i in state["revealed"]:
            cols[i % 2].markdown(f'<div class="answer-revealed"><span>{i+1}. {answer}</span><span>{points}</span></div>', unsafe_allow_html=True)
        else:
            cols[i % 2].markdown(f'<div class="answer-hidden">{i+1}</div>', unsafe_allow_html=True)
    if state["strikes"]:
        st.markdown(f'<div class="message">{"❌" * state["strikes"]}</div>', unsafe_allow_html=True)
    if state["buzzed"]:
        st.markdown(f'<div class="message">🚨 Buzzed first: {state["buzzed"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="message">{state["message"]}</div>', unsafe_allow_html=True)


def render_fast_money(state, view):
    teams = state.get("fast_money_teams", [])
    st.markdown('<div class="board">Fast Money Final</div>', unsafe_allow_html=True)
    if len(teams) < 2:
        st.info("Fast Money starts after the bracket narrows to 2 teams.")
        return

    score_cols = st.columns(2)
    for i, team in enumerate(teams[:2]):
        score_cols[i].markdown(f'<div class="card">{team}<br>{state["fast_money_scores"].get(team, 0)} pts</div>', unsafe_allow_html=True)

    active_team = state.get("fast_money_active_team") or teams[0]
    active_player = state.get("fast_money_active_player", "Player 1")
    q = current_fast_money_question(state)

    st.subheader(f"Current Fast Money: {active_team} — {active_player}")
    st.write(q["question"])

    started_at = state.get("fast_money_started_at")
    if started_at:
        elapsed = int(time.time() - started_at)
        remaining = max(0, FAST_MONEY_SECONDS - elapsed)
        st.metric("Time Remaining", f"{remaining}s")
        if remaining > 0:
            st_autorefresh(interval=1000, key="fm_timer")
        else:
            st.warning("Time is up. Submit now or host can move to the next player.")
    else:
        st.info("Waiting for host to start the Fast Money timer.")

    if view == "player" and started_at:
        key_base = f"{active_team}_{active_player}"
        answers = []
        with st.form("fast_money_form"):
            for i in range(5):
                answers.append(st.text_input(f"Answer {i+1}", key=f"fm_{key_base}_{i}"))
            submitted = st.form_submit_button("Submit Fast Money Answers")
        if submitted:
            total = 0
            details = []
            for ans in answers:
                points, matched, sim = score_answer(ans, q["answers"])
                total += points
                details.append({"answer": ans, "matched": matched, "points": points, "similarity": sim})

            def submit_fast_money(latest_state):
                latest_state["fast_money_submissions"][key_base] = details
                latest_state["fast_money_scores"][active_team] = latest_state["fast_money_scores"].get(active_team, 0) + total
                latest_state["message"] = f"{active_team} {active_player} submitted Fast Money answers."
                latest_state["fast_money_started_at"] = None

            update_state(submit_fast_money)
            st.success(f"Submitted! Awarded {total} points.")
            st.rerun()

    with st.expander("Fast Money Submissions / Scoring"):
        for key, rows in state.get("fast_money_submissions", {}).items():
            st.write(f"**{key}**")
            for row in rows:
                st.write(f"{row['answer']} → {row['matched']} = {row['points']} pts")

    if all(team in state.get("fast_money_scores", {}) for team in teams[:2]):
        scores = state["fast_money_scores"]
        if scores.get(teams[0], 0) != scores.get(teams[1], 0):
            winner = max(teams[:2], key=lambda t: scores.get(t, 0))
            st.success(f"🏆 Current winner: {winner}")


def render_host_controls(state):
    st.sidebar.title("Host Controls")

    st.sidebar.subheader("Google Sheet Questions")
    url = st.sidebar.text_input("Published CSV URL", value=state.get("google_sheet_url", ""))
    if st.sidebar.button("Load Questions"):
        try:
            questions = load_questions_from_google_sheet(url)

            def load_questions(latest_state):
                latest_state["questions"] = questions
                latest_state["google_sheet_url"] = url
                latest_state["current_question_index"] = 0
                reset_main_round(latest_state)
                latest_state["message"] = "Questions loaded from Google Sheet."

            update_state(load_questions)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Could not load questions: {e}")

    st.sidebar.subheader("Team Sign-Up")
    st.sidebar.write(f"Teams: {len(state['teams'])}/8")
    if not state["locked"]:
        if st.sidebar.button("Lock Game + Create Bracket", disabled=not (6 <= len(state["teams"]) <= 8)):
            def lock_game(latest_state):
                if 6 <= len(latest_state["teams"]) <= 8:
                    start_tournament(latest_state)
            update_state(lock_game)
            st.rerun()
        if len(state["teams"]) < 6:
            st.sidebar.caption("Need at least 6 teams to lock.")
    else:
        st.sidebar.success("Game locked")

    if st.sidebar.button("Unlock Sign-Up / Reset Bracket"):
        def unlock(latest_state):
            latest_state["locked"] = False
            latest_state["mode"] = "signup"
            latest_state["bracket_matches"] = []
            latest_state["match_winners"] = []
            latest_state["champion"] = ""
        update_state(unlock)
        st.rerun()

    if state.get("mode") == "main":
        st.sidebar.subheader("Main Game")
        q = current_main_question(state)
        for i, (answer, points) in enumerate(q["answers"]):
            if st.sidebar.button(f"Reveal {answer} ({points})"):
                def reveal_answer(latest_state, idx=i, ans=answer, pts=points):
                    if idx not in latest_state["revealed"]:
                        latest_state["revealed"].append(idx)
                        latest_state["round_bank"] += int(pts)
                        latest_state["message"] = f"{ans} is on the board!"
                update_state(reveal_answer)
                st.rerun()

        match = current_match(state)
        if match:
            left, right = match["team_a"], match["team_b"]
            if st.sidebar.button(f"Award Bank to {left}"):
                def award_left(latest_state):
                    latest_state["scores"][left] = latest_state["scores"].get(left, 0) + latest_state["round_bank"]
                    latest_state["round_bank"] = 0
                update_state(award_left)
                st.rerun()
            if right != "BYE" and st.sidebar.button(f"Award Bank to {right}"):
                def award_right(latest_state):
                    latest_state["scores"][right] = latest_state["scores"].get(right, 0) + latest_state["round_bank"]
                    latest_state["round_bank"] = 0
                update_state(award_right)
                st.rerun()

            winner_options = [left] if right == "BYE" else [left, right]
            winner = st.sidebar.selectbox("Match Winner", winner_options)
            if st.sidebar.button("End Match / Advance Winner"):
                def end_match(latest_state):
                    latest_state["bracket_matches"][latest_state["match_index"]]["winner"] = winner
                    latest_state["message"] = f"{winner} advances!"
                    advance_to_next_match_or_round(latest_state)
                update_state(end_match)
                st.rerun()

        if st.sidebar.button("Next Question in Match"):
            def next_question(latest_state):
                if latest_state["match_question_number"] < 3:
                    latest_state["match_question_number"] += 1
                    latest_state["current_question_index"] += 1
                    reset_main_round(latest_state)
                    latest_state["message"] = "Next question in this match."
                else:
                    latest_state["message"] = "This match has completed 3 questions. Select and advance a winner."
            update_state(next_question)
            st.rerun()

        buzz = st.sidebar.text_input("Buzz input / player name")
        if st.sidebar.button("Set Buzz Winner"):
            def set_buzz(latest_state):
                latest_state["buzzed"] = buzz
            update_state(set_buzz)
            st.rerun()
        if st.sidebar.button("Add Strike"):
            def add_strike(latest_state):
                latest_state["strikes"] = min(3, latest_state["strikes"] + 1)
            update_state(add_strike)
            st.rerun()
        if st.sidebar.button("Clear Strikes"):
            def clear_strikes(latest_state):
                latest_state["strikes"] = 0
            update_state(clear_strikes)
            st.rerun()

    if state.get("mode") == "fast_money":
        st.sidebar.subheader("Fast Money")
        teams = state.get("fast_money_teams", [])
        if teams:
            selected_team = st.sidebar.selectbox(
                "Active Team",
                teams,
                index=teams.index(state.get("fast_money_active_team", teams[0])) if state.get("fast_money_active_team") in teams else 0,
            )
            selected_player = st.sidebar.selectbox("Active Player", ["Player 1", "Player 2"])

            if selected_team != state.get("fast_money_active_team") or selected_player != state.get("fast_money_active_player"):
                def set_fast_money_active(latest_state):
                    latest_state["fast_money_active_team"] = selected_team
                    latest_state["fast_money_active_player"] = selected_player
                update_state(set_fast_money_active)

            if st.sidebar.button("Start Timer"):
                def start_timer(latest_state):
                    latest_state["fast_money_active_team"] = selected_team
                    latest_state["fast_money_active_player"] = selected_player
                    latest_state["fast_money_started_at"] = int(time.time())
                update_state(start_timer)
                st.rerun()
            if st.sidebar.button("Stop / Reset Timer"):
                def stop_timer(latest_state):
                    latest_state["fast_money_started_at"] = None
                update_state(stop_timer)
                st.rerun()
            if st.sidebar.button("Crown Fast Money Winner"):
                def crown_winner(latest_state):
                    scores = latest_state.get("fast_money_scores", {})
                    winner = max(teams, key=lambda t: scores.get(t, 0))
                    latest_state["champion"] = winner
                    latest_state["message"] = f"{winner} wins Baby in Bloom Feud!"
                update_state(crown_winner)
                st.rerun()

    st.sidebar.subheader("Danger Zone")
    if st.sidebar.button("Reset This Game Session"):
        save_state(default_state())
        st.rerun()


view = st.query_params.get("view", "player")
page = st.query_params.get("page", "game")

state = load_state()

render_css()
render_header()
render_session_info(view)

if view != "host":
    st_autorefresh(interval=1000, key="player_auto_refresh")

if view == "host":
    render_host_controls(state)

if page == "bracket":
    render_bracket(state)
elif state.get("mode") == "fast_money":
    render_fast_money(state, view)
elif state.get("mode") == "main":
    render_main_game(state)
    render_bracket(state)
else:
    render_signup(state, view)
    render_bracket(state)
