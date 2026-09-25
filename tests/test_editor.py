from backend.app.formatting.editor import ai_plan, analyze_post


def test_exam_options_are_locked():
    text = "آزمون امروز\n1) گزینه اول\n2) گزینه دوم\n3) گزینه سوم\nجواب: 2"
    decision = analyze_post(text)
    assert decision.category == "exam"
    assert decision.strategy == "preserve_strict"
    assert decision.has_options is True


def test_rank_number_is_not_rewritten():
    decision = analyze_post("رتبه ۱۲۳۴ در کنکور سراسری ثبت شد و کارنامه آماده است برای بررسی دقیق")
    assert decision.category == "rank"
    assert decision.strategy == "preserve_strict"
    assert decision.has_number is True


def test_solution_is_its_own_category():
    decision = analyze_post("پاسخ تشریحی سوال ۳: گزینه صحیح ب است و دلیلش در متن کتاب آمده است.")
    assert decision.category == "solution"
    assert decision.strategy == "preserve_strict"


def test_long_soft_post_may_be_lightly_edited():
    text = "مشاوره " + ("سوال داوطلب را دقیق جواب بده و قدم بعدی را روشن کن. " * 30)
    decision = analyze_post(text)
    assert decision.category == "consulting"
    assert decision.length_class == "long"
    assert decision.strategy == "light_edit"
    assert decision.template_family == "consultation"


def test_short_post_is_not_sent_to_ai():
    decision = analyze_post("سلام وقت بخیر")
    assert decision.strategy == "preserve_strict"
    assert decision.length_class == "short"


def test_fact_post_is_read_in_tidy_mode():
    text = "اطلاعیه ثبت نام " + "جزئیات برنامه فردا اعلام شد. " * 6
    decision = analyze_post(text)
    assert decision.strategy == "preserve_strict"
    assert decision.length_class != "short"
    assert ai_plan(decision) == "tidy"


def test_exam_options_are_not_sent_to_the_model():
    decision = analyze_post("آزمون امروز\n1) گزینه اول\n2) گزینه دوم")
    assert ai_plan(decision) == "skip"


def test_quote_entity_locks_the_post():
    text = "این جمله باید همان بماند و طولانی شود " * 8
    entities = [{"type": "blockquote", "offset": 0, "length": 10}]
    decision = analyze_post(text, entities)
    assert decision.has_quote is True
    assert decision.strategy == "preserve_strict"
