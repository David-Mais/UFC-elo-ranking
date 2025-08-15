# imports
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter, Retry
from typing import Union

# --- add near top of LIB ---
import re
from bs4 import BeautifulSoup

def _txt(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True) if node else "").strip()

def _clean_value(v: str) -> str:
    if v is None:
        return ""
    v = v.replace("—", "").replace("--", "").strip()
    v = re.sub(r"\s+", " ", v)
    return "" if v.lower() in {"", "n/a", "na", "none"} else v

def _extract_fighter_name(soup: BeautifulSoup) -> str:
    # typical page title contains the name, sometimes followed by "Record:"
    title = _txt(soup.select_one(".b-content__title")) or _txt(soup.select_one("h1, h2"))
    return title.split("Record:")[0].strip()



# Create and start new session
def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "ufcstats-scraper/1.0 (+https://example.com)"})
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

_SESSION = _make_session()

def get_soup(src: Union[str, bytes]) -> BeautifulSoup:
    """
    Accepts a URL or raw HTML and returns a BeautifulSoup object.
    """
    if isinstance(src, (bytes, bytearray)):
        html = src
    elif src.strip().lower().startswith(("http://", "https://")):
        resp = _SESSION.get(src, timeout=15)
        resp.raise_for_status()
        html = resp.content
    else:
        # assume raw html string
        html = src.encode("utf-8", errors="ignore")
    return BeautifulSoup(html, "html.parser")



# parse event details
def parse_event_details(soup: BeautifulSoup) -> pd.DataFrame:
    """
    Robustly parse the Events table into a DataFrame with columns:
    EVENT, URL, DATE, LOCATION
    """
    rows = []
    # The events table rows usually have 'tr' with a link to the event page.
    for tr in soup.select("table.b-statistics__table-events tr"):
        a = tr.select_one("a.b-link.b-link_style_black")
        date = tr.select_one("span.b-statistics__date")
        loc  = tr.select_one("td.b-statistics__table-col.b-statistics__table-col_style_big-top-padding")
        if not a or not a.get("href"):
            continue
        rows.append({
            "EVENT": _txt(a),
            "URL": a["href"].strip(),
            "DATE": _txt(date),
            "LOCATION": _txt(loc),
        })
    df = pd.DataFrame(rows, columns=["EVENT", "URL", "DATE", "LOCATION"])
    # Drop obvious upcoming events (no stats yet) by heuristic: empty details page? (Optional)
    # df = df[df["URL"].str.contains("/event-details/")]
    return df.reset_index(drop=True)



# parse fight details
def parse_fight_details(soup: BeautifulSoup) -> pd.DataFrame:
    rows = []
    event_name = _txt(soup.select_one("h2.b-content__title"))
    for tr in soup.select("tr.b-fight-details__table-row.b-fight-details__table-row__hover.js-fight-details-click"):
        fight_url = tr.get("data-link", "").strip()
        # fighter name cells often have two 'p' elements (red & blue)
        fighters = [ _txt(p) for p in tr.select("p.b-fight-details__table-text") if _txt(p) ]
        # keep only first two meaningful text chunks for names
        names = [n for n in fighters if len(n) > 1][:2]
        if fight_url and len(names) == 2:
            rows.append({"EVENT": event_name, "BOUT": f"{names[0]} vs. {names[1]}", "URL": fight_url})
    return pd.DataFrame(rows, columns=["EVENT", "BOUT", "URL"])




# parse fight results from soup
def parse_fight_results_dict(soup: BeautifulSoup) -> dict:
    out = {
        "EVENT": _txt(soup.select_one("h2.b-content__title")),
        "BOUT": " vs. ".join([_txt(a) for a in soup.select("a.b-link.b-fight-details__person-link")][:2]),
        "OUTCOME": "/".join([_txt(i) for i in soup.select("div.b-fight-details__person i")][:2]),
        "WEIGHTCLASS": _txt(soup.select_one("div.b-fight-details__fight-head")),
        "METHOD": _txt(soup.select_one("i.b-fight-details__text-item_first")),
        "ROUND": "",
        "TIME": "",
        "TIMEFORMAT": "",
        "REFEREE": "",
        "DETAILS": "",
    }
    # remaining meta (order can vary)
    metas = [ _txt(i) for i in soup.select("p.b-fight-details__text i.b-fight-details__text-item") ]
    lab_map = {"Round:": "ROUND", "Time:": "TIME", "Time format:": "TIMEFORMAT", "Referee:": "REFEREE"}
    for m in metas:
        if ":" in m:
            k, v = m.split(":", 1)
            k = (k.strip() + ":")
            if k in lab_map:
                out[lab_map[k]] = _clean_value(v)

    details = soup.select("p.b-fight-details__text")
    if len(details) >= 2:
        out["DETAILS"] = _clean_value(_txt(details[1]))
    return out

def organise_fight_results(results: dict, columns: list) -> pd.DataFrame:
    row = {c: results.get(c, "") for c in columns}
    return pd.DataFrame([row], columns=columns)



# parse full fight stats for both fighters
def parse_fight_stats(soup):
    '''
    parse full fight stats for both fighters from soup
    loop through soup to find all 'td' tags with the class 'b-fight-details__table-col'
    this returns a list of stats for both fighters in alternate order
    e.g. [0, 1, 2, 2, 20, 30] stats [0, 2, 20] belong to the first fighter and [1, 2, 30] belong to the second fighter
    use enumerate to add index to results
    stats with even indexes belongs to the first fighter and odd indexes belong to the second fighter
    clean each element in the list, removing '\n' and ' ' 
    e.g cleans '\n fighter name \n' into 'fighter name' and  '\n      19 of 32\n    ' into '19 of 32'
    
    arguments:
    soup (html): output of get_soup() parser

    returns:
    two lists of fighter stats, one for each fighter
    '''

    # create empty list to store each fighter's stats
    fighter_a_stats = []
    fighter_b_stats = []

    # loop through soup to find all 'td' tags with the class 'b-fight-details__table-col'
    for tag in soup.find_all('td', class_='b-fight-details__table-col'):
        # loop through each 'td' tag and find all 'p' tags
        # this returns a list of stats for both fighters in alternate order
        # stats with even indexes belongs to the first fighter and odd indexes belong to the second fighter
        for index, p_text in enumerate(tag.find_all('p')):
            # check if index is even, if true then append to fighter_a_stats
            if index % 2 == 0:
                fighter_a_stats.append(p_text.text.strip())
            # if index is odd then append to fighter_b_stats
            else:
                fighter_b_stats.append(p_text.text.strip())

    # return
    return fighter_a_stats, fighter_b_stats



# organise stats extracted from soup
def organise_fight_stats(stats_from_soup: list) -> list[list]:
    """
    Split the flat list into segments starting at each occurrence of the fighter's name
    (assumes the fighter's name appears before each block of stats).
    Returns a list of segments: [ [name, ...block1...], [name, ...block2...], ... ]
    """
    if not stats_from_soup:
        return []
    name = stats_from_soup[0]
    chunks, cur = [], []
    for item in stats_from_soup:
        if item == name and cur:
            chunks.append(cur)
            cur = [item]
        else:
            cur.append(item)
    if cur:
        chunks.append(cur)
    return chunks



# convert list of fighter stats into a structured dataframe
def convert_fight_stats_to_df(clean_fighter_stats: list, totals_cols: list, sig_cols: list) -> pd.DataFrame:
    """
    Expecting clean_fighter_stats like:
    [
      [name, 'Totals', 'KD', '...', 'Summary values...'],
      [name, 'Round 1', '...', '...'],
      ...
      [name, 'Significant Strikes', '...', 'Summary values...'],
      [name, 'Round 1', '...', '...'],
      ...
    ]
    This function extracts only the per-round rows for both Totals & Significant sections and merges them on ROUND.
    """
    if not clean_fighter_stats:
        return pd.DataFrame(columns=totals_cols).assign(**{c: np.nan for c in totals_cols}).merge(
            pd.DataFrame(columns=sig_cols).assign(**{c: np.nan for c in sig_cols}), how="outer"
        )

    # Separate totals vs significant blocks by scanning headings
    def _is_round(s: str) -> bool:
        return isinstance(s, str) and s.strip().lower().startswith("round ")

    totals_rows, sig_rows = [], []
    section = None
    for block in clean_fighter_stats:
        # defensive checks
        if not block:
            continue
        # find label tokens inside the block
        label_tokens = [t for t in block if isinstance(t, str)]
        # rudimentary section detection
        if any("total" in t.lower() for t in label_tokens):
            section = "totals"; continue
        if any("significant" in t.lower() for t in label_tokens):
            section = "sig"; continue
        # round rows
        if section and any(_is_round(t) for t in label_tokens):
            if section == "totals":
                totals_rows.append(block)
            else:
                sig_rows.append(block)

    # Build DataFrames. Expect first value in each row to be 'Round X' (coerce if needed).
    def _rows_to_df(rows, cols):
        out = []
        for r in rows:
            # pick the first token that looks like "Round x"
            round_tok = next((t for t in r if _is_round(t)), "Round 1")
            # then take the trailing numeric/stat tokens to match cols[1:]
            values = [v for v in r if v != round_tok]
            out.append([round_tok] + values[:len(cols)-1])
        return pd.DataFrame(out, columns=cols)

    totals_df = _rows_to_df(totals_rows, totals_cols) if totals_rows else pd.DataFrame(columns=totals_cols)
    sig_df    = _rows_to_df(sig_rows, sig_cols)       if sig_rows    else pd.DataFrame(columns=sig_cols)

    # Merge on ROUND
    return totals_df.merge(sig_df, on="ROUND", how="outer")



# combine fighter stats into one
def combine_fighter_stats_dfs(fighter_a_stats_df: pd.DataFrame, fighter_b_stats_df: pd.DataFrame, soup: BeautifulSoup) -> pd.DataFrame:
    fight_stats = pd.concat([fighter_a_stats_df, fighter_b_stats_df], ignore_index=True)
    fight_stats["EVENT"] = _txt(soup.select_one("h2.b-content__title"))
    names = [_txt(a) for a in soup.select("a.b-link.b-fight-details__person-link")][:2]
    fight_stats["BOUT"] = " vs. ".join(names)
    # reorder if present
    cols = list(fight_stats.columns)
    for key in ["EVENT", "BOUT"]:
        if key in cols and "ROUND" in cols:
            fight_stats = move_columns(fight_stats, [key], "ROUND", "before")
    return fight_stats




# parse and organise fight results and fight stats
def parse_organise_fight_results_and_stats(soup: BeautifulSoup, url: str,
                                           fight_results_column_names: list,
                                           totals_column_names: list,
                                           significant_strikes_column_names: list):
    results = parse_fight_results_dict(soup)
    results["URL"] = url
    fight_results_df = organise_fight_results(results, fight_results_column_names)

    a_raw, b_raw = parse_fight_stats(soup)
    a_clean = organise_fight_stats(a_raw)
    b_clean = organise_fight_stats(b_raw)
    a_df = convert_fight_stats_to_df(a_clean, totals_column_names, significant_strikes_column_names)
    b_df = convert_fight_stats_to_df(b_clean, totals_column_names, significant_strikes_column_names)

    # tag fighter names if available (first element of each raw list is often name)
    if a_raw:
        a_df["FIGHTER"] = a_raw[0]
    if b_raw:
        b_df["FIGHTER"] = b_raw[0]

    fight_stats_df = combine_fighter_stats_dfs(a_df, b_df, soup)
    fight_stats_df["URL"] = url
    return fight_results_df, fight_stats_df



# generate list of urls for fighter details
def generate_alphabetical_urls():
    """
    Return the 27 UFCStats fighter index pages (a–z + 'other'), all on one page.
    Example: https://ufcstats.com/statistics/fighters?char=a&page=all
    """
    import string
    base = "http://ufcstats.com/statistics/fighters?char={}&page=all"
    chars = list(string.ascii_lowercase) + ["other"]
    return [base.format(c) for c in chars]




# parse fighter details
def parse_fighter_details(soup: BeautifulSoup, fighter_details_column_names: list) -> pd.DataFrame:
    names, urls = [], []
    for row in soup.select("table.b-statistics__table tr"):
        anchors = row.select("a.b-link.b-link_style_black")
        if len(anchors) >= 3:
            # first, last, nickname
            trio = [ _txt(a) for a in anchors[:3] ]
            href = anchors[0].get("href", "").strip()
            names.extend(trio)
            urls.append(href)
    # Interleave to tuples
    records = list(zip(names[0::3], names[1::3], names[2::3], urls))
    return pd.DataFrame(records, columns=fighter_details_column_names)



# parse fighter tale of the tape
def parse_fighter_tott(soup: BeautifulSoup) -> dict:
    """
    Returns a dict with keys: FIGHTER, HEIGHT, WEIGHT, REACH, STANCE, DOB
    Works across layout variants and odd whitespace/punctuation.
    """
    out = {
        "FIGHTER": _extract_fighter_name(soup),
        "HEIGHT": "",
        "WEIGHT": "",
        "REACH": "",
        "STANCE": "",
        "DOB": "",
    }

    # map of canonical key -> list of label patterns we accept
    label_map = {
        "HEIGHT": [r"^height\b"],
        "WEIGHT": [r"^weight\b"],
        "REACH":  [r"^reach\b", r"^arm\s*reach\b"],  # sometimes "Arm Reach"
        "STANCE": [r"^stance\b"],
        "DOB":    [r"^dob\b", r"^date of birth\b"],
    }

    # ---- 1) primary: read "label: value" pairs from info boxes ----
    # different pages swap wrappers/classes; cover a few
    li_candidates = soup.select(
        ".b-list__info-box .b-list__info-box-list li, "
        ".b-list__box-list li, "
        ".b-list__info-box li, "
        "ul.b-list__box-list li"
    )

    for li in li_candidates:
        line = _txt(li)
        if not line or ":" not in line:
            continue
        lab, val = [x.strip() for x in line.split(":", 1)]
        lab_l = lab.lower().rstrip(".")
        for key, patterns in label_map.items():
            if any(re.search(p, lab_l, re.I) for p in patterns):
                out[key] = _clean_value(val)

    # ---- 2) fallback: regex scan over full page text if any still missing ----
    page_text = _txt(soup)

    def _rx_one(label_regex: str) -> str:
        # capture until the next known label or line end to avoid swallowing neighbors
        pat = rf"{label_regex}\s*:\s*(.*?)(?=\s+(?:Height|Weight|Reach|Arm Reach|Stance|DOB|Date of Birth)\s*:|$)"
        m = re.search(pat, page_text, re.I)
        return _clean_value(m.group(1)) if m else ""

    if not out["HEIGHT"]:
        out["HEIGHT"] = _rx_one(r"Height")
    if not out["WEIGHT"]:
        out["WEIGHT"] = _rx_one(r"Weight")
    if not out["REACH"]:
        out["REACH"]  = _rx_one(r"(?:Reach|Arm Reach)")
    if not out["STANCE"]:
        out["STANCE"] = _rx_one(r"Stance")
    if not out["DOB"]:
        out["DOB"]    = _rx_one(r"(?:DOB|Date of Birth)")

    # final cleanup (some values contain trailing labels accidentally)
    for k in list(out.keys()):
        out[k] = _clean_value(out[k])

    return out



# organise fighter tale of the tape
def organise_fighter_tott(fighter_tott: dict, column_order: list, url: str) -> pd.DataFrame:
    """
    Aligns parsed dict to your YAML columns, fills blanks, and adds URL.
    """
    row = {c: "" for c in column_order}
    for c in ("FIGHTER", "HEIGHT", "WEIGHT", "REACH", "STANCE", "DOB"):
        if c in row and c in fighter_tott:
            row[c] = fighter_tott[c]
    if "URL" in row:
        row["URL"] = url
    return pd.DataFrame([row], columns=column_order)



# reorder columns
def move_columns(df: pd.DataFrame, cols_to_move=None, ref_col="", place="before") -> pd.DataFrame:
    cols_to_move = cols_to_move or []
    cols = list(df.columns)
    if ref_col not in cols:
        return df
    # remove duplicates from cols_to_move and keep order
    cols_to_move = [c for c in cols_to_move if c in cols and c != ref_col]
    keep = [c for c in cols if c not in cols_to_move]
    idx = keep.index(ref_col)
    if place == "after":
        new_order = keep[:idx+1] + cols_to_move + keep[idx+1:]
    else:
        new_order = keep[:idx] + cols_to_move + [ref_col] + keep[idx+1:]
    return df.reindex(columns=new_order)