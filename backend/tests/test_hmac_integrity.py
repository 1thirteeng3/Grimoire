from app.models.pacts import InquisitorReport, StatelessPactModel, ToolCallIntent

SECRET = b"test_secret_key_grimoire"


def make_test_pact() -> StatelessPactModel:
    return StatelessPactModel.create(
        session_id="sess_hmac_test_0001",
        entity_manifest_hash="abc123",
        operator_proposal_raw="print('hello')",
        tool_intent=ToolCallIntent(
            tool_name="execute_python",
            literal_arguments={"code": "print('hello')"},
        ),
        critic_report=[InquisitorReport(severity="WARN", technical_reasoning="teste")],
        secret_key=SECRET,
    )


def test_valid_signature_passes():
    pact = make_test_pact()
    assert pact.verify_signature(SECRET) is True


def test_tampered_arguments_fail_verification():
    pact = make_test_pact()
    tampered = pact.model_copy(
        update={
            "tool_intent": ToolCallIntent(
                tool_name="execute_python",
                literal_arguments={"code": "import os; os.system('rm -rf /')"},
            )
        }
    )
    assert tampered.verify_signature(SECRET) is False


def test_wrong_key_fails():
    pact = make_test_pact()
    assert pact.verify_signature(b"wrong_key") is False
