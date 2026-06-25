import base64
import json
import os
import random
import re
import string
import tempfile
import time
from contextlib import contextmanager
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

# ============================================================
# SURVEY STYLE INTERACTIVE PARTY GAME — VERSION 2.1
# Single-file Streamlit app for easy Etsy/customer deployment.
# ============================================================

st.set_page_config(page_title="Survey Style Interactive Party Game", layout="wide")

SESSIONS_DIR = "game_sessions"
HOSTS_FILE = "host_sessions.json"
DEFAULT_GAME_CODE = "default"
GAME_CODE_LENGTH = 4
FAST_MONEY_SECONDS = 45
FUZZY_THRESHOLD = 78

# -----------------------------
# Event themes + colors
# -----------------------------

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

THEME_COLOR_FIELDS = [
    ("Page Background", "paper"),
    ("Card Background", "cream"),
    ("Primary Text", "primary"),
    ("Secondary Text", "secondary"),
    ("Accent", "accent"),
    ("Border", "border"),
    ("Highlight", "highlight"),
    ("Sidebar", "sidebar"),
]

FONT_OPTIONS = {
    "Playfair Display": "'Playfair Display', serif",
    "Cormorant Garamond": "'Cormorant Garamond', serif",
    "Georgia": "Georgia, serif",
    "Times New Roman": "'Times New Roman', serif",
    "Arial": "Arial, sans-serif",
    "Verdana": "Verdana, sans-serif",
}


def q(question: str, answers: List[Tuple[str, int]]) -> Dict:
    return {"question": question, "answers": [[a, int(p)] for a, p in answers]}


def build_pack(main: List[Dict], fast: List[Dict]) -> Dict:
    if len(main) != 20:
        raise ValueError("Each event preset must contain exactly 20 main questions.")
    if len(fast) < 5:
        raise ValueError("Each event preset must contain at least 5 Fast Money questions.")
    return {"main": main, "fast_money": fast[:5]}

COMMON_FAST = [
    q("Name something people do at a celebration.", [("Dance", 35), ("Eat", 25), ("Drink", 20), ("Talk", 12), ("Take pictures", 8)]),
    q("Name something people forget to bring to an event.", [("Gift", 30), ("Phone", 25), ("Wallet", 20), ("Keys", 15), ("Jacket", 10)]),
    q("Name something you see on a party table.", [("Food", 35), ("Drinks", 25), ("Plates", 15), ("Flowers", 15), ("Candles", 10)]),
    q("Name a reason someone arrives late.", [("Traffic", 40), ("Getting ready", 25), ("Lost", 15), ("Work", 10), ("Parking", 10)]),
    q("Name something people take pictures of at a party.", [("People", 35), ("Decor", 25), ("Food", 15), ("Cake", 15), ("Group photo", 10)]),
]

EVENT_QUESTION_PRESETS = {
    "Classic Party": build_pack([
        q("Name something people bring to a party.", [("Drinks", 35), ("Food", 25), ("Gift", 15), ("Dessert", 10), ("Flowers", 8), ("Games", 7)]),
        q("Name something people do at a celebration.", [("Dance", 35), ("Eat", 25), ("Drink", 20), ("Talk", 12), ("Take pictures", 8)]),
        q("Name something you see on a party table.", [("Food", 35), ("Drinks", 25), ("Plates", 15), ("Flowers", 15), ("Candles", 10)]),
        q("Name a reason someone arrives late.", [("Traffic", 40), ("Getting ready", 25), ("Lost", 15), ("Work", 10), ("Parking", 10)]),
        q("Name something people wear to a party.", [("Dress", 30), ("Jeans", 20), ("Heels", 15), ("Button-up", 15), ("Jewelry", 10), ("Jacket", 10)]),
        q("Name something people do before guests arrive.", [("Clean", 35), ("Cook", 25), ("Decorate", 20), ("Get dressed", 10), ("Set table", 10)]),
        q("Name a party food people love.", [("Pizza", 30), ("Chips", 25), ("Cake", 20), ("Dip", 15), ("Tacos", 10)]),
        q("Name something you might find in a party favor bag.", [("Candy", 35), ("Sticker", 20), ("Toy", 20), ("Keychain", 15), ("Thank-you note", 10)]),
        q("Name something people complain about at parties.", [("Parking", 30), ("Noise", 25), ("Crowds", 20), ("Food", 15), ("Weather", 10)]),
        q("Name something a host runs out of.", [("Ice", 35), ("Drinks", 25), ("Plates", 15), ("Napkins", 15), ("Food", 10)]),
        q("Name a party game people play.", [("Charades", 30), ("Cards", 25), ("Trivia", 20), ("Bingo", 15), ("Board games", 10)]),
        q("Name something people decorate with.", [("Balloons", 35), ("Flowers", 25), ("Banner", 20), ("Lights", 10), ("Candles", 10)]),
        q("Name a song people dance to at a party.", [("Cupid Shuffle", 25), ("Cha Cha Slide", 25), ("Uptown Funk", 20), ("September", 15), ("Dancing Queen", 15)]),
        q("Name something people post after a party.", [("Photos", 40), ("Videos", 25), ("Thank you", 15), ("Group selfie", 10), ("Food pics", 10)]),
        q("Name a place people host parties.", [("House", 40), ("Restaurant", 25), ("Park", 15), ("Backyard", 10), ("Event hall", 10)]),
        q("Name something you need for a toast.", [("Drink", 45), ("Glass", 25), ("Speech", 15), ("Cheers", 10), ("Audience", 5)]),
        q("Name something guests do when they first arrive.", [("Say hello", 35), ("Drop off gift", 25), ("Get a drink", 20), ("Find seat", 10), ("Take photos", 10)]),
        q("Name a party dessert besides cake.", [("Cookies", 35), ("Cupcakes", 25), ("Brownies", 20), ("Pie", 10), ("Ice cream", 10)]),
        q("Name something that makes a party memorable.", [("Music", 30), ("People", 25), ("Food", 20), ("Games", 15), ("Decor", 10)]),
        q("Name something people clean up after a party.", [("Trash", 35), ("Dishes", 25), ("Decorations", 20), ("Food", 10), ("Spills", 10)]),
    ], COMMON_FAST),
    "Baby Shower - Boy": build_pack([
        q("Name something parents always carry in a diaper bag.", [("Diapers", 35), ("Wipes", 25), ("Bottle", 15), ("Snacks", 10), ("Extra clothes", 8), ("Pacifier", 7)]),
        q("Name something blue you might see at a baby shower.", [("Balloons", 30), ("Cake", 25), ("Decorations", 20), ("Plates", 10), ("Flowers", 8), ("Outfit", 7)]),
        q("Name a gift people buy for a baby boy.", [("Clothes", 35), ("Blanket", 25), ("Toys", 18), ("Diapers", 12), ("Books", 6), ("Shoes", 4)]),
        q("Name something babies need every day.", [("Diapers", 35), ("Milk", 30), ("Sleep", 18), ("Clothes", 10), ("Love", 7)]),
        q("Name something in a nursery.", [("Crib", 35), ("Changing table", 25), ("Rocking chair", 15), ("Diapers", 15), ("Mobile", 10)]),
        q("Name something babies wear.", [("Onesie", 35), ("Pajamas", 25), ("Socks", 15), ("Hat", 15), ("Bib", 10)]),
        q("Name something new parents lose a lot of.", [("Sleep", 50), ("Patience", 20), ("Time", 15), ("Money", 10), ("Keys", 5)]),
        q("Name a baby shower game.", [("Baby bingo", 30), ("Don’t say baby", 25), ("Diaper raffle", 20), ("Guess belly", 15), ("Price is right", 10)]),
        q("Name something babies do that makes everyone smile.", [("Smile", 35), ("Laugh", 25), ("Crawl", 15), ("Sleep", 15), ("Coo", 10)]),
        q("Name something parents baby-proof.", [("Outlets", 35), ("Cabinets", 25), ("Stairs", 20), ("Doors", 10), ("Corners", 10)]),
        q("Name a popular baby name theme.", [("Classic", 30), ("Family", 25), ("Biblical", 15), ("Nature", 15), ("Unique", 15)]),
        q("Name something babies make a lot of.", [("Noise", 30), ("Mess", 25), ("Laundry", 20), ("Diapers", 15), ("Smiles", 10)]),
        q("Name something found at a baby shower dessert table.", [("Cake", 35), ("Cupcakes", 25), ("Cookies", 20), ("Candy", 10), ("Macarons", 10)]),
        q("Name something parents use at bath time.", [("Soap", 30), ("Towel", 25), ("Tub", 20), ("Washcloth", 15), ("Lotion", 10)]),
        q("Name something people write in a baby card.", [("Congrats", 35), ("Best wishes", 25), ("Love", 20), ("Advice", 10), ("Name suggestion", 10)]),
        q("Name a baby milestone.", [("First steps", 35), ("First word", 25), ("Crawling", 20), ("Sitting", 10), ("Rolling", 10)]),
        q("Name something babies sleep in.", [("Crib", 45), ("Bassinet", 25), ("Swaddle", 15), ("Onesie", 10), ("Sleep sack", 5)]),
        q("Name something you need for feeding a baby.", [("Bottle", 35), ("Milk", 30), ("Burp cloth", 15), ("Bib", 10), ("High chair", 10)]),
        q("Name something guests guess at a baby shower.", [("Due date", 30), ("Weight", 25), ("Name", 20), ("Gender", 15), ("Belly size", 10)]),
        q("Name something that calms a baby.", [("Pacifier", 30), ("Rocking", 25), ("Bottle", 20), ("Singing", 15), ("Swaddle", 10)]),
    ], COMMON_FAST),
    "Baby Shower - Girl": build_pack([
        q("Name something pink you might see at a baby shower.", [("Balloons", 30), ("Cake", 25), ("Flowers", 20), ("Decorations", 15), ("Plates", 6), ("Ribbon", 4)]),
        q("Name a gift people buy for a baby girl.", [("Clothes", 35), ("Blanket", 25), ("Headbands", 15), ("Toys", 12), ("Books", 8), ("Diapers", 5)]),
        q("Name something parents always carry in a diaper bag.", [("Diapers", 35), ("Wipes", 25), ("Bottle", 15), ("Snacks", 10), ("Extra clothes", 8), ("Pacifier", 7)]),
        q("Name something babies do that makes everyone say aww.", [("Smile", 40), ("Laugh", 25), ("Sleep", 15), ("Wave", 10), ("Cuddle", 10)]),
        q("Name a popular baby shower decoration.", [("Balloons", 35), ("Flowers", 25), ("Banner", 15), ("Cake", 12), ("Centerpieces", 8), ("Backdrop", 5)]),
        q("Name something babies wear on their head.", [("Bow", 35), ("Hat", 30), ("Headband", 20), ("Bonnet", 10), ("Nothing", 5)]),
        q("Name something you put on a baby registry.", [("Diapers", 30), ("Stroller", 25), ("Car seat", 20), ("Crib", 15), ("Bottles", 10)]),
        q("Name something a newborn does a lot.", [("Sleep", 35), ("Cry", 25), ("Eat", 20), ("Poop", 10), ("Cuddle", 10)]),
        q("Name something people serve at a baby shower brunch.", [("Mimosas", 30), ("Fruit", 25), ("Pastries", 20), ("Quiche", 15), ("Coffee", 10)]),
        q("Name something found in a nursery.", [("Crib", 35), ("Dresser", 25), ("Rocking chair", 15), ("Books", 15), ("Lamp", 10)]),
        q("Name something babies need when leaving the hospital.", [("Car seat", 45), ("Blanket", 20), ("Outfit", 15), ("Diapers", 10), ("Hat", 10)]),
        q("Name something parents do when the baby sleeps.", [("Sleep", 40), ("Clean", 25), ("Eat", 15), ("Shower", 10), ("Watch TV", 10)]),
        q("Name something that might be on a baby shower cake.", [("Name", 30), ("Baby", 25), ("Flowers", 20), ("Pink icing", 15), ("Booties", 10)]),
        q("Name something people write on advice cards.", [("Sleep when baby sleeps", 35), ("Enjoy it", 25), ("Ask for help", 20), ("Take photos", 10), ("Be patient", 10)]),
        q("Name something in a baby closet.", [("Onesies", 35), ("Dresses", 25), ("Pajamas", 15), ("Shoes", 15), ("Blankets", 10)]),
        q("Name a baby shower prize.", [("Candle", 30), ("Gift card", 25), ("Wine", 20), ("Candy", 15), ("Soap", 10)]),
        q("Name something babies grab.", [("Hair", 30), ("Fingers", 25), ("Toys", 20), ("Blanket", 15), ("Food", 10)]),
        q("Name something used during diaper changes.", [("Wipes", 35), ("Diapers", 30), ("Cream", 15), ("Changing pad", 10), ("Trash bag", 10)]),
        q("Name something people guess at a baby shower.", [("Due date", 30), ("Weight", 25), ("Name", 20), ("Belly size", 15), ("Birth time", 10)]),
        q("Name something babies love to chew on.", [("Teether", 35), ("Toys", 25), ("Fingers", 20), ("Blanket", 10), ("Pacifier", 10)]),
    ], COMMON_FAST),
    "Gender Neutral Baby Shower": build_pack([
        q("Name a popular baby shower decoration.", [("Balloons", 35), ("Flowers", 25), ("Banner", 15), ("Cake", 12), ("Tableware", 8), ("Centerpieces", 5)]),
        q("Name something every new parent needs.", [("Diapers", 35), ("Sleep", 25), ("Wipes", 18), ("Help", 12), ("Patience", 6), ("Coffee", 4)]),
        q("Name a baby shower game people play.", [("Guess the belly", 30), ("Don’t say baby", 25), ("Diaper raffle", 20), ("Baby bingo", 15), ("Price is right", 10)]),
        q("Name something babies make a lot of.", [("Noise", 30), ("Mess", 25), ("Laundry", 20), ("Smiles", 15), ("Diapers", 10)]),
        q("Name a gender-neutral baby color.", [("Green", 30), ("Yellow", 25), ("White", 20), ("Cream", 15), ("Gray", 10)]),
        q("Name something on a baby registry.", [("Diapers", 35), ("Car seat", 25), ("Stroller", 20), ("Crib", 10), ("Bottles", 10)]),
        q("Name an animal used in baby shower decor.", [("Bear", 30), ("Elephant", 25), ("Giraffe", 20), ("Bunny", 15), ("Lion", 10)]),
        q("Name something babies sleep with.", [("Blanket", 30), ("Pacifier", 25), ("Stuffed animal", 20), ("Sound machine", 15), ("Swaddle", 10)]),
        q("Name something parents do at 3 AM.", [("Feed baby", 35), ("Change diaper", 25), ("Rock baby", 20), ("Cry", 10), ("Make coffee", 10)]),
        q("Name something guests bring to a baby shower.", [("Gift", 40), ("Card", 25), ("Diapers", 15), ("Food", 10), ("Flowers", 10)]),
        q("Name a baby item that is hard to assemble.", [("Crib", 35), ("Stroller", 25), ("Car seat", 20), ("Swing", 10), ("High chair", 10)]),
        q("Name something babies find funny.", [("Peekaboo", 35), ("Faces", 25), ("Tickles", 20), ("Silly sounds", 10), ("Pets", 10)]),
        q("Name something parents take lots of photos of.", [("Baby sleeping", 30), ("Smiling", 25), ("Firsts", 20), ("Outfits", 15), ("Bath time", 10)]),
        q("Name something found in a diaper caddy.", [("Diapers", 35), ("Wipes", 30), ("Cream", 15), ("Pacifier", 10), ("Burp cloth", 10)]),
        q("Name something people say to a pregnant person.", [("Congratulations", 35), ("When are you due", 25), ("You look great", 20), ("Boy or girl", 10), ("Need anything", 10)]),
        q("Name something babies do in public.", [("Cry", 35), ("Sleep", 25), ("Smile", 20), ("Spit up", 10), ("Wave", 10)]),
        q("Name something a baby shower host sets up.", [("Food", 30), ("Decor", 25), ("Games", 20), ("Favors", 15), ("Gift table", 10)]),
        q("Name something tiny babies have.", [("Fingers", 30), ("Toes", 25), ("Clothes", 20), ("Shoes", 15), ("Nose", 10)]),
        q("Name a baby shower theme.", [("Woodland", 25), ("Safari", 25), ("Boho", 20), ("Teddy bear", 15), ("Little cutie", 15)]),
        q("Name something that helps babies sleep.", [("Rocking", 30), ("Sound machine", 25), ("Pacifier", 20), ("Swaddle", 15), ("Bottle", 10)]),
    ], COMMON_FAST),
    "Bachelor Party": build_pack([
        q("Name something people do at a bachelor party.", [("Drink", 35), ("Go out", 25), ("Play games", 15), ("Eat", 10), ("Golf", 8), ("Take pictures", 7)]),
        q("Name something the groom might forget to pack.", [("Toothbrush", 30), ("Suit", 25), ("Wallet", 20), ("Phone charger", 15), ("Shoes", 10)]),
        q("Name a place people go for a bachelor party.", [("Vegas", 40), ("Bar", 25), ("Golf course", 15), ("Beach", 10), ("Cabin", 10)]),
        q("Name something people toast to at a bachelor party.", [("The groom", 40), ("Marriage", 25), ("Friendship", 15), ("Good luck", 12), ("The future", 8)]),
        q("Name a bachelor party activity.", [("Golf", 30), ("Bar hopping", 25), ("Dinner", 20), ("Casino", 15), ("Boat day", 10)]),
        q("Name something found in a hotel room.", [("Bed", 40), ("Towels", 25), ("TV", 15), ("Mini fridge", 10), ("Shampoo", 10)]),
        q("Name a reason the group is late.", [("Someone overslept", 30), ("Traffic", 25), ("Getting ready", 20), ("Lost", 15), ("Waiting on rideshare", 10)]),
        q("Name something people regret after a night out.", [("Drinking too much", 35), ("Spending money", 25), ("Staying out late", 20), ("Bad photos", 10), ("Texting", 10)]),
        q("Name a guys’ trip essential.", [("Clothes", 30), ("Wallet", 25), ("Phone charger", 20), ("Snacks", 15), ("Sunglasses", 10)]),
        q("Name a bachelor party destination besides Vegas.", [("Nashville", 30), ("Miami", 25), ("Austin", 20), ("Scottsdale", 15), ("New Orleans", 10)]),
        q("Name something on the itinerary.", [("Dinner", 30), ("Drinks", 25), ("Golf", 20), ("Pool", 15), ("Nightclub", 10)]),
        q("Name a food ordered for a bachelor party group.", [("Pizza", 35), ("Burgers", 25), ("Steak", 20), ("Wings", 10), ("Tacos", 10)]),
        q("Name something the best man is responsible for.", [("Planning", 35), ("Reservations", 25), ("Keeping groom safe", 15), ("Speech", 15), ("Payments", 10)]),
        q("Name something people wear on a night out.", [("Button-up", 30), ("Jeans", 25), ("Sneakers", 20), ("Watch", 15), ("Jacket", 10)]),
        q("Name something used to celebrate the groom.", [("Toast", 35), ("Speech", 25), ("Banner", 15), ("Custom shirt", 15), ("Photos", 10)]),
        q("Name a bachelor party game.", [("Poker", 30), ("Trivia", 25), ("Cards", 20), ("Darts", 15), ("Pool", 10)]),
        q("Name something people lose on a trip.", [("Wallet", 30), ("Phone", 25), ("Keys", 20), ("Sunglasses", 15), ("Room key", 10)]),
        q("Name something the groom should avoid before the wedding.", [("Injury", 35), ("Too much drinking", 25), ("Sunburn", 20), ("Missing flight", 10), ("Drama", 10)]),
        q("Name something people take photos of at a bachelor party.", [("Groom", 35), ("Group", 25), ("Drinks", 20), ("Food", 10), ("Destination", 10)]),
        q("Name something needed for a weekend rental house.", [("Food", 30), ("Drinks", 25), ("Towels", 20), ("Speaker", 15), ("Games", 10)]),
    ], COMMON_FAST),
    "Bachelorette Party": build_pack([
        q("Name something people wear to a bachelorette party.", [("Dress", 30), ("Sash", 25), ("Cowboy boots", 15), ("Matching shirts", 12), ("Veil", 10), ("Heels", 8)]),
        q("Name something you see at a bachelorette party.", [("Balloons", 30), ("Cocktails", 25), ("Decorations", 20), ("Bride sash", 15), ("Photo props", 10)]),
        q("Name a popular bachelorette destination.", [("Nashville", 35), ("Vegas", 25), ("Miami", 15), ("Scottsdale", 15), ("Palm Springs", 10)]),
        q("Name something the bride might do during a bachelorette weekend.", [("Dance", 30), ("Drink", 25), ("Take photos", 20), ("Pool day", 15), ("Open gifts", 10)]),
        q("Name something people pack for a girls’ trip.", [("Outfits", 35), ("Makeup", 25), ("Shoes", 20), ("Swimsuit", 10), ("Phone charger", 10)]),
        q("Name a bachelorette party activity.", [("Dancing", 35), ("Pool day", 25), ("Dinner", 20), ("Bar hopping", 10), ("Games", 10)]),
        q("Name something you put on a party itinerary.", [("Dinner", 30), ("Drinks", 25), ("Pool", 20), ("Brunch", 15), ("Photos", 10)]),
        q("Name a drink ordered at a bachelorette party.", [("Margarita", 30), ("Champagne", 25), ("Martini", 20), ("Vodka soda", 15), ("Wine", 10)]),
        q("Name something people take photos with.", [("Bride", 35), ("Decor", 25), ("Balloons", 20), ("Drinks", 10), ("Group", 10)]),
        q("Name a bachelorette decoration.", [("Balloons", 35), ("Banner", 25), ("Streamers", 15), ("Disco balls", 15), ("Flowers", 10)]),
        q("Name something matching the group wears.", [("Shirts", 30), ("Pajamas", 25), ("Sunglasses", 20), ("Hats", 15), ("Swimsuits", 10)]),
        q("Name something the maid of honor plans.", [("Itinerary", 35), ("Dinner", 25), ("Games", 20), ("Decor", 10), ("Payments", 10)]),
        q("Name a bachelorette party theme.", [("Last rodeo", 35), ("Disco", 25), ("Barbie", 15), ("Tropical", 15), ("Pajama party", 10)]),
        q("Name something people do at brunch.", [("Eat", 35), ("Drink mimosas", 25), ("Take photos", 20), ("Toast", 10), ("Recover", 10)]),
        q("Name something that might be on a bride sash.", [("Bride", 45), ("Mrs", 20), ("Future Mrs", 15), ("Name", 10), ("Bride to be", 10)]),
        q("Name something people forget on a girls’ trip.", [("Charger", 30), ("Makeup", 25), ("Shoes", 20), ("ID", 15), ("Swimsuit", 10)]),
        q("Name a bachelorette photo pose.", [("Cheers", 30), ("Group hug", 25), ("Bride center", 20), ("Kiss face", 15), ("Jumping", 10)]),
        q("Name something in a welcome bag.", [("Snacks", 30), ("Itinerary", 25), ("Mini bottle", 20), ("Sunglasses", 15), ("Hangover kit", 10)]),
        q("Name a song played at a bachelorette party.", [("Single Ladies", 30), ("Man I Feel Like a Woman", 25), ("Dancing Queen", 20), ("Girls Just Want to Have Fun", 15), ("Shania Twain", 10)]),
        q("Name something the bride might need the morning after.", [("Coffee", 30), ("Water", 25), ("Pain reliever", 20), ("Breakfast", 15), ("Sunglasses", 10)]),
    ], COMMON_FAST),
    "Bridal Shower": build_pack([
        q("Name something people bring to a bridal shower.", [("Gift", 40), ("Card", 25), ("Flowers", 15), ("Dessert", 10), ("Wine", 10)]),
        q("Name a common bridal shower gift.", [("Kitchen item", 35), ("Towels", 25), ("Candles", 15), ("Glassware", 15), ("Cookbook", 10)]),
        q("Name a bridal shower game.", [("How well do you know bride", 35), ("Gift bingo", 25), ("He said she said", 20), ("Advice cards", 10), ("Toilet paper dress", 10)]),
        q("Name something you see on a bridal shower table.", [("Flowers", 35), ("Cake", 25), ("Plates", 15), ("Candles", 15), ("Favors", 10)]),
        q("Name something the bride registers for.", [("Dishes", 30), ("Towels", 25), ("Mixer", 20), ("Sheets", 15), ("Cookware", 10)]),
        q("Name a bridal shower color.", [("White", 30), ("Blush", 25), ("Gold", 20), ("Champagne", 15), ("Sage", 10)]),
        q("Name something people write in a wedding card.", [("Congratulations", 35), ("Best wishes", 25), ("Love", 20), ("Advice", 10), ("Cheers", 10)]),
        q("Name a bridal shower dessert.", [("Cake", 35), ("Cupcakes", 25), ("Cookies", 20), ("Macarons", 10), ("Donuts", 10)]),
        q("Name something the bride opens.", [("Gifts", 45), ("Cards", 30), ("Champagne", 15), ("Advice", 10)]),
        q("Name something on a bridal shower invitation.", [("Bride name", 35), ("Date", 25), ("Location", 20), ("Registry", 10), ("RSVP", 10)]),
        q("Name something found at a mimosa bar.", [("Champagne", 35), ("Orange juice", 30), ("Fruit", 15), ("Glasses", 10), ("Labels", 10)]),
        q("Name a bridal shower theme.", [("Garden", 30), ("Tea party", 25), ("Brunch", 20), ("Boho", 15), ("Champagne", 10)]),
        q("Name something people ask the bride.", [("Wedding date", 30), ("Honeymoon", 25), ("Dress", 20), ("Venue", 15), ("How you met", 10)]),
        q("Name something needed for a wedding.", [("Dress", 30), ("Rings", 25), ("Venue", 20), ("Flowers", 15), ("Cake", 10)]),
        q("Name something people do during gift opening.", [("Watch", 35), ("Take notes", 25), ("Take photos", 20), ("Clap", 10), ("Pass gifts", 10)]),
        q("Name a bridal shower favor.", [("Candle", 30), ("Soap", 25), ("Candy", 20), ("Mini champagne", 15), ("Plant", 10)]),
        q("Name something elegant at a bridal shower.", [("Flowers", 35), ("Candles", 25), ("China", 20), ("Linen", 10), ("Gold accents", 10)]),
        q("Name something the maid of honor does.", [("Plan shower", 35), ("Speech", 25), ("Help bride", 20), ("Track gifts", 10), ("Decorate", 10)]),
        q("Name a wedding-related word.", [("Love", 30), ("Bride", 25), ("Groom", 20), ("Forever", 15), ("I do", 10)]),
        q("Name something people toast with.", [("Champagne", 40), ("Wine", 25), ("Cocktail", 15), ("Juice", 10), ("Water", 10)]),
    ], COMMON_FAST),
    "Birthday Party": build_pack([
        q("Name something at almost every birthday party.", [("Cake", 40), ("Balloons", 25), ("Gifts", 15), ("Candles", 10), ("Music", 10)]),
        q("Name a birthday party activity.", [("Games", 35), ("Dancing", 25), ("Eating", 20), ("Opening gifts", 10), ("Photos", 10)]),
        q("Name a popular birthday dessert.", [("Cake", 45), ("Cupcakes", 25), ("Ice cream", 20), ("Cookies", 5), ("Pie", 5)]),
        q("Name something people say on someone's birthday.", [("Happy birthday", 50), ("Make a wish", 20), ("How old are you", 15), ("Congrats", 8), ("Many more", 7)]),
        q("Name something you put on a birthday cake.", [("Candles", 40), ("Name", 25), ("Sprinkles", 15), ("Frosting", 10), ("Topper", 10)]),
        q("Name a kids birthday party theme.", [("Princess", 25), ("Dinosaurs", 25), ("Superheroes", 20), ("Animals", 15), ("Sports", 15)]),
        q("Name an adult birthday party theme.", [("Disco", 25), ("Casino", 25), ("Roaring 20s", 20), ("Tropical", 15), ("Black tie", 15)]),
        q("Name something people bring to a birthday party.", [("Gift", 35), ("Card", 25), ("Food", 20), ("Drinks", 10), ("Balloons", 10)]),
        q("Name a birthday party decoration.", [("Balloons", 40), ("Banner", 25), ("Streamers", 15), ("Confetti", 10), ("Centerpieces", 10)]),
        q("Name something people do before blowing candles.", [("Sing", 45), ("Make a wish", 25), ("Take photos", 15), ("Light candles", 10), ("Gather around", 5)]),
        q("Name a place to host a birthday.", [("House", 30), ("Restaurant", 25), ("Park", 20), ("Bowling alley", 15), ("Event venue", 10)]),
        q("Name a birthday gift people love.", [("Money", 30), ("Gift card", 25), ("Clothes", 20), ("Electronics", 15), ("Jewelry", 10)]),
        q("Name something found in a party bag.", [("Candy", 35), ("Toy", 25), ("Sticker", 20), ("Bubbles", 10), ("Crayon", 10)]),
        q("Name a birthday song besides Happy Birthday.", [("Celebration", 30), ("Birthday", 25), ("In Da Club", 20), ("Dancing Queen", 15), ("Party Rock", 10)]),
        q("Name something people do at milestone birthdays.", [("Toast", 30), ("Speech", 25), ("Video", 20), ("Photo slideshow", 15), ("Roast", 10)]),
        q("Name something on a birthday invitation.", [("Date", 30), ("Time", 25), ("Location", 20), ("Theme", 15), ("RSVP", 10)]),
        q("Name a birthday candle problem.", [("Won’t light", 30), ("Too many", 25), ("Wax drips", 20), ("Wind", 15), ("Forgot lighter", 10)]),
        q("Name something people take photos of.", [("Cake", 30), ("Birthday person", 25), ("Gifts", 20), ("Decor", 15), ("Group", 10)]),
        q("Name something a host forgets.", [("Candles", 30), ("Ice", 25), ("Plates", 20), ("Napkins", 15), ("Music", 10)]),
        q("Name something people eat with cake.", [("Ice cream", 45), ("Coffee", 20), ("Milk", 15), ("Fruit", 10), ("Nothing", 10)]),
    ], COMMON_FAST),
    "Holiday Party": build_pack([
        q("Name something people bring to a holiday party.", [("Dessert", 30), ("Wine", 25), ("Gift", 20), ("Side dish", 15), ("Cookies", 10)]),
        q("Name something you see at a holiday party.", [("Decorations", 35), ("Tree", 25), ("Lights", 20), ("Food", 10), ("Gifts", 10)]),
        q("Name a holiday party food.", [("Cookies", 30), ("Ham", 25), ("Turkey", 20), ("Pie", 15), ("Cheese board", 10)]),
        q("Name a holiday party activity.", [("Gift exchange", 35), ("Games", 25), ("Eating", 20), ("Singing", 10), ("Photos", 10)]),
        q("Name something people drink at a holiday party.", [("Wine", 30), ("Eggnog", 25), ("Hot cocoa", 20), ("Cocktails", 15), ("Cider", 10)]),
        q("Name a holiday decoration.", [("Lights", 35), ("Tree", 25), ("Wreath", 20), ("Ornaments", 10), ("Candles", 10)]),
        q("Name a white elephant gift.", [("Mug", 25), ("Candle", 25), ("Gift card", 20), ("Funny socks", 15), ("Blanket", 15)]),
        q("Name something people wear to a holiday party.", [("Sweater", 30), ("Dress", 25), ("Suit", 20), ("Santa hat", 15), ("Pajamas", 10)]),
        q("Name a holiday song.", [("Jingle Bells", 30), ("Mariah Carey", 25), ("Silent Night", 20), ("Frosty", 15), ("Rudolph", 10)]),
        q("Name something found on a holiday dessert table.", [("Cookies", 35), ("Pie", 25), ("Cake", 20), ("Candy", 10), ("Fudge", 10)]),
        q("Name something people complain about during holidays.", [("Traffic", 30), ("Shopping", 25), ("Money", 20), ("Family drama", 15), ("Weather", 10)]),
        q("Name a holiday party theme.", [("Ugly sweater", 35), ("Winter wonderland", 25), ("Pajama", 15), ("Cocktail", 15), ("Grinch", 10)]),
        q("Name something people wrap.", [("Gifts", 50), ("Baked goods", 20), ("Ornaments", 15), ("Cards", 10), ("Wine", 5)]),
        q("Name something a host runs out of.", [("Ice", 30), ("Drinks", 25), ("Food", 20), ("Plates", 15), ("Napkins", 10)]),
        q("Name a holiday smell.", [("Pine", 30), ("Cinnamon", 25), ("Cookies", 20), ("Vanilla", 15), ("Peppermint", 10)]),
        q("Name a holiday movie.", [("Elf", 30), ("Home Alone", 25), ("Christmas Vacation", 20), ("Grinch", 15), ("Polar Express", 10)]),
        q("Name something people exchange.", [("Gifts", 40), ("Cards", 25), ("Cookies", 15), ("Hugs", 10), ("Recipes", 10)]),
        q("Name a holiday party game.", [("White elephant", 35), ("Trivia", 25), ("Charades", 20), ("Bingo", 10), ("Name that tune", 10)]),
        q("Name something people do at midnight on New Year’s.", [("Kiss", 30), ("Toast", 25), ("Countdown", 20), ("Cheer", 15), ("Take photos", 10)]),
        q("Name something people clean up after holidays.", [("Wrapping paper", 30), ("Dishes", 25), ("Decor", 20), ("Trash", 15), ("Food", 10)]),
    ], COMMON_FAST),
}

# -----------------------------
# Question template
# -----------------------------

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

# -----------------------------
# State + persistence
# -----------------------------


def deep_copy(value):
    return json.loads(json.dumps(value))


def default_custom_theme():
    return THEMES["Custom"].copy()


def default_state():
    main_qs, fast_qs = preset_questions_for_theme("Classic Party")
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
        "match_question_number": 1,
        "questions_per_match": 3,
        "max_teams": 4,
        "revealed": [],
        "strike": False,
        "steal_mode": False,
        "questions": main_qs,
        "fast_money_questions": fast_qs,
        "google_sheet_url": "",
        "questions_source": "preset:Classic Party",
        "theme": "Classic Party",
        "custom_theme": default_custom_theme(),
        "theme_overrides": {},
        "title": "Survey Style Interactive Party Game",
        "subtitle": "Tournament Edition",
        "title_font": "Playfair Display",
        "body_font": "Cormorant Garamond",
        "title_size": 64,
        "subtitle_size": 24,
        "title_color": "#6E5873",
        "subtitle_color": "#A58BB7",
        "panel_color": "#FFFAF8",
        "panel_opacity": 0.20,
        "background_image": "",
        "background_mime": "image/png",
        "background_style": "Fill / Cover",
        "background_pattern_size": 220,
        "background_position": "Center",
        "background_brightness": 100,
        "background_blur": 0,
        "champion_team": "",
        "tournament_complete": False,
        "fast_money_started": False,
        "fast_money_start_time": 0,
        "fast_money_answers": {},
        "ended": False,
        "ended_reason": "",
        "ended_at": 0,
        "message": "Welcome! Create or join a team before the host starts the game.",
    }


def sanitize_game_code(raw_code):
    raw_code = str(raw_code or "").strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "-", raw_code).strip("-")


def has_game_code_in_url():
    return bool(sanitize_game_code(st.query_params.get("game", "")))


def get_game_code():
    return sanitize_game_code(st.query_params.get("game", DEFAULT_GAME_CODE)) or DEFAULT_GAME_CODE


def get_host_id():
    return sanitize_game_code(st.query_params.get("host", ""))


def generate_game_code():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(100):
        code = "".join(random.choice(alphabet) for _ in range(GAME_CODE_LENGTH)).lower()
        if not os.path.exists(os.path.join(SESSIONS_DIR, f"{code}.json")):
            return code
    return str(int(time.time()))


def generate_host_id():
    alphabet = string.ascii_lowercase + string.digits
    return "h" + "".join(random.choice(alphabet) for _ in range(10))


def get_state_file_for_code(game_code):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{sanitize_game_code(game_code)}.json")


def get_state_file():
    return get_state_file_for_code(get_game_code())


def get_lock_file_for_code(game_code):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{sanitize_game_code(game_code)}.lock")


def get_lock_file():
    return get_lock_file_for_code(get_game_code())


def get_host_index_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, HOSTS_FILE)


def get_host_index_lock_file():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, HOSTS_FILE + ".lock")


@contextmanager
def file_lock(lock_path):
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


@contextmanager
def state_file_lock():
    with file_lock(get_lock_file()):
        yield


@contextmanager
def host_index_lock():
    with file_lock(get_host_index_lock_file()):
        yield


def load_host_index_unlocked():
    index_file = get_host_index_file()
    if not os.path.exists(index_file):
        return {}
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_host_index_unlocked(index):
    index_file = get_host_index_file()
    directory = os.path.dirname(index_file) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="hosts_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        os.replace(temp_path, index_file)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def write_json_atomic(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="state_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def preset_questions_for_theme(theme_name):
    preset = EVENT_QUESTION_PRESETS.get(theme_name) or EVENT_QUESTION_PRESETS["Classic Party"]
    return deep_copy(preset["main"]), deep_copy(preset["fast_money"])


def apply_theme_question_preset(state, theme_name):
    main_qs, fast_qs = preset_questions_for_theme(theme_name)
    state["questions"] = main_qs
    state["fast_money_questions"] = fast_qs
    state["google_sheet_url"] = ""
    state["questions_source"] = f"preset:{theme_name}"
    state["current_question_index"] = 0
    state["match_question_number"] = 1
    reset_question_state(state)
    state["message"] = f"Loaded {theme_name} preset questions."


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
    if state.get("theme") not in THEMES:
        state["theme"] = "Classic Party"
    if not isinstance(state.get("custom_theme"), dict):
        state["custom_theme"] = default_custom_theme()
    if not isinstance(state.get("theme_overrides"), dict):
        state["theme_overrides"] = {}
    if state.get("title_font") not in FONT_OPTIONS:
        state["title_font"] = "Playfair Display"
    if state.get("body_font") not in FONT_OPTIONS:
        state["body_font"] = "Cormorant Garamond"
    if not state.get("questions"):
        state["questions"] = preset_questions_for_theme(state.get("theme", "Classic Party"))[0]
    if not state.get("fast_money_questions"):
        state["fast_money_questions"] = preset_questions_for_theme(state.get("theme", "Classic Party"))[1]

    # Clamp newer settings
    state["max_teams"] = int(max(2, min(20, int(state.get("max_teams", 4)))))
    state["questions_per_match"] = int(max(1, min(10, int(state.get("questions_per_match", 3)))))
    state["title_size"] = int(max(24, min(110, int(state.get("title_size", 64)))))
    state["subtitle_size"] = int(max(12, min(56, int(state.get("subtitle_size", 24)))))
    state["panel_opacity"] = float(max(0.05, min(0.95, float(state.get("panel_opacity", 0.20)))))
    return state


def load_state():
    state_file = get_state_file()
    with state_file_lock():
        if not os.path.exists(state_file):
            state = default_state()
            write_json_atomic(state_file, state)
            return state
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = default_state()
        state = migrate_state(state)
        write_json_atomic(state_file, state)
        return state


def save_state(state):
    with state_file_lock():
        write_json_atomic(get_state_file(), state)


def end_game_session(game_code, reason="A new game session was started by this host."):
    safe_code = sanitize_game_code(game_code)
    if not safe_code:
        return
    state_file = get_state_file_for_code(safe_code)
    if not os.path.exists(state_file):
        return
    with file_lock(get_lock_file_for_code(safe_code)):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                old_state = json.load(f)
        except Exception:
            old_state = default_state()
        old_state = migrate_state(old_state)
        old_state["ended"] = True
        old_state["ended_reason"] = reason
        old_state["ended_at"] = int(time.time())
        old_state["fast_money_started"] = False
        old_state["message"] = reason
        write_json_atomic(state_file, old_state)


def register_active_game_for_host(host_id, new_game_code):
    safe_host = sanitize_game_code(host_id)
    safe_game = sanitize_game_code(new_game_code)
    if not safe_host or not safe_game:
        return
    with host_index_lock():
        index = load_host_index_unlocked()
        previous_game = index.get(safe_host, {}).get("active_game")
        if previous_game and previous_game != safe_game:
            end_game_session(previous_game)
        index[safe_host] = {"active_game": safe_game, "updated_at": int(time.time())}
        save_host_index_unlocked(index)


def should_create_new_host_game():
    if st.query_params.get("view", "player") != "host":
        return False
    requested_code = sanitize_game_code(st.query_params.get("game", ""))
    wants_new_game = str(st.query_params.get("new", "")).lower() in {"1", "true", "yes"}
    return wants_new_game or not requested_code or requested_code == DEFAULT_GAME_CODE


def create_new_host_session():
    host_id = get_host_id() or generate_host_id()
    new_code = generate_game_code()
    register_active_game_for_host(host_id, new_code)
    st.query_params.clear()
    st.query_params["view"] = "host"
    st.query_params["game"] = new_code
    st.query_params["host"] = host_id


# -----------------------------
# Utility functions
# -----------------------------


def get_theme_colors(state):
    selected_theme = state.get("theme", "Classic Party")

    if selected_theme == "Custom":
        colors = default_custom_theme()
        colors.update(state.get("custom_theme", {}) if isinstance(state.get("custom_theme"), dict) else {})
    else:
        colors = THEMES.get(selected_theme, THEMES["Classic Party"]).copy()

    overrides = state.get("theme_overrides", {}) if isinstance(state.get("theme_overrides"), dict) else {}
    for key, value in overrides.items():
        if key in colors and value:
            colors[key] = value

    return colors


def hex_to_rgba(hex_color, alpha):
    hex_color = str(hex_color or "#FFFFFF").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "FFFFFF"
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except Exception:
        r, g, b = 255, 255, 255
    return f"rgba({r}, {g}, {b}, {alpha})"


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

    def build(source_df):
        out = []
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
                out.append({"question": str(question_text), "answers": answers})
        return out

    main_qs = build(df[df["game_type"] == "main"])
    fast_qs = build(df[df["game_type"] == "fast_money"])
    if not main_qs:
        raise ValueError("No main questions found. Use game_type = main.")
    if len(fast_qs) < 5:
        raise ValueError("Fast Money needs at least 5 questions with game_type = fast_money.")
    return main_qs, fast_qs[:5]


def load_questions_from_csv(csv_url):
    return build_questions_from_dataframe(pd.read_csv(csv_url))


def load_questions_from_upload(uploaded_file):
    return build_questions_from_dataframe(pd.read_csv(uploaded_file))


def encode_uploaded_image(uploaded_file):
    return base64.b64encode(uploaded_file.getvalue()).decode("utf-8"), uploaded_file.type or "image/png"


def build_initial_matches(team_names, max_teams):
    names = list(team_names)[:max_teams]
    matches = []
    for i in range(0, len(names), 2):
        if i + 1 < len(names):
            matches.append([names[i], names[i + 1]])
        else:
            matches.append([names[i], "BYE"])
    return matches


def set_active_match_from_index(state):
    if not state.get("matches"):
        state["active_teams"] = []
        return
    idx = state.get("current_match_index", 0)
    if idx >= len(state["matches"]):
        state["active_teams"] = []
        return
    match = state["matches"][idx]
    state["active_teams"] = match
    for team in match:
        if team != "BYE":
            state["match_scores"].setdefault(team, 0)
            state["total_scores"].setdefault(team, 0)


def reset_question_state(state):
    state["revealed"] = []
    state["round_bank"] = 0
    state["strike"] = False
    state["steal_mode"] = False


def current_question(state):
    questions = state.get("questions") or preset_questions_for_theme("Classic Party")[0]
    idx = state.get("current_question_index", 0)
    return questions[idx % len(questions)]


def award_bank(state, team):
    points = state.get("round_bank", 0)
    state["match_scores"][team] = state["match_scores"].get(team, 0) + points
    state["total_scores"][team] = state["total_scores"].get(team, 0) + points
    state["message"] = f"{team} wins {points} points!"
    state["round_bank"] = 0


def advance_question_in_match(state):
    if state.get("match_question_number", 1) < state.get("questions_per_match", 3):
        state["match_question_number"] += 1
        state["current_question_index"] += 1
        reset_question_state(state)
        state["message"] = "Next question."
    else:
        state["message"] = "This match has completed its questions. End the match to advance a winner."


def end_match_and_advance(state):
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
            state["message"] = "Tie game! Award points or use a tiebreaker before advancing."
            return
        winner = team_a if score_a > score_b else team_b
    state.setdefault("round_winners", []).append(winner)
    state["message"] = f"{winner} advances!"
    state["current_match_index"] += 1
    state["current_question_index"] += 1
    state["match_question_number"] = 1
    reset_question_state(state)

    if state["current_match_index"] >= len(state["matches"]):
        winners = state.get("round_winners", [])
        if len(winners) == 1:
            state["champion_team"] = winners[0]
            state["tournament_complete"] = True
            state["message"] = f"{winners[0]} wins the tournament! Fast Money is ready."
            state["matches"] = []
            state["active_teams"] = []
        else:
            state["matches"] = build_initial_matches(winners, len(winners))
            state["round_winners"] = []
            state["current_match_index"] = 0
            state["match_scores"] = {}
            set_active_match_from_index(state)
    else:
        set_active_match_from_index(state)


def score_fast_money_answers(state, answer_list):
    total = 0
    results = []
    fm_questions = (state.get("fast_money_questions") or COMMON_FAST)[:5]
    for idx, typed_answer in enumerate(answer_list):
        typed_answer = str(typed_answer).strip()
        result = {
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
                result.update(best)
                total += best["points"]
            elif best:
                result.update({"matched": best["matched"], "points": 0, "similarity": best["similarity"]})
        results.append(result)
    return total, results


def timer_remaining(state):
    if not state.get("fast_money_started"):
        return FAST_MONEY_SECONDS
    elapsed = int(time.time() - int(state.get("fast_money_start_time", 0)))
    return max(0, FAST_MONEY_SECONDS - elapsed)


# -----------------------------
# Layout + styling
# -----------------------------


def inject_css(state):
    theme = get_theme_colors(state)
    panel_rgba = hex_to_rgba(state.get("panel_color", theme["cream"]), state.get("panel_opacity", 0.20))
    title_size = int(state.get("title_size", 64))
    subtitle_size = int(state.get("subtitle_size", 24))
    title_font = FONT_OPTIONS.get(state.get("title_font"), FONT_OPTIONS["Playfair Display"])
    body_font = FONT_OPTIONS.get(state.get("body_font"), FONT_OPTIONS["Cormorant Garamond"])

    # Background designer settings
    background_style = state.get("background_style", "Fill / Cover")
    pattern_size = int(state.get("background_pattern_size", 220))
    position_map = {
        "Center": "center center",
        "Top": "center top",
        "Bottom": "center bottom",
        "Left": "left center",
        "Right": "right center",
    }
    bg_position = position_map.get(state.get("background_position", "Center"), "center center")
    bg_brightness = int(state.get("background_brightness", 100))
    bg_blur = int(state.get("background_blur", 0))

    if state.get("background_image"):
        bg_url = f"url('data:{state.get('background_mime', 'image/png')};base64,{state.get('background_image')}')"
        if background_style == "Fit / Contain":
            bg_size = "contain"
            bg_repeat = "no-repeat"
        elif background_style == "Repeat Pattern":
            bg_size = f"{pattern_size}px auto"
            bg_repeat = "repeat"
        elif background_style == "Repeat Horizontally":
            bg_size = f"{pattern_size}px auto"
            bg_repeat = "repeat-x"
        elif background_style == "Repeat Vertically":
            bg_size = f"{pattern_size}px auto"
            bg_repeat = "repeat-y"
        else:
            bg_size = "cover"
            bg_repeat = "no-repeat"
        background_css = f"""
            background-color: {theme['paper']} !important;
            background-image: {bg_url} !important;
            background-size: {bg_size} !important;
            background-repeat: {bg_repeat} !important;
            background-position: {bg_position} !important;
            background-attachment: fixed !important;
            filter: brightness({bg_brightness}%);
        """
    else:
        background_css = f"background: {theme['paper']} !important;"

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Cormorant+Garamond:wght@500;600;700&display=swap');

:root {{
    --paper: {theme['paper']};
    --cream: {theme['cream']};
    --plum: {theme['primary']};
    --lavender: {theme['secondary']};
    --soft-lavender: {theme['accent']};
    --border-lavender: {theme['border']};
    --dusty-rose: {theme['secondary']};
    --blush-pink: {theme['highlight']};
}}

html, body, .stApp {{
    min-height: 100vh;
    color: var(--plum) !important;
    font-family: {body_font} !important;
}}

.stApp {{
    background: {theme['paper']} !important;
}}

.stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    {background_css}
    transform: scale({1.03 if state.get("background_blur", 0) else 1});
}}

.stApp::after {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    backdrop-filter: blur({bg_blur}px);
}}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stVerticalBlock"] {{
    position: relative;
    z-index: 1;
}}

[data-testid="stAppViewContainer"],
[data-testid="stMain"] {{
    min-height: 100vh !important;
}}

/*
   Center panel layout:
   The transparent panel is a full-height layer behind the content.
   This avoids Streamlit shrinking the panel to only the content height.
*/
[data-testid="stMain"] {{
    display: block !important;
    position: relative !important;
    overflow: visible !important;
}}

[data-testid="stMain"]::before {{
    content: "";
    position: fixed;
    top: 0;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: min(1120px, calc(100vw - 4rem));
    height: 100vh;
    background: {panel_rgba};
    box-shadow: 0 0 35px rgba(0,0,0,0.08);
    pointer-events: none;
    z-index: 1;
}}

.main .block-container,
[data-testid="stMainBlockContainer"] {{
    position: relative;
    z-index: 2;
    width: min(1120px, calc(100vw - 4rem)) !important;
    max-width: min(1120px, calc(100vw - 4rem)) !important;
    min-height: 100vh !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding: 2.5rem 3rem 5rem 3rem !important;
    background: transparent !important;
    box-shadow: none !important;
    box-sizing: border-box !important;
}}

/* Make long host controls scrollable */
section[data-testid="stSidebar"] {{
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
}}

section[data-testid="stSidebar"] > div:first-child,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    height: 100vh !important;
    max-height: 100vh !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    padding-bottom: 5rem !important;
}}

@media (max-width: 900px) {{
    [data-testid="stMain"]::before {{
        width: 100% !important;
    }}

    .main .block-container,
    [data-testid="stMainBlockContainer"] {{
        width: 100% !important;
        max-width: 100% !important;
        min-height: 100vh !important;
        padding: 1.5rem 1rem 4rem 1rem !important;
    }}
}}

* {{ color: var(--plum); }}

.main-title {{
    font-family: {title_font};
    font-size: clamp(24px, 5vw, {title_size}px);
    line-height: 1.05;
    text-align: center;
    font-weight: 800;
    color: {state.get('title_color', theme['primary'])} !important;
    margin: 10px auto 4px auto;
    letter-spacing: 1px;
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
}}

.subtitle {{
    text-align: center;
    font-size: clamp(14px, 2.2vw, {subtitle_size}px);
    color: {state.get('subtitle_color', theme['secondary'])} !important;
    margin-bottom: 24px;
    letter-spacing: 0.5px;
}}

.question-card {{
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 28px;
    padding: 28px;
    margin: 20px 0 24px 0;
    font-size: clamp(24px, 3.5vw, 40px);
    font-weight: 700;
    text-align: center;
    color: var(--plum) !important;
    box-shadow: 0 10px 30px rgba(0,0,0, 0.10);
}}

.answer-tile {{
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 22px;
    padding: 18px 22px;
    margin-bottom: 14px;
    color: var(--plum) !important;
    font-size: clamp(20px, 2.8vw, 30px);
    font-weight: 700;
    display: flex;
    justify-content: space-between;
    gap: 20px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.08);
}}

.answer-hidden {{
    color: var(--blush-pink) !important;
    text-align: center;
    justify-content: center;
    font-weight: 700;
}}

.score-card, .bracket-card, .info-card {{
    background: var(--cream);
    border: 2px solid var(--border-lavender);
    border-radius: 22px;
    padding: 18px;
    margin-bottom: 12px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    color: var(--plum) !important;
}}

.score-number {{
    font-family: {title_font};
    font-size: 42px;
    font-weight: 800;
    color: var(--dusty-rose) !important;
}}

.message {{
    text-align: center;
    font-size: 24px;
    font-weight: 700;
    color: var(--dusty-rose) !important;
    margin: 18px 0;
}}

.small-note {{
    font-size: 18px;
    color: var(--lavender) !important;
}}

.stButton button {{
    background: var(--soft-lavender) !important;
    color: var(--plum) !important;
    border: 1px solid var(--border-lavender) !important;
    border-radius: 14px !important;
    font-family: {body_font} !important;
    font-size: 18px !important;
    font-weight: 700 !important;
}}

section[data-testid="stSidebar"] {{ background: {theme['sidebar']} !important; }}
section[data-testid="stSidebar"] * {{ color: var(--plum) !important; }}

input, textarea, select {{ color: var(--plum) !important; background: #FFFFFF !important; }}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div,
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {{
    background: #FFFFFF !important;
    color: var(--plum) !important;
}}

[data-testid="stMetricValue"] {{ color: var(--dusty-rose) !important; }}
</style>
""", unsafe_allow_html=True)


def render_header(state):
    title = str(state.get("title", "Survey Style Interactive Party Game"))
    subtitle = str(state.get("subtitle", "Tournament Edition"))
    st.markdown(f'<div class="main-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_answer_board(state):
    question = current_question(state)
    st.markdown(f'<div class="question-card">{question["question"]}</div>', unsafe_allow_html=True)
    for idx, (answer, points) in enumerate(question["answers"]):
        if idx in state.get("revealed", []):
            st.markdown(f'<div class="answer-tile"><span>{idx + 1}. {answer}</span><span>{points}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="answer-tile answer-hidden">{idx + 1}</div>', unsafe_allow_html=True)


def render_scoreboard(state):
    teams = [t for t in state.get("active_teams", []) if t != "BYE"]
    if not teams:
        return
    cols = st.columns(len(teams) + 1)
    for idx, team in enumerate(teams):
        cols[idx].markdown(f"""
        <div class="score-card">
            <div>{team}</div>
            <div class="score-number">{state['match_scores'].get(team, 0)}</div>
            <div class="small-note">match points</div>
        </div>
        """, unsafe_allow_html=True)
    cols[-1].markdown(f"""
    <div class="score-card">
        <div>Round Bank</div>
        <div class="score-number">{state.get('round_bank', 0)}</div>
        <div class="small-note">Q {state.get('match_question_number', 1)}/{state.get('questions_per_match', 3)}</div>
    </div>
    """, unsafe_allow_html=True)


def render_bracket(state):
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
        st.markdown(f'<div class="bracket-card"><strong>{label}</strong><br>{team_a} vs {team_b}</div>', unsafe_allow_html=True)


# -----------------------------
# Boot session
# -----------------------------

if should_create_new_host_game():
    create_new_host_session()
    st.rerun()

if st.query_params.get("view", "player") == "host" and has_game_code_in_url() and not get_host_id():
    st.query_params["host"] = generate_host_id()
    register_active_game_for_host(st.query_params["host"], get_game_code())
    st.rerun()

state = load_state()
inject_css(state)
render_header(state)

view = st.query_params.get("view", "player")
page = st.query_params.get("page", "main")
game_code = get_game_code()
has_game_code = has_game_code_in_url()

# -----------------------------
# Session header / join screen
# -----------------------------

if view == "host":
    player_url = f"?view=player&game={game_code}"
    st.markdown(f"""
    <div class="info-card">
        <strong>Game Code:</strong> {game_code.upper()}<br>
        <span class="small-note"><a href="{player_url}" target="_self">Open player join page</a></span>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Start New Game Session"):
        create_new_host_session()
        st.rerun()
elif not has_game_code:
    ended_notice = st.session_state.pop("ended_session_notice", "")
    if ended_notice:
        st.warning(ended_notice)
    st.markdown('<div class="info-card">Enter the game code from your host to join.</div>', unsafe_allow_html=True)
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
    st.markdown(f'<div class="info-card"><strong>Game Code:</strong> {game_code.upper()}</div>', unsafe_allow_html=True)

if state.get("ended"):
    ended_reason = state.get("ended_reason") or "This game session has ended because the host started a new session."
    if view == "player":
        st.session_state["ended_session_notice"] = ended_reason
        st.query_params.clear()
        st.query_params["view"] = "player"
        st.rerun()
    st.warning(ended_reason)
    if view == "host" and st.button("Create Another New Session"):
        create_new_host_session()
        st.rerun()
    st.stop()

if page == "bracket":
    render_bracket(state)
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
        can_create_team = len(existing_teams) < int(state.get("max_teams", 4))
        team_options = existing_teams + (["Create new team"] if can_create_team else [])
        team_choice = st.selectbox("Join a team", team_options if team_options else ["Create new team"])
        new_team_name = ""
        if team_choice == "Create new team":
            if not can_create_team and existing_teams:
                st.warning("Team limit reached. Join an existing team.")
            else:
                new_team_name = st.text_input("New team name")
        if st.button("Sign In"):
            name = player_name.strip()
            team = new_team_name.strip() if team_choice == "Create new team" else team_choice
            if not name:
                st.error("Enter your name.")
            elif not team:
                st.error("Enter or select a team name.")
            else:
                state = load_state()
                if team not in state["teams"] and len(state["teams"]) >= int(state.get("max_teams", 4)):
                    st.error("Team limit reached. Join an existing team.")
                else:
                    state["teams"].setdefault(team, [])
                    if name not in state["teams"][team]:
                        state["teams"][team].append(name)
                    save_state(state)
                    st.success(f"You are signed in as {name} on {team}.")
                    st.rerun()
        if state.get("teams"):
            st.subheader(f"Signed-In Teams ({len(state['teams'])}/{state.get('max_teams', 4)})")
            for team, players in state["teams"].items():
                st.markdown(f'<div class="info-card"><strong>{team}</strong><br>{", ".join(players) if players else "No players yet"}</div>', unsafe_allow_html=True)
    else:
        st.success("Teams are locked. Game is in progress!")
        render_scoreboard(state)
        render_answer_board(state)
        if state.get("strike"):
            st.markdown('<div class="message">Strike! The other team may steal.</div>', unsafe_allow_html=True)
        if state.get("message"):
            st.markdown(f'<div class="message">{state["message"]}</div>', unsafe_allow_html=True)

    if state.get("champion_team"):
        st.divider()
        st.header("Fast Money: Individual Championship")
        champion = state["champion_team"]
        st.markdown(f'<div class="info-card">Only players on <strong>{champion}</strong> are eligible. Everyone on the winning team answers at the same time.</div>', unsafe_allow_html=True)
        eligible_players = state.get("teams", {}).get(champion, [])
        player = st.selectbox("Sign in as", [""] + eligible_players)
        if not state.get("fast_money_started"):
            st.info("Waiting for the host to start the Fast Money timer.")
        else:
            remaining = timer_remaining(state)
            st.metric("Time Remaining", f"{remaining}s")
            st.progress(remaining / FAST_MONEY_SECONDS)
            already_submitted = player in state.get("fast_money_answers", {})
            if not player:
                st.warning("Select your name to begin.")
            elif already_submitted:
                st.success(f"Submitted! Your score: {state['fast_money_answers'][player]['score']}")
            elif remaining <= 0:
                st.error("Time is up.")
            else:
                answers = []
                for idx, fm_q in enumerate(state.get("fast_money_questions", COMMON_FAST)[:5]):
                    answers.append(st.text_input(f"{idx + 1}. {fm_q['question']}", key=f"fm_answer_{idx}_{player}"))
                if st.button("Submit Fast Money Answers"):
                    score, results = score_fast_money_answers(state, answers)
                    state = load_state()
                    state.setdefault("fast_money_answers", {})[player] = {"team": champion, "score": score, "answers": answers, "results": results}
                    save_state(state)
                    st.success(f"Submitted! Your score: {score}")
                    st.rerun()
        if state.get("fast_money_answers"):
            st.subheader("Fast Money Leaderboard")
            leaderboard = sorted(state["fast_money_answers"].items(), key=lambda item: item[1].get("score", 0), reverse=True)
            for rank, (player_name, data) in enumerate(leaderboard, start=1):
                st.markdown(f'<div class="score-card"><strong>#{rank} {player_name}</strong><br>{data.get("score", 0)} points</div>', unsafe_allow_html=True)

# -----------------------------
# Host View
# -----------------------------

if view == "host":
    st.sidebar.header("Host Controls")

    # 1) Pick the event/theme first. This sets the overall look and loads matching questions.
    with st.sidebar.expander("1. Event Theme + Preset Questions", expanded=True):
        theme_names = list(THEMES.keys())
        current_theme = state.get("theme", "Classic Party") if state.get("theme", "Classic Party") in theme_names else "Classic Party"
        selected_theme = st.selectbox("Event Theme", theme_names, index=theme_names.index(current_theme))

        if selected_theme != state.get("theme"):
            state["theme"] = selected_theme
            state["theme_overrides"] = {}
            selected_colors = THEMES.get(selected_theme, THEMES["Classic Party"])

            # Auto-match font colors to the selected event theme.
            # Hosts can override these later in Branding + Layout.
            state["title_color"] = selected_colors["primary"]
            state["subtitle_color"] = selected_colors["secondary"]

            if selected_theme != "Custom":
                apply_theme_question_preset(state, selected_theme)
            save_state(state)
            st.rerun()

        st.caption("Choose an event theme as your starting point. You can customize colors and fonts in Branding + Layout without switching to Custom.")
        if selected_theme != "Custom":
            if st.button("Reload Preset Questions for This Event"):
                apply_theme_question_preset(state, selected_theme)
                save_state(state)
                st.rerun()
        st.caption(f"Questions: {state.get('questions_source', 'unknown')}")

    # 2) Set game size before teams join/lock.
    with st.sidebar.expander("2. Game Setup", expanded=True):
        max_teams = st.number_input("Number of Teams Playing", min_value=2, max_value=20, value=int(state.get("max_teams", 4)), step=1, disabled=state.get("locked", False))
        q_per_match = st.number_input("Questions per Match", min_value=1, max_value=10, value=int(state.get("questions_per_match", 3)), step=1, disabled=state.get("locked", False))
        if state.get("locked", False):
            st.caption("Unlock teams to change these settings.")
        if not state.get("locked") and (max_teams != state.get("max_teams") or q_per_match != state.get("questions_per_match")):
            state["max_teams"] = int(max_teams)
            state["questions_per_match"] = int(q_per_match)
            save_state(state)
            st.rerun()

    # 3) Optional branding overrides after the preset has been chosen.
    with st.sidebar.expander("3. Branding + Layout", expanded=True):
        theme_colors = get_theme_colors(state)
        new_title = st.text_input("Game Title", value=state.get("title", "Survey Style Interactive Party Game"))
        new_subtitle = st.text_input("Subtitle", value=state.get("subtitle", "Tournament Edition"))
        title_size = st.slider("Title Size", 24, 110, int(state.get("title_size", 64)))
        subtitle_size = st.slider("Subtitle Size", 12, 56, int(state.get("subtitle_size", 24)))
        font_names = list(FONT_OPTIONS.keys())
        title_font = st.selectbox(
            "Title Font",
            font_names,
            index=font_names.index(state.get("title_font", "Playfair Display"))
            if state.get("title_font", "Playfair Display") in FONT_OPTIONS else 0,
        )
        body_font = st.selectbox(
            "Body Font",
            font_names,
            index=font_names.index(state.get("body_font", "Cormorant Garamond"))
            if state.get("body_font", "Cormorant Garamond") in FONT_OPTIONS else 1,
        )
        title_color = st.color_picker("Title Color", state.get("title_color", theme_colors["primary"]))
        subtitle_color = st.color_picker("Subtitle Color", state.get("subtitle_color", theme_colors["secondary"]))
        panel_color = st.color_picker("Center Panel Color", state.get("panel_color", theme_colors["cream"]))
        panel_opacity = st.slider("Center Panel Opacity", 5, 95, int(float(state.get("panel_opacity", 0.20)) * 100)) / 100

        st.markdown("**Theme Colors**")
        if state.get("theme") == "Custom":
            base_theme = default_custom_theme()
            base_theme.update(state.get("custom_theme", {}) if isinstance(state.get("custom_theme"), dict) else {})
        else:
            base_theme = THEMES.get(state.get("theme", "Classic Party"), THEMES["Classic Party"]).copy()
        overrides = state.get("theme_overrides", {}) if isinstance(state.get("theme_overrides"), dict) else {}
        new_overrides = {}
        for label, key in THEME_COLOR_FIELDS:
            new_overrides[key] = st.color_picker(
                label,
                overrides.get(key, base_theme.get(key, "#FFFFFF")),
                key=f"theme_override_{key}",
            )

        st.markdown("**Background Designer**")
        bg_upload = st.file_uploader("Upload Background Image", type=["png", "jpg", "jpeg", "webp"])
        background_style = st.selectbox(
            "Background Style",
            ["Fill / Cover", "Fit / Contain", "Repeat Pattern", "Repeat Horizontally", "Repeat Vertically"],
            index=["Fill / Cover", "Fit / Contain", "Repeat Pattern", "Repeat Horizontally", "Repeat Vertically"].index(state.get("background_style", "Fill / Cover"))
            if state.get("background_style", "Fill / Cover") in ["Fill / Cover", "Fit / Contain", "Repeat Pattern", "Repeat Horizontally", "Repeat Vertically"] else 0,
            help="Use Fill for photos, Fit for illustrations, and Repeat Pattern for seamless backgrounds or icon patterns.",
        )
        pattern_size = st.slider("Pattern / Image Scale", 40, 700, int(state.get("background_pattern_size", 220)), 10)
        bg_position = st.selectbox(
            "Background Position",
            ["Center", "Top", "Bottom", "Left", "Right"],
            index=["Center", "Top", "Bottom", "Left", "Right"].index(state.get("background_position", "Center"))
            if state.get("background_position", "Center") in ["Center", "Top", "Bottom", "Left", "Right"] else 0,
        )
        bg_brightness = st.slider("Background Brightness", 30, 130, int(state.get("background_brightness", 100)), 5)
        bg_blur = st.slider("Background Blur", 0, 12, int(state.get("background_blur", 0)), 1)

        changed = False
        for key, value in {
            "title": new_title,
            "subtitle": new_subtitle,
            "title_font": title_font,
            "body_font": body_font,
            "title_size": title_size,
            "subtitle_size": subtitle_size,
            "title_color": title_color,
            "subtitle_color": subtitle_color,
            "panel_color": panel_color,
            "panel_opacity": panel_opacity,
            "theme_overrides": new_overrides,
            "background_style": background_style,
            "background_pattern_size": pattern_size,
            "background_position": bg_position,
            "background_brightness": bg_brightness,
            "background_blur": bg_blur,
        }.items():
            if state.get(key) != value:
                state[key] = value
                changed = True

        if bg_upload is not None:
            encoded, mime = encode_uploaded_image(bg_upload)
            state["background_image"] = encoded
            state["background_mime"] = mime
            changed = True

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Use Theme Font Colors"):
                state["title_color"] = theme_colors["primary"]
                state["subtitle_color"] = theme_colors["secondary"]
                changed = True
        with col_b:
            if st.button("Reset Colors to Selected Theme"):
                state["theme_overrides"] = {}
                reset_colors = THEMES.get(state.get("theme", "Classic Party"), THEMES["Classic Party"])
                state["title_color"] = reset_colors["primary"]
                state["subtitle_color"] = reset_colors["secondary"]
                state["panel_color"] = reset_colors["cream"]
                changed = True

        if state.get("background_image") and st.button("Remove Background"):
            state["background_image"] = ""
            state["background_mime"] = "image/png"
            changed = True

        if changed:
            save_state(state)
            st.rerun()

    # 4) Bring your own questions, if desired.
    with st.sidebar.expander("4. Custom Questions", expanded=False):
        st.caption("Required columns: game_type, question, answer, points. Use game_type values main or fast_money.")
        st.download_button("Download Question Template", data=question_template_csv(), file_name="survey_game_question_template.csv", mime="text/csv")
        uploaded_questions = st.file_uploader("Upload completed CSV template", type=["csv"])
        if uploaded_questions is not None and st.button("Load Uploaded Questions"):
            try:
                main_qs, fast_qs = load_questions_from_upload(uploaded_questions)
                state["questions"] = main_qs
                state["fast_money_questions"] = fast_qs
                state["google_sheet_url"] = ""
                state["questions_source"] = "uploaded CSV"
                state["current_question_index"] = 0
                state["match_question_number"] = 1
                reset_question_state(state)
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
                state["match_question_number"] = 1
                reset_question_state(state)
                save_state(state)
                st.success(f"Loaded {len(main_qs)} main questions and {len(fast_qs)} Fast Money questions from URL.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not load questions from URL: {error}")

    # 5) Review questions after choosing a theme or uploading custom questions.
    with st.sidebar.expander("5. Questions Preview", expanded=False):
        st.write(f"Main Questions: {len(state.get('questions', []))}")
        for i, item in enumerate(state.get("questions", []), start=1):
            with st.expander(f"{i}. {item.get('question', '')[:45]}"):
                for answer, points in item.get("answers", []):
                    st.write(f"• {answer} — {points}")
        st.write(f"Fast Money Questions: {len(state.get('fast_money_questions', []))}")
        for i, item in enumerate(state.get("fast_money_questions", []), start=1):
            st.caption(f"{i}. {item.get('question', '')}")

    # 6) Lock teams and run the bracket.
    with st.sidebar.expander("6. Teams + Bracket", expanded=True):
        st.write(f"Teams signed up: {len(state.get('teams', {}))}/{state.get('max_teams', 4)}")
        if not state.get("locked"):
            if st.button("Lock Teams + Build Bracket"):
                if len(state.get("teams", {})) < 2:
                    st.error("You need at least 2 teams to play.")
                else:
                    state["locked"] = True
                    selected_team_names = list(state["teams"].keys())[:int(state.get("max_teams", 4))]
                    state["matches"] = build_initial_matches(selected_team_names, int(state.get("max_teams", 4)))
                    state["current_match_index"] = 0
                    state["round_winners"] = []
                    state["match_scores"] = {}
                    state["total_scores"] = {team: 0 for team in selected_team_names}
                    state["tournament_complete"] = False
                    state["champion_team"] = ""
                    state["fast_money_started"] = False
                    state["fast_money_answers"] = {}
                    state["match_question_number"] = 1
                    reset_question_state(state)
                    set_active_match_from_index(state)
                    save_state(state)
                    st.rerun()
        else:
            if st.button("Unlock Teams"):
                state["locked"] = False
                save_state(state)
                st.rerun()

    render_bracket(state)

    if state.get("locked") and not state.get("tournament_complete"):
        render_scoreboard(state)
        render_answer_board(state)
        q_cur = current_question(state)
        st.sidebar.subheader("Reveal Answers")
        for idx, (answer, points) in enumerate(q_cur["answers"]):
            if st.sidebar.button(f"Reveal {idx + 1}: {answer} ({points})"):
                if idx not in state["revealed"]:
                    state["revealed"].append(idx)
                    state["round_bank"] += int(points)
                    state["message"] = f"{answer} is on the board!"
                    save_state(state)
                    st.rerun()
        active = [t for t in state.get("active_teams", []) if t != "BYE"]
        st.sidebar.subheader("Award / Steal")
        for team in active:
            if st.sidebar.button(f"Award Bank to {team}"):
                award_bank(state, team)
                save_state(state)
                st.rerun()
        if st.sidebar.button("1 Strike → Enable Steal"):
            state["strike"] = True
            state["steal_mode"] = True
            state["message"] = "Strike! The other team gets one chance to steal."
            save_state(state)
            st.rerun()
        st.sidebar.subheader("Match Flow")
        if st.sidebar.button("Next Question in Match"):
            advance_question_in_match(state)
            save_state(state)
            st.rerun()
        if st.sidebar.button("End Match / Auto-Advance Winner"):
            end_match_and_advance(state)
            save_state(state)
            st.rerun()
        if st.sidebar.button("Reset Current Question"):
            reset_question_state(state)
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
            remaining = timer_remaining(state)
            st.metric("Fast Money Time Remaining", f"{remaining}s")
            st.progress(remaining / FAST_MONEY_SECONDS)
            if st.button("Restart Fast Money Timer"):
                state["fast_money_start_time"] = int(time.time())
                state["fast_money_answers"] = {}
                save_state(state)
                st.rerun()
        if state.get("fast_money_answers"):
            st.subheader("Leaderboard")
            leaderboard = sorted(state["fast_money_answers"].items(), key=lambda item: item[1].get("score", 0), reverse=True)
            for rank, (player_name, data) in enumerate(leaderboard, start=1):
                st.markdown(f'<div class="score-card"><strong>#{rank} {player_name}</strong><br>{data.get("score", 0)} points</div>', unsafe_allow_html=True)
                with st.expander(f"See {player_name}'s answer matches"):
                    for result in data.get("results", []):
                        st.write(f"{result.get('question')}: typed '{result.get('typed')}' → matched '{result.get('matched')}' ({result.get('similarity')}%) = {result.get('points')} pts")

    st.sidebar.divider()
    if st.sidebar.button("Reset Entire Game"):
        save_state(default_state())
        st.rerun()
