import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import json
import os
import random
import time
import html
import base64
from pathlib import Path
from difflib import SequenceMatcher

st.set_page_config(page_title="Baby in Bloom Feud", layout="wide")

STATE_FILE = "game_state.json"

DEFAULT_QUESTIONS = [
    {
        "question": "Name something parents always carry in a diaper bag.",
        "answers": [["Diapers", 35], ["Wipes", 25], ["Bottle", 15], ["Snacks", 10], ["Extra clothes", 8], ["Pacifier", 7]],
        "type": "main",
    },
    {
        "question": "Name something a baby needs every day.",
        "answers": [["Diapers", 35], ["Milk", 30], ["Sleep", 18], ["Love", 10], ["Clothes", 7]],
        "type": "fast_money",
    },
    {
        "question": "Name something parents keep near the crib.",
        "answers": [["Monitor", 30], ["Pacifier", 25], ["Blanket", 18], ["Diapers", 15], ["Wipes", 12]],
        "type": "fast_money",
    },
    {
        "question": "Name something babies do when they are tired.",
        "answers": [["Cry", 35], ["Rub eyes", 25], ["Yawn", 20], ["Fuss", 12], ["Sleep", 8]],
        "type": "fast_money",
    },
    {
        "question": "Name something you buy before a baby arrives.",
        "answers": [["Diapers", 30], ["Clothes", 25], ["Crib", 20], ["Car seat", 15], ["Stroller", 10]],
        "type": "fast_money",
    },
    {
        "question": "Name something people bring to a baby shower.",
        "answers": [["Gift", 35], ["Diapers", 25], ["Card", 18], ["Flowers", 12], ["Food", 10]],
        "type": "fast_money",
    },
]

APP_TITLE = "Baby Family Feud"
FAST_MONEY_SECONDS = 25
FUZZY_MATCH_THRESHOLD = 0.78


def default_state():
    return {
        "locked": False,
        "teams": [],
        "team_players": {},
        "scores": {},
        "match_scores": {},
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


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state():
    if not os.path.exists(STATE_FILE):
        save_state(default_state())
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    # Backward-compatible missing-key repair
    fresh = default_state()
    changed = False
    for key, value in fresh.items():
        if key not in state:
            state[key] = value
            changed = True
    if changed:
        save_state(state)
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
        raise ValueError(
            f"Missing columns: {', '.join(missing)}. "
            "Required: question, answer, points, plus game_type or type."
        )

    # Support either column name. Your Google Sheet can use game_type.
    # Valid values are main and fast_money.
    if "game_type" in df.columns:
        df["type"] = df["game_type"]
    elif "type" not in df.columns:
        df["type"] = "main"

    df["type"] = (
        df["type"]
        .fillna("main")
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
    )

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

    fast_count = len([q for q in questions if q.get("type") == "fast_money"])
    if fast_count < 5:
        raise ValueError(
            f"Found only {fast_count} fast_money questions. "
            "Add at least 5 rows/groups where game_type is fast_money."
        )

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
    set_current_match_scores(state)
    state["message"] = "Tournament locked. Round 1 started."


def current_match(state):
    matches = state.get("bracket_matches", [])
    if not matches:
        return None
    idx = min(state.get("match_index", 0), len(matches) - 1)
    return matches[idx]




def set_current_match_scores(state):
    match = current_match(state)
    if not match:
        state["match_scores"] = {}
        return
    left, right = match["team_a"], match["team_b"]
    state["match_scores"] = {left: 0}
    if right != "BYE":
        state["match_scores"][right] = 0


def automatic_match_winner(state):
    match = current_match(state)
    if not match:
        return None, "No active match."
    left, right = match["team_a"], match["team_b"]
    if right == "BYE":
        return left, f"{left} advances with a bye."
    scores = state.get("match_scores", {})
    left_score = scores.get(left, 0)
    right_score = scores.get(right, 0)
    if left_score > right_score:
        return left, f"{left} advances with {left_score} points."
    if right_score > left_score:
        return right, f"{right} advances with {right_score} points."
    return None, f"Tie game: {left} {left_score} — {right} {right_score}. Award a tie-breaker point or play another question."

def current_main_question(state):
    qs = main_questions(state)
    if not qs:
        return DEFAULT_QUESTIONS[0]
    return qs[state.get("current_question_index", 0) % len(qs)]


def current_fast_money_set(state):
    qs = fast_money_questions(state)
    if not qs:
        return [DEFAULT_QUESTIONS[1]]
    return qs[:5]


def get_fast_money_finalist_teams(state):
    """Return the two teams allowed to play Fast Money.

    Primary source is state['fast_money_teams']. As a safety fallback, if the
    host opened Fast Money from the current bracket match, use the two active
    match teams. This prevents the player page from getting stuck on the
    'starts after bracket narrows to 2 teams' message.
    """
    teams = [t for t in state.get("fast_money_teams", []) if t and t != "BYE"]
    if len(teams) >= 2:
        return teams[:2]

    match = current_match(state)
    if match:
        fallback = [match.get("team_a"), match.get("team_b")]
        fallback = [t for t in fallback if t and t != "BYE"]
        if len(fallback) >= 2:
            return fallback[:2]

    return teams


def start_fast_money_with_teams(state, teams):
    teams = [t for t in teams if t and t != "BYE"][:2]
    state["mode"] = "fast_money"
    state["fast_money_teams"] = teams
    state["fast_money_active_team"] = teams[0] if teams else ""
    state["fast_money_active_player"] = "Player 1"
    state["fast_money_started_at"] = None
    state["fast_money_scores"] = {team: state.get("fast_money_scores", {}).get(team, 0) for team in teams}
    state["fast_money_submissions"] = {}
    state["message"] = "Fast Money is ready. Players can sign in from their phones."


def advance_to_next_match_or_round(state):
    matches = state["bracket_matches"]
    if state["match_index"] + 1 < len(matches):
        state["match_index"] += 1
        state["match_question_number"] = 1
        state["current_question_index"] += 1
        reset_main_round(state)
        set_current_match_scores(state)
        state["message"] = "Next match started."
        return

    winners = [m["winner"] for m in matches if m["winner"] and m["winner"] != "BYE"]
    if len(winners) == 2:
        start_fast_money_with_teams(state, winners)
        state["message"] = "Final two teams advanced to Fast Money!"
        return

    if len(winners) == 1:
        state["champion"] = winners[0]
        state["mode"] = "complete"
        state["message"] = f"{winners[0]} wins the tournament!"
        return

    state["bracket_round"] += 1
    state["bracket_matches"] = build_bracket(winners)
    state["match_index"] = 0
    state["match_question_number"] = 1
    state["current_question_index"] += 1
    reset_main_round(state)
    set_current_match_scores(state)
    state["message"] = f"Bracket Round {state['bracket_round']} started."


def get_custom_font_css():
    """Load SophiaRonald.ttf from the same folder as app.py for the title font.
    If the font file is missing, the app still works with a cursive fallback.
    """
    font_path = Path(__file__).with_name("SophiaRonald.ttf")
    if not font_path.exists():
        return ""
    try:
        encoded_font = base64.b64encode(font_path.read_bytes()).decode("utf-8")
        return f"""
        @font-face {{
            font-family: 'SophiaRonald';
            src: url(data:font/truetype;charset=utf-8;base64,{encoded_font}) format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
        """
    except Exception:
        return ""


def render_css():
    custom_font_css = get_custom_font_css()
    st.markdown("""
    <style>
    """ + custom_font_css + """
    .stApp { background: radial-gradient(circle at top, #fff6fa 0%, #f8d9e4 45%, #eeb2c9 100%); }
    .title { text-align:center; font-family:'SophiaRonald', 'Brush Script MT', cursive; font-size:200px; font-weight:400; color:#7b2348; text-shadow:2px 2px 0 #fff, 6px 6px 14px rgba(0,0,0,.25); margin-bottom:8px; }
    .subtitle { text-align:center; font-size:22px; color:#7b2348; font-weight:800; margin-bottom:22px; }
    .board { background:linear-gradient(180deg,#9d3260,#52122f); color:white; border:8px solid #ffd5e4; border-radius:34px; padding:26px; font-size:34px; font-weight:900; text-align:center; box-shadow:0 12px 28px rgba(80,20,50,.35); margin:18px 0; }
    .answer-revealed { background:linear-gradient(180deg,#fff8fb,#f7c7d9); color:#5c1435; border:5px solid #7b2348; border-radius:22px; padding:18px; font-size:26px; font-weight:900; margin:10px 0; display:flex; justify-content:space-between; }
    .answer-hidden { background:linear-gradient(180deg,#7b2348,#3e0d25); color:#ffd5e4; border:5px solid #ffd5e4; border-radius:22px; padding:18px; font-size:30px; font-weight:900; text-align:center; margin:10px 0; }
    .answer-grid { display:grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; }
    @media (max-width: 700px) { .title { font-size: 52px; line-height: 1.05; } .answer-grid { grid-template-columns: 1fr; } .answer-revealed, .answer-hidden { margin: 6px 0; font-size: 24px; } }
    .card { background:#fff8fb; border:4px solid #7b2348; border-radius:24px; padding:18px; color:#5c1435; font-size:22px; font-weight:900; text-align:center; box-shadow:0 6px 16px rgba(80,20,50,.18); }
    .bracket { background:#fff8fb; border:3px solid #c8658d; border-radius:18px; padding:14px; color:#5c1435; font-weight:800; margin:8px 0; }
    .message { text-align:center; color:#5c1435; font-size:26px; font-weight:900; margin-top:16px; }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown(f'<div class="title">{APP_TITLE}</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Tournament Edition</div>', unsafe_allow_html=True)


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
    state.setdefault("team_players", {})

    if state["locked"]:
        st.warning("Team sign-up is locked. Ask the host if you need to join or change teams.")
    else:
        if view == "player":
            create_tab, join_tab = st.tabs(["Create Team", "Sign In to Team"])

            with create_tab:
                team_name = st.text_input("Create your team name")
                captain_name = st.text_input("Your name", key="captain_name")
                if st.button("Register Team"):
                    name = team_name.strip()
                    captain = captain_name.strip()
                    if not name:
                        st.error("Enter a team name.")
                    elif name in state["teams"]:
                        st.error("That team name already exists. Use the Sign In tab to join it.")
                    else:
                        state["teams"].append(name)
                        state["scores"][name] = 0
                        state["team_players"][name] = []
                        if captain:
                            state["team_players"][name].append(captain)
                        state["message"] = f"{name} joined the game!"
                        save_state(state)
                        st.rerun()

            with join_tab:
                if not state["teams"]:
                    st.info("No teams have been created yet. Create the first team above.")
                else:
                    selected_team = st.selectbox("Choose your team", state["teams"])
                    player_name = st.text_input("Your name", key="join_player_name")
                    if st.button("Sign In to Team"):
                        player = player_name.strip()
                        if not player:
                            st.error("Enter your name.")
                        else:
                            state["team_players"].setdefault(selected_team, [])
                            if player not in state["team_players"][selected_team]:
                                state["team_players"][selected_team].append(player)
                            state["message"] = f"{player} signed in to {selected_team}."
                            save_state(state)
                            st.success(f"You're signed in to {selected_team}!")
                            st.rerun()
        else:
            st.info("Guests can create teams or sign in to an existing team from the player link. Lock the game when you are ready.")

    st.subheader(f"Registered Teams: {len(state['teams'])}")
    if state["teams"]:
        for t in state["teams"]:
            players = state.get("team_players", {}).get(t, [])
            player_text = ", ".join(players) if players else "No signed-in players yet"
            st.write(f"• **{t}** — {player_text}")
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
    match_scores = state.get("match_scores", {})
    score_cols[0].markdown(f'<div class="card">{left}<br>Match: {match_scores.get(left, 0)}<br>Total: {state["scores"].get(left, 0)}</div>', unsafe_allow_html=True)
    score_cols[1].markdown(f'<div class="card">Match Q {state["match_question_number"]}/3<br>Bank: {state["round_bank"]}</div>', unsafe_allow_html=True)
    score_cols[2].markdown(f'<div class="card">{right}<br>Match: {match_scores.get(right, 0)}<br>Total: {state["scores"].get(right, 0)}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="board">{html.escape(str(q["question"]))}</div>', unsafe_allow_html=True)

    # Mobile-order fix:
    # Streamlit columns stack as 1,3,5,2,4,6 on phones.
    # This CSS grid keeps the visual order as 1,2,3,4,5,6 on mobile
    # while still showing a two-column board on desktop.
    answer_tiles = []
    for i, (answer, points) in enumerate(q["answers"]):
        if i in state["revealed"]:
            answer_tiles.append(
                f'<div class="answer-revealed"><span>{i+1}. {html.escape(str(answer))}</span><span>{points}</span></div>'
            )
        else:
            answer_tiles.append(f'<div class="answer-hidden">{i+1}</div>')

    st.markdown(
        '<div class="answer-grid">' + ''.join(answer_tiles) + '</div>',
        unsafe_allow_html=True,
    )
    if state["strikes"]:
        st.markdown(f'<div class="message">{"❌" * state["strikes"]}</div>', unsafe_allow_html=True)
    if state["buzzed"]:
        st.markdown(f'<div class="message">🚨 Buzzed first: {state["buzzed"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="message">{state["message"]}</div>', unsafe_allow_html=True)


def render_fast_money(state, view):
    teams = get_fast_money_finalist_teams(state)
    st.markdown('<div class="board">Fast Money Final</div>', unsafe_allow_html=True)

    if len(teams) < 2:
        st.info("Fast Money is waiting for two finalist teams. The host can start Fast Money once the bracket is down to two teams.")
        if state.get("teams"):
            st.caption("Current signed-up teams: " + ", ".join(state.get("teams", [])))
        return

    # Repair state if it was missing finalist teams.
    if state.get("fast_money_teams") != teams:
        state["fast_money_teams"] = teams
        state["fast_money_scores"] = {team: state.get("fast_money_scores", {}).get(team, 0) for team in teams}
        if not state.get("fast_money_active_team") or state.get("fast_money_active_team") not in teams:
            state["fast_money_active_team"] = teams[0]
        save_state(state)

    score_cols = st.columns(2)
    for i, team in enumerate(teams[:2]):
        score_cols[i].markdown(f'<div class="card">{team}<br>{state["fast_money_scores"].get(team, 0)} pts</div>', unsafe_allow_html=True)

    active_team = state.get("fast_money_active_team") or teams[0]
    active_player = state.get("fast_money_active_player", "Player 1")
    fm_questions = current_fast_money_set(state)

    st.subheader(f"Current Turn: {active_team} — {active_player}")
    st.caption("Fast Money has 5 different questions. Enter one answer for each question.")

    started_at = state.get("fast_money_started_at")
    if started_at:
        elapsed = int(time.time() - started_at)
        remaining = max(0, FAST_MONEY_SECONDS - elapsed)
        st.markdown(f'<div class="message">⏱️ {remaining} seconds remaining</div>', unsafe_allow_html=True)
        st.progress(remaining / FAST_MONEY_SECONDS)
        if remaining > 0:
            st_autorefresh(interval=1000, key="fm_timer")
        else:
            st.warning("Time is up. Submit now or ask the host to reset/move to the next player.")
    else:
        st.info("Waiting for host to start the Fast Money timer.")

    if view == "player":
        st.subheader("Fast Money Sign In")
        selected_team = st.selectbox("Choose your finalist team", teams[:2], key="fm_signin_team")
        player_name = st.text_input("Your name", key="fm_signin_name")

        if st.button("Sign In for Fast Money"):
            if not player_name.strip():
                st.error("Enter your name first.")
            else:
                st.session_state["fast_money_team"] = selected_team
                st.session_state["fast_money_name"] = player_name.strip()
                st.success(f"Signed in as {player_name.strip()} on {selected_team}.")
                st.rerun()

        signed_team = st.session_state.get("fast_money_team")
        signed_name = st.session_state.get("fast_money_name")

        if signed_team and signed_name:
            st.success(f"✅ You are signed in as {signed_name} on {signed_team}.")
            st.caption(f"Active turn right now: {active_team} — {active_player}")

            if signed_team not in teams[:2]:
                st.error("You are signed into a team that is not in Fast Money. Sign in again using one of the finalist teams above.")
            elif signed_team != active_team:
                st.info(f"Waiting for {signed_team}'s turn. Current turn is {active_team} — {active_player}.")
            elif not started_at:
                st.info("You are on the active team. Wait for the host to start the timer, then enter your answers.")
            else:
                safe_name = normalize_text(signed_name).replace(" ", "_") or "player"
                key_base = f"{active_team}_{active_player}_{safe_name}"

                if key_base in state.get("fast_money_submissions", {}):
                    st.success("Your Fast Money answers were already submitted.")
                else:
                    answers = []
                    with st.form(f"fast_money_form_{key_base}"):
                        for i, fq in enumerate(fm_questions):
                            st.markdown(f"**Question {i+1}: {fq['question']}**")
                            answers.append(st.text_input(f"Your answer for Question {i+1}", key=f"fm_{key_base}_{i}"))
                        submitted = st.form_submit_button("Submit Fast Money Answers")

                    if submitted:
                        total = 0
                        details = []
                        for i, ans in enumerate(answers):
                            fq = fm_questions[i]
                            points, matched, sim = score_answer(ans, fq["answers"])
                            total += points
                            details.append({"question": fq["question"], "answer": ans, "matched": matched, "points": points, "similarity": sim})

                        state.setdefault("fast_money_submissions", {})[key_base] = details
                        state.setdefault("fast_money_scores", {})[active_team] = state.get("fast_money_scores", {}).get(active_team, 0) + total
                        state["message"] = f"{signed_name} submitted Fast Money answers for {active_team}."
                        state["fast_money_started_at"] = None
                        save_state(state)
                        st.success(f"Submitted! Awarded {total} points.")
                        st.rerun()
        else:
            st.info("Sign in above so the game knows which team you are answering for.")

    with st.expander("Fast Money Submissions / Scoring"):
        for key, rows in state.get("fast_money_submissions", {}).items():
            st.write(f"**{key}**")
            for row in rows:
                percent = round(row.get("similarity", 0) * 100)
                if row.get("question"):
                    st.write(f"**Q:** {row['question']}")
                st.write(f"{row['answer']} → {row['matched']} = {row['points']} pts ({percent}% match)")

    scores = state.get("fast_money_scores", {})
    if len(teams) >= 2 and scores.get(teams[0], 0) != scores.get(teams[1], 0):
        winner = max(teams[:2], key=lambda t: scores.get(t, 0))
        st.success(f"🏆 Current winner: {winner}")

def render_host_controls(state):
    st.sidebar.title("Host Controls")

    st.sidebar.subheader("Google Sheet Questions")
    url = st.sidebar.text_input("Published CSV URL", value=state.get("google_sheet_url", ""))
    if st.sidebar.button("Load Questions"):
        try:
            state["questions"] = load_questions_from_google_sheet(url)
            state["google_sheet_url"] = url
            state["current_question_index"] = 0
            reset_main_round(state)
            state["message"] = "Questions loaded from Google Sheet."
            save_state(state)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Could not load questions: {e}")

    st.sidebar.subheader("Team Sign-Up")
    st.sidebar.write(f"Teams: {len(state['teams'])}")
    if not state["locked"]:
        if st.sidebar.button("Lock Game + Create Bracket", disabled=len(state["teams"]) < 2):
            start_tournament(state)
            save_state(state)
            st.rerun()
        if len(state["teams"]) < 2:
            st.sidebar.caption("Add at least 2 teams to create a playable bracket.")
    else:
        st.sidebar.success("Game locked")
        fm_candidates = get_fast_money_finalist_teams(state)
        if len(fm_candidates) >= 2 and st.sidebar.button("Start Fast Money With Current Finalists"):
            start_fast_money_with_teams(state, fm_candidates)
            save_state(state)
            st.rerun()

    if st.sidebar.button("Unlock Sign-Up / Reset Bracket"):
        state["locked"] = False
        state["mode"] = "signup"
        state["bracket_matches"] = []
        state["match_winners"] = []
        state["champion"] = ""
        state["match_scores"] = {}
        save_state(state)
        st.rerun()

    if state.get("mode") == "main":
        st.sidebar.subheader("Main Game")
        q = current_main_question(state)
        for i, (answer, points) in enumerate(q["answers"]):
            if st.sidebar.button(f"Reveal {answer} ({points})"):
                if i not in state["revealed"]:
                    state["revealed"].append(i)
                    state["round_bank"] += int(points)
                    state["message"] = f"{answer} is on the board!"
                    save_state(state)
                    st.rerun()

        match = current_match(state)
        if match:
            left, right = match["team_a"], match["team_b"]
            if st.sidebar.button(f"Award Bank to {left}"):
                state["scores"][left] = state["scores"].get(left, 0) + state["round_bank"]
                state.setdefault("match_scores", {})[left] = state.get("match_scores", {}).get(left, 0) + state["round_bank"]
                state["round_bank"] = 0
                save_state(state)
                st.rerun()
            if right != "BYE" and st.sidebar.button(f"Award Bank to {right}"):
                state["scores"][right] = state["scores"].get(right, 0) + state["round_bank"]
                state.setdefault("match_scores", {})[right] = state.get("match_scores", {}).get(right, 0) + state["round_bank"]
                state["round_bank"] = 0
                save_state(state)
                st.rerun()

            left_match_score = state.get("match_scores", {}).get(left, 0)
            right_match_score = state.get("match_scores", {}).get(right, 0) if right != "BYE" else 0
            st.sidebar.caption(f"Match score: {left} {left_match_score} — {right} {right_match_score}")
            if st.sidebar.button("End Match / Auto-Advance Winner"):
                winner, msg = automatic_match_winner(state)
                if winner:
                    state["bracket_matches"][state["match_index"]]["winner"] = winner
                    state["message"] = msg
                    advance_to_next_match_or_round(state)
                    save_state(state)
                    st.rerun()
                else:
                    state["message"] = msg
                    save_state(state)
                    st.sidebar.error(msg)

        if st.sidebar.button("Next Question in Match"):
            if state["match_question_number"] < 3:
                state["match_question_number"] += 1
                state["current_question_index"] += 1
                reset_main_round(state)
                state["message"] = "Next question in this match."
            else:
                state["message"] = "This match has completed 3 questions. Use Auto-Advance Winner to move on."
            save_state(state)
            st.rerun()

        buzz = st.sidebar.text_input("Buzz input / player name")
        if st.sidebar.button("Set Buzz Winner"):
            state["buzzed"] = buzz
            save_state(state)
            st.rerun()
        if st.sidebar.button("Add Strike"):
            state["strikes"] = min(3, state["strikes"] + 1)
            save_state(state)
            st.rerun()
        if st.sidebar.button("Clear Strikes"):
            state["strikes"] = 0
            save_state(state)
            st.rerun()

    if state.get("mode") == "fast_money":
        st.sidebar.subheader("Fast Money")
        teams = state.get("fast_money_teams", [])
        if teams:
            state["fast_money_active_team"] = st.sidebar.selectbox("Active Team", teams, index=teams.index(state.get("fast_money_active_team", teams[0])) if state.get("fast_money_active_team") in teams else 0)
            state["fast_money_active_player"] = st.sidebar.selectbox("Active Player", ["Player 1", "Player 2"])
            if st.sidebar.button("Start Timer"):
                state["fast_money_started_at"] = int(time.time())
                save_state(state)
                st.rerun()
            if st.sidebar.button("Stop / Reset Timer"):
                state["fast_money_started_at"] = None
                save_state(state)
                st.rerun()
            if st.sidebar.button("Crown Fast Money Winner"):
                scores = state.get("fast_money_scores", {})
                winner = max(teams, key=lambda t: scores.get(t, 0))
                state["champion"] = winner
                state["message"] = f"{winner} wins Baby in Bloom Feud!"
                save_state(state)
                st.rerun()

    st.sidebar.subheader("Danger Zone")
    if st.sidebar.button("Reset Entire Game"):
        save_state(default_state())
        st.rerun()


state = load_state()
view = st.query_params.get("view", "player")
page = st.query_params.get("page", "game")

render_css()
render_header()

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
