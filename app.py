import base64
import html
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
# Survey-Style Party Game
# Quickplay tournament + individual Fast Money championship
# ============================================================

st.set_page_config(page_title="Survey-Style Party Game", layout="wide")

SESSIONS_DIR = "game_sessions"
HOSTS_FILE = "host_sessions.json"
DEFAULT_GAME_CODE = "default"
GAME_CODE_LENGTH = 4
FAST_MONEY_SECONDS = 45
FUZZY_THRESHOLD = 78

QUESTION_TEMPLATE_ROWS = [
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Drinks", "points": 35},
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Food", "points": 25},
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Gift", "points": 15},
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Dessert", "points": 10},
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Flowers", "points": 8},
    {"game_type": "main", "question": "Name something people bring to a party.", "answer": "Games", "points": 7},
    {"game_type": "fast_money", "question": "Name something people do at a celebration.", "answer": "Dance", "points": 35},
    {"game_type": "fast_money", "question": "Name something people forget to bring to an event.", "answer": "Gift", "points": 30},
    {"game_type": "fast_money", "question": "Name something you see on a party table.", "answer": "Food", "points": 35},
    {"game_type": "fast_money", "question": "Name a reason someone arrives late.", "answer": "Traffic", "points": 40},
    {"game_type": "fast_money", "question": "Name something people take pictures of at a party.", "answer": "People", "points": 35},
]


# Start with no teams so this can be reused for any party/theme.
# Players can create teams from the player page before the host locks the game.
PRELOADED_TEAMS = []


DEFAULT_MAIN_QUESTIONS = [
    {
        "question": "Name something people bring to a party.",
        "answers": [
            ["Drinks", 35],
            ["Food", 25],
            ["Gift", 15],
            ["Dessert", 10],
            ["Flowers", 8],
            ["Games", 7],
        ],
    }
]

DEFAULT_FAST_MONEY_QUESTIONS = [
    {
        "question": "Name something people do at a celebration.",
        "answers": [["Dance", 35], ["Eat", 25], ["Drink", 20], ["Talk", 12], ["Take pictures", 8]],
    },
    {
        "question": "Name something people forget to bring to an event.",
        "answers": [["Gift", 30], ["Phone", 25], ["Wallet", 20], ["Keys", 15], ["Jacket", 10]],
    },
    {
        "question": "Name something you see on a party table.",
        "answers": [["Food", 35], ["Drinks", 25], ["Plates", 15], ["Flowers", 15], ["Candles", 10]],
    },
    {
        "question": "Name a reason someone arrives late.",
        "answers": [["Traffic", 40], ["Getting ready", 25], ["Lost", 15], ["Work", 10], ["Parking", 10]],
    },
    {
        "question": "Name something people take pictures of at a party.",
        "answers": [["People", 35], ["Decor", 25], ["Food", 15], ["Cake", 15], ["Group photo", 10]],
    },
]


THEMES = {
    "Classic Party": {
        "paper": "#F8F5F0", "cream": "#FFFAF8", "primary": "#6E5873", "secondary": "#A58BB7",
        "accent": "#EADFED", "border": "#D8C4DD", "highlight": "#E8C7D0", "sidebar": "#F2EAF4",
    },
    "Baby Shower - Boy": {
        "paper": "#F5F9FD", "cream": "#FFFFFF", "primary": "#355C7D", "secondary": "#5D8AA8",
        "accent": "#D8EAF8", "border": "#B8D5EA", "highlight": "#C8E5FF", "sidebar": "#E7F2FB",
    },
    "Baby Shower - Girl": {
        "paper": "#FFF7FA", "cream": "#FFFFFF", "primary": "#7A4E68", "secondary": "#C47FA0",
        "accent": "#F4DCE8", "border": "#E7BFD2", "highlight": "#FFD6E7", "sidebar": "#FBEAF2",
    },
    "Gender Neutral Baby Shower": {
        "paper": "#F7F7F0", "cream": "#FFFDF8", "primary": "#59684A", "secondary": "#7D8F68",
        "accent": "#E4EAD8", "border": "#C9D4B8", "highlight": "#DDEBCB", "sidebar": "#EEF3E6",
    },
    "Bachelor Party": {
        "paper": "#F6F4EF", "cream": "#FFFFFF", "primary": "#252525", "secondary": "#8A6F3D",
        "accent": "#E8DEC3", "border": "#C8B889", "highlight": "#D4AF37", "sidebar": "#EEE7D8",
    },
    "Bachelorette Party": {
        "paper": "#FFF6FB", "cream": "#FFFFFF", "primary": "#7A255B", "secondary": "#D95FA7",
        "accent": "#F8D3EA", "border": "#EDAED6", "highlight": "#FFC2E6", "sidebar": "#FCE4F3",
    },
    "Bridal Shower": {
        "paper": "#FFFDF8", "cream": "#FFFFFF", "primary": "#5F5449", "secondary": "#B98F78",
        "accent": "#F1E3DA", "border": "#DBC4B6", "highlight": "#F7D8C7", "sidebar": "#F8EEE8",
    },
    "Birthday Party": {
        "paper": "#FFF9E8", "cream": "#FFFFFF", "primary": "#5E3B76", "secondary": "#E18F2F",
        "accent": "#FBE6B8", "border": "#E8C97A", "highlight": "#FFE08A", "sidebar": "#FFF1C8",
    },
    "Holiday Party": {
        "paper": "#F8FAF8", "cream": "#FFFFFF", "primary": "#28513A", "secondary": "#A53636",
        "accent": "#E4EFE6", "border": "#BFD6C4", "highlight": "#F2C7C7", "sidebar": "#EAF4EC",
    },
    "Custom": {
        "paper": "#F8F5F0", "cream": "#FFFAF8", "primary": "#6E5873", "secondary": "#A58BB7",
        "accent": "#EADFED", "border": "#D8C4DD", "highlight": "#E8C7D0", "sidebar": "#F2EAF4",
    },
}


EVENT_QUESTION_PRESETS = {
    "Classic Party": {
        "main": [
            {"question": "Name something people bring to a party.", "answers": [["Drinks", 35], ["Food", 25], ["Gift", 15], ["Dessert", 10], ["Flowers", 8], ["Games", 7]]},
            {"question": "Name something people do at a celebration.", "answers": [["Dance", 35], ["Eat", 25], ["Drink", 20], ["Talk", 12], ["Take pictures", 8]]},
            {"question": "Name something you see on a party table.", "answers": [["Food", 35], ["Drinks", 25], ["Plates", 15], ["Flowers", 15], ["Candles", 10]]},
            {"question": "Name a reason someone arrives late.", "answers": [["Traffic", 40], ["Getting ready", 25], ["Lost", 15], ["Work", 10], ["Parking", 10]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Baby Shower - Boy": {
        "main": [
            {"question": "Name something parents always carry in a diaper bag.", "answers": [["Diapers", 35], ["Wipes", 25], ["Bottle", 15], ["Snacks", 10], ["Extra clothes", 8], ["Pacifier", 7]]},
            {"question": "Name something blue you might see at a baby shower.", "answers": [["Balloons", 30], ["Cake", 25], ["Decorations", 20], ["Plates", 10], ["Flowers", 8], ["Outfit", 7]]},
            {"question": "Name a gift people buy for a baby boy.", "answers": [["Clothes", 35], ["Blanket", 25], ["Toys", 18], ["Diapers", 12], ["Books", 6], ["Shoes", 4]]},
            {"question": "Name something babies need every day.", "answers": [["Diapers", 35], ["Milk", 30], ["Sleep", 18], ["Clothes", 10], ["Love", 7]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Baby Shower - Girl": {
        "main": [
            {"question": "Name something pink you might see at a baby shower.", "answers": [["Balloons", 30], ["Cake", 25], ["Flowers", 20], ["Decorations", 15], ["Plates", 6], ["Ribbon", 4]]},
            {"question": "Name a gift people buy for a baby girl.", "answers": [["Clothes", 35], ["Blanket", 25], ["Headbands", 15], ["Toys", 12], ["Books", 8], ["Diapers", 5]]},
            {"question": "Name something parents always carry in a diaper bag.", "answers": [["Diapers", 35], ["Wipes", 25], ["Bottle", 15], ["Snacks", 10], ["Extra clothes", 8], ["Pacifier", 7]]},
            {"question": "Name something babies do that makes everyone say 'aww'.", "answers": [["Smile", 40], ["Laugh", 25], ["Sleep", 15], ["Wave", 10], ["Cuddle", 10]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Gender Neutral Baby Shower": {
        "main": [
            {"question": "Name a popular baby shower decoration.", "answers": [["Balloons", 35], ["Flowers", 25], ["Banner", 15], ["Cake", 12], ["Tableware", 8], ["Centerpieces", 5]]},
            {"question": "Name something every new parent needs.", "answers": [["Diapers", 35], ["Sleep", 25], ["Wipes", 18], ["Help", 12], ["Patience", 6], ["Coffee", 4]]},
            {"question": "Name a baby shower game people play.", "answers": [["Guess the belly", 30], ["Don't say baby", 25], ["Diaper raffle", 20], ["Baby bingo", 15], ["Price is right", 10]]},
            {"question": "Name something babies make a lot of.", "answers": [["Noise", 30], ["Mess", 25], ["Laundry", 20], ["Smiles", 15], ["Diapers", 10]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Bachelor Party": {
        "main": [
            {"question": "Name something people do at a bachelor party.", "answers": [["Drink", 35], ["Go out", 25], ["Play games", 15], ["Eat", 10], ["Golf", 8], ["Take pictures", 7]]},
            {"question": "Name something the groom might forget to pack.", "answers": [["Toothbrush", 30], ["Suit", 25], ["Wallet", 20], ["Phone charger", 15], ["Shoes", 10]]},
            {"question": "Name a place people go for a bachelor party.", "answers": [["Vegas", 40], ["Bar", 25], ["Golf course", 15], ["Beach", 10], ["Cabin", 10]]},
            {"question": "Name something people toast to at a bachelor party.", "answers": [["The groom", 40], ["Marriage", 25], ["Friendship", 15], ["Good luck", 12], ["The future", 8]]},
        ],
        "fast_money": [
            {"question": "Name something people do on a guys' trip.", "answers": [["Drink", 35], ["Golf", 25], ["Eat", 15], ["Watch sports", 15], ["Gamble", 10]]},
            {"question": "Name something people pack for a weekend trip.", "answers": [["Clothes", 35], ["Toiletries", 25], ["Phone charger", 20], ["Shoes", 10], ["Snacks", 10]]},
            {"question": "Name a bachelor party destination.", "answers": [["Vegas", 45], ["Nashville", 20], ["Miami", 15], ["Lake Tahoe", 10], ["Austin", 10]]},
            {"question": "Name something found in a hotel room.", "answers": [["Bed", 40], ["Towels", 25], ["TV", 15], ["Mini fridge", 10], ["Shampoo", 10]]},
            {"question": "Name something people regret after a night out.", "answers": [["Drinking too much", 35], ["Spending money", 25], ["Staying out late", 20], ["Bad photos", 10], ["Texting", 10]]},
        ],
    },
    "Bachelorette Party": {
        "main": [
            {"question": "Name something people wear to a bachelorette party.", "answers": [["Dress", 30], ["Sash", 25], ["Cowboy boots", 15], ["Matching shirts", 12], ["Veil", 10], ["Heels", 8]]},
            {"question": "Name something you see at a bachelorette party.", "answers": [["Balloons", 30], ["Cocktails", 25], ["Decorations", 20], ["Bride sash", 15], ["Photo props", 10]]},
            {"question": "Name a popular bachelorette destination.", "answers": [["Nashville", 35], ["Vegas", 25], ["Miami", 15], ["Scottsdale", 15], ["Palm Springs", 10]]},
            {"question": "Name something the bride might do during a bachelorette weekend.", "answers": [["Dance", 30], ["Drink", 25], ["Take photos", 20], ["Pool day", 15], ["Open gifts", 10]]},
        ],
        "fast_money": [
            {"question": "Name something people pack for a girls' trip.", "answers": [["Outfits", 35], ["Makeup", 25], ["Shoes", 20], ["Swimsuit", 10], ["Phone charger", 10]]},
            {"question": "Name a bachelorette party activity.", "answers": [["Dancing", 35], ["Pool day", 25], ["Dinner", 20], ["Bar hopping", 10], ["Games", 10]]},
            {"question": "Name something you put on a party itinerary.", "answers": [["Dinner", 30], ["Drinks", 25], ["Pool", 20], ["Brunch", 15], ["Photos", 10]]},
            {"question": "Name a drink ordered at a bachelorette party.", "answers": [["Margarita", 30], ["Champagne", 25], ["Martini", 20], ["Vodka soda", 15], ["Wine", 10]]},
            {"question": "Name something people take photos with.", "answers": [["Bride", 35], ["Decor", 25], ["Balloons", 20], ["Drinks", 10], ["Group", 10]]},
        ],
    },
    "Bridal Shower": {
        "main": [
            {"question": "Name something people bring to a bridal shower.", "answers": [["Gift", 40], ["Card", 25], ["Flowers", 15], ["Dessert", 10], ["Wine", 10]]},
            {"question": "Name a common bridal shower gift.", "answers": [["Kitchen item", 35], ["Towels", 25], ["Candles", 15], ["Glassware", 15], ["Cookbook", 10]]},
            {"question": "Name a bridal shower game.", "answers": [["How well do you know bride", 35], ["Gift bingo", 25], ["He said she said", 20], ["Advice cards", 10], ["Toilet paper dress", 10]]},
            {"question": "Name something you see on a bridal shower table.", "answers": [["Flowers", 35], ["Cake", 25], ["Plates", 15], ["Candles", 15], ["Favors", 10]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Birthday Party": {
        "main": [
            {"question": "Name something at almost every birthday party.", "answers": [["Cake", 40], ["Balloons", 25], ["Gifts", 15], ["Candles", 10], ["Music", 10]]},
            {"question": "Name a birthday party activity.", "answers": [["Games", 35], ["Dancing", 25], ["Eating", 20], ["Opening gifts", 10], ["Photos", 10]]},
            {"question": "Name a popular birthday dessert.", "answers": [["Cake", 45], ["Cupcakes", 25], ["Ice cream", 20], ["Cookies", 5], ["Pie", 5]]},
            {"question": "Name something people say on someone's birthday.", "answers": [["Happy birthday", 50], ["Make a wish", 20], ["How old are you", 15], ["Congrats", 8], ["Many more", 7]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
    "Holiday Party": {
        "main": [
            {"question": "Name something people bring to a holiday party.", "answers": [["Dessert", 30], ["Wine", 25], ["Gift", 20], ["Side dish", 15], ["Cookies", 10]]},
            {"question": "Name something you see at a holiday party.", "answers": [["Decorations", 35], ["Tree", 25], ["Lights", 20], ["Food", 10], ["Gifts", 10]]},
            {"question": "Name a holiday party food.", "answers": [["Cookies", 30], ["Ham", 25], ["Turkey", 20], ["Pie", 15], ["Cheese board", 10]]},
            {"question": "Name a holiday party activity.", "answers": [["Gift exchange", 35], ["Games", 25], ["Eating", 20], ["Singing", 10], ["Photos", 10]]},
        ],
        "fast_money": DEFAULT_FAST_MONEY_QUESTIONS,
    },
}


EXTRA_EVENT_MAIN_QUESTIONS = {
    "Classic Party": [
        {"question": "Name something people do when music starts playing.", "answers": [["Dance", 35], ["Sing", 25], ["Clap", 15], ["Record video", 12], ["Smile", 8], ["Leave the room", 5]]},
        {"question": "Name something guests look for when they arrive at a party.", "answers": [["Food", 30], ["Drinks", 25], ["Bathroom", 18], ["Host", 12], ["Seat", 10], ["Friends", 5]]},
        {"question": "Name something people put on a party invitation.", "answers": [["Date", 30], ["Time", 25], ["Address", 20], ["Dress code", 10], ["RSVP", 10], ["Theme", 5]]},
        {"question": "Name a party food people eat with their hands.", "answers": [["Pizza", 30], ["Chips", 25], ["Sliders", 15], ["Tacos", 12], ["Cookies", 10], ["Wings", 8]]},
        {"question": "Name something that can ruin a party.", "answers": [["Rain", 30], ["Bad music", 25], ["No food", 18], ["Drama", 12], ["Power outage", 10], ["Running late", 5]]},
        {"question": "Name something people do before guests arrive.", "answers": [["Clean", 35], ["Decorate", 25], ["Cook", 18], ["Set the table", 12], ["Get dressed", 6], ["Light candles", 4]]},
        {"question": "Name something people take home from a party.", "answers": [["Favor", 30], ["Leftovers", 25], ["Photos", 20], ["Gift bag", 15], ["Flowers", 5], ["Memories", 5]]},
        {"question": "Name a reason people RSVP no.", "answers": [["Work", 30], ["Out of town", 25], ["Sick", 18], ["Busy", 15], ["No babysitter", 8], ["Too far", 4]]},
        {"question": "Name something people decorate with.", "answers": [["Balloons", 35], ["Flowers", 25], ["Streamers", 15], ["Candles", 10], ["Signs", 10], ["Lights", 5]]},
        {"question": "Name something people do after a party ends.", "answers": [["Clean", 35], ["Sleep", 25], ["Take trash out", 15], ["Look at photos", 12], ["Eat leftovers", 8], ["Send thank yous", 5]]},
        {"question": "Name something found near the dessert table.", "answers": [["Cake", 35], ["Cupcakes", 25], ["Plates", 15], ["Forks", 10], ["Cookies", 10], ["Napkins", 5]]},
        {"question": "Name something guests compliment at a party.", "answers": [["Food", 35], ["Decor", 25], ["Outfit", 15], ["Music", 10], ["Venue", 10], ["Cake", 5]]},
        {"question": "Name something a host worries about.", "answers": [["Food running out", 35], ["Guests arriving", 20], ["Weather", 15], ["Clean house", 12], ["Timing", 10], ["Parking", 8]]},
        {"question": "Name something people use to take photos.", "answers": [["Phone", 50], ["Camera", 20], ["Photo booth", 15], ["Polaroid", 8], ["Tablet", 4], ["Drone", 3]]},
        {"question": "Name something people write on a party sign.", "answers": [["Welcome", 35], ["Name", 25], ["Happy Birthday", 15], ["Cheers", 10], ["Congrats", 10], ["Date", 5]]},
        {"question": "Name a drink people serve at parties.", "answers": [["Water", 25], ["Soda", 22], ["Wine", 18], ["Cocktails", 15], ["Lemonade", 12], ["Juice", 8]]},
    ],
    "Baby Shower - Boy": [
        {"question": "Name something you might find in a nursery.", "answers": [["Crib", 35], ["Changing table", 20], ["Rocking chair", 18], ["Diapers", 12], ["Books", 8], ["Blanket", 7]]},
        {"question": "Name something new parents lose a lot of.", "answers": [["Sleep", 45], ["Time", 20], ["Patience", 15], ["Money", 10], ["Keys", 5], ["Sanity", 5]]},
        {"question": "Name something people write in a baby shower card.", "answers": [["Congrats", 35], ["Best wishes", 25], ["Love", 15], ["Advice", 10], ["Baby name", 8], ["Blessings", 7]]},
        {"question": "Name something babies spit up on.", "answers": [["Clothes", 35], ["Blanket", 25], ["Parent", 20], ["Burp cloth", 10], ["Car seat", 5], ["Floor", 5]]},
        {"question": "Name something parents use to calm a baby.", "answers": [["Pacifier", 30], ["Bottle", 25], ["Rocking", 20], ["Singing", 12], ["Swaddle", 8], ["White noise", 5]]},
        {"question": "Name something people guess at a baby shower.", "answers": [["Due date", 30], ["Weight", 25], ["Name", 20], ["Gender", 15], ["Height", 5], ["Hair color", 5]]},
        {"question": "Name a baby shower favor.", "answers": [["Candy", 30], ["Candle", 25], ["Soap", 15], ["Cookies", 12], ["Seeds", 10], ["Keychain", 8]]},
        {"question": "Name something a baby wears.", "answers": [["Onesie", 35], ["Diaper", 25], ["Socks", 15], ["Hat", 12], ["Bib", 8], ["Pajamas", 5]]},
        {"question": "Name something in a baby registry.", "answers": [["Diapers", 30], ["Stroller", 25], ["Car seat", 20], ["Bottles", 12], ["Monitor", 8], ["Clothes", 5]]},
        {"question": "Name something babies do loudly.", "answers": [["Cry", 45], ["Laugh", 20], ["Scream", 15], ["Burp", 10], ["Babble", 5], ["Cough", 5]]},
        {"question": "Name a baby shower dessert.", "answers": [["Cake", 35], ["Cupcakes", 25], ["Cookies", 15], ["Cake pops", 12], ["Donuts", 8], ["Macarons", 5]]},
        {"question": "Name something parents baby-proof.", "answers": [["Outlets", 35], ["Cabinets", 25], ["Stairs", 20], ["Doors", 10], ["Corners", 5], ["Drawers", 5]]},
        {"question": "Name something babies chew on.", "answers": [["Teether", 30], ["Toys", 25], ["Fingers", 20], ["Pacifier", 12], ["Blanket", 8], ["Books", 5]]},
        {"question": "Name something parents keep in the car for baby.", "answers": [["Car seat", 35], ["Diapers", 20], ["Wipes", 18], ["Blanket", 12], ["Toys", 8], ["Snacks", 7]]},
        {"question": "Name a baby milestone.", "answers": [["First steps", 35], ["First word", 25], ["Crawling", 18], ["Rolling over", 12], ["Sitting up", 6], ["First tooth", 4]]},
        {"question": "Name something people say about a newborn.", "answers": [["So cute", 35], ["Tiny", 25], ["Looks like dad", 15], ["Looks like mom", 12], ["Beautiful", 8], ["Sweet", 5]]},
    ],
    "Baby Shower - Girl": [],
    "Gender Neutral Baby Shower": [],
    "Bachelor Party": [
        {"question": "Name something people do before a night out.", "answers": [["Get dressed", 30], ["Shower", 25], ["Eat", 18], ["Call a ride", 12], ["Take photos", 10], ["Pre-game", 5]]},
        {"question": "Name something found at a sports bar.", "answers": [["TVs", 35], ["Beer", 25], ["Wings", 15], ["Games", 10], ["Fries", 10], ["Fans", 5]]},
        {"question": "Name something people wear on a guys' trip.", "answers": [["Jeans", 30], ["Hat", 25], ["Sneakers", 20], ["Golf shirt", 10], ["Sunglasses", 10], ["Jacket", 5]]},
        {"question": "Name something people do at a golf outing.", "answers": [["Golf", 40], ["Drink", 25], ["Drive cart", 15], ["Eat", 10], ["Take photos", 5], ["Lose balls", 5]]},
        {"question": "Name something the groom gets teased about.", "answers": [["Marriage", 35], ["Dancing", 20], ["Exes", 15], ["Outfit", 12], ["Age", 10], ["Being nervous", 8]]},
        {"question": "Name a bachelor party expense.", "answers": [["Hotel", 35], ["Drinks", 25], ["Food", 15], ["Flights", 12], ["Uber", 8], ["Activities", 5]]},
        {"question": "Name something you need for a road trip.", "answers": [["Gas", 35], ["Snacks", 25], ["Music", 15], ["GPS", 12], ["Phone charger", 8], ["Drinks", 5]]},
        {"question": "Name something people forget after a night out.", "answers": [["Wallet", 30], ["Phone", 25], ["Keys", 20], ["Jacket", 10], ["Sunglasses", 10], ["Plans", 5]]},
        {"question": "Name something people book for a bachelor party.", "answers": [["Hotel", 35], ["Dinner", 20], ["Golf", 15], ["Party bus", 12], ["Flights", 10], ["Cabana", 8]]},
        {"question": "Name a late-night food.", "answers": [["Pizza", 35], ["Tacos", 25], ["Burgers", 15], ["Fries", 10], ["Hot dogs", 8], ["Wings", 7]]},
        {"question": "Name something people say in a toast.", "answers": [["Cheers", 35], ["Congrats", 25], ["To the groom", 20], ["Good luck", 10], ["Love you", 5], ["Finally", 5]]},
        {"question": "Name something a best man plans.", "answers": [["Bachelor party", 40], ["Speech", 25], ["Travel", 15], ["Dinner", 10], ["Games", 5], ["Suit fitting", 5]]},
        {"question": "Name something people do on a party bus.", "answers": [["Drink", 35], ["Dance", 25], ["Sing", 15], ["Take photos", 12], ["Laugh", 8], ["Play music", 5]]},
        {"question": "Name something in a cooler.", "answers": [["Beer", 35], ["Ice", 25], ["Water", 15], ["Soda", 10], ["Snacks", 10], ["Juice", 5]]},
        {"question": "Name a reason the groom might be nervous.", "answers": [["Wedding", 40], ["Speech", 20], ["Dancing", 15], ["Vows", 12], ["Money", 8], ["Family", 5]]},
        {"question": "Name something people do the morning after a bachelor party.", "answers": [["Sleep", 35], ["Drink water", 25], ["Eat breakfast", 15], ["Pack", 10], ["Complain", 10], ["Find phone", 5]]},
    ],
    "Bachelorette Party": [
        {"question": "Name something on a bachelorette packing list.", "answers": [["Outfits", 30], ["Makeup", 25], ["Swimsuit", 15], ["Shoes", 12], ["Phone charger", 10], ["Sash", 8]]},
        {"question": "Name something people wear for a western bachelorette.", "answers": [["Cowboy boots", 35], ["Hat", 25], ["Denim", 15], ["Fringe", 10], ["White dress", 10], ["Bandana", 5]]},
        {"question": "Name something at a pool day.", "answers": [["Swimsuit", 30], ["Sunscreen", 25], ["Drinks", 20], ["Towels", 10], ["Floaties", 10], ["Snacks", 5]]},
        {"question": "Name something the bride wears.", "answers": [["White dress", 35], ["Veil", 25], ["Sash", 15], ["Ring", 10], ["Heels", 10], ["Cowboy boots", 5]]},
        {"question": "Name something on a bachelorette itinerary.", "answers": [["Dinner", 30], ["Brunch", 25], ["Pool day", 20], ["Dancing", 10], ["Photos", 10], ["Games", 5]]},
        {"question": "Name something people decorate a hotel room with.", "answers": [["Balloons", 35], ["Streamers", 20], ["Banner", 15], ["Confetti", 12], ["Photos", 10], ["Flowers", 8]]},
        {"question": "Name a bachelorette party favor.", "answers": [["Sunglasses", 25], ["Cup", 20], ["Hair tie", 18], ["Hangover kit", 15], ["Lip balm", 12], ["Tote bag", 10]]},
        {"question": "Name something people do at brunch.", "answers": [["Drink mimosas", 35], ["Eat", 25], ["Take photos", 15], ["Toast", 10], ["Talk", 10], ["Laugh", 5]]},
        {"question": "Name a bachelorette party game.", "answers": [["Truth or dare", 30], ["Bride trivia", 25], ["Scavenger hunt", 20], ["Never have I ever", 15], ["Drink if", 10]]},
        {"question": "Name something people do for the bride.", "answers": [["Toast her", 30], ["Take photos", 25], ["Buy drinks", 20], ["Give gifts", 10], ["Dance", 10], ["Celebrate", 5]]},
        {"question": "Name a popular bachelorette color.", "answers": [["Pink", 35], ["White", 25], ["Black", 15], ["Gold", 10], ["Red", 10], ["Purple", 5]]},
        {"question": "Name something in a hangover kit.", "answers": [["Advil", 30], ["Water", 25], ["Electrolytes", 20], ["Gum", 10], ["Snacks", 10], ["Bandages", 5]]},
        {"question": "Name something people do before going out.", "answers": [["Makeup", 30], ["Hair", 25], ["Get dressed", 20], ["Photos", 10], ["Music", 10], ["Drinks", 5]]},
        {"question": "Name something at a themed bachelorette.", "answers": [["Matching outfits", 30], ["Decor", 25], ["Signs", 15], ["Props", 12], ["Playlist", 10], ["Favors", 8]]},
        {"question": "Name something people post after the trip.", "answers": [["Group photo", 35], ["Bride photo", 25], ["Video", 15], ["Decor", 10], ["Food", 10], ["Story recap", 5]]},
        {"question": "Name something people forget on a girls' trip.", "answers": [["Phone charger", 30], ["Makeup", 20], ["Shoes", 15], ["Swimsuit", 15], ["ID", 10], ["Toothbrush", 10]]},
    ],
    "Bridal Shower": [],
    "Birthday Party": [],
    "Holiday Party": [],
}

# Reuse the boy baby shower extras for girl/neutral showers, with existing theme-specific questions still first.
EXTRA_EVENT_MAIN_QUESTIONS["Baby Shower - Girl"] = EXTRA_EVENT_MAIN_QUESTIONS["Baby Shower - Boy"]
EXTRA_EVENT_MAIN_QUESTIONS["Gender Neutral Baby Shower"] = EXTRA_EVENT_MAIN_QUESTIONS["Baby Shower - Boy"]
EXTRA_EVENT_MAIN_QUESTIONS["Bridal Shower"] = EXTRA_EVENT_MAIN_QUESTIONS["Classic Party"]
EXTRA_EVENT_MAIN_QUESTIONS["Birthday Party"] = EXTRA_EVENT_MAIN_QUESTIONS["Classic Party"]
EXTRA_EVENT_MAIN_QUESTIONS["Holiday Party"] = EXTRA_EVENT_MAIN_QUESTIONS["Classic Party"]


GENERIC_FILLER_MAIN_QUESTIONS = [
    {"question": "Name something people bring to a celebration.", "answers": [["Gift", 30], ["Food", 25], ["Drinks", 20], ["Dessert", 12], ["Camera", 8], ["Flowers", 5]]},
    {"question": "Name something people do when they first arrive at a party.", "answers": [["Say hello", 35], ["Find food", 20], ["Get a drink", 18], ["Take photos", 12], ["Look for friends", 10], ["Put down bags", 5]]},
    {"question": "Name something that makes a party more fun.", "answers": [["Music", 35], ["Games", 25], ["Food", 15], ["Drinks", 12], ["Decorations", 8], ["Dancing", 5]]},
    {"question": "Name something people take pictures of at an event.", "answers": [["People", 30], ["Decor", 25], ["Food", 15], ["Cake", 12], ["Group photos", 10], ["Outfits", 8]]},
    {"question": "Name something guests talk about after a party.", "answers": [["Food", 30], ["Music", 20], ["Decor", 18], ["People", 15], ["Games", 10], ["Drama", 7]]},
    {"question": "Name something people forget before leaving for an event.", "answers": [["Gift", 30], ["Phone", 25], ["Wallet", 15], ["Keys", 12], ["Jacket", 10], ["Card", 8]]},
    {"question": "Name something you might see on an invitation.", "answers": [["Date", 30], ["Time", 25], ["Location", 20], ["Names", 12], ["Dress code", 8], ["RSVP", 5]]},
    {"question": "Name something that can go wrong at a party.", "answers": [["Bad weather", 25], ["Late guests", 20], ["Not enough food", 18], ["Spills", 15], ["Music issues", 12], ["Parking", 10]]},
    {"question": "Name something people serve at a party.", "answers": [["Appetizers", 30], ["Dessert", 25], ["Drinks", 20], ["Cake", 12], ["Chips", 8], ["Fruit", 5]]},
    {"question": "Name something guests do before they leave.", "answers": [["Say goodbye", 35], ["Take photos", 20], ["Thank host", 18], ["Grab favors", 12], ["Clean up", 10], ["Find keys", 5]]},
    {"question": "Name something people wear to a themed party.", "answers": [["Dress", 25], ["Costume", 22], ["Matching shirt", 18], ["Hat", 15], ["Boots", 10], ["Accessories", 10]]},
    {"question": "Name something a host worries about before guests arrive.", "answers": [["Food", 30], ["Cleaning", 25], ["Decor", 15], ["Timing", 12], ["Weather", 10], ["Parking", 8]]},
    {"question": "Name something people put on a party table.", "answers": [["Food", 30], ["Drinks", 25], ["Plates", 18], ["Napkins", 12], ["Flowers", 10], ["Candles", 5]]},
    {"question": "Name something that makes guests laugh.", "answers": [["Games", 30], ["Jokes", 25], ["Stories", 18], ["Photos", 12], ["Dancing", 10], ["Toasts", 5]]},
    {"question": "Name something people do when music comes on.", "answers": [["Dance", 40], ["Sing", 20], ["Clap", 15], ["Record video", 10], ["Talk louder", 8], ["Request a song", 7]]},
    {"question": "Name something people look for at a venue.", "answers": [["Bathroom", 30], ["Food", 20], ["Bar", 18], ["Seat", 15], ["Parking", 10], ["Host", 7]]},
    {"question": "Name something that appears in party photos.", "answers": [["Smiles", 30], ["Decor", 25], ["Drinks", 15], ["Food", 12], ["Balloons", 10], ["Cake", 8]]},
    {"question": "Name something people bring home from a party.", "answers": [["Favor", 30], ["Leftovers", 25], ["Photos", 20], ["Gift bag", 12], ["Flowers", 8], ["Memories", 5]]},
    {"question": "Name something people do while waiting for food.", "answers": [["Talk", 35], ["Drink", 20], ["Take photos", 18], ["Play games", 12], ["Check phone", 10], ["Dance", 5]]},
    {"question": "Name something people compliment at an event.", "answers": [["Decor", 30], ["Food", 25], ["Outfit", 18], ["Venue", 12], ["Cake", 10], ["Music", 5]]},
]


def extend_event_question_presets_to_20():
    """Ensure each built-in event theme has exactly 20 main questions available."""
    for theme_name, preset in EVENT_QUESTION_PRESETS.items():
        preset.setdefault("main", [])
        extras = EXTRA_EVENT_MAIN_QUESTIONS.get(theme_name, EXTRA_EVENT_MAIN_QUESTIONS["Classic Party"])
        existing_questions = {q.get("question") for q in preset.get("main", [])}

        for source in (extras, GENERIC_FILLER_MAIN_QUESTIONS):
            for extra in source:
                if len(preset["main"]) >= 20:
                    break
                if extra.get("question") not in existing_questions:
                    preset["main"].append(json.loads(json.dumps(extra)))
                    existing_questions.add(extra.get("question"))
            if len(preset["main"]) >= 20:
                break

        # Keep the built-in packs to exactly 20 main questions so the host preview is predictable.
        preset["main"] = preset["main"][:20]


extend_event_question_presets_to_20()


def preset_questions_for_theme(theme_name):
    preset = EVENT_QUESTION_PRESETS.get(theme_name) or EVENT_QUESTION_PRESETS["Classic Party"]
    # Deep copy through JSON so changing the active game does not mutate the preset.
    return json.loads(json.dumps(preset["main"])), json.loads(json.dumps(preset["fast_money"]))


def apply_theme_question_preset(state, theme_name):
    main_qs, fast_qs = preset_questions_for_theme(theme_name)
    state["questions"] = main_qs
    state["fast_money_questions"] = fast_qs
    state["google_sheet_url"] = ""
    state["current_question_index"] = 0
    state["questions_source"] = f"preset:{theme_name}"
    state["message"] = f"Loaded {theme_name} preset questions."

def default_custom_theme():
    return THEMES["Custom"].copy()


def get_theme_colors(state):
    selected_theme = state.get("theme", "Classic Party")
    if selected_theme == "Custom":
        custom = default_custom_theme()
        custom.update(state.get("custom_theme", {}) if isinstance(state.get("custom_theme"), dict) else {})
        return custom
    return THEMES.get(selected_theme, THEMES["Classic Party"])


def default_state():
    return {
        "teams": {},
        "locked": False,
        "matches": [],
        "current_match_index": 0,
        "active_teams": [],
        "round_winners": [],
        "round_bank": 0,
        "match_scores": {},
        "total_scores": {},
        "current_question_index": 0,
        "match_question_count": 1,
        "questions_per_match": 3,
        "target_team_count": 4,
        "revealed": [],
        "strike": False,
        "steal_mode": False,
        "questions": DEFAULT_MAIN_QUESTIONS,
        "fast_money_questions": DEFAULT_FAST_MONEY_QUESTIONS,
        "google_sheet_url": "",
        "background_image_data": "",
        "background_image_mime": "",
        "center_panel_color": "",
        "app_title": "Survey-Style Party Game",
        "app_subtitle": "Tournament Edition",
        "theme": "Classic Party",
        "custom_theme": default_custom_theme(),
        "champion_team": "",
        "tournament_complete": False,
        "fast_money_started": False,
        "fast_money_start_time": 0,
        "fast_money_answers": {},
        "ended": False,
        "ended_reason": "",
        "ended_at": 0,
        "questions_source": "preset:Classic Party",
        "message": "Welcome to the Survey-Style Party Game!",
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


    if state.get("theme") not in THEMES:
        state["theme"] = "Classic Party"
    if not isinstance(state.get("custom_theme"), dict):
        state["custom_theme"] = default_custom_theme()
    if not isinstance(state.get("match_question_count"), int) or state.get("match_question_count", 1) < 1:
        state["match_question_count"] = 1
    if not isinstance(state.get("questions_per_match"), int) or state.get("questions_per_match", 3) < 1:
        state["questions_per_match"] = 3
    if not isinstance(state.get("target_team_count"), int) or state.get("target_team_count", 4) < 2:
        state["target_team_count"] = 4
    if not isinstance(state.get("background_image_data"), str):
        state["background_image_data"] = ""
    if not isinstance(state.get("background_image_mime"), str):
        state["background_image_mime"] = ""
    if not isinstance(state.get("center_panel_color"), str):
        state["center_panel_color"] = ""
    if not isinstance(state.get("app_title"), str) or not state.get("app_title", "").strip():
        state["app_title"] = "Survey-Style Party Game"
    if not isinstance(state.get("app_subtitle"), str):
        state["app_subtitle"] = "Tournament Edition"

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


def hex_to_rgb(hex_color, fallback=(255, 255, 255)):
    value = str(hex_color or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return fallback
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


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
center_panel_color = state.get("center_panel_color") or active_theme.get("cream")
center_panel_rgb = hex_to_rgb(center_panel_color, fallback=(255, 255, 255))
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

/*
   Center-panel layout using layered backgrounds:
   - The uploaded image is the outside/background layer.
   - A centered solid-color stripe is layered above it.
   - Because it is a background layer, it always extends to the bottom of the viewport/page.
*/
:root {{
    --center-panel-width: min(1180px, calc(100vw - 120px));
}}

html, body, .stApp, [data-testid="stAppViewContainer"] {{
    min-height: 100vh !important;
    overflow-x: hidden !important;
    background-color: var(--paper) !important;
    background-image: linear-gradient(
        rgba({center_panel_rgb[0]}, {center_panel_rgb[1]}, {center_panel_rgb[2]}, 0.80),
        rgba({center_panel_rgb[0]}, {center_panel_rgb[1]}, {center_panel_rgb[2]}, 0.80)
    ) !important;
    background-size: var(--center-panel-width) 100% !important;
    background-position: center top !important;
    background-repeat: no-repeat !important;
    background-attachment: fixed !important;
}}

[data-testid="stAppViewContainer"] > .main {{
    background: transparent !important;
    min-height: 100vh !important;
}}

/* Streamlit content column: transparent, same width as the center panel */
.block-container,
[data-testid="stAppViewBlockContainer"] {{
    max-width: var(--center-panel-width) !important;
    width: var(--center-panel-width) !important;
    min-height: 100vh !important;
    background: transparent !important;
    background-image: none !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 2rem 2.5rem 4rem 2.5rem !important;
    margin: 0 auto !important;
    box-shadow: none !important;
}}

/* Keep phones usable: on small screens the center panel gets wider. */
@media (max-width: 900px) {{
    :root {{
        --center-panel-width: calc(100vw - 24px);
    }}

    .block-container,
    [data-testid="stAppViewBlockContainer"] {{
        padding: 1.25rem 1rem 3rem 1rem !important;
    }}
}}</style>
""",
    unsafe_allow_html=True,
)


# Optional host-uploaded background image. This is saved per game session.
if state.get("background_image_data") and state.get("background_image_mime"):
    st.markdown(
        f"""
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background-image:
        linear-gradient(
            rgba({center_panel_rgb[0]}, {center_panel_rgb[1]}, {center_panel_rgb[2]}, 0.80),
            rgba({center_panel_rgb[0]}, {center_panel_rgb[1]}, {center_panel_rgb[2]}, 0.80)
        ),
        url('data:{state["background_image_mime"]};base64,{state["background_image_data"]}') !important;
    background-size: var(--center-panel-width) 100%, cover !important;
    background-position: center top, center center !important;
    background-repeat: no-repeat, no-repeat !important;
    background-attachment: fixed, fixed !important;
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


def question_template_csv():
    return pd.DataFrame(QUESTION_TEMPLATE_ROWS).to_csv(index=False).encode("utf-8")


def build_questions_from_dataframe(df):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"game_type", "question", "answer", "points"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    df = df.dropna(subset=["game_type", "question", "answer"])
    df["game_type"] = df["game_type"].astype(str).str.strip().str.lower()
    df["question"] = df["question"].astype(str).str.strip()
    df["answer"] = df["answer"].astype(str).str.strip()

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
                if row["answer"]:
                    answers.append([str(row["answer"]), points])
            if answers:
                questions.append({"question": str(question_text), "answers": answers})
        return questions

    main_questions = build_questions(main_df)
    fast_money_questions = build_questions(fast_df)

    if not main_questions:
        raise ValueError("No main questions found. Use game_type = main.")
    if len(fast_money_questions) < 5:
        raise ValueError("Fast Money needs at least 5 questions with game_type = fast_money.")

    return main_questions, fast_money_questions[:5]


def load_questions_from_csv(csv_url):
    df = pd.read_csv(csv_url)
    return build_questions_from_dataframe(df)


def load_questions_from_upload(uploaded_file):
    df = pd.read_csv(uploaded_file)
    return build_questions_from_dataframe(df)

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
    state["match_question_count"] = 1
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



def advance_to_next_question_in_match():
    questions_per_match = max(1, int(state.get("questions_per_match", 3)))
    current_count = max(1, int(state.get("match_question_count", 1)))

    if current_count >= questions_per_match:
        state["message"] = f"This match already has {questions_per_match} question(s). End the match to advance."
        return

    state["match_question_count"] = current_count + 1
    state["current_question_index"] += 1
    reset_question_state()
    state["message"] = f"Question {state['match_question_count']} of {questions_per_match}."


def render_question_preview():
    st.subheader("Question Preview")
    st.caption("Preview what is currently loaded for this game session before you lock the teams.")

    with st.expander(f"Main Game Questions ({len(state.get('questions', []))})", expanded=False):
        for q_idx, question in enumerate(state.get("questions", []), start=1):
            st.markdown(f"**{q_idx}. {question.get('question', '')}**")
            for answer, points in question.get("answers", []):
                st.write(f"- {answer} — {points}")

    with st.expander(f"Fast Money Questions ({len(state.get('fast_money_questions', []))})", expanded=False):
        for q_idx, question in enumerate(state.get("fast_money_questions", []), start=1):
            st.markdown(f"**{q_idx}. {question.get('question', '')}**")
            for answer, points in question.get("answers", []):
                st.write(f"- {answer} — {points}")


def render_header():
    title = html.escape(state.get("app_title", "Survey-Style Party Game "))
    subtitle = html.escape(state.get("app_subtitle", "Tournament Edition"))
    st.markdown(f'<div class="main-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="subtitle">{subtitle}</div>', unsafe_allow_html=True)


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


    st.markdown(
        f'<div class="info-card"><strong>Match Question:</strong> {state.get("match_question_count", 1)} of {state.get("questions_per_match", 3)}</div>',
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
                target_team_count = int(state.get("target_team_count", 4))
                creating_new_team = team not in state.get("teams", {})
                if creating_new_team and len(state.get("teams", {})) >= target_team_count:
                    st.error(f"This game is limited to {target_team_count} teams. Join an existing team or ask the host to increase the limit.")
                    st.stop()
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

    with st.sidebar.expander("Game Title", expanded=True):
        new_title = st.text_input("Main title", value=state.get("app_title", "Survey-Style Party Game"), max_chars=60)
        new_subtitle = st.text_input("Subtitle", value=state.get("app_subtitle", "Tournament Edition"), max_chars=80)
        if new_title != state.get("app_title") or new_subtitle != state.get("app_subtitle"):
            state["app_title"] = new_title.strip() or "Survey-Style Party Game"
            state["app_subtitle"] = new_subtitle.strip()
            save_state(state)
            st.rerun()

    with st.sidebar.expander("Background Image", expanded=False):
        st.caption("Upload a JPG/PNG/WebP image for the outer page background. The center game panel stays a 20% transparent solid color for readability.")
        uploaded_background = st.file_uploader("Upload background image", type=["png", "jpg", "jpeg", "webp"], key="background_image_upload")
        if uploaded_background is not None and st.button("Use Uploaded Background"):
            image_bytes = uploaded_background.getvalue()
            if len(image_bytes) > 2_500_000:
                st.error("Please upload an image under 2.5 MB so the player view stays fast.")
            else:
                state["background_image_data"] = base64.b64encode(image_bytes).decode("utf-8")
                state["background_image_mime"] = uploaded_background.type or "image/png"
                save_state(state)
                st.success("Background image updated.")
                st.rerun()
        if state.get("background_image_data"):
            st.success("A custom background is active for this session.")
            if st.button("Remove Background Image"):
                state["background_image_data"] = ""
                state["background_image_mime"] = ""
                save_state(state)
                st.rerun()

        st.divider()
        current_panel_color = state.get("center_panel_color") or get_theme_colors(state).get("cream", "#FFFFFF")
        new_panel_color = st.color_picker("Center panel color", current_panel_color)
        if new_panel_color != state.get("center_panel_color", ""):
            state["center_panel_color"] = new_panel_color
            save_state(state)
            st.rerun()
        st.caption("The center panel uses this color at 80% opacity, meaning it is 20% transparent. It is fixed from top to bottom so it always reaches the bottom of the screen.")

    with st.sidebar.expander("Event Theme + Preset Questions", expanded=True):
        theme_names = list(THEMES.keys())
        current_theme_name = state.get("theme", "Classic Party")
        if current_theme_name not in theme_names:
            current_theme_name = "Classic Party"

        selected_theme = st.selectbox(
            "Event Theme",
            theme_names,
            index=theme_names.index(current_theme_name),
            help="This changes the game colors. For built-in event themes, it can also load matching preset questions.",
        )

        theme_changed = selected_theme != state.get("theme")

        if theme_changed:
            state["theme"] = selected_theme
            if selected_theme != "Custom":
                apply_theme_question_preset(state, selected_theme)
                reset_question_state()
            save_state(state)
            st.rerun()

        if selected_theme == "Custom":
            st.caption("Choose your own colors for this game session. Custom keeps the current questions unless you upload or load a preset separately.")
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
                save_state(state)
                st.rerun()
        else:
            st.caption("Changing to this event theme automatically loads matching preset questions.")
            if st.button("Reload Preset Questions for This Event"):
                apply_theme_question_preset(state, selected_theme)
                reset_question_state()
                save_state(state)
                st.success(f"Reloaded {selected_theme} preset questions.")
                st.rerun()

        current_source = state.get("questions_source", "preset:Classic Party")
        st.markdown(
            f'<div class="info-card"><strong>Preview:</strong><br>'
            f'<span style="color:{get_theme_colors(state)["primary"]};">Primary</span> • '
            f'<span style="color:{get_theme_colors(state)["secondary"]};">Accent</span><br>'
            f'<span class="small-note">Questions: {current_source}</span></div>',
            unsafe_allow_html=True,
        )

    with st.sidebar.expander("Custom Questions", expanded=True):
        st.caption("Use the CSV template below. Required columns: game_type, question, answer, points. Use game_type values main or fast_money.")
        st.download_button(
            "Download Question Template",
            data=question_template_csv(),
            file_name="family_feud_question_template.csv",
            mime="text/csv",
        )

        uploaded_questions = st.file_uploader("Upload completed CSV template", type=["csv"])
        if uploaded_questions is not None and st.button("Load Uploaded Questions"):
            try:
                main_qs, fast_qs = load_questions_from_upload(uploaded_questions)
                state["questions"] = main_qs
                state["fast_money_questions"] = fast_qs
                state["google_sheet_url"] = ""
                state["questions_source"] = "uploaded CSV"
                state["current_question_index"] = 0
                reset_question_state()
                save_state(state)
                st.success(f"Loaded {len(main_qs)} main questions and {len(fast_qs)} Fast Money questions from CSV.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not load uploaded questions: {error}")

        st.divider()
        csv_url = st.text_input("Or paste a published Google Sheet CSV URL", value=state.get("google_sheet_url", ""))
        if st.button("Load Questions from URL"):
            try:
                main_qs, fast_qs = load_questions_from_csv(csv_url)
                state["questions"] = main_qs
                state["fast_money_questions"] = fast_qs
                state["google_sheet_url"] = csv_url
                state["questions_source"] = "Google Sheet URL"
                state["current_question_index"] = 0
                reset_question_state()
                save_state(state)
                st.success(f"Loaded {len(main_qs)} main questions and {len(fast_qs)} Fast Money questions from URL.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not load questions from URL: {error}")

    with st.sidebar.expander("Question Preview", expanded=False):
        st.write(f"Main questions loaded: {len(state.get('questions', []))}")
        st.write(f"Fast Money questions loaded: {len(state.get('fast_money_questions', []))}")
        if st.button("Show / Refresh Question Preview"):
            st.session_state["show_question_preview"] = True

    with st.sidebar.expander("Teams + Bracket", expanded=True):
        configured_teams = st.number_input(
            "How many teams are playing?",
            min_value=2,
            max_value=20,
            value=int(state.get("target_team_count", 4)),
            step=1,
            disabled=state.get("locked", False),
        )
        configured_questions = st.number_input(
            "Questions per match",
            min_value=1,
            max_value=10,
            value=int(state.get("questions_per_match", 3)),
            step=1,
            disabled=state.get("locked", False),
        )
        if not state.get("locked") and (configured_teams != state.get("target_team_count") or configured_questions != state.get("questions_per_match")):
            state["target_team_count"] = int(configured_teams)
            state["questions_per_match"] = int(configured_questions)
            save_state(state)
            st.rerun()

        st.write(f"Teams signed up: {len(state.get('teams', {}))}/{state.get('target_team_count', 4)}")

        if not state.get("locked"):
            if st.button("Lock Teams + Build Bracket"):
                signed_up_count = len(state.get("teams", {}))
                target_count = int(state.get("target_team_count", 4))
                if signed_up_count < 2:
                    st.error("You need at least 2 teams to play.")
                elif signed_up_count != target_count:
                    st.error(f"You selected {target_count} teams, but {signed_up_count} team(s) are signed up. Adjust the team count or wait for more teams.")
                else:
                    state["locked"] = True
                    state["match_question_count"] = 1
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

    if st.session_state.get("show_question_preview"):
        render_question_preview()

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
        st.sidebar.caption(f"Question {state.get('match_question_count', 1)} of {state.get('questions_per_match', 3)} for this match.")
        if st.sidebar.button("Next Question in This Match"):
            advance_to_next_question_in_match()
            save_state(state)
            st.rerun()

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
