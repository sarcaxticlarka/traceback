from tbk.agents.qa import answer_question, detect_intent
from tbk.evalx.questions import build_questions
from tbk.evalx.run import f1, grade


def test_f1_and_exact():
    assert f1({"a", "b"}, {"a", "b"}) == 1.0 and f1(set(), {"a"}) == 0.0 and f1(set(), set()) == 1.0
    assert round(f1({"a", "b"}, {"a", "c"}), 2) == 0.5
    assert grade({"a"}, {"a"})["exact"] and not grade({"a"}, {"a", "b"})["exact"]


def test_every_question_routes_to_its_intent():
    for t in ("helix", "orbit"):
        for q in build_questions(t):
            assert detect_intent(q.text) == q.intent, q.text


def test_ground_truth_is_independent_and_graph_agrees():
    """Truth comes from the generator's model; the graph agent must reproduce it from FalkorDB alone."""
    qs = build_questions("helix")
    assert len(qs) >= 45 and {q.bucket for q in qs} == {"1-hop", "2-hop", "temporal", "3+-hop"}
    wrong = [q.text for q in qs if answer_question("helix", q.text).answers != q.truth]
    assert not wrong, wrong[:3]
