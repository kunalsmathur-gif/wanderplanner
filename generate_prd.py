from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
from datetime import datetime

def create_prd():
    doc = SimpleDocTemplate(
        "docs/WanderPlan_PRD.pdf",
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a56db'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.grey,
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    heading1_style = ParagraphStyle(
        'CustomHeading1',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a56db'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2563eb'),
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        alignment=TA_JUSTIFY,
        leading=14
    )
    
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontSize=10,
        leftIndent=20,
        spaceAfter=6,
        leading=14
    )
    
    # Title Page
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("WanderPlan", title_style))
    story.append(Paragraph("Product Requirements Document", subtitle_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("AI-Powered Conversational Travel Planning Platform", subtitle_style))
    story.append(Spacer(1, 0.5*inch))
    
    info_data = [
        ["Version:", "2.0"],
        ["Last Updated:", datetime.now().strftime("%B %d, %Y")],
        ["Document Owner:", "Product Team"],
        ["Status:", "Active Development"]
    ]
    info_table = Table(info_data, colWidths=[2*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    
    story.append(PageBreak())
    
    # Table of Contents
    story.append(Paragraph("Table of Contents", heading1_style))
    toc_data = [
        "1. Executive Summary",
        "2. Product Vision & Goals",
        "3. Target Audience",
        "4. Core Features",
        "5. User Experience & Interface",
        "6. Technical Architecture",
        "7. AI & Machine Learning",
        "8. Success Metrics",
        "9. Roadmap & Milestones",
        "10. Risks & Mitigation"
    ]
    for item in toc_data:
        story.append(Paragraph(item, bullet_style))
        story.append(Spacer(1, 6))
    
    story.append(PageBreak())
    
    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary", heading1_style))
    story.append(Paragraph(
        "WanderPlan is an AI-powered travel planning platform that revolutionizes trip planning through natural, "
        "conversational interactions. Unlike traditional booking platforms with complex forms, WanderPlan introduces "
        "<b>Anya</b> — an intelligent AI assistant that guides users through personalized itinerary creation using voice "
        "and text conversations.",
        body_style
    ))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("<b>Key Differentiators:</b>", body_style))
    differentiators = [
        "<b>Conversational Interface:</b> Replace multi-step wizards with natural dialogue",
        "<b>Voice-First Design:</b> Fully functional voice input and output with Indian English accent",
        "<b>AI-Powered Personalization:</b> Leverages Gemini 2.0 Flash for context-aware recommendations",
        "<b>Community Intelligence:</b> Incorporates real traveler experiences from Reddit and Wikivoyage",
        "<b>Transparent Pricing:</b> No hidden fees, budget-aware planning from the start"
    ]
    for diff in differentiators:
        story.append(Paragraph(f"• {diff}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 2. Product Vision & Goals
    story.append(Paragraph("2. Product Vision & Goals", heading1_style))
    
    story.append(Paragraph("2.1 Vision Statement", heading2_style))
    story.append(Paragraph(
        "\"Make travel planning as simple as having a conversation with a knowledgeable friend.\"",
        body_style
    ))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("2.2 Product Goals", heading2_style))
    goals = [
        "<b>Reduce planning time:</b> From 5-10 hours to under 15 minutes for a complete itinerary",
        "<b>Increase accessibility:</b> Enable voice-first planning for users uncomfortable with complex interfaces",
        "<b>Improve personalization:</b> Deliver itineraries that match user preferences with 90%+ satisfaction",
        "<b>Build trust:</b> Transparent pricing, no spam, community-validated recommendations"
    ]
    for goal in goals:
        story.append(Paragraph(f"• {goal}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 3. Target Audience
    story.append(Paragraph("3. Target Audience", heading1_style))
    
    personas = [
        {
            "name": "Primary: Young Professionals (25-35)",
            "desc": "Time-constrained individuals seeking quick, personalized trip planning. Comfortable with technology, prefer voice/chat over forms. Budget: ₹50K-2.5L per trip."
        },
        {
            "name": "Secondary: Families (30-45)",
            "desc": "Parents planning kid-friendly vacations. Need detailed itineraries with safety considerations, age-appropriate activities, and flexible pacing. Budget: ₹1L-5L per trip."
        },
        {
            "name": "Tertiary: Senior Travelers (55+)",
            "desc": "Retirees with time and budget for leisure travel. Prefer voice interaction, need clear guidance, value relaxed pace. Budget: ₹2L-10L+ per trip."
        }
    ]
    
    for persona in personas:
        story.append(Paragraph(f"<b>{persona['name']}</b>", body_style))
        story.append(Paragraph(persona['desc'], bullet_style))
        story.append(Spacer(1, 10))
    
    story.append(PageBreak())
    
    # 4. Core Features
    story.append(Paragraph("4. Core Features", heading1_style))
    
    story.append(Paragraph("4.1 Anya - AI Travel Assistant", heading2_style))
    story.append(Paragraph(
        "Anya is the conversational interface that replaces traditional forms with natural dialogue. "
        "She guides users through 9 key inputs (purpose, origin, destination, dates, group, budget, accommodation, pace, themes) "
        "via text or voice.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    anya_features = [
        "<b>Voice Mode:</b> Single animated button for continuous voice interaction (speak + listen)",
        "<b>Smart City Suggestions:</b> Recommends destinations based on user preferences when exploring",
        "<b>Multi-Select Themes:</b> Culture, Food, Adventure, Nature, Photography, Shopping, etc.",
        "<b>Refinement Loop:</b> 'Anything else before I generate?' step for final tweaks",
        "<b>Persona:</b> Female, aged 20-25, Indian English accent, friendly and energetic tone"
    ]
    for feature in anya_features:
        story.append(Paragraph(f"• {feature}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("4.2 Itinerary Generation", heading2_style))
    story.append(Paragraph(
        "AI-generated day-by-day schedules with timestamps, cost estimates, locations, and activity descriptions. "
        "Powered by Gemini 2.0 Flash with real-time streaming (30-60 seconds for 5-7 day trips).",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    itinerary_features = [
        "<b>Timeline View:</b> Visual day-by-day cards with activities, duration, and costs",
        "<b>Interactive Map:</b> Leaflet integration with pins for all activity locations",
        "<b>YouTube Embeds:</b> Video previews for attractions and activities",
        "<b>Transit Warnings:</b> Alerts when travel time between activities exceeds 30 minutes",
        "<b>Expense Breakdown:</b> Category-wise cost summary (Transport, Food, Activities, etc.)"
    ]
    for feature in itinerary_features:
        story.append(Paragraph(f"• {feature}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("4.3 Booking Integration", heading2_style))
    story.append(Paragraph(
        "Seamless handoff to trusted booking platforms for hotels, flights, and car rentals.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    booking_partners = [
        "<b>Hotels:</b> Booking.com, Agoda, Hotels.com",
        "<b>Flights:</b> Skyscanner, Google Flights",
        "<b>Car Rentals:</b> Rentalcars.com"
    ]
    for partner in booking_partners:
        story.append(Paragraph(f"• {partner}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("4.4 Travel Intelligence", heading2_style))
    travel_intel = [
        "<b>Best Time to Visit:</b> Weather data, temperature, rainfall, tourist density analysis",
        "<b>Community Tips:</b> AI-curated insights from Reddit and Wikivoyage (6 tips per destination)",
        "<b>Budget Recommendations:</b> Data-driven budget guidance based on destination and group size"
    ]
    for intel in travel_intel:
        story.append(Paragraph(f"• {intel}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 5. User Experience & Interface
    story.append(Paragraph("5. User Experience & Interface", heading1_style))
    
    story.append(Paragraph("5.1 Desktop Layout (Primary)", heading2_style))
    story.append(Paragraph(
        "Three-column responsive design optimized for 1920×1080 and above.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    layout_desc = [
        "<b>Left Column (20%):</b> Trip metrics, booking CTAs, expense breakdown, currency selector",
        "<b>Center Column (55%):</b> Itinerary timeline or comparison panel",
        "<b>Right Column (25%):</b> Map, best time widget, travel tips",
        "<b>Overlay:</b> Conversational wizard (Anya) opens by default on first visit"
    ]
    for desc in layout_desc:
        story.append(Paragraph(f"• {desc}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("5.2 Conversational Flow", heading2_style))
    flow_steps = [
        "User opens app → Anya greets: \"Hi! I'm Anya from WanderPlan...\"",
        "Sequential prompts for 9 inputs (purpose → origin → destination → dates → group → budget → accommodation → pace → themes)",
        "City suggestions for exploring/country modes via Gemini",
        "Refinement step: \"Anything else before I generate?\"",
        "Trip summary card with edit options",
        "Generate itinerary (30-60s streaming)",
        "Wizard stays open with \"View Itinerary\" CTA"
    ]
    for i, step in enumerate(flow_steps, 1):
        story.append(Paragraph(f"{i}. {step}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("5.3 Voice Interaction", heading2_style))
    story.append(Paragraph(
        "Single 🎙️ button with pulsating animation. Click to toggle voice mode — Anya both speaks and listens "
        "in a continuous loop. Auto-restart after each response.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    voice_specs = [
        "<b>Recognition:</b> Web Speech API, language: en-IN",
        "<b>Synthesis:</b> Browser Speech Synthesis, priority: Indian English female voices",
        "<b>Voice Characteristics:</b> Pitch 1.15 (young female), rate 1.05 (energetic), volume 1.0"
    ]
    for spec in voice_specs:
        story.append(Paragraph(f"• {spec}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 6. Technical Architecture
    story.append(Paragraph("6. Technical Architecture", heading1_style))
    
    story.append(Paragraph("6.1 Frontend Stack", heading2_style))
    frontend = [
        "<b>Framework:</b> Next.js 16.2.9 with Turbopack",
        "<b>Language:</b> TypeScript 5.x",
        "<b>State Management:</b> Zustand (4 stores: app, tripConfig, itinerary, wizardChat)",
        "<b>Styling:</b> Tailwind CSS v4",
        "<b>Maps:</b> Leaflet with OpenStreetMap tiles",
        "<b>Charts:</b> Recharts",
        "<b>Deployment:</b> Vercel (recommended)"
    ]
    for item in frontend:
        story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("6.2 Backend Stack", heading2_style))
    backend = [
        "<b>Framework:</b> FastAPI (Python 3.9+)",
        "<b>LLM:</b> Google Gemini 2.0 Flash (gemini-2.0-flash-exp)",
        "<b>Vector Database:</b> Qdrant (in-memory mode, 384-dim embeddings)",
        "<b>Embedding Model:</b> sentence-transformers/all-MiniLM-L6-v2",
        "<b>Scheduler:</b> APScheduler (Reddit refresh every 6 hours)",
        "<b>Deployment:</b> Railway / Render (recommended)"
    ]
    for item in backend:
        story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("6.3 External APIs", heading2_style))
    apis = [
        "<b>Geocoding:</b> Nominatim (OpenStreetMap, rate-limited 1 req/sec)",
        "<b>Weather:</b> Open-Meteo (free, no API key)",
        "<b>Community Content:</b> Reddit JSON API (no auth required)",
        "<b>Maps:</b> OpenStreetMap tiles (free)",
        "<b>YouTube:</b> HTML scraping for thumbnail search"
    ]
    for api in apis:
        story.append(Paragraph(f"• {api}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 7. AI & Machine Learning
    story.append(Paragraph("7. AI & Machine Learning", heading1_style))
    
    story.append(Paragraph("7.1 Gemini 2.0 Flash Integration", heading2_style))
    story.append(Paragraph(
        "Primary LLM for all generative tasks. Chosen for speed (2-5s responses), cost-efficiency (free during preview), "
        "and strong JSON structured output.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    gemini_use_cases = [
        "<b>Itinerary Generation:</b> 30-60s streaming, temperature 0.7, max tokens 4096",
        "<b>Chat Refinement (Anya):</b> 2-5s response, temperature 0.5, structured JSON output",
        "<b>City Recommendations:</b> 3-6s, temperature 0.7, returns 5 cities with descriptions",
        "<b>Travel Tips:</b> 2-4s, temperature 0.8, generates 6 community-style tips (cached)"
    ]
    for use_case in gemini_use_cases:
        story.append(Paragraph(f"• {use_case}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("7.2 Vector Search (Qdrant)", heading2_style))
    story.append(Paragraph(
        "Retrieves relevant community insights from Reddit and Wikivoyage during itinerary generation. "
        "Queries use destination + themes → cosine similarity > 0.1 → top 10 results.",
        body_style
    ))
    story.append(Spacer(1, 10))
    
    qdrant_details = [
        "<b>Embedding Model:</b> all-MiniLM-L6-v2 (384 dimensions, runs locally)",
        "<b>Collections:</b> reddit_highlights, wikivoyage_content",
        "<b>Ingestion:</b> APScheduler job every 6 hours (Reddit), on-demand (Wikivoyage)",
        "<b>Storage:</b> In-memory (data lost on restart, re-ingestion required)"
    ]
    for detail in qdrant_details:
        story.append(Paragraph(f"• {detail}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("7.3 Prompt Engineering", heading2_style))
    story.append(Paragraph(
        "All prompts follow structured templates with user profile context (purpose, group, pace, budget, themes) "
        "and retrieved community insights. Anya's persona is defined in system prompts with guardrails against "
        "non-travel queries.",
        body_style
    ))
    
    story.append(PageBreak())
    
    # 8. Success Metrics
    story.append(Paragraph("8. Success Metrics", heading1_style))
    
    story.append(Paragraph("8.1 User Engagement", heading2_style))
    engagement_metrics = [
        "<b>Wizard Completion Rate:</b> >80% of users complete all 9 fields",
        "<b>Voice Mode Adoption:</b> >30% of users try voice interaction",
        "<b>Average Session Duration:</b> 12-18 minutes (wizard + itinerary review)",
        "<b>Repeat Usage:</b> >40% of users plan 2+ trips within 6 months"
    ]
    for metric in engagement_metrics:
        story.append(Paragraph(f"• {metric}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("8.2 Product Quality", heading2_style))
    quality_metrics = [
        "<b>Itinerary Satisfaction:</b> >90% users rate itinerary 4-5 stars",
        "<b>Anya Response Accuracy:</b> >95% responses correctly interpret user intent",
        "<b>Booking Conversion:</b> >25% of generated itineraries lead to bookings (tracked via affiliate links)",
        "<b>Error Rate:</b> <2% of API calls result in errors"
    ]
    for metric in quality_metrics:
        story.append(Paragraph(f"• {metric}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("8.3 Performance", heading2_style))
    performance_metrics = [
        "<b>Itinerary Generation (P95):</b> <60 seconds for 5-7 day trips",
        "<b>Chat Response Time (P95):</b> <5 seconds",
        "<b>Page Load Time (P95):</b> <2 seconds",
        "<b>Uptime:</b> >99.5%"
    ]
    for metric in performance_metrics:
        story.append(Paragraph(f"• {metric}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 9. Roadmap & Milestones
    story.append(Paragraph("9. Roadmap & Milestones", heading1_style))
    
    story.append(Paragraph("9.1 Phase 1: MVP (Current)", heading2_style))
    phase1 = [
        "✅ Conversational wizard with Anya",
        "✅ Voice input and output (Indian English)",
        "✅ Itinerary generation with Gemini 2.0 Flash",
        "✅ Booking links integration",
        "✅ Travel tips and best time widget",
        "✅ Desktop-optimized UI (mobile warning banner)"
    ]
    for item in phase1:
        story.append(Paragraph(item, bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("9.2 Phase 2: Mobile & Sharing (Q3 2026)", heading2_style))
    phase2 = [
        "Responsive mobile web app",
        "Shareable itinerary links (public/private)",
        "PDF export with branding",
        "WhatsApp/email sharing",
        "Progressive Web App (PWA) support"
    ]
    for item in phase2:
        story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("9.3 Phase 3: Collaboration & Booking (Q4 2026)", heading2_style))
    phase3 = [
        "Multi-user trip planning (invite friends/family)",
        "Real-time collaboration on itineraries",
        "In-app booking for flights and hotels",
        "Payment integration (Stripe/Razorpay)",
        "Booking commission revenue model"
    ]
    for item in phase3:
        story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("9.4 Phase 4: Intelligence & Scale (2027)", heading2_style))
    phase4 = [
        "Personalized recommendations based on past trips",
        "Price tracking and alerts",
        "Multi-city trip support",
        "Currency conversion across multiple currencies",
        "Regional language support (Hindi, Spanish, etc.)",
        "Integration with Google Calendar/Apple Calendar"
    ]
    for item in phase4:
        story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 4))
    
    story.append(PageBreak())
    
    # 10. Risks & Mitigation
    story.append(Paragraph("10. Risks & Mitigation", heading1_style))
    
    risks = [
        {
            "risk": "Gemini API Rate Limits",
            "impact": "High",
            "mitigation": "Implement aggressive caching (travel tips already cached), queue requests during peak, migrate to paid tier if needed"
        },
        {
            "risk": "Voice Recognition Accuracy",
            "impact": "Medium",
            "mitigation": "Provide text fallback always visible, show transcript for confirmation, improve with user feedback"
        },
        {
            "risk": "Qdrant Data Loss (In-Memory)",
            "impact": "Medium",
            "mitigation": "Migrate to persistent storage (Railway volume), automated backup, graceful degradation without context"
        },
        {
            "risk": "Reddit API Blocking",
            "impact": "Low",
            "mitigation": "Already using Gemini as primary source for tips, Reddit is fallback only"
        },
        {
            "risk": "Booking Conversion Low",
            "impact": "High",
            "mitigation": "A/B test CTA placement, add urgency messaging (price alerts), improve trust signals (reviews)"
        }
    ]
    
    risk_data = [["Risk", "Impact", "Mitigation"]]
    for r in risks:
        risk_data.append([r["risk"], r["impact"], r["mitigation"]])
    
    risk_table = Table(risk_data, colWidths=[2*inch, 1*inch, 3.5*inch])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
    ]))
    story.append(risk_table)
    
    story.append(Spacer(1, 20))
    story.append(Paragraph("—", subtitle_style))
    story.append(Paragraph("End of Product Requirements Document", subtitle_style))
    
    doc.build(story)
    print("✅ PRD PDF created: docs/WanderPlan_PRD.pdf")

if __name__ == "__main__":
    create_prd()
