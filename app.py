import streamlit as st
from anthropic import Anthropic
import json
from pypdf import PdfReader
from pptx import Presentation
import tempfile
import os

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
</style>
""", unsafe_allow_html=True)

# Load investor database
@st.cache_data
def load_investors():
    with open("investors.json", "r") as f:
        return json.load(f)

INVESTORS = load_investors()


def find_matching_investors(stage=None, sector_keywords=None, geography=None, investor_type=None, max_results=20):
    """Filter investors based on criteria"""
    matches = []
    
    for inv in INVESTORS:
        score = 0
        
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
        
        if sector_keywords and inv.get('thesis'):
            thesis_lower = inv['thesis'].lower()
            for keyword in sector_keywords:
                if keyword.lower() in thesis_lower:
                    score += 2
        
        if geography and inv.get('countries'):
            countries_lower = inv['countries'].lower()
            if geography.lower() in countries_lower or 'uk' in countries_lower:
                score += 2
        
        if investor_type:
            if investor_type.lower() in inv.get('type', '').lower():
                score += 1
        
        if score > 0 and (inv.get('thesis') or inv.get('stage')):
            matches.append((score, inv))
    
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


def extract_text_from_pdf_basic(file):
    """Extract text from PDF using basic pypdf method"""
    reader = PdfReader(file)
    text = ""
    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            text += f"\n--- Page {page_num} ---\n{page_text}"
    return text


def extract_text_from_pdf_ocr(file):
    """Extract text from PDF using OCR for image-heavy documents"""
    try:
        import pdf2image
        import pytesseract
        
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Convert PDF to images (lower DPI for speed, still readable)
            images = pdf2image.convert_from_path(tmp_path, dpi=150)
            
            text = ""
            for i, image in enumerate(images, 1):
                page_text = pytesseract.image_to_string(image)
                if page_text.strip():
                    text += f"\n--- Page {i} (OCR) ---\n{page_text}"
            
            return text
        finally:
            os.unlink(tmp_path)
            
    except ImportError as e:
        st.warning(f"OCR libraries not available: {e}")
        return None
    except Exception as e:
        st.warning(f"OCR processing error: {str(e)}")
        return None


def extract_text_from_pdf(file):
    """Extract text from PDF, trying basic extraction first then OCR if needed"""
    # First try basic extraction
    file.seek(0)
    basic_text = extract_text_from_pdf_basic(file)
    
    # If we got reasonable text, use it
    if basic_text and len(basic_text.strip()) > 500:
        return basic_text, "text"
    
    # Otherwise try OCR
    file.seek(0)
    ocr_text = extract_text_from_pdf_ocr(file)
    
    if ocr_text and len(ocr_text.strip()) > len(basic_text.strip() if basic_text else ""):
        return ocr_text, "OCR"
    
    # Return whatever we got
    return basic_text, "text"


def extract_text_from_pptx(file):
    """Extract text from PowerPoint file"""
    prs = Presentation(file)
    text = ""
    for slide_num, slide in enumerate(prs.slides, 1):
        slide_text = ""
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text += shape.text + "\n"
        if slide_text.strip():
            text += f"\n--- Slide {slide_num} ---\n{slide_text}"
    return text


def extract_deck_content(uploaded_file):
    """Extract text content from uploaded deck file"""
    if uploaded_file is None:
        return None, None
    
    try:
        if uploaded_file.type == "application/pdf":
            text, method = extract_text_from_pdf(uploaded_file)
            return text, method
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return extract_text_from_pptx(uploaded_file), "PPTX"
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return None, None
    
    return None, None


# System prompt
SYSTEM_PROMPT = """You are Fundraising Co-Pilot, an on-demand decision support assistant for early-stage founders who are actively fundraising or about to start.

Your role is to help founders make better fundraising decisions in real time, using an investor's perspective — so small mistakes don't compound.

## What You Help With
- Pressure-test pitch decks from an investor point of view
- Improve investor outreach emails before sending
- Sanity-check which investors are a realistic fit
- Clarify fundraising readiness and next priorities
- Understand likely objections investors will have
- Find relevant investors from the database

You explain WHY, not just what.

## Tone & Style
- Calm, direct, non-hypey
- Investor-realistic, not motivational
- Clear about trade-offs and uncertainty
- Assume the founder is smart but missing insider context

## Guardrails
You must never:
- Promise funding, responses, or introductions
- Claim certainty about investor decisions
- Act as legal, financial, or investment advice
- Encourage mass or untargeted investor outreach

If asked for guarantees: "There are no guarantees in fundraising — what I can do is help you reduce avoidable mistakes and improve clarity."

## How to Respond

**CRITICAL: When a pitch deck is provided, you MUST analyze THAT SPECIFIC DECK. Reference their actual content. Do not give generic advice.**

When a pitch deck is provided:
1. Start with a quick summary of what you understand the business to be
2. Identify the 2-3 biggest red flags an investor would notice
3. Point out what's unclear or missing
4. Give specific slide-by-slide observations where relevant
5. End with 2-3 priority fixes

When recommending investors:
1. Use the provided investor database matches
2. Explain why each investor might be a fit based on their thesis
3. Remind them to research each one and look for warm intro paths

## Key Heuristics

### Deck Red Flags
- **Vague Verbs**: "disrupting," "optimizing," "leveraging" without specifics
- **Mystery Product**: By slide 4, investor doesn't know what the product actually IS
- **Generic Titles**: "Our Solution" instead of "15% MoM Growth via Direct Sales"
- **Scale Mismatch**: Global problem → niche solution

### Pre-Seed Red Flags
- "We need money to build the MVP" (in 2026 with AI/no-code, this signals low resourcefulness)
- Core tech/sales outsourced to agency
- TAM = "1% of $100B market" (vs bottom-up: "5,000 law firms × £1k/mo")
- Messy cap table (advisors with 5% for nothing)

### What Investors Listen For
- **Earned Insight**: Non-obvious discovery from talking to 100+ customers
- **Speed of Iteration**: What happened since last meeting?
- **Unit Economics**: Know your CAC and margin
- **Why Now**: What changed recently that enables this?

### Too Early Signals
- Waitlist but zero pilots/LOIs
- Founder-problem mismatch (MedTech founder never worked in healthcare)
- Unclear what the money gets you to
- Only feedback from friends/family

## Default Framing
Use often: "From an investor's perspective…"

---
You are decision support, not a decision maker. Your goal is clarity, not confidence theatre.
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
if "deck_content" not in st.session_state:
    st.session_state.deck_content = None
if "deck_filename" not in st.session_state:
    st.session_state.deck_filename = None

# File uploader
st.markdown("📎 **Upload your pitch deck** (PDF or PowerPoint)")
uploaded_file = st.file_uploader(
    "Upload deck",
    type=["pdf", "pptx"],
    help="Image-heavy PDFs will be processed with OCR (may take longer)",
    label_visibility="collapsed"
)

# Process uploaded file
if uploaded_file is not None:
    if st.session_state.deck_filename != uploaded_file.name:
        with st.spinner("Processing deck... (OCR may take 30-60 seconds for image-heavy PDFs)"):
            deck_content, method = extract_deck_content(uploaded_file)
            
        if deck_content and len(deck_content.strip()) > 100:
            st.session_state.deck_content = deck_content
            st.session_state.deck_filename = uploaded_file.name
            st.success(f"✅ Deck loaded via {method}: {uploaded_file.name} ({len(deck_content):,} characters)")
            
            if len(deck_content.strip()) < 500:
                st.warning("⚠️ Limited text extracted. Feedback may be less detailed.")
        else:
            st.error("Could not extract meaningful content. Try a different format.")
    else:
        st.success(f"✅ Using: {uploaded_file.name}")
elif st.session_state.deck_content:
    st.info(f"📄 Deck loaded: {st.session_state.deck_filename}")

st.markdown("---")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Starter prompts
if not st.session_state.messages:
    st.markdown("**What can I help you with?**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Review my pitch deck", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Review my pitch deck from an investor's perspective. Be specific about what's working and what needs to change."
            else:
                starter = "I'd like you to review my pitch deck. Please upload it above first."
            st.session_state.starter_prompt = starter
            st.rerun()
        if st.button("🎯 Am I ready to raise?", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Based on my deck, am I ready to fundraise? What proof points am I missing?"
            else:
                starter = "How do I know if I'm ready to start fundraising? (Upload your deck for specific feedback)"
            st.session_state.starter_prompt = starter
            st.rerun()
    with col2:
        if st.button("🔍 Find investors for me", use_container_width=True):
            if st.session_state.deck_content:
                starter = "Based on my deck, find 5-10 investors who might be a good fit for my startup."
            else:
                starter = "Help me find investors. First, tell me: what's your startup, stage, sector, and geography?"
            st.session_state.starter_prompt = starter
            st.rerun()
        if st.button("✉️ Review my outreach email", use_container_width=True):
            starter = "What makes a cold investor email get a response vs ignored? Give me examples."
            st.session_state.starter_prompt = starter
            st.rerun()

# Handle starter prompts
if "starter_prompt" in st.session_state:
    prompt = st.session_state.starter_prompt
    del st.session_state.starter_prompt
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Build full prompt with deck if available
    full_prompt = prompt
    if st.session_state.deck_content:
        full_prompt = f"""{prompt}

---
**PITCH DECK CONTENT** (from {st.session_state.deck_filename}):

{st.session_state.deck_content[:15000]}

---
Analyze THIS SPECIFIC DECK. Reference their actual slides and content. Do not give generic advice.
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
if prompt := st.chat_input("Ask a fundraising question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Check for investor search
    investor_keywords = ['investor', 'investors', 'find', 'recommend', 'who should i pitch', 'vc', 'angel', 'funding', 'fit for my']
    is_investor_search = any(kw in prompt.lower() for kw in investor_keywords)
    
    additional_context = ""
    
    # Always include deck if available
    if st.session_state.deck_content:
        additional_context += f"""

---
**PITCH DECK CONTENT** (from {st.session_state.deck_filename}):

{st.session_state.deck_content[:15000]}

---
Reference this deck content in your response where relevant.
"""
    
    # Add investor matches if searching
    if is_investor_search:
        stage = None
        if any(s in prompt.lower() for s in ['pre-seed', 'preseed', 'idea', 'prototype']):
            stage = "pre-seed"
        elif any(s in prompt.lower() for s in ['seed', 'early revenue', 'mvp']):
            stage = "seed"
        elif any(s in prompt.lower() for s in ['series a', 'scaling', 'growth']):
            stage = "series a"
        
        sector_keywords = []
        sectors = ['ai', 'fintech', 'healthtech', 'health', 'saas', 'b2b', 'b2c', 'consumer', 'enterprise', 
                   'climate', 'sustainability', 'edtech', 'proptech', 'foodtech', 'biotech', 'deeptech',
                   'marketplace', 'ecommerce', 'gaming', 'web3', 'blockchain', 'crypto', 'mental health', 
                   'wellness', 'fashion', 'retail', 'logistics', 'hr', 'legal', 'insurance', 'cybersecurity', 
                   'iot', 'robotics', 'energy', 'cleantech', 'agtech', 'space', 'mobility', 'impact']
        
        # Check prompt and deck for sectors
        search_text = prompt.lower()
        if st.session_state.deck_content:
            search_text += " " + st.session_state.deck_content.lower()
        
        for sector in sectors:
            if sector in search_text:
                sector_keywords.append(sector)
        
        geography = None
        if any(g in prompt.lower() for g in ['uk', 'united kingdom', 'london', 'britain']):
            geography = "UK"
        elif any(g in prompt.lower() for g in ['us', 'usa', 'united states', 'america']):
            geography = "USA"
        elif any(g in prompt.lower() for g in ['europe', 'eu']):
            geography = "Europe"
        
        if stage or sector_keywords:
            matches = find_matching_investors(
                stage=stage,
                sector_keywords=sector_keywords[:5] if sector_keywords else None,
                geography=geography,
                max_results=15
            )
            
            if matches:
                additional_context += f"""

---
**MATCHING INVESTORS FROM DATABASE**:

{format_investor_for_context(matches)}

Recommend 5-10 that fit best. Explain why. Remind them to research and find warm intros.
---
"""
    
    client = get_client()
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            messages_for_api = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            messages_for_api.append({"role": "user", "content": prompt + additional_context})
            
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                system=SYSTEM_PROMPT,
                messages=messages_for_api
            )
            assistant_message = response.content[0].text
            st.markdown(assistant_message)
    
    st.session_state.messages.append({"role": "assistant", "content": assistant_message})

# Clear button
if st.session_state.messages:
    if st.button("🔄 Start new conversation", type="secondary"):
        st.session_state.messages = []
        st.session_state.deck_content = None
        st.session_state.deck_filename = None
        st.rerun()

# Footer
st.markdown("""
<div class="footer">
    Built by <a href="https://thefundraisingaccelerator.com" target="_blank">The Fundraising Accelerator</a><br>
    Your network should not determine your net worth.<br><br>
    <small>⚠️ Decision support, not advice. No guarantees in fundraising.</small>
</div>
""", unsafe_allow_html=True)
