import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import json
import os
from rapidfuzz import fuzz

st.set_page_config(page_title="Baby in Bloom Feud", layout="wide")

STATE_FILE = "game_state.json"

DEFAULT_STATE = {
    "teams": {},
    "locked": False,
    "matches": [],
    "current_match": 0,
    "round_points": {},
    "revealed": [],
    "strike": False,
    "steal_mode": False,
    "questions": [],
    "fast_money_questions": [],
    "current_question": 0,
    "winner_team": "",
    "fast_money_answers": {},
    "message": ""
}

# ---------- STATE ----------

def load_state():
    if not os.path.exists(STATE_FILE):
        save_state(DEFAULT_STATE)
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()

# ---------- CSS ----------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Cormorant+Garamond:wght@500;700&display=swap');

html, body, [class*="css"] {
    background-color: #F8F5F0;
    color: #6E5873 !important;
    font-family: 'Cormorant Garamond', serif;
}

.main-title {
    font-family: 'Playfair Display', serif;
    font-size: 72px;
    text-align: center;
    color: #6E5873;
    margin-bottom: 0px;
}

.subtitle {
    text-align: center;
    color: #A58BB7;
    margin-bottom: 30px;
    font-size: 22px;
}

.question-card {
    background: #fffaf8;
    border: 2px solid #d8c4dd;
    border-radius: 24px;
    padding: 24px;
    margin-bottom: 24px;
    font-size: 32px;
    text-align: center;
    color: #6E5873;
}

.answer-tile {
    background: #fffaf8;
    border: 2px solid #d8c4dd;
    border-radius: 20px;
    padding: 18px;
    margin-bottom: 14px;
    color: #6E5873;
    font-size: 24px;
}

.unrevealed-answer {
    color: #A58BB7;
    text-align: center;
    font-size: 24px;
}

.score-card {
    background: #fffaf8;
    border-radius: 20px;
    border: 2px solid #d8c4dd;
    padding: 18px;
    text-align: center;
    color: #6E5873;
}

.bracket-card {
    background: #fffaf8;
    border-radius: 18px;
    border: 2px solid #d8c4dd;
    padding: 16px;
    margin-bottom: 10px;
}

.stButton button {
    background: #EADFED;
    color: #6E5873 !important;
    border-radius: 12px;
    border: 1px solid #d0b9d8;
}
</style>
""", unsafe_allow_html=True)

# ---------- HELPERS ----------

def build_bracket(teams):
    matches = []
    team_names = list(teams.keys())
    for i in range(0, len(team_names), 2):
        if i + 1 < len(team_names):
            matches.append([team_names[i], team_names[i+1]])
    return matches

def load_questions(csv_url):
    df = pd.read_csv(csv_url)

    main_df = df[df["game_type"] == "main"]
    fast_df = df[df["game_type"] == "fast_money"]

    main_questions = []
    for q, group in main_df.groupby("question", sort=False):
        answers = []
        for _, row in group.iterrows():
            answers.append([row["answer"], int(row["points"])])
        main_questions.append({
            "question": q,
            "answers": answers
        })

    fast_questions = []
    for q, group in fast_df.groupby("question", sort=False):
        answers = []
        for _, row in group.iterrows():
            answers.append([row["answer"], int(row["points"])])
        fast_questions.append({
            "question": q,
            "answers": answers
        })

    state["questions"] = main_questions
    state["fast_money_questions"] = fast_questions
    save_state(state)

def score_fast_money(answers):
    total = 0
    fast_questions = state["fast_money_questions"]

    for idx, player_answer in enumerate(answers):
        if idx >= len(fast_questions):
            continue

        q = fast_questions[idx]

        for correct_answer, points in q["answers"]:
            similarity = fuzz.ratio(
                player_answer.lower(),
                str(correct_answer).lower()
            )

            if similarity >= 80:
                total += points
                break

    return total

# ---------- HEADER ----------

st.markdown('<div class="main-title">Baby in Bloom Feud</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Baby Shower Tournament Edition</div>', unsafe_allow_html=True)

view = st.query_params.get("view", "player")
page = st.query_params.get("page", "main")

# ---------- BRACKET PAGE ----------

if page == "bracket":
    st.header("Tournament Bracket")

    for idx, match in enumerate(state["matches"]):
        st.markdown(
            f"""
            <div class="bracket-card">
            Match {idx+1}<br>
            {match[0]} vs {match[1]}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.stop()

# ---------- PLAYER VIEW ----------

if view == "player":

    st_autorefresh(interval=1000, key="refresh")

    st.subheader("Team Sign-In")

    if not state["locked"]:
        player_name = st.text_input("Your Name")
        team_name = st.text_input("Team Name")

        if st.button("Join Team"):
            if team_name not in state["teams"]:
                state["teams"][team_name] = []

            if player_name not in state["teams"][team_name]:
                state["teams"][team_name].append(player_name)

            save_state(state)
            st.success(f"Joined {team_name}")

    else:
        st.success("Teams are locked!")

    # ---------- MAIN GAME ----------

    if state["questions"]:

        q = state["questions"][state["current_question"]]

        st.markdown(
            f'<div class="question-card">{q["question"]}</div>',
            unsafe_allow_html=True
        )

        for idx, answer in enumerate(q["answers"]):

            if idx in state["revealed"]:
                st.markdown(
                    f'<div class="answer-tile">{idx+1}. {answer[0]} — {answer[1]}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="answer-tile unrevealed-answer">{idx+1}</div>',
                    unsafe_allow_html=True
                )

    # ---------- FAST MONEY ----------

    if state["winner_team"]:

        st.divider()
        st.header("Fast Money")

        team = st.selectbox(
            "Select Your Team",
            [state["winner_team"]]
        )

        player = st.text_input("Your Name")

        answers = []

        for idx, q in enumerate(state["fast_money_questions"][:5]):
            ans = st.text_input(
                q["question"],
                key=f"fm_{idx}"
            )
            answers.append(ans)

        if st.button("Submit Fast Money Answers"):

            score = score_fast_money(answers)

            state["fast_money_answers"][player] = {
                "team": team,
                "score": score
            }

            save_state(state)

            st.success(f"Submitted! Score: {score}")

# ---------- HOST VIEW ----------

if view == "host":

    st.sidebar.header("Host Controls")

    csv_url = st.sidebar.text_input("Google Sheet CSV URL")

    if st.sidebar.button("Load Questions"):
        load_questions(csv_url)
        st.sidebar.success("Questions loaded!")

    if st.sidebar.button("Lock Teams"):
        state["locked"] = True
        state["matches"] = build_bracket(state["teams"])
        save_state(state)

    if state["matches"]:

        current_match = state["matches"][state["current_match"]]

        st.sidebar.write(
            f"Current Match: {current_match[0]} vs {current_match[1]}"
        )

    if state["questions"]:

        q = state["questions"][state["current_question"]]

        st.markdown(
            f'<div class="question-card">{q["question"]}</div>',
            unsafe_allow_html=True
        )

        for idx, answer in enumerate(q["answers"]):

            if st.sidebar.button(f"Reveal {answer[0]}"):
                if idx not in state["revealed"]:
                    state["revealed"].append(idx)
                    save_state(state)
                    st.rerun()

        if st.sidebar.button("Strike / Enable Steal"):
            state["strike"] = True
            state["steal_mode"] = True
            save_state(state)

        if st.sidebar.button("Next Match Question"):
            state["current_question"] += 1
            state["revealed"] = []
            state["strike"] = False
            state["steal_mode"] = False
            save_state(state)

    st.sidebar.subheader("Fast Money Winner Team")

    winner_team = st.sidebar.selectbox(
        "Winning Team",
        list(state["teams"].keys()) if state["teams"] else []
    )

    if st.sidebar.button("Start Fast Money"):
        state["winner_team"] = winner_team
        save_state(state)

    if state["fast_money_answers"]:

        st.header("Fast Money Leaderboard")

        leaderboard = sorted(
            state["fast_money_answers"].items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )

        for player, data in leaderboard:
            st.markdown(
                f"""
                <div class="score-card">
                {player}<br>
                {data["score"]} points
                </div>
                """,
                unsafe_allow_html=True
            )

