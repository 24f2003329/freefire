import google.generativeai as genai
import json
import os
from datetime import datetime

INDIAN_PROVIDERS = [
    {"name": "ICICI Lombard", "id": "icici_lombard", "color": "#E44D26", "icon": "fa-building"},
    {"name": "HDFC ERGO", "id": "hdfc_ergo", "color": "#004B87", "icon": "fa-university"},
    {"name": "Bajaj Allianz", "id": "bajaj_allianz", "color": "#0066B3", "icon": "fa-shield-alt"},
    {"name": "Tata AIG", "id": "tata_aig", "color": "#1A1F71", "icon": "fa-landmark"},
    {"name": "New India Assurance", "id": "new_india", "color": "#138808", "icon": "fa-flag"},
    {"name": "Reliance General", "id": "reliance_gen", "color": "#D32F2F", "icon": "fa-bolt"},
]


def get_providers():
    return INDIAN_PROVIDERS


def run_negotiation(user_profile: dict) -> dict:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.0-flash")

    provider_names = [p["name"] for p in INDIAN_PROVIDERS]

    prompt = f"""You are an expert AI insurance negotiation agent operating in India.

A user wants to renew their insurance. Negotiate the best deal across providers.

## User Profile
- Insurance Type: {user_profile.get('insurance_type', 'Motor')}
- Current Provider: {user_profile.get('current_provider', 'Unknown')}
- Current Annual Premium: ₹{user_profile.get('current_premium', 0):,}
- Coverage / Sum Insured: ₹{user_profile.get('coverage_amount', 0):,}
- Policy Tenure: {user_profile.get('tenure', 1)} year(s)
- Policyholder Age: {user_profile.get('age', 30)}
- City: {user_profile.get('city', 'Mumbai')}
- No-Claim Bonus: {user_profile.get('ncb', 0)}%
- Additional Notes: {user_profile.get('notes', 'None')}

## Task
Simulate a complete negotiation with these 6 Indian insurers: {', '.join(provider_names)}

Return a JSON object (NO markdown, NO code fences, ONLY raw JSON) with this EXACT structure:

{{
  "providers": [
    {{
      "name": "Provider Name",
      "initial_quote": 25000,
      "negotiation_strategy": "What the agent said to negotiate",
      "provider_response": "How the provider responded",
      "discount_type": "NCB + Loyalty + Online",
      "discount_percent": 15,
      "final_quote": 21250,
      "features": ["Feature 1", "Feature 2", "Feature 3", "Feature 4"],
      "claim_settlement_ratio": 95.5,
      "network_size": 5000,
      "cashless": true,
      "rating": 4.2,
      "pros": ["Pro 1", "Pro 2"],
      "cons": ["Con 1"]
    }}
  ],
  "best_deal": {{
    "provider_name": "Best Provider Name",
    "final_quote": 20000,
    "reason": "Why this is the best deal in 2-3 sentences",
    "savings_vs_current": 5000,
    "savings_percent": 20.0
  }},
  "negotiation_log": [
    {{
      "round": 1,
      "action": "Short action title",
      "detail": "Detailed description of what happened",
      "icon": "fa-search"
    }},
    {{
      "round": 2,
      "action": "Short action title",
      "detail": "Detailed description",
      "icon": "fa-comments"
    }}
  ],
  "market_insights": "2-3 sentences about current market conditions for this insurance type in India",
  "recommendation_summary": "4-5 sentence detailed recommendation for the user"
}}

RULES:
1. All prices in Indian Rupees as integers
2. Realistic Indian insurance market prices
3. best_deal.savings_vs_current = current_premium - best final_quote
4. Generate 5-7 negotiation_log entries with icons from: fa-search, fa-paper-plane, fa-comments, fa-handshake, fa-chart-line, fa-trophy, fa-check-circle, fa-gavel
5. Realistic negotiation strategies (NCB, loyalty, bundling, online discount, competition leverage)
6. Most final quotes should be lower than current premium; at least one can be higher
7. Sort providers by final_quote ascending in the array
8. Return ONLY valid JSON"""

    response = model.generate_content(prompt)
    text = response.text.strip()

    # Clean markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    result = json.loads(text)

    # Enrich providers with color/icon metadata
    provider_map = {p["name"]: p for p in INDIAN_PROVIDERS}
    current_premium = user_profile.get("current_premium", 0)

    for prov in result.get("providers", []):
        meta = provider_map.get(prov["name"], {})
        prov["color"] = meta.get("color", "#666666")
        prov["meta_icon"] = meta.get("icon", "fa-building")
        prov["id"] = meta.get("id", prov["name"].lower().replace(" ", "_"))
        prov["savings"] = current_premium - prov.get("final_quote", current_premium)
        prov["savings_percent"] = round(
            (prov["savings"] / current_premium * 100) if current_premium > 0 else 0, 1
        )
        prov["is_best"] = prov["name"] == result.get("best_deal", {}).get("provider_name", "")

    best_name = result.get("best_deal", {}).get("provider_name", "")
    best_meta = provider_map.get(best_name, {})
    result["best_deal"]["color"] = best_meta.get("color", "#4CAF50")
    result["best_deal"]["meta_icon"] = best_meta.get("icon", "fa-trophy")

    result["user_profile"] = user_profile
    result["timestamp"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    result["provider_count"] = len(result.get("providers", []))

    # Compute max quote for bar chart scaling
    quotes = [p.get("final_quote", 0) for p in result.get("providers", [])]
    quotes.append(current_premium)
    result["max_quote"] = max(quotes) if quotes else 1

    return result
