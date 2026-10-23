from pathlib import Path
import math
import re

import pandas as pd
import streamlit as st


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="NammaTrip AI | Karnataka Travel Planner",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 2. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "destinations.csv"

REQUIRED_COLUMNS = [
    "name",
    "region",
    "categories",
    "visit_hours",
    "entry_fee_estimate",
    "description",
    "why_visit",
]

INTERESTS = [
    "Nature",
    "Adventure",
    "History",
    "Culture",
    "Wildlife",
    "Beaches",
    "Food",
    "Spiritual",
    "Waterfalls",
    "Photography",
    "Family",
    "Education",
    "Science",
]

STAY_RATES = {
    "Budget": 700,
    "Standard": 1400,
    "Comfort": 2600,
}

TRANSPORT_RATES = {
    "Public transport": 500,
    "Shared cab": 1000,
    "Private cab": 2500,
}

FOOD_COST_PER_PERSON_PER_DAY = 450
CONTINGENCY_PERCENT = 0.10


# ============================================================
# 3. USER INTERFACE STYLING
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f7faf7;
        color: #1f2937;
    }

    [data-testid="stAppViewContainer"] {
        background-color: #f7faf7;
    }

    [data-testid="stHeader"] {
        background-color: rgba(247, 250, 247, 0.95);
    }

    .hero {
        padding: 32px;
        border-radius: 20px;
        background: linear-gradient(120deg, #123c2b, #16865a);
        margin-bottom: 24px;
    }

    .hero h1 {
        color: #ffffff !important;
        font-size: 42px;
        margin-bottom: 10px;
    }

    .hero p {
        color: #ffffff !important;
        font-size: 17px;
        line-height: 1.6;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stCaptionContainer"] {
        color: #1f2937;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #1f2937 !important;
    }

    [data-testid="stSidebar"] {
        background-color: #20242c;
    }

    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #ffffff !important;
    }

    [data-testid="stExpander"] {
        background-color: #ffffff;
        border: 1px solid #dce5dd;
        border-radius: 12px;
    }

    [data-testid="stTabs"] button {
        font-weight: 600;
    }

    .small-muted {
        color: #64748b !important;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. LOAD AND VALIDATE DESTINATION DATA
# ============================================================

@st.cache_data
def load_destinations(file_path, modified_time):
    """Load destination information from the CSV file."""

    # The timestamp forms part of Streamlit's cache key.
    del modified_time

    df = pd.read_csv(file_path, encoding="utf-8-sig")

    # Normalize column names.
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[\s\-]+", "_", regex=True)
    )

    missing_columns = sorted(
        set(REQUIRED_COLUMNS) - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing columns in destinations.csv: "
            + ", ".join(missing_columns)
        )

    # Clean text fields.
    text_columns = [
        "name",
        "region",
        "categories",
        "description",
        "why_visit",
    ]

    for column in text_columns:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # Convert numeric fields safely.
    df["visit_hours"] = pd.to_numeric(
        df["visit_hours"],
        errors="coerce",
    ).fillna(2).clip(lower=0.5, upper=24)

    df["entry_fee_estimate"] = pd.to_numeric(
        df["entry_fee_estimate"],
        errors="coerce",
    ).fillna(0).clip(lower=0)

    # Remove unnamed destinations.
    df = df[df["name"] != ""].copy()

    # Split categories regardless of whether commas or semicolons
    # are used in the CSV.
    df["category_list"] = df["categories"].apply(
        lambda value: [
            item.strip().casefold()
            for item in re.split(r"[;,]", value)
            if item.strip()
        ]
    )

    # Avoid duplicate destination entries.
    df = df.drop_duplicates(
        subset=["name", "region"],
        keep="first",
    )

    if df.empty:
        raise ValueError(
            "destinations.csv does not contain any valid destinations."
        )

    return df.reset_index(drop=True)


if not CSV_FILE.exists():
    st.error(
        "Destination data not found. Place destinations.csv "
        "in the same folder as app.py."
    )
    st.code(f"Expected location: {CSV_FILE}")
    st.stop()

try:
    destinations_df = load_destinations(
        str(CSV_FILE),
        CSV_FILE.stat().st_mtime,
    )
except Exception as error:
    st.error("Could not load the destination database.")
    st.exception(error)
    st.info(
        "Check that destinations.csv contains all seven required "
        "columns and is saved as a valid CSV file."
    )
    st.stop()


# ============================================================
# 5. RECOMMENDATION ENGINE
# ============================================================

def recommend_destinations(
    df,
    interests,
    max_places,
    selected_regions=None,
    search_text="",
):
    """
    Rank destinations by interest matches and apply filters.
    Matching is based on the categories in the CSV.
    """

    result = df.copy()

    selected_regions = selected_regions or []

    # Filter by selected regions.
    if selected_regions:
        result = result[
            result["region"].isin(selected_regions)
        ]

    # Filter by search text.
    query = search_text.strip().casefold()

    if query:
        searchable_columns = [
            "name",
            "region",
            "categories",
            "description",
            "why_visit",
        ]

        mask = pd.Series(False, index=result.index)

        for column in searchable_columns:
            mask |= result[column].str.casefold().str.contains(
                query,
                regex=False,
                na=False,
            )

        result = result[mask]

    selected = {
        interest.strip().casefold()
        for interest in interests
    }

    def matched_categories(categories):
        return sorted(set(categories) & selected)

    result["matched_categories"] = result[
        "category_list"
    ].apply(matched_categories)

    result["match_score"] = result[
        "matched_categories"
    ].apply(len)

    # When interests are selected, matching destinations come first.
    # Alphabetical ordering makes ties predictable.
    result = result.sort_values(
        by=["match_score", "name"],
        ascending=[False, True],
        kind="stable",
    )

    return result.head(max_places).reset_index(drop=True)


# ============================================================
# 6. ITINERARY BUILDER
# ============================================================

def build_itinerary(places, number_of_days):
    """
    Distribute destinations across days while balancing estimated
    sightseeing hours. This does not calculate road distances.
    """

    itinerary = {
        day: [] for day in range(1, number_of_days + 1)
    }

    daily_hours = [0.0] * number_of_days

    if places.empty:
        return itinerary

    # Schedule longer visits first.
    ordered = places.sort_values(
        by=["visit_hours", "name"],
        ascending=[False, True],
        kind="stable",
    )

    assigned_names = set()

    for _, place in ordered.iterrows():
        name = str(place["name"]).strip()

        if name in assigned_names:
            continue

        # Assign the next place to the day with the fewest
        # currently scheduled sightseeing hours.
        day_index = min(
            range(number_of_days),
            key=lambda index: (daily_hours[index], index),
        )

        itinerary[day_index + 1].append(place)

        daily_hours[day_index] += float(
            place["visit_hours"]
        )

        assigned_names.add(name)

    return itinerary


# ============================================================
# 7. BUDGET CALCULATOR
# ============================================================

def calculate_budget(
    places,
    travelers,
    days,
    stay_style,
    transport_style,
):
    """Calculate an illustrative trip budget in Indian rupees."""

    travelers = int(travelers)
    days = int(days)

    food_cost = (
        FOOD_COST_PER_PERSON_PER_DAY
        * travelers
        * days
    )

    accommodation_cost = (
        STAY_RATES[stay_style]
        * travelers
        * days
    )

    # Simple trip-wide transport allowance.
    transport_cost = (
        TRANSPORT_RATES[transport_style]
        * travelers
    )

    # The CSV entry fees are estimates, not live prices.
    entry_cost = round(
        float(places["entry_fee_estimate"].sum())
        * travelers
    )

    subtotal = (
        food_cost
        + accommodation_cost
        + transport_cost
        + entry_cost
    )

    extra_allowance = math.ceil(
        subtotal * CONTINGENCY_PERCENT
    )

    total = subtotal + extra_allowance

    return {
        "food": food_cost,
        "accommodation": accommodation_cost,
        "transport": transport_cost,
        "entry": entry_cost,
        "subtotal": subtotal,
        "extra": extra_allowance,
        "total": total,
    }


# ============================================================
# 8. SIDEBAR INPUTS
# ============================================================

st.sidebar.title("🧭 Plan Your Trip")
st.sidebar.caption("Build your Karnataka getaway.")

origin_choice = st.sidebar.selectbox(
    "Starting city",
    [
        "Bengaluru",
        "Mysuru",
        "Mangaluru",
        "Hubballi",
        "Belagavi",
        "Shivamogga",
        "Other",
    ],
)

if origin_choice == "Other":
    origin = st.sidebar.text_input(
        "Enter your starting city",
        value="",
    ).strip()
else:
    origin = origin_choice

days = st.sidebar.slider(
    "Trip duration",
    min_value=1,
    max_value=10,
    value=3,
    format="%d days",
)

travelers = st.sidebar.number_input(
    "Number of travellers",
    min_value=1,
    max_value=20,
    value=2,
    step=1,
)

budget_limit = st.sidebar.number_input(
    "Your total budget (₹)",
    min_value=1000,
    max_value=1000000,
    value=15000,
    step=1000,
)

stay_style = st.sidebar.selectbox(
    "Accommodation",
    list(STAY_RATES.keys()),
    index=1,
)

transport_style = st.sidebar.selectbox(
    "Transport preference",
    list(TRANSPORT_RATES.keys()),
    index=1,
)

interests = st.sidebar.multiselect(
    "Select your interests",
    INTERESTS,
    default=["Nature", "History"],
)

available_regions = sorted(
    destinations_df["region"].dropna().unique().tolist()
)

selected_regions = st.sidebar.multiselect(
    "Preferred regions (optional)",
    available_regions,
    default=[],
)

max_places = st.sidebar.slider(
    "Maximum recommended places",
    min_value=1,
    max_value=min(20, len(destinations_df)),
    value=min(6, len(destinations_df)),
)

generate_button = st.sidebar.button(
    "✨ Generate My Travel Plan",
    type="primary",
    use_container_width=True,
)


# ============================================================
# 9. MAIN HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>🌿 NammaTrip AI</h1>
        <p>Your Karnataka travel companion.</p>
        <p>
            Discover destinations, build your itinerary,
            explore Kannada phrases and estimate trip expenses.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    f"📍 Starting point: {origin or 'Not specified'}"
)

if generate_button:
    st.session_state["plan_generated"] = True
    st.session_state["plan_settings"] = {
        "origin": origin,
        "days": days,
        "travelers": travelers,
        "interests": interests,
        "regions": selected_regions,
        "max_places": max_places,
    }

    st.success("Your travel plan has been generated!")


# ============================================================
# 10. GENERATE CURRENT RECOMMENDATIONS
# ============================================================

recommended = recommend_destinations(
    destinations_df,
    interests,
    max_places,
    selected_regions=selected_regions,
)

budget_data = calculate_budget(
    recommended,
    travelers,
    days,
    stay_style,
    transport_style,
)


# ============================================================
# 11. SUMMARY METRICS
# ============================================================

metric1, metric2, metric3, metric4 = st.columns(4)

with metric1:
    st.metric("Trip duration", f"{days} days")

with metric2:
    st.metric("Travellers", int(travelers))

with metric3:
    st.metric("Recommended places", len(recommended))

with metric4:
    st.metric("Estimated total", f"₹{budget_data['total']:,}")

st.divider()


# ============================================================
# 12. APPLICATION TABS
# ============================================================

tab_itinerary, tab_explore, tab_budget, tab_kannada, tab_about = (
    st.tabs(
        [
            "🗺️ Itinerary",
            "🌄 Explore Destinations",
            "💰 Budget",
            "🗣️ Kannada Phrases",
            "ℹ️ About",
        ]
    )
)


# ============================================================
# TAB 1: ITINERARY
# ============================================================

with tab_itinerary:
    st.subheader("Your Recommended Trip")

    if recommended.empty:
        st.warning(
            "No destinations match your current filters. "
            "Clear the region filter or change your interests."
        )

    else:
        st.success(
            f"Found {len(recommended)} destination(s) "
            f"for your {days}-day trip."
        )

        if interests:
            st.write(
                "Destinations are ranked by how well their "
                "categories match your selected interests."
            )
        else:
            st.info(
                "No interests selected. Showing destinations "
                "in alphabetical order."
            )

        itinerary = build_itinerary(
            recommended,
            days,
        )

        for day_number in range(1, days + 1):
            day_places = itinerary.get(day_number, [])

            with st.expander(
                f"Day {day_number} — {len(day_places)} destination(s)",
                expanded=(day_number == 1),
            ):
                if not day_places:
                    st.info(
                        "No destination assigned to this day."
                    )
                    continue

                total_hours = sum(
                    float(place["visit_hours"])
                    for place in day_places
                )

                st.caption(
                    f"Estimated sightseeing time: {total_hours:g} hours"
                )

                for place in day_places:
                    st.markdown(
                        f"### 📍 {place['name']}"
                    )

                    st.write(
                        f"**Region:** {place['region']}"
                    )

                    st.write(place["description"])

                    st.write(
                        f"**Why visit:** {place['why_visit']}"
                    )

                    st.write(
                        f"**Visit duration:** "
                        f"{float(place['visit_hours']):g} hours"
                    )

                    st.write(
                        f"**Entry fee estimate:** "
                        f"₹{float(place['entry_fee_estimate']):,.0f} "
                        "per person"
                    )

                    matched = place["matched_categories"]

                    if matched:
                        st.write(
                            "**Matched interests:** "
                            + ", ".join(
                                item.title() for item in matched
                            )
                        )

                    st.divider()

        # Download the selected destinations.
        export_columns = [
            "name",
            "region",
            "categories",
            "visit_hours",
            "entry_fee_estimate",
            "description",
            "why_visit",
        ]

        export_data = recommended[
            export_columns
        ].to_csv(index=False)

        st.download_button(
            label="⬇️ Download My Itinerary",
            data=export_data,
            file_name="nammatrip_itinerary.csv",
            mime="text/csv",
        )


# ============================================================
# TAB 2: EXPLORE DESTINATIONS
# ============================================================

with tab_explore:
    st.subheader("Explore Karnataka")

    search_text = st.text_input(
        "Search by destination, region or category",
        key="destination_search",
        placeholder="Example: Hampi, beaches, nature...",
    )

    search_results = recommend_destinations(
        destinations_df,
        interests=[],
        max_places=len(destinations_df),
        selected_regions=selected_regions,
        search_text=search_text,
    )

    st.caption(
        f"{len(search_results)} destination(s) found."
    )

    if search_results.empty:
        st.info(
            "No matching places found. Try another search "
            "or clear the region filter."
        )

    else:
        for _, place in search_results.iterrows():
            with st.container(border=True):
                st.markdown(
                    f"### 📍 {place['name']}"
                )

                st.write(
                    f"**Region:** {place['region']}"
                )

                st.write(
                    f"**Categories:** {place['categories']}"
                )

                st.write(place["description"])

                st.write(
                    f"**Why visit:** {place['why_visit']}"
                )

                st.caption(
                    f"Visit duration: "
                    f"{float(place['visit_hours']):g} hours "
                    f"| Entry fee estimate: "
                    f"₹{float(place['entry_fee_estimate']):,.0f} "
                    "per person"
                )


# ============================================================
# TAB 3: BUDGET
# ============================================================

with tab_budget:
    st.subheader("Your Estimated Trip Budget")

    st.info(
        "These are illustrative planning estimates, not live prices. "
        "Actual accommodation, food, transport and entry fees may differ."
    )

    budget_left, budget_right = st.columns(2)

    with budget_left:
        st.metric(
            "Food",
            f"₹{budget_data['food']:,}",
        )

        st.metric(
            "Accommodation",
            f"₹{budget_data['accommodation']:,}",
        )

        st.metric(
            "Transport",
            f"₹{budget_data['transport']:,}",
        )

    with budget_right:
        st.metric(
            "Entry fees",
            f"₹{budget_data['entry']:,}",
        )

        st.metric(
            "Extra allowance (10%)",
            f"₹{budget_data['extra']:,}",
        )

        st.metric(
            "Estimated total",
            f"₹{budget_data['total']:,}",
        )

    st.divider()

    if budget_data["total"] <= budget_limit:
        st.success(
            f"Your estimated trip is within budget. "
            f"Remaining amount: "
            f"₹{budget_limit - budget_data['total']:,}."
        )

    else:
        st.warning(
            f"The estimated trip exceeds your budget by "
            f"₹{budget_data['total'] - budget_limit:,}."
        )

        st.write(
            "Consider choosing Budget accommodation, "
            "public transport, or fewer destinations."
        )

    st.markdown("#### Calculation assumptions")

    st.write(
        f"- Food: ₹{FOOD_COST_PER_PERSON_PER_DAY:,} "
        "per person per day."
    )

    st.write(
        f"- Accommodation: ₹{STAY_RATES[stay_style]:,} "
        "per person per day."
    )

    st.write(
        f"- Transport: ₹{TRANSPORT_RATES[transport_style]:,} "
        "per person for the trip."
    )

    st.write(
        "- Entry fees are estimated from the selected destination records."
    )

    st.write(
        "- An additional 10% allowance is added for unexpected expenses."
    )


# ============================================================
# TAB 4: KANNADA PHRASES
# ============================================================

with tab_kannada:
    st.subheader("Useful Kannada Travel Phrases")

    phrases = [
        (
            "Hello",
            "ನಮಸ್ಕಾರ",
            "Namaskara",
        ),
        (
            "Thank you",
            "ಧನ್ಯವಾದಗಳು",
            "Dhanyavaadagalu",
        ),
        (
            "How much is this?",
            "ಇದು ಎಷ್ಟು?",
            "Idu eshtu?",
        ),
        (
            "Where is the bus stand?",
            "ಬಸ್ ನಿಲ್ದಾಣ ಎಲ್ಲಿದೆ?",
            "Bus nildana ellide?",
        ),
        (
            "Please help me",
            "ದಯವಿಟ್ಟು ಸಹಾಯ ಮಾಡಿ",
            "Dayavittu sahaaya maadi",
        ),
        (
            "I need water",
            "ನನಗೆ ನೀರು ಬೇಕು",
            "Nanage neeru beku",
        ),
        (
            "Where is the toilet?",
            "ಶೌಚಾಲಯ ಎಲ್ಲಿದೆ?",
            "Shauchalaya ellide?",
        ),
    ]

    for english, kannada, pronunciation in phrases:
        with st.container(border=True):
            st.markdown(f"**{english}**")
            st.write(f"Kannada: {kannada}")
            st.caption(f"Pronunciation: {pronunciation}")


# ============================================================
# TAB 5: ABOUT
# ============================================================

with tab_about:
    st.subheader("About NammaTrip AI")

    st.write(
        """
        NammaTrip AI is a Karnataka-focused travel-planning prototype.
        It helps travellers discover destinations, organize sightseeing,
        and estimate travel expenses using a local destination dataset.
        """
    )

    st.markdown("#### Current features")

    st.markdown(
        """
        - Interest-based destination recommendations
        - Region filters
        - Day-wise sightseeing allocation
        - Budget estimates
        - Destination search
        - Kannada travel phrases
        - CSV itinerary download
        """
    )

    st.markdown("#### Current limitations")

    st.markdown(
        """
        - Does not calculate actual road distances.
        - Does not optimize driving routes or traffic.
        - Does not fetch live hotel or ticket prices.
        - Does not currently use a generative AI model.
        - Destination data and fees should be verified before travel.
        """
    )


# ============================================================
# 13. FOOTER
# ============================================================

st.divider()

st.markdown(
    """
    <p class="small-muted" style="text-align:center;">
        NammaTrip AI • Discover Karnataka thoughtfully 🌿
    </p>
    """,
    unsafe_allow_html=True,
)