import streamlit as st
from anthropic import Anthropic
import json
from pypdf import PdfReader
from pptx import Presentation

# Page config
st.set_page_config(
    page_title="Fundraising Co-Pilot",
    page_icon="🚀",
    layout="centered"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        max-width: 800px;
        margin: 0 auto;
    }
    .main-header {
        text-align: center;
        padding: 1rem 0 2rem 0;
    }
    .main-header h1 {
        color: #1a1a1a;
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    .main-header p {
        color: #666;
        font-size: 1rem;
    }
    .footer {
        text-align: center;
        padding: 2rem 0;
        color: #888;
        font-size: 0.85rem;
    }
    .upload-section {
        padding: 0.5rem 0;
        border-top: 1px solid #eee;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Load investor database
@st.cache_data
def load_investors():
    with open("investors.json", "r") as f:
        return json.load(f)

INVESTORS = load_investors()

# Function to search/filter investors
def find_matching_investors(stage=None, sector_keywords=None, geography=None, investor_type=None, max_results=20):
    """Filter investors based on criteria"""
    matches = []
    
    for inv in INVESTORS:
        score = 0
        
        # Stage matching
        if stage and inv.get('stage'):
            inv_stages = inv['stage'].lower()
            if 'pre-seed' in stage.lower() or 'prototype' in stage.lower() or 'idea' in stage.lower():
                if 'prototype' in inv_stages or 'idea' in inv_stages or 'early revenue' in inv_stages:
                    score += 3
            elif 'seed' in stage.lower() or 'early revenue' in stage.lower():
                if 'early revenue' in inv_stages or 'prototype' in inv_stages:
                    score += 3
            elif 'series a' in stage.lower() or 'scaling' in stage.lower():
                if 'scaling' in inv_stages or 'growth' in inv_stages:
                    score += 3
        
        # Sector/thesis matching
        if sector_keywords and inv.get('thesis'):
            thesis_lower = inv['thesis'].lower()
            for keyword in sector_keywords:
                if keyword.lower() in thesis_lower:
                    score += 2
        
        # Geography matching
        if geography and inv.get('countries'):
            countries_lower = inv['countries'].lower()
            if geography.lower() in countries_lower or 'uk' in countries_lower:
                score += 2
        
        # Investor type preference
        if investor_type:
            if investor_type.lower() in inv.get('type', '').lower():
                score += 1
        
        # Must have some thesis or stage info to be useful
        if score > 0 and (inv.get('thesis') or inv.get('stage')):
            matches.append((score, inv))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matches[:max_results]]


def format_investor_for_context(investors):
    """Format investor list for inclusion in AI context"""
    if not investors:
        return "No matching investors found in the database."
    
    formatted = []
    for inv in investors:
        parts = [f"**{inv['name']}** ({inv['type']})"]
        if inv.get('stage'):
            parts.append(f"  - Stage: {inv['stage']}")
        if inv.get('thesis'):
            thesis = inv['thesis'][:300] + "..." if len(inv['thesis']) > 300 else inv['thesis']
            parts.append(f"  - Thesis: {thesis}")
        if inv.get('cheque_min') or inv.get('cheque_max'):
            cheque = f"{inv.get('cheque_min', '?')} - {inv.get('cheque_max', '?')}"
            parts.append(f"  - Cheque size: {cheque}")
        if inv.get('countries'):
            countries = inv['countries'][:100] + "..." if len(inv['countries']) > 100 else inv['countries']
            parts.append(f"  - Geography: {countries}")
        if inv.get('website'):
            parts.append(f"  - Website: {inv['website']}")
        formatted.append("\n".join(parts))
    
    return "\n\n".join(formatted)


def extract_text_from_pdf(file):
    """Extract text from PDF file"""
    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_text_from_pptx(file):
    """Extract text from PowerPoint file"""
    prs = Presentation(file)
    text = ""
    for slide_num, slide in enumerate(prs.slides, 1):
        text += f"\n--- Slide {slide_num} ---\n"
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text += shape.text + "\n"
    return text


def extract_deck_content(uploaded_file):
    """Extract text content from uploaded deck file"""
    if uploaded_file is None:
        return None
    
    try:
        if uploaded_file.type == "application/pdf":
            return extract_text_from_pdf(uploaded_file)
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return extract_text_from_pptx(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return None
    
    return None


# System prompt
SYSTEM_PROMPT = """You are Fundraising Co-Pilot, an on-demand decision support assistant for early-stage founders who are actively fundraising or about to start.

Your role is to help founders make better fundraising decisions in real time, using an investor's perspective — so small mistakes don't compound.

You are trained on:
- A curated pre-seed and seed investor database (stage, cheque size, thesis, geography)
- Fundraising heuristics and judgment patterns used by experienced investors
- Examples of effective and ineffective investor outreach
- Common early-stage fundraising pitfalls

## What You Help With
You help founders:
- Pressure-test pitch decks from an investor point of view
- Improve investor outreach emails before sending
- Sanity-check which investors are a realistic fit (and who to avoid)
- Clarify fundraising readiness and next priorities
- Understand likely objections investors will have
- **Find relevant investors from the database based on their startup's stage, sector, and geography**

You explain WHY, not just what.

## Tone & Style
- Calm, direct, non-hypey
- Investor-realistic, not motivational
- Clear about trade-offs and uncertainty
- Willing to say when something is unclear, premature, or risky
- Assume the founder is smart but missing insider context

## Guardrails (VERY IMPORTANT)
You must never:
- Promise funding, responses, or introductions
- Claim certainty about investor decisions
- Act as legal, financial, or investment advice
- Encourage mass or untargeted investor outreach
- Replace human judgment or live coaching

If asked for guarantees, respond with:
"There are no guarantees in fundraising — what I can do is help you reduce avoidable mistakes and improve clarity."

## How to Respond
When reviewing anything (deck, email, strategy):
1. Start with what's unclear or risky
2. Explain how an investor is likely interpreting it
3. Suggest specific improvements
4. End with 1–3 concrete next actions

**IMPORTANT: When a pitch deck is provided in the conversation, ALWAYS analyze it specifically. Do not give generic advice. Reference specific content from their deck.**

When a pitch deck is provided:
1. Assess overall clarity and narrative flow based on THEIR specific content
2. Identify red flags an investor would notice in THEIR deck
3. Point out missing or weak sections specific to what they've shared
4. Give specific slide-by-slide feedback referencing THEIR actual slides
5. Suggest 2-3 priority improvements based on what YOU SEE in their deck

When recommending investors:
1. Confirm the founder's stage, sector, and geography
2. Explain why each investor might be a good fit (based on thesis/stage match)
3. Flag any potential mismatches or concerns
4. Recommend researching each investor before outreach
5. Remind them that warm intros are always better than cold outreach

If information is missing, ask one or two focused follow-up questions, not many.

## Default Framing
Use often: "From an investor's perspective…"

---

## KEY HEURISTICS AND FRAMEWORKS

### What Makes a Deck Unclear (Instant Red Flags)
- **The "Vague Verb" Trap**: Using words like "disrupting," "optimizing," or "leveraging" without a direct object. Bad: "We leverage AI to optimize synergy." Good: "Our AI reduces shipping costs by 15% via route-batching."
- **The "Mystery Product" Slide**: If by slide 4 an investor doesn't know if this is a mobile app, a hardware sensor, or a Chrome extension, the deck is dead.
- **Missing Headlines**: Slides titled "Our Solution" or "Traction" waste prime real estate. Good slides use the title as a conclusion: "15% MoM Growth Driven by Direct Sales"
- **The "Messy Logic" Gap**: The Problem slide describes a global catastrophe, but the Solution slide describes a niche tool. The scale doesn't match.

### Common Pre-Seed Red Flags
- **"We Need Money to Build the MVP"**: In 2026, with no-code and AI, building a prototype costs almost zero. This signals lack of resourcefulness.
- **The Outsourced Founder**: Core tech or sales strategy outsourced to an agency before the first hire.
- **TAM via "1% of a $100B Market"**: Real founders pitch "Bottom-Up" (e.g., "5,000 mid-sized law firms × £1k/mo").
- **Messy Cap Table**: Too many advisors taking 5% for nothing, or 50/50 split with a co-founder who has a full-time job.

### What Investors Actually Listen For
- **Earned Insight**: Did the founder discover something non-obvious by talking to 100 customers?
- **Speed of Iteration**: How much has happened since the last meeting?
- **Unit Economics Intuition**: Know your CAC and Margin.
- **The "Why Now"**: What changed recently (regulatory, technical, social) that makes this possible today?

### When It's "Too Early" to Raise
- **No "Proof of Demand"**: Waitlist but zero pilots or LOIs.
- **Founder-Problem Mismatch**: Building MedTech with no healthcare experience.
- **Unclear Milestones**: Don't know what the money gets you to.
- **"Self-Validation" Loop**: Only feedback from friends and family.

### Top Reasons Investors Say No
1. Lack of traction or validation
2. Poor storytelling or pitch delivery
3. Unclear or weak business model
4. Team concerns
5. Market timing/size issues
6. Competitive positioning unclear

### Good vs Bad Outreach

**BAD - The "Life Story" Email:**
Long personal history, vague subject line, asking for 60-min meeting before proving value, "we only need 1% of the market."

**BAD - The "Bot" Email:**
"We leverage blockchain to optimize digital transformation synergy." Zero research on investor, no traction mentioned.

**GOOD - The "Traction Lead":**
Subject: [Startup] // 25% MoM Growth // Ex-Google Team // Pre-Seed
- References specific portfolio companies
- Leads with traction metrics
- Specific ask (15-min call on Tuesday/Wednesday)
- DocSend link, not attachment

### The "One-Minute Rule"
Investors spend <60 seconds on a teaser deck. Every slide title should state the main takeaway.

---

## INVESTOR DATABASE
You have access to a database of 3,600+ investors including VCs, angels, and angel networks. When a founder asks for investor recommendations, use the provided investor matches to give specific, actionable suggestions. Always encourage them to:
1. Research each investor's recent investments
2. Look for warm intro paths (LinkedIn, portfolio founders)
3. Personalize outreach based on the investor's thesis

---

## Final Reminder
You are decision support, not a decision maker.
Your goal is clarity, not confidence theatre.

**CRITICAL: If pitch deck content is included in the user's message, you MUST analyze that specific deck. Do not give generic advice when you have their actual deck to review.**
"""

# Initialize Anthropic client
@st.cache_resource
def get_client():
    return Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# Header
st.markdown("""
<div class="main-header">
    <h1>🚀 Fundraising Co-Pilot</h1>
    <p>AI-powered fundraising decision support, built by an investor for underestimated founders</p>
</div>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "startup_context" not in st.session_state:
    st.session_state.startup_context = {}
if "deck_content" not in st.session_state:
    st.session_state.deck_content = None
if "deck_filename" not in st.session_state:
    st.session_state.deck_filename = None

# File uploader - FIRST, before anything else
st.markdown("📎 **Upload your pitch deck** (PDF or PowerPoint)")
uploaded_file = st.file_uploader(
    "Upload deck",
    type=["pdf", "pptx"],
    help="Upload a PDF or PowerPoint deck to get specific feedback",
    label_visibility="collapsed"
)

# Process uploaded file immediately
if uploaded_file is not None:
    # Check if this is a new file
    if st.session_state.deck_filename != uploaded_file.name:
        deck_content = extract_deck_content(uploaded_file)
        if deck_content:
            st.session_state.deck_content = deck_content
            st.session_state.deck_filename = uploaded_file.name
            st.success(f"✅ Deck loaded: {uploaded_file.name} ({len(deck_content)} characters extracted)")
            
            if len(deck_content.strip()) < 300:
                st.warning("⚠️ We couldn't extract much text. If your deck is image-heavy, feedback may be limited.")
        else:
            st.error("Could not extract content from file.")
    else:
        st.success(f"✅ Using: {uploaded_file.name}")
elif st.session_state.deck_content:
    st.info(f"📄 Deck still loaded: {st.session_state.deck_filename}")

st.markdown("---")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Starter prompts for new users (only show if no messages yet)
if not st.session_state.messages:
    st.markdown("**What can I help you with?**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Review my pitch deck", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Please review my pitch deck from an investor's perspective. Be specific about what's working and what needs improvement."
            else:
                starter = "I'd like you to review my pitch deck. Please upload it using the file uploader above first."
            st.session_state.starter_prompt = starter
            st.rerun()
        if st.button("🎯 Am I ready to raise?", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Based on my pitch deck, am I ready to start fundraising? What proof points am I missing? Be specific about what you see in my deck."
            else:
                starter = "How do I know if I'm ready to start fundraising? What proof points should I have before approaching investors? (Tip: upload your deck above for specific feedback)"
            st.session_state.starter_prompt = starter
            st.rerun()
    with col2:
        if st.button("🔍 Find investors for me", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Based on my pitch deck, help me find 5-10 investors who might be a good fit. Look at my sector, stage, and what I'm building."
            else:
                starter = "I need help finding investors who might be a good fit for my startup. Can you help me identify 5-10 relevant investors? Tell me about your startup first."
            st.session_state.starter_prompt = starter
            st.rerun()
        if st.button("✉️ Review my outreach email", use_container_width=True):
            starter = "I want to send a cold email to an investor. What makes the difference between an email that gets ignored vs one that gets a response?"
            st.session_state.starter_prompt = starter
            st.rerun()

# Handle starter prompts
if "starter_prompt" in st.session_state:
    prompt = st.session_state.starter_prompt
    del st.session_state.starter_prompt
    
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Build the full prompt with deck content if available
    full_prompt = prompt
    if st.session_state.deck_content:
        full_prompt = f"""{prompt}

---
**PITCH DECK CONTENT** (from {st.session_state.deck_filename}):

{st.session_state.deck_content[:15000]}

---
IMPORTANT: Analyze THIS SPECIFIC DECK above. Reference specific slides, content, and issues you see. Do not give generic advice.
"""
    
    client = get_client()
    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": full_prompt}]
            )
            assistant_message = response.content[0].text
            st.markdown(assistant_message)
    
    st.session_state.messages.append({"role": "assistant", "content": assistant_message})
    st.rerun()

# Chat input
if prompt := st.chat_input("Describe your startup or ask a fundraising question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Check if this looks like an investor search request
    investor_keywords = ['investor', 'investors', 'find', 'recommend', 'who should i pitch', 'vc', 'angel', 'funding', 'fit for my']
    is_investor_search = any(kw in prompt.lower() for kw in investor_keywords)
    
    # Build additional context - ALWAYS include deck if available
    additional_context = ""
    
    # ALWAYS add deck content if available
    if st.session_state.deck_content:
        additional_context += f"""

---
**PITCH DECK CONTENT** (from {st.session_state.deck_filename}):

{st.session_state.deck_content[:15000]}

---
IMPORTANT: Use this deck content to give specific, personalized feedback. Reference their actual slides and content.
"""
    
    # Add investor matches if relevant
    if is_investor_search:
        # Try to extract stage
        stage = None
        if any(s in prompt.lower() for s in ['pre-seed', 'preseed', 'idea', 'prototype']):
            stage = "pre-seed"
        elif any(s in prompt.lower() for s in ['seed', 'early revenue', 'mvp']):
            stage = "seed"
        elif any(s in prompt.lower() for s in ['series a', 'scaling', 'growth']):
            stage = "series a"
        
        # Try to extract sector keywords
        sector_keywords = []
        sectors = ['ai', 'fintech', 'healthtech', 'health', 'saas', 'b2b', 'b2c', 'consumer', 'enterprise', 
                   'climate', 'sustainability', 'edtech', 'proptech', 'foodtech', 'biotech', 'deeptech',
                   'marketplace', 'ecommerce', 'gaming', 'web3', 'blockchain', 'crypto', 'defi',
                   'mental health', 'wellness', 'fashion', 'retail', 'logistics', 'hr', 'legal',
                   'insurance', 'insurtech', 'regtech', 'cybersecurity', 'security', 'iot', 'robotics',
                   'energy', 'cleantech', 'agtech', 'space', 'mobility', 'transport', 'social impact', 'impact']
        for sector in sectors:
            if sector in prompt.lower():
                sector_keywords.append(sector)
        
        # Also try to extract from deck content if available
        if st.session_state.deck_content and not sector_keywords:
            deck_lower = st.session_state.deck_content.lower()
            for sector in sectors:
                if sector in deck_lower:
                    sector_keywords.append(sector)
        
        # Try to extract geography
        geography = None
        if any(g in prompt.lower() for g in ['uk', 'united kingdom', 'london', 'britain']):
            geography = "UK"
        elif any(g in prompt.lower() for g in ['us', 'usa', 'united states', 'america']):
            geography = "USA"
        elif any(g in prompt.lower() for g in ['europe', 'eu']):
            geography = "Europe"
        
        # Find matching investors
        if stage or sector_keywords:
            matches = find_matching_investors(
                stage=stage,
                sector_keywords=sector_keywords if sector_keywords else None,
                geography=geography,
                max_results=15
            )
            
            if matches:
                additional_context += f"""

---
**INVESTOR DATABASE RESULTS**
Based on the startup, here are potentially relevant investors from the database:

{format_investor_for_context(matches)}

Recommend 5-10 investors that seem like the best fit. Explain WHY each might be relevant. Remind them to research each one and look for warm intro paths.
---
"""
    
    # Get assistant response
    client = get_client()
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Build messages for API
            messages_for_api = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            
            # Add current message with context
            current_message = prompt + additional_context
            messages_for_api.append({"role": "user", "content": current_message})
            
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                system=SYSTEM_PROMPT,
                messages=messages_for_api
            )
            assistant_message = response.content[0].text
            st.markdown(assistant_message)
    
    st.session_state.messages.append({"role": "assistant", "content": assistant_message})

# Clear chat button
if st.session_state.messages:
    if st.button("🔄 Start new conversation", type="secondary"):
        st.session_state.messages = []
        st.session_state.startup_context = {}
        st.session_state.deck_content = None
        st.session_state.deck_filename = None
        st.rerun()

# Footer
st.markdown("""
<div class="footer">
    Built by <a href="https://thefundraisingaccelerator.com" target="_blank">The Fundraising Accelerator</a><br>
    Your network should not determine your net worth.<br><br>
    <small>⚠️ This is decision support, not advice. There are no guarantees in fundraising.</small>
</div>
""", unsafe_allow_html=True)
