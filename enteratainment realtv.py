"""
Real TV — Entertainment Sub-Channel Decision Report
---------------------------------------------------
A ONE-TIME strategic report (not a live tracker) that answers:

  "Should Real TV launch an entertainment sub-channel branched off the
   main news channel — and if so, which lane (world/travel & health,
   movie updates, or conspiracies/investigations) should it enter?"

It studies two things from real public data:
  A. PROOF-OF-CONCEPT — how news-brand entertainment branches perform
     (Telugu + global), so the "should we?" is answered with evidence.
  B. LANE OPPORTUNITY — the three priority lanes, ranked by demand,
     engagement, format, length, and 5-month trend direction.

Trend method (honest): the YouTube API returns each video's CURRENT
totals, not historical snapshots. So "5-month trend" here compares
COHORTS of videos by the month they were POSTED — e.g. are videos
posted recently out-performing older ones, is a lane's output rising,
are Shorts taking over. It does NOT track one video's day-by-day climb
(that needs going-forward logging). This cohort read is the correct
tool for a market-entry decision.

Dashboard + one-click HTML export. API key in Secrets, not here.
"""

from datetime import datetime, timezone, timedelta
import re
import requests
import pandas as pd
import streamlit as st

IST = timezone(timedelta(hours=5, minutes=30))
API_BASE = "https://www.googleapis.com/youtube/v3"
MONTHS_BACK = 5
PER_CHANNEL_CAP = 120   # max recent videos pulled per channel (keeps quota sane)

# ─────────────────────────────────────────────────────────────────────────────
# STUDY SET
# group "A_newsbrand" = news-brand entertainment/infotainment branches (proof)
# group "B_lane"      = the three priority lanes (opportunity)
# Fill "id" (UC...) for any that fail to resolve by handle.
# Everything here is an editable starting point — refine freely.
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [
    # ══════════════════════════════════════════════════════════════════════
    # A. NEWS-BRAND ENTERTAINMENT ARMS — the proof-of-concept group.
    # Major Telugu news/media brands' entertainment & themed sister channels.
    # This is the model Real TV is weighing: an established news brand
    # spinning off entertainment content. Editable — add/fix as needed.
    # ══════════════════════════════════════════════════════════════════════
    {"label": "TV9 Entertainment",   "handle": "@tv9entertainment",  "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "ETV Plus India",      "handle": "@etvplusindia",      "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "ETV Cinema",          "handle": "@etvcinema",         "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "ETV Life India",      "handle": "@etvlifeindia",      "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "Sakshi Entertainment","handle": "@SakshiEntertainment","id": None,"group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "ABNChitrajyothy",   "handle": "@ABNEntertainment",  "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "V6 Life",             "handle": "@V6EntertainmentTelugu",            "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},
    {"label": "NTV ENT",             "handle": "@NTVENT",            "id": None, "group": "A_newsbrand", "lane": "News-brand arm"},

    # ══════════════════════════════════════════════════════════════════════
    # B. THE THREE PRIORITY LANES — 4 channels each (demand + trend).
    # ══════════════════════════════════════════════════════════════════════
    # ── B1. Movie updates / cinema-news (proven biggest lane in India) ──
    {"label": "Thyview",     "handle": "@thyview",   "id": None, "group": "B_lane", "lane": "Movie updates"},
    {"label": "Gulte",               "handle": "@GulteOfficial",     "id": None, "group": "B_lane", "lane": "Movie updates"},
    {"label": "All In One Film Updates 2.0",           "handle": "@AllInOneFilmUpdates2.0",         "id": None, "group": "B_lane", "lane": "Movie updates"},
    {"label": "GreatAndhra",        "handle": "@greatandhranews","id": None,"group": "B_lane", "lane": "Movie updates"},

    # ── B2. World/travel & health (Telugu) ──
    {"label": "Telugu Travel Vlogger","handle": "@TeluguTravelVlogger","id": None,"group": "B_lane", "lane": "World/Travel & Health"},
    {"label": "facts forever",       "handle": "@factsforever","id": None, "group": "B_lane", "lane": "World/Travel & Health"},
    {"label": " TeluguOne Health",       "handle": "@teluguonehealth",      "id": None, "group": "B_lane", "lane": "World/Travel & Health"},
    {"label": "Dr. Manthena Official", "handle": "@dr.manthenaofficial3931",  "id": None, "group": "B_lane", "lane": "World/Travel & Health"},

    # ── B3. Conspiracies / investigations / strange-unexplained (Telugu) ──
    {"label": "A Touch Of Mystery Telugu","handle": "@ATouchOfMystery-Telugu","id": None,"group": "B_lane", "lane": "Conspiracies/Investigations"},
    {"label": "Think Deep",        "handle": "@ThinkDeep",   "id": None, "group": "B_lane", "lane": "Conspiracies/Investigations"},
    {"label": "VR Raja","handle": "@iamvrraja", "id": None, "group": "B_lane", "lane": "Conspiracies/Investigations"},
    {"label": "Telugu Real Facts",   "handle": "@Telugurealfacts",   "id": None, "group": "B_lane", "lane": "Conspiracies/Investigations"},
]

# ─────────────────────────────────────────────────────────────────────────────
def get_api_key():
    try:
        return st.secrets["YT_API_KEY"]
    except Exception:
        st.error('No API key. In Streamlit → Settings → Secrets add:  YT_API_KEY = "your-key"')
        st.stop()


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_channel(channel, api_key):
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
        return {"label": channel["label"], "error": f"not found ({hint})"}
    c = items[0]
    return {
        "label": channel["label"], "group": channel["group"], "lane": channel["lane"],
        "uploads_playlist": c["contentDetails"]["relatedPlaylists"]["uploads"],
        "subs": int(c["statistics"].get("subscriberCount", 0)),
        "total_views": int(c["statistics"].get("viewCount", 0)),
        "error": None,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_recent_uploads(uploads_playlist, api_key, max_items):
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
def build(api_key, months_back, cap):
    now = datetime.now(IST)
    cutoff = now - timedelta(days=months_back*30)
    vrows, crows, errors = [], [], []

    for channel in CHANNELS:
        ch = resolve_channel(channel, api_key)
        if ch.get("error"):
            errors.append(f"{channel['label']}: {ch['error']}")
            continue
        vids = fetch_video_details(
            fetch_recent_uploads(ch["uploads_playlist"], api_key, cap), api_key)
        kept = 0
        for v in vids:
            published = datetime.fromisoformat(
                v["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(IST)
            if published < cutoff:
                continue
            kept += 1
            stats = v.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            dur = parse_duration(v.get("contentDetails", {}).get("duration", ""))
            vrows.append({
                "Channel": ch["label"], "Group": ch["group"], "Lane": ch["lane"],
                "Title": v["snippet"]["title"], "Views": views,
                "Likes": likes, "Comments": comments,
                "Engagement %": round((likes+comments)/views*100, 2) if views else 0,
                "Type": "Short" if 0 < dur <= 60 else "Long",
                "Length_s": dur,
                "Month": published.strftime("%Y-%m"),
                "Posted": published,
                "Link": f"https://youtu.be/{v['id']}",
            })
        crows.append({"Channel": ch["label"], "Group": ch["group"], "Lane": ch["lane"],
                      "Subscribers": ch["subs"], "Videos in window": kept})
    return pd.DataFrame(vrows), pd.DataFrame(crows), errors, now


def length_band(sec):
    if sec <= 60:   return "Short (≤1m)"
    if sec <= 480:  return "Mid (1–8m)"
    if sec <= 1200: return "Long (8–20m)"
    return "XLong (20m+)"


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Real TV — Entertainment Decision Report", layout="wide")
st.title("Real TV — Entertainment Sub-Channel Decision Report")
st.caption("A one-time strategic report on whether to branch an entertainment "
           "sub-channel off the main news channel, and which lane to enter. "
           "Real public data; trend = post-month cohorts, not per-video history.")

with st.sidebar:
    st.header("Settings")
    months = st.slider("Months to look back", 3, 6, MONTHS_BACK)
    cap = st.slider("Max videos per channel", 40, 200, PER_CHANNEL_CAP, step=20,
                    help="Higher = more complete but slower and more quota.")
    if st.button("Rebuild report", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Caches 24h. First build across all channels is slow (a few min).")

api_key = get_api_key()
with st.spinner("Building the report — pulling ~5 months across all channels…"):
    vdf, cdf, errors, now = build(api_key, months, cap)

st.caption(f"Built {now.strftime('%d %b %Y, %I:%M %p IST')} · {months}-month window")
if errors:
    with st.expander(f"⚠️ {len(errors)} channel(s) couldn't be read — fix handle/id"):
        for e in errors:
            st.write("•", e)

if vdf.empty:
    st.warning("No data resolved. Fix handles/IDs in the config and rebuild.")
    st.stop()

vdf["Length band"] = vdf["Length_s"].apply(length_band)

tabs = st.tabs([
    "🧭 Verdict",
    "✅ Proof: news-brand branches",
    "🎯 Lane opportunity",
    "🎬 Format & length",
    "📈 5-month trend",
    "⬇️ Export",
])

# ── Verdict ──
with tabs[0]:
    st.subheader("The decision, from the data")
    lanes_B = vdf[vdf["Group"] == "B_lane"]
    lane_summary = (lanes_B.groupby("Lane")
                    .agg(Videos=("Title", "size"),
                         **{"Median views": ("Views", "median"),
                            "Avg engagement %": ("Engagement %", "mean")})
                    .reset_index().sort_values("Median views", ascending=False))
    best_lane = lane_summary.iloc[0]["Lane"] if not lane_summary.empty else "—"

    A = vdf[vdf["Group"] == "A_newsbrand"]
    a_median = int(A["Views"].median()) if not A.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Best-performing lane", best_lane)
    c2.metric("News-brand branch median views", humanize(a_median))
    c3.metric("Videos analysed", len(vdf))

    st.markdown(f"""
**Should Real TV launch an entertainment branch?**  
The evidence to weigh sits in the next tabs, but in short: news-brand
entertainment branches in this sample pull a median of **{humanize(a_median)}**
views per video — proof the model *can* work when a news brand extends into
lighter content. The strongest lane by demand right now is
**{best_lane}**.

**How to read the recommendation:**
- **Proof tab** — do news brands actually succeed at this? Compare their
  branch performance and output.
- **Lane opportunity** — which of your three lanes (world/travel & health,
  movie updates, conspiracies/investigations) has the best demand vs
  saturation.
- **Format & length** — how to produce for the chosen lane.
- **5-month trend** — is that lane rising or fading (enter something with
  momentum).

Decide the lane on demand **and** fit with a newsroom's strengths: movie
updates and investigations play to research/credibility; world/heatlh
plays to storytelling. Avoid sensational clickbait in the investigations lane —
framed as *"what's actually known,"* it protects the news brand instead of
cheapening it.
""")

# ── Proof: news-brand branches ──
with tabs[1]:
    st.subheader("Do news-brand entertainment branches actually work?")
    A = vdf[vdf["Group"] == "A_newsbrand"]
    if A.empty:
        st.info("No news-brand branch data resolved.")
    else:
        by_ch = (A.groupby(["Channel", "Lane"])
                 .agg(Videos=("Title", "size"),
                      **{"Median views": ("Views", "median"),
                         "Avg engagement %": ("Engagement %", "mean")})
                 .reset_index().sort_values("Median views", ascending=False))
        by_ch["Median views"] = by_ch["Median views"].round().astype(int).apply(humanize)
        by_ch["Avg engagement %"] = by_ch["Avg engagement %"].round(2)
        st.dataframe(by_ch, use_container_width=True, hide_index=True)
        st.caption("Telugu news brands' entertainment arms. If these branches "
                   "sustain solid median views, the model is validated for a "
                   "Telugu news brand specifically — the audience you actually serve.")
        st.markdown("**Top branch videos (what these news brands do well)**")
        top = A.sort_values("Views", ascending=False).head(12)[
            ["Channel", "Title", "Views", "Engagement %", "Type", "Link"]].copy()
        top["Views"] = top["Views"].apply(humanize)
        st.dataframe(top, use_container_width=True, hide_index=True,
                     column_config={"Link": st.column_config.LinkColumn("Watch", display_text="▶")})

# ── Lane opportunity ──
with tabs[2]:
    st.subheader("Which lane to enter")
    B = vdf[vdf["Group"] == "B_lane"]
    lane = (B.groupby("Lane")
            .agg(Channels=("Channel", "nunique"), Videos=("Title", "size"),
                 **{"Median views": ("Views", "median"),
                    "Avg engagement %": ("Engagement %", "mean")})
            .reset_index().sort_values("Median views", ascending=False))
    disp = lane.copy()
    disp["Median views"] = disp["Median views"].round().astype(int).apply(humanize)
    disp["Avg engagement %"] = disp["Avg engagement %"].round(2)
    st.dataframe(disp, use_container_width=True, hide_index=True)
    st.markdown("**How to read it:** high median views = proven demand; high "
                "engagement = loyal, active audience (better base for a new channel). "
                "The best entry lane is strong on both but not saturated by one giant.")
    st.divider()
    st.markdown("**Top videos per lane**")
    for lane_name in B["Lane"].unique():
        st.markdown(f"**{lane_name}**")
        sub = B[B["Lane"] == lane_name].sort_values("Views", ascending=False).head(6)[
            ["Channel", "Title", "Views", "Engagement %", "Type", "Link"]].copy()
        sub["Views"] = sub["Views"].apply(humanize)
        st.dataframe(sub, use_container_width=True, hide_index=True,
                     column_config={"Link": st.column_config.LinkColumn("Watch", display_text="▶")})

# ── Format & length ──
with tabs[3]:
    st.subheader("What format and length wins, per lane")
    B = vdf[vdf["Group"] == "B_lane"]
    order = {"Short (≤1m)":0,"Mid (1–8m)":1,"Long (8–20m)":2,"XLong (20m+)":3}
    for lane_name in B["Lane"].unique():
        st.markdown(f"**{lane_name}**")
        sub = B[B["Lane"] == lane_name]
        lb = (sub.groupby("Length band")["Views"].median().round().astype(int)
              .reset_index().rename(columns={"Views": "Median views"}))
        lb["_o"] = lb["Length band"].map(order)
        lb = lb.sort_values("_o").drop(columns="_o")
        shorts_share = round((sub["Type"] == "Short").mean() * 100)
        lb["Median views"] = lb["Median views"].apply(humanize)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(lb, use_container_width=True, hide_index=True)
        with c2:
            st.metric("Shorts share", f"{shorts_share}%")
        st.divider()

# ── 5-month trend ──
with tabs[4]:
    st.subheader("How the trend is moving (post-month cohorts)")
    st.caption("Median views by the month a video was POSTED. Rising line = the lane "
               "is gaining traction; also watch whether output (video count) is growing.")
    B = vdf[vdf["Group"] == "B_lane"]
    pivot = (B.groupby(["Month", "Lane"])["Views"].median().round().astype(int)
             .reset_index())
    if not pivot.empty:
        wide = pivot.pivot(index="Month", columns="Lane", values="Views").sort_index()
        st.line_chart(wide)
        st.caption("Median views per posted-month, by lane.")
        vol = (B.groupby(["Month", "Lane"])["Title"].size().reset_index()
               .rename(columns={"Title": "Videos"}))
        wide_vol = vol.pivot(index="Month", columns="Lane", values="Videos").sort_index()
        st.markdown("**Output volume by month (are creators leaning in?)**")
        st.bar_chart(wide_vol)
    else:
        st.info("Not enough data to chart trend.")

# ── Export ──
with tabs[5]:
    st.subheader("Export the report")
    st.caption("Download a standalone HTML report (opens in any browser, printable to PDF).")

    B = vdf[vdf["Group"] == "B_lane"]
    A = vdf[vdf["Group"] == "A_newsbrand"]
    lane = (B.groupby("Lane").agg(Videos=("Title","size"),
            median=("Views","median"), eng=("Engagement %","mean")).reset_index()
            .sort_values("median", ascending=False))
    best_lane = lane.iloc[0]["Lane"] if not lane.empty else "—"
    a_median = int(A["Views"].median()) if not A.empty else 0

    lane_rows = "".join(
        f"<tr><td>{r.Lane}</td><td>{int(r.Videos)}</td>"
        f"<td>{humanize(int(r.median))}</td><td>{r.eng:.2f}%</td></tr>"
        for r in lane.itertuples())

    top_overall = B.sort_values("Views", ascending=False).head(15)
    top_rows = "".join(
        f"<tr><td>{row.Lane}</td><td>{row.Channel}</td>"
        f"<td>{row.Title[:70]}</td><td>{humanize(row.Views)}</td>"
        f"<td>{row['Engagement %']:.1f}%</td></tr>"
        for _, row in top_overall.iterrows())

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Real TV — Entertainment Decision Report</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;
margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.5}}
h1{{border-bottom:3px solid #c00;padding-bottom:8px}}
h2{{margin-top:32px;color:#c00}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left;font-size:14px}}
th{{background:#f4f4f4}}
.box{{background:#f9f9f9;border-left:4px solid #c00;padding:12px 16px;margin:16px 0}}
.muted{{color:#666;font-size:13px}}
</style></head><body>
<h1>Real TV — Entertainment Sub-Channel Decision Report</h1>
<p class="muted">Generated {now.strftime('%d %b %Y')} · {months}-month window ·
{len(vdf)} videos across {vdf['Channel'].nunique()} channels · public data.
Trend = post-month cohorts, not per-video history.</p>

<div class="box">
<b>Headline:</b> News-brand entertainment branches in this sample pull a median
of <b>{humanize(a_median)}</b> views/video — the model can work. The strongest
lane by current demand is <b>{best_lane}</b>.
</div>

<h2>Should we launch the branch?</h2>
<p>Evidence supports a <b>yes, with discipline</b>. News brands hold advantages
pure entertainers lack: an existing audience to cross-promote, newsroom research
capacity, credibility, and shared production resources. The risk is brand
dilution — the investigations/strange-stories lane must be framed as
<i>"what's actually known,"</i> not sensational clickbait, to protect the news
brand. Launch as a real editorial product with its own standards, resourced so
it doesn't starve the main channel.</p>

<h2>Which lane? (ranked by demand)</h2>
<table><tr><th>Lane</th><th>Videos</th><th>Median views</th><th>Avg engagement</th></tr>
{lane_rows}</table>
<p class="muted">High median views = proven demand. High engagement = loyal base,
better for a new channel. Pick the lane strong on both that also fits a
newsroom's strengths (research/credibility for movie updates & investigations;
storytelling for world/Health).</p>

<h2>What's winning right now (top videos in the priority lanes)</h2>
<table><tr><th>Lane</th><th>Channel</th><th>Title</th><th>Views</th><th>Eng.</th></tr>
{top_rows}</table>

<h2>Recommendation</h2>
<p>Enter <b>{best_lane}</b> first if it also suits the team's strengths; otherwise
choose the highest-demand lane that does. Produce in the length band that wins
for that lane (see dashboard Format tab), seed the sub-channel using the main
news channel's existing reach, and hold entertainment content to the same
factual standard as the newsroom. Re-run this report every 1–2 months to watch
the trend shift.</p>

<p class="muted">Prepared for Real TV Telugu · strategy input, not a guarantee —
validate with the sub-channel's own YouTube Studio data once live.</p>
</body></html>"""

    st.download_button("⬇️ Download HTML report", data=html,
                       file_name=f"realtv_entertainment_report_{now.strftime('%Y%m%d')}.html",
                       mime="text/html", use_container_width=True)
    st.caption("Open the file → Print → Save as PDF for a shareable PDF.")
    with st.expander("Preview the report HTML"):
        st.code(html[:1500] + "…", language="html")
