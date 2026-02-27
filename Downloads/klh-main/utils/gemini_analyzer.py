import google.generativeai as genai
import json
import re
import os
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def analyze_car_damage(image_path):
    model = genai.GenerativeModel("gemini-3-flash-preview")
    img = Image.open(image_path)

    prompt = """You are an expert automotive insurance damage assessor working in INDIA. Analyze this car damage image and provide a detailed assessment.

IMPORTANT PRICING GUIDELINES (Indian Market in INR - Indian Rupees):
- Use realistic Indian market rates for parts and labor
- Labor rate: ₹400 - ₹800 per hour depending on complexity
- Consider Indian car brands and their part costs (Maruti, Hyundai, Tata, Mahindra, Honda, Toyota, Kia etc.)
- Minor dent repair: ₹1,000 - ₹5,000
- Bumper repair: ₹2,000 - ₹8,000, Bumper replacement: ₹5,000 - ₹25,000
- Headlight/Taillight replacement: ₹3,000 - ₹20,000
- Door panel repair: ₹3,000 - ₹10,000, Door replacement: ₹15,000 - ₹40,000
- Windshield replacement: ₹5,000 - ₹25,000
- Fender repair: ₹2,000 - ₹8,000, Fender replacement: ₹8,000 - ₹20,000
- Hood repair: ₹3,000 - ₹10,000, Hood replacement: ₹10,000 - ₹35,000
- Full body paint per panel: ₹3,000 - ₹8,000
- Keep estimates REALISTIC for Indian market

Return your response STRICTLY as a valid JSON object (no markdown, no code blocks, just pure JSON):

{
    "vehicle_info": {
        "estimated_make": "string",
        "color": "string",
        "vehicle_type": "string"
    },
    "damage_assessment": {
        "overall_severity": "string (Minor/Moderate/Severe/Total Loss)",
        "severity_score": "number 1-10",
        "damaged_areas": [
            {
                "part_name": "string",
                "damage_type": "string",
                "severity": "string (Low/Medium/High/Critical)",
                "description": "string"
            }
        ],
        "damage_summary": "string"
    },
    "cost_estimation": {
        "currency": "INR",
        "parts": [
            {
                "part_name": "string",
                "repair_or_replace": "string (Repair/Replace)",
                "estimated_part_cost": "number in INR",
                "estimated_labor_cost": "number in INR",
                "estimated_labor_hours": "number"
            }
        ],
        "paint_and_finish": {
            "required": "boolean",
            "estimated_cost": "number in INR"
        },
        "subtotal_parts": "number in INR",
        "subtotal_labor": "number in INR",
        "subtotal_paint": "number in INR",
        "total_estimated_cost": "number in INR"
    },
    "pre_approval": {
        "recommendation": "string (Approve/Review/Deny)",
        "confidence_level": "string (High/Medium/Low)",
        "reasoning": "string",
        "estimated_repair_days": "number",
        "is_drivable": "boolean"
    },
    "additional_notes": "string"
}

ALL costs must be in Indian Rupees (INR). Be realistic."""

    response = model.generate_content([prompt, img])

    try:
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
    except (json.JSONDecodeError, Exception):
        result = {
            "vehicle_info": {"estimated_make": "Unknown", "color": "Unknown", "vehicle_type": "Unknown"},
            "damage_assessment": {
                "overall_severity": "Unknown", "severity_score": 0,
                "damaged_areas": [],
                "damage_summary": response.text if response else "Analysis failed"
            },
            "cost_estimation": {
                "currency": "INR", "parts": [],
                "paint_and_finish": {"required": False, "estimated_cost": 0},
                "subtotal_parts": 0, "subtotal_labor": 0, "subtotal_paint": 0,
                "total_estimated_cost": 0
            },
            "pre_approval": {
                "recommendation": "Review", "confidence_level": "Low",
                "reasoning": "Could not parse AI response", "estimated_repair_days": 0,
                "is_drivable": True
            },
            "additional_notes": "Please try again with a clearer image."
        }

    return result