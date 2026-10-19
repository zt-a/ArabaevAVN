from parsers.card import parse_grades


def test_parse_grades_maps_fields():
    card = [
        {
            "p34": "Алгоритмический язык 1,2,3",
            "p30": "Экзамен",
            "ball": 80,
            "p31": "хор",
            "t_fio": "  Зав.кафедрой  ",
            "p36": "03.10.25",
            "kredits": 4,
            "p32": "2024-25",
            "p42": "Осенний семестр",
        },
        {"p34": ""},  # пропускается (нет дисциплины)
        "not a dict",
    ]
    grades = parse_grades(card)
    assert len(grades) == 1
    g = grades[0]
    assert g["discipline"] == "Алгоритмический язык 1,2,3"
    assert g["control_type"] == "Экзамен"
    assert g["ball"] == "80"
    assert g["grade"] == "хор"
    assert g["teacher"] == "Зав.кафедрой"
    assert g["credits"] == "4"
    assert g["year"] == "2024-25"
    assert g["semester"] == "Осенний семестр"


def test_parse_grades_empty():
    assert parse_grades([]) == []
    assert parse_grades(None) == []


def test_parse_grades_missing_optionals():
    grades = parse_grades([{"p34": "Физкультура"}])
    assert grades[0]["discipline"] == "Физкультура"
    assert grades[0]["ball"] == ""
    assert grades[0]["credits"] == ""
