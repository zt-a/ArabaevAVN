from parsers.attendance import attendance_percent, attendance_risk_message


def test_attendance_percent_from_percentvisit():
    rows = [
        {"posetil": 0, "kol_pos": 9, "Percentvisit": "47,37", "name_pos": "Посетил"},
        {"posetil": 1, "kol_pos": 10, "Percentvisit": "52,63", "name_pos": "Не посещал"},
    ]
    assert attendance_percent(rows) == 47.4


def test_attendance_percent_computes_when_no_percent_field():
    rows = [
        {"posetil": 0, "kol_pos": 9},
        {"posetil": 1, "kol_pos": 11},
    ]
    assert attendance_percent(rows) == 45.0


def test_attendance_percent_empty():
    assert attendance_percent([]) == 0.0


def test_attendance_percent_zero_total():
    assert attendance_percent([{"posetil": 0, "kol_pos": 0}]) == 0.0


def test_attendance_risk_levels():
    assert attendance_risk_message(90) == ""
    assert "ниже 75" in attendance_risk_message(60)
    assert "КРИТИЧЕСКАЯ" in attendance_risk_message(30)
    assert "🆘" in attendance_risk_message(10)
