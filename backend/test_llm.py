from llm import explain_square_off, generate_report_card

print("=== SQUARE-OFF EXPLANATION ===")
print(explain_square_off(daily_loss_limit=500, total_loss=-659, warnings_count=1))

print("\n=== REPORT CARD ===")
summary = {
    "total_trades": 1,
    "total_pnl": -659.0,
    "early_warnings_ignored": 1,
    "cool_off_breaches": 1,
    "hard_stop_triggered": True,
    "revenge_trades": 0,
    "discipline_score": 40,
}
print(generate_report_card(summary))