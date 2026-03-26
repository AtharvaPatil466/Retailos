# brain/price_analyzer.py

def analyze_quote(quoted_price: float, market_ref: dict) -> dict:
    """Takes a quoted price and market reference to output a verdict & exact delta."""
    median = market_ref.get("median_price")
    
    if not median:
        return {"verdict": "unknown", "delta_percentage": 0.0, "risk_flag": None}
        
    delta = quoted_price - median
    delta_pct = (delta / median) * 100.0
    
    if delta_pct > 5.0:
        verdict = "above_market"
    elif delta_pct < -5.0:
        verdict = "below_market"
    else:
        verdict = "at_market"
        
    # Risk flagging for severe outliers
    risk_flag = None
    if delta_pct < -25.0:
        risk_flag = "suspiciously_low (possible quality/expiry issue)"
    elif delta_pct > 30.0:
        risk_flag = "suspiciously_high (opportunistic pricing)"
        
    return {
        "verdict": verdict,
        "delta_percentage": round(delta_pct, 1),
        "risk_flag": risk_flag
    }

def format_supplier_verdict(supplier_name: str, quoted_price: float, market_ref: dict) -> str:
    """Helper to cleanly format the injected text block for AI prompts."""
    median = market_ref.get("median_price")
    if not median:
        return f"{supplier_name} quote: ₹{quoted_price}/unit (No market data to compare)"
        
    analysis = analyze_quote(quoted_price, market_ref)
    verdict_display = analysis["verdict"].replace("_", " ").title()
    sign = "+" if analysis["delta_percentage"] > 0 else ""
    
    risk_str = f" [RISK: {analysis['risk_flag']}]" if analysis["risk_flag"] else ""
    
    block = (
        f"  {supplier_name} quote: ₹{quoted_price}/unit ({sign}{analysis['delta_percentage']}% from market)\n"
        f"  Verdict: {verdict_display}.{risk_str}"
    )
    if verdict_display == "Above Market":
        target = median * 0.98
        block += f" Recommend countering at ₹{int(target)}-{int(median)} range."
        
    return block
