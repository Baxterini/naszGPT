# app.py — NaszGPT v1.3 (czat z osobowościami, historia, koszt, klucz w UI)
# ----------------------------------------------------------------------------
# Funkcje:
# - Sidebar: wybór osobowości, modelu, pole na OPENAI_API_KEY (opcjonalnie fallback do st.secrets)
# - Czat: historia (st.session_state), reset, zapisywanie/ładowanie rozmów (JSON)
# - Koszt: zliczanie tokenów i szacowanie kosztu per model na podstawie usage z API
# - Kolorowe tło (gradient) i lekki tuning UI + top-toolbar (poziomo)
# ----------------------------------------------------------------------------

import json
import time
from typing import Dict, List

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # fallback: UI zadziała nawet bez zainstalowanego pakietu

# ----------------------- KONFIGURACJA STRONY -----------------------
st.set_page_config(page_title="NaszGPT — czat z osobowościami", page_icon="🧠", layout="wide")

# ----------------------- STYLING / CSS -----------------------------
st.markdown(
    """
    <style>
      .stApp {
        background: linear-gradient(135deg, #9be7ff 0%, #d0b3ff 50%, #ffd1dc 100%) fixed !important;
      }
      /* Karty czatu delikatnie przezroczyste */
      [data-testid="stChatMessage"]>div{
        background: rgba(255,255,255,0.75) !important;
        border-radius: 16px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08) !important;
      }
      .cost-pill {
        display:inline-block; padding:6px 10px; border-radius:999px; background:rgba(0,0,0,0.08);
        font-size:12px; margin-left:8px;
      }
      .center { display:flex; gap:8px; align-items:center; }

      /* >>> Toolbar (przyciski Reset / Wczytaj / Zapisz u góry) <<< */
      .toolbar {
        display: flex;
        gap: .5rem;
        flex-wrap: wrap;
        align-items: stretch;
        margin-bottom: .75rem;
      }
      .toolbar .stButton > button {
        width: 100%;
        border-radius: 12px;
        padding: .6rem .9rem;
        font-weight: 600;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------- STAN -----------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("show_loader", False)   # pokazuj expander z uploadem JSON
st.session_state.setdefault("last_action", None)
st.session_state.setdefault("total_prompt_tokens", 0)
st.session_state.setdefault("total_completion_tokens", 0)

# ----------------------- OSOBOWOŚCI -----------------------
PERSONALITIES: Dict[str, str] = {
    "🧘 Zen Mistrz": (
        "Mów spokojnie, powoli i obrazowo. Używaj metafor natury: rzeki, chmur, lasu. "
        "Dawaj proste ćwiczenia oddechowe i krótkie sentencje jak koany. "
        "Unikaj długich wykładów – każde zdanie jak mądrość z klasztoru zen."
    ),
    "🎭 Szalony Stand-uper": (
        "Bądź błyskotliwy i zabawny. Żarty sytuacyjne, gra słowem, trochę absurdu. "
        "Każda odpowiedź to mini-show: lekki roast, riposta, humor – ale nadal pomocny."
    ),
    "💼 Business Pro": (
        "Mów jak konsultant biznesowy. Zwięźle, konkretnie, w punktach. "
        "Skup się na KPI, ryzykach, wariantach i next steps. Profesjonalny ton + pewność."
    ),
    "🎩 Gangster z lat 30.": (
        "Noir, klimat retro. Żargon: 'słuchaj, chłopaczku', 'interes życia', 'prosto z portu'. "
        "Brzmisz jak z filmu gangsterskiego przy maszynie do pisania. Bez przemocy i wulgaryzmów."
    ),
    "🐸 Sceptyczna Żaba": (
        "Zgryźliwy, sceptyczny, ironiczny płaz. Zadawaj podchwytliwe pytania, "
        "wytykaj dziury w logice, dawaj kontrprzykłady. Kąśliwie zabawny, nie agresywny."
    ),
    "🧔‍♂️ Sokrates": (
        "Metoda majeutyczna. Odpowiadaj głównie pytaniami naprowadzającymi. "
        "Prowadź do samodzielnego wniosku, spokojnie i refleksyjnie."
    ),
    "🧒 Tryb dziecięcy": (
        "Bardzo prosto i obrazowo, przykłady z bajek i życia codziennego. "
        "Krótkie zdania, ciepły ton, dużo zachęty i empatii."
    ),
    "🧠 Trener mentalny": (
        "Motywuj konkretnie. Narzędzia psychologiczne, zadania i mini-cele. "
        "Podkreślaj mocne strony, wskazuj kierunki poprawy, dawaj plan działania."
    ),
}

DEFAULT_SYSTEM = "Jesteś NaszGPT — asystentem rozmownym. Odpowiadasz po polsku, zwięźle i jasno."

# Szacunkowe stawki (USD / 1K tokenów) — dostosuj do swoich realnych stawek
MODEL_PRICES = {
    "gpt-4o-mini": (0.150, 0.600),
    "gpt-4o":      (5.000, 15.000),
}

# Domyślne wybory
st.session_state.setdefault("personality", list(PERSONALITIES.keys())[0])
st.session_state.setdefault("model", "gpt-4o-mini")

# ----------------------- SIDEBAR (USTAWIENIA) -----------------------
st.sidebar.header("⚙️ Ustawienia")

api_key_input = st.sidebar.text_input("🔑 OPENAI_API_KEY (opcjonalnie)", type="password")
use_secrets = st.sidebar.toggle('Użyj st.secrets["OPENAI_API_KEY"] jeśli brak powyżej', value=True)

st.session_state.personality = st.sidebar.selectbox(
    "🧩 Osobowość",
    list(PERSONALITIES.keys()),
    index=list(PERSONALITIES.keys()).index(st.session_state.personality),
)

st.session_state.model = st.sidebar.selectbox(
    "🧪 Model",
    list(MODEL_PRICES.keys()),
    index=list(MODEL_PRICES.keys()).index(st.session_state.model),
)

# ----------------------- TOP TOOLBAR (POZIOMO) -----------------------
st.markdown('<div class="toolbar">', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    reset = st.button("🔄 Reset czatu", use_container_width=True)
with col2:
    load_json = st.button("📂 Wczytaj JSON", use_container_width=True)
with col3:
    save_json = st.button("💾 Zapisz JSON", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# ----------------------- AKCJE TOOLBARA -----------------------
if reset:
    st.session_state["messages"] = []
    st.session_state["total_prompt_tokens"] = 0
    st.session_state["total_completion_tokens"] = 0
    st.session_state["show_loader"] = False
    st.session_state["last_action"] = "reset"
    st.success("Czat zresetowany ✅")

if load_json:
    st.session_state["show_loader"] = True
    st.session_state["last_action"] = "load"

if save_json:
    payload = {
        "messages": st.session_state["messages"],
        "total_prompt_tokens": st.session_state["total_prompt_tokens"],
        "total_completion_tokens": st.session_state["total_completion_tokens"],
        "personality": st.session_state["personality"],
        "model": st.session_state["model"],
        "ts": int(time.time()),
    }
    st.session_state["last_action"] = "save"
    with st.container():
        st.download_button(
            "Pobierz chat (JSON)",
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="naszgpt_chat.json",
            mime="application/json",
            use_container_width=True,
            key=f"download-json-{int(time.time())}",
        )
    st.toast("Gotowy plik do pobrania ✅", icon="💾")

# Sekcja do wczytania historii pojawia się po kliknięciu "Wczytaj JSON"
if st.session_state["show_loader"]:
    with st.expander("📂 Wczytaj historię z pliku JSON", expanded=True):
        up = st.file_uploader("Wybierz plik .json", type=["json"])
        if up is not None:
            try:
                data = json.load(up)
                if isinstance(data, dict) and "messages" in data:
                    st.session_state["messages"] = data.get("messages", [])
                    st.session_state["total_prompt_tokens"] = data.get("total_prompt_tokens", 0)
                    st.session_state["total_completion_tokens"] = data.get("total_completion_tokens", 0)
                    st.session_state["personality"] = data.get("personality", st.session_state["personality"])
                    st.session_state["model"] = data.get("model", st.session_state["model"])
                elif isinstance(data, list):
                    st.session_state["messages"] = data
                else:
                    st.warning("Plik JSON w nieoczekiwanym formacie — wczytałem tylko to, co się dało.")
                st.success("Wczytano historię ✅")
                st.session_state["show_loader"] = False
            except Exception as e:
                st.error(f"Nie udało się wczytać: {e}")

# ----------------------- NAGŁÓWEK I KOSZT -----------------------
st.title("🧠 NaszGPT — czat z osobowościami")

pp, pc = MODEL_PRICES[st.session_state.model]
cost = (st.session_state.total_prompt_tokens / 1000.0) * pp + (
    st.session_state.total_completion_tokens / 1000.0
) * pc

st.markdown(
    f"**Model:** `{st.session_state.model}`  "
    f"<span class='cost-pill'>Szac. koszt: ${cost:.4f}</span>",
    unsafe_allow_html=True,
)

st.write("Rozmawiaj z różnymi stylami. Z lewej ustaw osobowość i model. Klucz API wprowadź w sidebarze lub użyj `st.secrets`.")

# ----------------------- RENDER HISTORII -----------------------
for m in st.session_state.messages:
    with st.chat_message(m.get("role", "assistant")):
        st.markdown(m.get("content", ""))

# ----------------------- POBIERZ KLUCZ -----------------------
api_key = (api_key_input or "").strip() or None
missing_secrets = False
if not api_key and use_secrets:
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
        if not api_key:
            missing_secrets = True
    except FileNotFoundError:
        api_key = None
        missing_secrets = True

if missing_secrets:
    st.sidebar.warning(
        "Włączono użycie st.secrets, ale nie znaleziono `OPENAI_API_KEY`. "
        "Podaj klucz w polu wyżej albo utwórz `.streamlit/secrets.toml`."
    )

# ----------------------- WYWOŁANIE OPENAI -----------------------
def call_openai_chat(messages: List[Dict], model: str, api_key: str):
    if OpenAI is None:
        raise RuntimeError("Brak biblioteki 'openai' (>=1.0). Zainstaluj pakiet: pip install openai")

    client = OpenAI(api_key=api_key) if api_key else OpenAI()

    # chat.completions – wersja zgodna z openai>=1.0.0
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    content = resp.choices[0].message.content
    usage = getattr(resp, "usage", None)
    usage_dict = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
    }
    return content, usage_dict

# ----------------------- LOGIKA CZATU -----------------------
user_input = st.chat_input("Napisz wiadomość…")

if user_input is not None:
    # pokaż wiadomość użytkownika od razu
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # system prompt + wybrana osobowość
    system_prompt = DEFAULT_SYSTEM + "\n\n" + (
        f"Styl: {st.session_state.personality} — {PERSONALITIES[st.session_state.personality]}"
    )

    api_messages = [{"role": "system", "content": system_prompt}] + st.session_state.messages

    with st.chat_message("assistant"):
        placeholder = st.empty()
        try:
            if not api_key:
                placeholder.warning("Podaj OPENAI_API_KEY w sidebarze lub w Streamlit Secrets.")
            else:
                reply, usage = call_openai_chat(api_messages, st.session_state.model, api_key)
                # zaktualizuj licznik tokenów
                st.session_state.total_prompt_tokens += usage.get("prompt_tokens", 0)
                st.session_state.total_completion_tokens += usage.get("completion_tokens", 0)
                # wyświetl i zapisz
                placeholder.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            placeholder.error(f"Błąd: {e}")

# ----------------------- STOPKA -----------------------
st.caption("Made with ❤️ in Streamlit — NaszGPT v1.3")
