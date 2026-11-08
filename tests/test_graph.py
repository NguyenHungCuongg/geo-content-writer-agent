"""Test workflow LangGraph của UC-09 (agent/graph.py): checkpoint, resume, approval, xử lý lỗi."""

from __future__ import annotations

import pytest

from agent.claims import ClaimReport, ClaimVerdict, Evidence, Location
from agent.graph import (
    FileCheckpointSaver,
    ScriptedWorkflowLLM,
    approve_graph,
    build_graph,
    make_checkpointer,
    resume_graph,
    start_graph,
)
from agent.kb import BRAND_KIT_PATH, MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import LLMError
from agent.loop import AgentStopped
from agent.trace import Tracer
from agent.uc09 import (
    ApprovalBlockedError,
    ApprovalConflictError,
    ApprovalDecision,
)


@pytest.fixture(scope="module")
def shared_kb() -> MemoryKB:
    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, BRAND_KIT_PATH)
    return kb


def test_graph_has_six_nodes_and_stop_condition(shared_kb, tmp_path):
    """DoD: Graph >= 3 node, có điều kiện dừng (HR-02)."""
    tracer = Tracer("g-nodes", traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / "g-nodes.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    node_names = set(graph.nodes.keys()) - {"__start__"}
    assert {"prompt_set", "plan", "research", "write", "fact_check", "approve"} <= node_names
    assert len(node_names) >= 6


def test_resume_after_kill_at_item_3(shared_kb, tmp_path):
    """DoD: node write ném lỗi giả lập tắt máy ở bài 3/8; graph mới dùng cùng checkpointer
    chạy tiếp; bài 1-2 không gọi lại LLM, không có bài trùng, cuối cùng đủ 8 bài."""
    run_id = "a1" * 16
    ckpt_path = tmp_path / f"{run_id}.ckpt"

    # Lần chạy 1: ném RuntimeError ở bước write của bài 3 (art-03)
    tracer1 = Tracer(run_id, traces_dir=tmp_path)
    saver1 = FileCheckpointSaver(ckpt_path)
    llm1 = ScriptedWorkflowLLM(shared_kb, crash_at_write_items={"art-03"})
    graph1 = build_graph(saver1, tracer=tracer1, llm=llm1, kb=shared_kb)

    with pytest.raises(RuntimeError, match="Simulated crash at write art-03"):
        start_graph(
            graph1,
            run_id,
            brief="Thương hiệu Skyveil chuyên sơn chống nóng mái tôn tại TP.HCM.",
            topics=["sơn chống nóng mái tôn"],
            auto_approve=True,
        )

    # Kiểm tra trạng thái đã lưu trong checkpoint sau khi sập ở bài 3:
    # Bài 1, 2 đã approved; bài 3 đang dở
    saver_check = FileCheckpointSaver(ckpt_path)
    snap = graph1.get_state({"configurable": {"thread_id": run_id}})
    items_before = snap.values["calendar"]["items"]
    assert items_before[0]["status"] == "approved"
    assert items_before[1]["status"] == "approved"
    assert items_before[2]["status"] != "approved"

    # Lần chạy 2: tạo graph mới + LLM mới trên cùng checkpointer, resume tới hết
    tracer2 = Tracer(run_id, traces_dir=tmp_path)
    llm2 = ScriptedWorkflowLLM(shared_kb)
    graph2 = build_graph(saver_check, tracer=tracer2, llm=llm2, kb=shared_kb)

    final_state = resume_graph(graph2, run_id, auto_approve=True)
    final_items = final_state["calendar"]["items"]

    assert len(final_items) == 8
    assert len({it["id"] for it in final_items}) == 8  # không có bài trùng
    assert all(it["status"] == "approved" for it in final_items)
    assert len(final_state["articles"]) == 8

    # Bài 1-2 không gọi lại LLM trong lần chạy 2
    assert "art-01" not in llm2.touched_items
    assert "art-02" not in llm2.touched_items
    assert "art-03" in llm2.touched_items


def test_resume_twice(shared_kb, tmp_path):
    """DoD: ngắt 2 lần liên tiếp (ở bài 2 và bài 5), kết quả như trên."""
    run_id = "b2" * 16
    ckpt_path = tmp_path / f"{run_id}.ckpt"

    # Lần 1: sập ở bài 2
    llm1 = ScriptedWorkflowLLM(shared_kb, crash_at_write_items={"art-02"})
    graph1 = build_graph(
        FileCheckpointSaver(ckpt_path),
        tracer=Tracer(run_id, traces_dir=tmp_path),
        llm=llm1,
        kb=shared_kb,
    )
    with pytest.raises(RuntimeError, match="art-02"):
        start_graph(
            graph1,
            run_id,
            brief="Skyveil sơn chống nóng mái tôn.",
            topics=["sơn chống nóng mái tôn"],
            auto_approve=True,
        )

    # Lần 2: resume, chạy qua bài 2-4 rồi sập tiếp ở bài 5
    llm2 = ScriptedWorkflowLLM(shared_kb, crash_at_write_items={"art-05"})
    graph2 = build_graph(
        FileCheckpointSaver(ckpt_path),
        tracer=Tracer(run_id, traces_dir=tmp_path),
        llm=llm2,
        kb=shared_kb,
    )
    with pytest.raises(RuntimeError, match="art-05"):
        resume_graph(graph2, run_id, auto_approve=True)

    assert "art-01" not in llm2.touched_items
    assert "art-02" in llm2.touched_items

    # Lần 3: resume hoàn tất bài 5..8
    llm3 = ScriptedWorkflowLLM(shared_kb)
    graph3 = build_graph(
        FileCheckpointSaver(ckpt_path),
        tracer=Tracer(run_id, traces_dir=tmp_path),
        llm=llm3,
        kb=shared_kb,
    )
    final_state = resume_graph(graph3, run_id, auto_approve=True)
    final_items = final_state["calendar"]["items"]

    assert len(final_items) == 8
    assert all(it["status"] == "approved" for it in final_items)
    for done_id in ("art-01", "art-02", "art-03", "art-04"):
        assert done_id not in llm3.touched_items
    assert "art-05" in llm3.touched_items


def test_item_waits_for_approval(shared_kb, tmp_path, monkeypatch):
    """DoD: run dừng ở approve, bài ở review; resume với approve -> approved;
    resume với reject -> revise_uc03 nhận đúng reason."""
    import agent.graph as graph_mod

    run_id = "c3" * 16
    tracer = Tracer(run_id, traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / f"{run_id}.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    state = start_graph(
        graph,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=False,
    )

    # Dừng ở node approve của bài đầu tiên (art-01), bài đang ở trạng thái review
    snap = graph.get_state({"configurable": {"thread_id": run_id}})
    assert snap.next == ("approve",)
    assert state["calendar"]["items"][0]["status"] == "review"
    assert any(
        e["event"] == "decision" and e.get("action") == "await_approval"
        for e in tracer.events
    )

    # Ghi nhận tham số truyền vào revise_uc03 khi người duyệt reject
    captured_feedback: list[list[str]] = []
    real_revise = graph_mod.revise_uc03

    def spy_revise(article, feedback, **kwargs):
        captured_feedback.append(list(feedback))
        return real_revise(article, feedback, **kwargs)

    monkeypatch.setattr(graph_mod, "revise_uc03", spy_revise)

    # 1. Resume với reject -> gọi revise_uc03 với đúng reason rồi quay lại chờ duyệt ở approve
    reason_text = "Cần bổ sung bảng so sánh chi tiết hơn ở mục 2"
    state_after_reject = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="reject", reason=reason_text, reviewer="editor1"),
    )
    assert captured_feedback == [[reason_text]]
    snap2 = graph.get_state({"configurable": {"thread_id": run_id}})
    assert snap2.next == ("approve",)
    assert state_after_reject["calendar"]["items"][0]["status"] == "review"

    # 2. Resume với approve -> bài 1 chuyển sang approved (và dừng chờ duyệt ở bài 2)
    state_after_approve = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="approve", reason="Đã đạt yêu cầu", reviewer="editor1"),
    )
    assert state_after_approve["calendar"]["items"][0]["status"] == "approved"
    assert state_after_approve["calendar"]["items"][1]["status"] == "review"


def test_approval_twice_is_rejected(shared_kb, tmp_path):
    """DoD: Bấm Duyệt hai lần -> lần thứ hai bị từ chối (ApprovalConflictError / 409)
    và bài chỉ chuyển approved một lần."""
    run_id = "d4" * 16
    tracer = Tracer(run_id, traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / f"{run_id}.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    start_graph(
        graph,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=False,
    )

    # Duyệt lần 1 cho bài art-01 (kèm item_id="art-01")
    approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="approve", reason="OK", reviewer="admin"),
        item_id="art-01",
    )

    # Bấm duyệt lần 2 cho cùng bài art-01 -> phải bị chặn bằng ApprovalConflictError
    with pytest.raises(ApprovalConflictError):
        approve_graph(
            graph,
            run_id,
            ApprovalDecision(decision="approve", reason="OK lần 2", reviewer="admin"),
            item_id="art-01",
        )

    # Kiểm tra trong trace chỉ có đúng 1 quyết định approval cho art-01
    approvals_art01 = [
        e for e in tracer.events
        if e["event"] == "decision"
        and e.get("action") == "approval"
        and e.get("item_id") == "art-01"
    ]
    assert len(approvals_art01) == 1


def test_approval_after_restart_resumes(shared_kb, tmp_path):
    """DoD: Duyệt sau khi server khởi động lại chạy tiếp từ checkpoint."""
    run_id = "e5" * 16
    ckpt_path = tmp_path / f"{run_id}.ckpt"

    # Server 1: chạy tới điểm dừng chờ duyệt bài 1
    tracer1 = Tracer(run_id, traces_dir=tmp_path)
    saver1 = FileCheckpointSaver(ckpt_path)
    llm1 = ScriptedWorkflowLLM(shared_kb)
    graph1 = build_graph(saver1, tracer=tracer1, llm=llm1, kb=shared_kb)

    start_graph(
        graph1,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=False,
    )
    del graph1, saver1

    # Server 2 (khởi động lại): nạp lại checkpointer từ đĩa, tạo graph mới và duyệt
    tracer2 = Tracer(run_id, traces_dir=tmp_path)
    saver2 = FileCheckpointSaver(ckpt_path)
    llm2 = ScriptedWorkflowLLM(shared_kb)
    graph2 = build_graph(saver2, tracer=tracer2, llm=llm2, kb=shared_kb)

    state2 = approve_graph(
        graph2,
        run_id,
        ApprovalDecision(decision="approve", reason="Duyệt sau restart", reviewer="lead"),
    )
    assert state2["calendar"]["items"][0]["status"] == "approved"
    assert state2["calendar"]["items"][1]["status"] == "review"


def test_second_reject_marks_item_failed_and_moves_on(shared_kb, tmp_path):
    """D-15: Từ chối lần thứ 2 thì bài chuyển failed và sang bài tiếp theo."""
    run_id = "f6" * 16
    tracer = Tracer(run_id, traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / f"{run_id}.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    start_graph(
        graph,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=False,
    )

    # Từ chối lần 1 -> sửa bài và quay lại review bài 1
    s1 = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="reject", reason="Chưa đạt lần 1", reviewer="r1"),
    )
    assert s1["calendar"]["items"][0]["status"] == "review"

    # Từ chối lần 2 -> bài 1 thành failed, chuyển sang bài 2 (review)
    s2 = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="reject", reason="Vẫn chưa đạt lần 2", reviewer="r1"),
    )
    assert s2["calendar"]["items"][0]["status"] == "failed"
    assert s2["calendar"]["items"][1]["status"] == "review"


def test_approve_blocked_when_unsourced_number_claims_remain(shared_kb, tmp_path, monkeypatch):
    """D-15: Nút duyệt bị khoá khi bài còn claim có số liệu chưa supported."""
    import agent.graph as graph_mod

    def fake_fact_check_with_blocking(article, **kwargs):
        unverifiable_claim = ClaimVerdict(
            claim="Sơn giúp giảm 99% hoá đơn tiền điện mỗi tháng.",
            location=Location(heading="Hiệu quả", paragraph=0),
            has_number=True,
            verdict="unverifiable",
            evidence=[
                Evidence(
                    chunk_id=None,
                    url="https://blogmaiton.example/x",
                    quote="giảm 99%",
                    trust_tier="C",
                    stance="supports",
                )
            ],
            action="rewrite",
        )
        return article, ClaimReport(claims=[unverifiable_claim], round=2)

    monkeypatch.setattr(graph_mod, "fact_check_loop", fake_fact_check_with_blocking)

    run_id = "77" * 16
    tracer = Tracer(run_id, traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / f"{run_id}.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    start_graph(
        graph,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=False,
    )

    with pytest.raises(ApprovalBlockedError) as exc:
        approve_graph(
            graph,
            run_id,
            ApprovalDecision(decision="approve", reason="Cố duyệt", reviewer="admin"),
        )
    assert len(exc.value.blocking) == 1


def test_agent_stopped_marks_item_failed_and_continues(shared_kb, tmp_path):
    """K5: AgentStopped ở một bài -> bài đó failed kèm lý do, lịch vẫn chạy tiếp các bài còn lại."""
    run_id = "88" * 16
    tracer = Tracer(run_id, traces_dir=tmp_path)
    saver = FileCheckpointSaver(tmp_path / f"{run_id}.ckpt")
    llm = ScriptedWorkflowLLM(shared_kb, stop_at_write_items={"art-02"})
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=shared_kb)

    final_state = start_graph(
        graph,
        run_id,
        brief="Skyveil sơn chống nóng mái tôn.",
        topics=["sơn chống nóng mái tôn"],
        auto_approve=True,
    )
    items = final_state["calendar"]["items"]
    assert items[1]["id"] == "art-02"
    assert items[1]["status"] == "failed"
    assert sum(1 for it in items if it["status"] == "approved") == 7
    assert any(
        e["event"] == "node" and e.get("name") == "write"
        and e.get("status") == "error" and e.get("item_id") == "art-02"
        for e in tracer.events
    )


def test_llm_error_stops_run_and_can_resume(shared_kb, tmp_path):
    """K5: LLMError (quota, mạng) -> dừng run, ghi error, resume được sau."""
    run_id = "99" * 16
    ckpt_path = tmp_path / f"{run_id}.ckpt"

    llm1 = ScriptedWorkflowLLM(shared_kb, llm_error_at_write_items={"art-02"})
    graph1 = build_graph(
        FileCheckpointSaver(ckpt_path),
        tracer=Tracer(run_id, traces_dir=tmp_path),
        llm=llm1,
        kb=shared_kb,
    )
    with pytest.raises(LLMError):
        start_graph(
            graph1,
            run_id,
            brief="Skyveil sơn chống nóng mái tôn.",
            topics=["sơn chống nóng mái tôn"],
            auto_approve=True,
        )

    # Resume lại khi hết lỗi mạng -> hoàn tất cả 8 bài (bài 2 được viết lại, không bị failed)
    llm2 = ScriptedWorkflowLLM(shared_kb)
    graph2 = build_graph(
        FileCheckpointSaver(ckpt_path),
        tracer=Tracer(run_id, traces_dir=tmp_path),
        llm=llm2,
        kb=shared_kb,
    )
    final_state = resume_graph(graph2, run_id, auto_approve=True)
    assert all(it["status"] == "approved" for it in final_state["calendar"]["items"])
    assert AgentStopped is not None


def test_postgres_checkpointer_resumes_across_graphs(db, shared_kb, tmp_path):
    """Kiểm tra trực tiếp PostgresSaver trên service Postgres (CI / Docker local)."""
    run_id = "ab" * 16
    saver1 = make_checkpointer(db)
    llm1 = ScriptedWorkflowLLM(shared_kb, crash_at_write_items={"art-03"})
    graph1 = build_graph(saver1, tracer=Tracer(run_id, traces_dir=tmp_path), llm=llm1, kb=shared_kb)

    with pytest.raises(RuntimeError, match="art-03"):
        start_graph(
            graph1,
            run_id,
            brief="Skyveil sơn chống nóng mái tôn.",
            topics=["sơn chống nóng mái tôn"],
            auto_approve=True,
        )

    saver2 = make_checkpointer(db)
    llm2 = ScriptedWorkflowLLM(shared_kb)
    graph2 = build_graph(saver2, tracer=Tracer(run_id, traces_dir=tmp_path), llm=llm2, kb=shared_kb)
    final_state = resume_graph(graph2, run_id, auto_approve=True)
    assert all(it["status"] == "approved" for it in final_state["calendar"]["items"])
    assert "art-01" not in llm2.touched_items
    assert "art-02" not in llm2.touched_items
