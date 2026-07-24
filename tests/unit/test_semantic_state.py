from astrbot.core.agent.semantic_state import infer_semantic_state


def test_short_fresh_fact_request_requires_planning():
    state = infer_semantic_state("金价呢")

    assert state.intent == "search"
    assert state.should_search is True
    assert "fresh_web" in state.required_evidence
    assert state.needs_planner is True


def test_context_followup_is_not_treated_as_generic_chat():
    state = infer_semantic_state("上面的图什么意思", has_image=True)

    assert state.intent == "vision"
    assert state.should_use_vision is True
    assert "image" in state.required_evidence
    assert "recent_context" in state.references


def test_audio_without_stt_is_still_semantic_evidence():
    state = infer_semantic_state("帮我听一下", has_audio=True)

    assert state.intent == "audio"
    assert state.should_use_audio is True
    assert "audio" in state.required_evidence


def test_plain_chat_does_not_require_a_planner():
    state = infer_semantic_state("在吗")

    assert state.intent == "chat"
    assert state.should_search is False
    assert state.needs_planner is False


def test_semantic_intent_set_covers_implicit_and_media_requests():
    cases = [
        ("今日金价", "search", "fresh_web"),
        ("金价呢", "search", "fresh_web"),
        ("今天天气", "search", "fresh_web"),
        ("总结这个 BV1abc123", "video", "video"),
        ("这个梗是什么", "search", "fresh_web"),
        ("这个呢", "context_followup", ""),
        ("他刚才说的可信吗", "search", "fresh_web"),
        ("帮我记住我喜欢猫", "memory", "scoped_memory"),
        ("这段语音说了什么", "audio", "audio"),
    ]

    for text, expected_intent, evidence in cases:
        state = infer_semantic_state(text, has_audio=(expected_intent == "audio"))
        assert state.intent == expected_intent, text
        if evidence:
            assert evidence in state.required_evidence, text


def test_meme_marker_does_not_turn_unrelated_chat_into_search():
    state = infer_semantic_state("我看了一个电影")

    assert state.intent == "chat"
    assert state.should_search is False
