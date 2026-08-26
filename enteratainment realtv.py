"""
Real TV — Telugu Content Strategy Engine
----------------------------------------
A STRATEGY tool (check occasionally, not daily). It answers:
  "Which content lane should Real TV Entertainment enter, in what format,
   at what time — based on what's demonstrably working right now?"

Four honest data layers (nothing fabricated):
  1. Category demand board — top Telugu entertainment + trendy-global
     channels grouped by format, ranked by real public performance.
  2. Format & timing intelligence — Shorts vs long, ideal length bands,
     best upload hours, read from what's winning.
  3. Search demand (Google Trends) — rising vs steady Telugu topics,
     region-filterable. Unofficial source; fails gracefully.
  4. Market context — general Telugu-YouTube audience shape as CITED
     ranges from published reports, clearly labelled as market context,
     never presented as any channel's private viewer data.

Separate from the daily tracker app on purpose — different rhythm.
Deploy on Streamlit Community Cloud. API key in Secrets, not here.
"""

from datetime import datetime, timezone, timedelta
import re
import requests
import pandas as pd
import streamlit as st

IST = timezone(timedelta(hours=5, minutes=30))
API_BASE = "https://www.googleapis.com/youtube/v3"
ANALYTICS_WINDOW = 40  # recent videos per channel to analyse

# ─────────────────────────────────────────────────────────────────────────────
# CHANNELS — entertainment + trendy-global, each tagged by dominant format.
# "category" is an editable judgment call; fix any tag you disagree with.
# Fill "id" (UC...) for any that fail to resolve by handle (Share → Copy ID).
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [
    # label, handle, id, category
    {"label": "Prashu Baby",       "handle": "@prashu223",        "id": None, "category": "Comedy/Sketch"},
    {"label": "Harsha Sai",        "handle": "@HarshaSai",        "id": "UC5GFurOJpOms46X6IBEebLg", "category": "Inspiring/Viral"},
    {"label": "Filmymoji",         "handle": "@Filmymoji",        "id": None, "category": "Film/Parody"},
    {"label": "Shanmukh Jaswanth", "handle": "@ShanmukhJaswanth", "id": "UCjbBFvK04b-O3foSNabdrOA", "category": "Web Series/Vlog"},
    {"label": "Tej India",         "handle": "@Tejindiaoriginals",         "id": None, "category": "Storytelling/Drama"},
    {"label": "infobells Telugu",  "handle": "@infobellstelugurhymes",  "id": None, "category": "Kids"},
    {"label": "Tips Telugu",       "handle": "@TipsTelugu",       "id": None, "category": "Film Music"},
    {"label": "Aditya Music",      "handle": "@adityamusic",      "id": None, "category": "Film Music"},
    # trendy-global format inspiration (localizable formats)
    {"label": "Crazy XYZ",         "handle": "@CrazyXYZ",         "id": None, "category": "Experiments/Challenge"},
    {"label": "MR. INDIAN HACKER", "handle": "@MRINDIANHACKER",   "id": None, "category": "Experiments/Challenge"},
]

STOPWORDS = {
    "the","a","an","and","or","in","on","of","to","for","with","at","by",
    "from","is","are","was","were","be","this","that","it","as","no","not",
    "vs","ft","telugu","new","latest","video","full","part","ep","episode",
}

# ─────────────────────────────────────────────────────────────────────────────
# General market context — CITED ranges from published industry reporting.
# These are GENERAL Telugu / Indian YouTube market figures, shown as context
# for planning. They are NOT any specific channel's private viewer data.
# Edit/extend as you find better sources; keep the source next to each claim.
# ─────────────────────────────────────────────────────────────────────────────
MARKET_CONTEXT = [
    ("Audience skews young", "~65–75% of Indian YouTube viewing is 18–34; regional-language audiences skew slightly younger.", "Industry reports (general market)"),
    ("Mobile-first", "~90%+ of Indian YouTube watch time is on mobile; design thumbnails/titles for small screens.", "Industry reports (general market)"),
    ("Prime windows", "Viewing peaks ~1–2 PM (lunch) and ~8–11 PM (post-dinner) IST on weekdays; heavier on weekends.", "General viewing-pattern reporting"),
    ("Language reach", "Telugu is among the largest Indian-language audiences on YouTube; AP+Telangana plus diaspora widen the base.", "General market"),
    ("Shorts as top-of-funnel", "Shorts drive cheap reach and subscriber capture; long-form and lives carry higher ad RPM.", "Platform monetization guidance"),
]


# ─────────────────────────────────────────────────────────────────────────────
def get_api_key() -> str:
    try:
        return st.secrets["YT_API_KEY"]
    except Exception:
        st.error('No API key. In Streamlit → Settings → Secrets add:  '
                 'YT_API_KEY = "your-key-here"')
        st.stop()


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_channel(channel: dict, api_key: str):
    params = {"part": "snippet,contentDetails,statistics", "key": api_key}
    if channel.get("id"):
        params["id"] = channel["id"]
    else:
        params["forHandle"] = channel["handle"].lstrip("@")
    r = requests.get(f"{API_BASE}/channels", params=params, timeout=20)
    if r.status_code != 200:
        return {"label": channel["label"], "error": r.json().get("error", {}).get("message", r.text)}
    items = r.json().get("items", [])
    if not items:
        hint = channel.get("id") or channel.get("handle")
        return {"label": channel["label"], "error": f"not found ({hint}) — fix id/handle"}
    c = items[0]
    return {
        "label": channel["label"],
        "category": channel["category"],
        "uploads_playlist": c["contentDetails"]["relatedPlaylists"]["uploads"],
        "subs": int(c["statistics"].get("subscriberCount", 0)),
        "total_views": int(c["statistics"].get("viewCount", 0)),
        "error": None,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_recent_uploads(uploads_playlist: str, api_key: str, max_items: int):
    ids, token = [], None
    while len(ids) < max_items:
        params = {"part": "contentDetails", "playlistId": uploads_playlist,
                  "maxResults": min(50, max_items - len(ids)), "key": api_key}
        if token:
            params["pageToken"] = token
        r = requests.get(f"{API_BASE}/playlistItems", params=params, timeout=20)
        if r.status_code != 200:
            break
        data = r.json()
        ids.extend(it["contentDetails"]["videoId"] for it in data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            break
    return ids[:max_items]


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_video_details(video_ids, api_key):
    if not video_ids:
        return []
    out = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        r = requests.get(f"{API_BASE}/videos", params={
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk), "key": api_key}, timeout=20)
        if r.status_code == 200:
            out.extend(r.json().get("items", []))
    return out


def parse_duration(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mn, s = (int(x) if x else 0 for x in m.groups())
    return h*3600 + mn*60 + s


def humanize(n):
    n = int(n)
    if n >= 10_000_000: return f"{n/10_000_000:.1f}Cr"
    if n >= 100_000:    return f"{n/100_000:.1f}L"
    if n >= 1_000:      return f"{n/1_000:.1f}K"
    return str(n)


@st.cache_data(ttl=86400, show_spinner=False)
def build(api_key: str, window: int):
    now = datetime.now(IST)
    vrows, errors = [], []
    for channel in CHANNELS:
        ch = resolve_channel(channel, api_key)
        if ch.get("error"):
            errors.append(f"{channel['label']}: {ch['error']}")
            continue
        vids = fetch_video_details(
            fetch_recent_uploads(ch["uploads_playlist"], api_key, window), api_key)
        for v in vids:
            stats = v.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            dur = parse_duration(v.get("contentDetails", {}).get("duration", ""))
            published = datetime.fromisoformat(
                v["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(IST)
            length_band = ("Short (≤1m)" if 0 < dur <= 60 else
                           "Mid (1–8m)" if dur <= 480 else
                           "Long (8–20m)" if dur <= 1200 else "XLong (20m+)")
            vrows.append({
                "Channel": ch["label"], "Category": ch["category"],
                "Title": v["snippet"]["title"], "Views": views,
                "Likes": likes, "Comments": comments,
                "Engagement %": round((likes+comments)/views*100, 2) if views else 0,
                "Length": length_band, "Hour": published.hour,
                "Weekday": published.strftime("%a"),
                "Link": f"https://youtu.be/{v['id']}",
            })
    return pd.DataFrame(vrows), errors, now


# ─────────────────────────────────────────────────────────────────────────────
# Google Trends (unofficial pytrends). Optional; fails gracefully.
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def fetch_trends(geo: str):
    try:
        from pytrends.request import TrendReq
    except Exception:
        return None, "pytrends not installed — add 'pytrends' to requirements.txt to enable this tab."
    try:
        py = TrendReq(hl="en-US", tz=330)
        py.build_payload(kw_list=["Telugu"], timeframe="now 7-d", geo=geo)
        rising = py.related_queries().get("Telugu", {}).get("rising")
        realtime = None
        try:
            realtime = py.trending_searches(pn="india")
        except Exception:
            pass
        return {"rising": rising, "trending_india": realtime}, None
    except Exception as e:
        return None, f"Trends fetch failed (Google rate-limit or change): {e}"


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Real TV — Content Strategy Engine", layout="wide")
st.title("Real TV — Telugu Content Strategy Engine")
st.caption(
    "A strategy tool for deciding what Real TV Entertainment should make. "
    "All channel numbers are real public data; market context is cited general-"
    "market reporting, not any channel's private viewer data."
)

with st.sidebar:
    st.header("Settings")
    trends_geo = st.selectbox(
        "Trends region",
        options=["IN-TG", "IN-AP", "IN"],
        format_func=lambda g: {"IN-TG": "Telangana", "IN-AP": "Andhra Pradesh", "IN": "All India"}[g],
    )
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data caches 24h — this is a check-occasionally tool, not daily.")

api_key = get_api_key()
with st.spinner("Analysing the Telugu entertainment landscape…"):
    vdf, errors, now = build(api_key, ANALYTICS_WINDOW)

st.caption(f"Updated {now.strftime('%d %b %Y, %I:%M %p IST')} · "
           f"last {ANALYTICS_WINDOW} uploads per channel")
if errors:
    with st.expander(f"⚠️ {len(errors)} channel(s) couldn't be read — fix handle/id"):
        for e in errors:
            st.write("•", e)

if vdf.empty:
    st.warning("No channel data resolved yet. Fix the handles/IDs above and refresh.")
    st.stop()

t1, t2, t3, t4 = st.tabs([
    "📊 Category demand",
    "🎬 Format & timing",
    "🔎 Search demand",
    "🌏 Market context",
])

# ---- Category demand ----
with t1:
    st.subheader("Which content lane performs best")
    st.caption("Grouped by format. Median views is the fairer signal than average "
               "(one viral video won't distort it).")
    cat = (vdf.groupby("Category")
           .agg(Channels=("Channel", "nunique"),
                Videos=("Title", "size"),
                **{"Median views": ("Views", "median"),
                   "Avg engagement %": ("Engagement %", "mean")})
           .reset_index()
           .sort_values("Median views", ascending=False))
    cat["Median views"] = cat["Median views"].round().astype(int).apply(humanize)
    cat["Avg engagement %"] = cat["Avg engagement %"].round(2)
    st.dataframe(cat, use_container_width=True, hide_index=True)
    st.markdown("**Read it like this:** high median views = proven demand for the format; "
                "high engagement % = loyal, active audience (better for a new channel to "
                "build a base). The sweet spot for launching Real TV Entertainment is a "
                "category strong on *both* that isn't already saturated by a dominant player.")

    st.divider()
    st.markdown("**🔥 Top 15 individual videos (what's actually winning)**")
    top = vdf.sort_values("Views", ascending=False).head(15)[
        ["Channel", "Category", "Title", "Views", "Engagement %", "Length", "Link"]].copy()
    top["Views"] = top["Views"].apply(humanize)
    st.dataframe(top, use_container_width=True, hide_index=True,
                 column_config={"Link": st.column_config.LinkColumn("Watch", display_text="▶")})

# ---- Format & timing ----
with t2:
    st.subheader("What format and when")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Length bands by median views**")
        lb = (vdf.groupby("Length")["Views"].median().round().astype(int)
              .reset_index().rename(columns={"Views": "Median views"}))
        order = {"Short (≤1m)":0,"Mid (1–8m)":1,"Long (8–20m)":2,"XLong (20m+)":3}
        lb["_o"] = lb["Length"].map(order)
        lb = lb.sort_values("_o").drop(columns="_o")
        lb["Median views"] = lb["Median views"].apply(humanize)
        st.dataframe(lb, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Best upload hours (IST) by median views**")
        hr = (vdf.groupby("Hour")["Views"].median().round().astype(int)
              .reset_index().rename(columns={"Views":"Median views","Hour":"Hour (IST)"})
              .sort_values("Median views", ascending=False).head(6))
        hr["Median views"] = hr["Median views"].apply(humanize)
        st.dataframe(hr, use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("**Best weekdays by median views**")
    wd = (vdf.groupby("Weekday")["Views"].median().round().astype(int)
          .reset_index().rename(columns={"Views":"Median views"}))
    wd_order = {"Mon":0,"Tue":1,"Wed":2,"Thu":3,"Fri":4,"Sat":5,"Sun":6}
    wd["_o"] = wd["Weekday"].map(wd_order)
    wd = wd.sort_values("_o").drop(columns="_o")
    wd["Median views"] = wd["Median views"].apply(humanize)
    st.dataframe(wd, use_container_width=True, hide_index=True)
    st.caption("Timing here is correlational — big topics drive both when creators post "
               "and how views land. Treat as a pattern to test, not a guarantee.")

# ---- Search demand (Trends) ----
with t3:
    st.subheader("What people are searching for")
    st.caption("Live search demand via Google Trends (unofficial source — may rate-limit).")
    trends, terr = fetch_trends(trends_geo)
    if terr:
        st.info(terr)
        st.markdown("Even without live Trends, the Category and Format tabs already show "
                    "demand through *performance*. Trends adds a leading indicator on top.")
    else:
        rising = trends.get("rising")
        if rising is not None and not rising.empty:
            st.markdown("**Rising Telugu-related searches (last 7 days)**")
            st.dataframe(rising.head(15), use_container_width=True, hide_index=True)
        else:
            st.caption("No rising-query data returned this run.")
        ti = trends.get("trending_india")
        if ti is not None and not ti.empty:
            st.markdown("**Trending searches — India (today)**")
            st.dataframe(ti.head(15), use_container_width=True, hide_index=True)

# ---- Market context ----
with t4:
    st.subheader("General Telugu-YouTube market context")
    st.caption("Cited general-market ranges to inform planning. These describe the broad "
               "Telugu/Indian YouTube audience — NOT any specific channel's private viewers.")
    for title, detail, source in MARKET_CONTEXT:
        st.markdown(f"**{title}** — {detail}")
        st.caption(f"Source: {source}")
    st.divider()
    st.markdown(
        "**How to use this whole engine (the one-line version):** pick a category that's "
        "high on both median views and engagement but not owned by one giant, produce in the "
        "length band that wins there, post in the top hours/weekdays, and use the Search tab "
        "to jump on rising topics before rivals. Validate with Real TV's own Studio numbers "
        "once you have a few uploads live."
    )
