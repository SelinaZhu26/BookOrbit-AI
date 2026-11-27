"""UC-01 Register an Account, UC-02 Log In Using Biometric Authentication."""
import pytest

from bookorbit import clock
from bookorbit.errors import BiometricError, NotFoundError, StorageError, ValidationError
from tests.helpers import NO_FACE, TWO_FACES, face


# ---------------------------------------------------------------- UC-01
def test_register_creates_rc_account_with_face_template(ctx):
    u = ctx.auth.register("Maya Lin", "maya_l", "maya@example.com", [face(40)])
    assert u["role"] == "RC" and u["status"] == "ACTIVE"
    assert u["balance"] == 0.0 and u["warnings"] == 0
    rec = ctx.store.find("biometrics", user_ID=u["user_ID"])
    assert rec and (ctx.config.data_dir / rec["template_Path"]).exists()
    # only the template is stored, never the photo
    assert not list((ctx.config.data_dir / "biometrics").glob("*.jpg"))


@pytest.mark.parametrize("name,username,email,field", [
    ("", "okname", "a@b.com", "full_name"),
    ("Ann", "ab", "a@b.com", "username"),                 # too short
    ("Ann", "has space", "a@b.com", "username"),
    ("Ann", "x" * 21, "a@b.com", "username"),
    ("Ann", "okname", "not-an-email", "email"),
    ("Ann", "ALICE", "a@b.com", "username"),              # taken (case-insensitive)
])
def test_register_invalid_fields_are_reported(ctx, name, username, email, field):
    with pytest.raises(ValidationError) as e:
        ctx.auth.register(name, username, email, [face(40)])
    assert field in e.value.fields
    assert ctx.users.by_username(username) is None or username.lower() == "alice"


def test_register_needs_exactly_one_face(ctx):
    with pytest.raises(BiometricError) as e:
        ctx.auth.register("Ann", "ann_1", "a@b.com", [NO_FACE])
    assert e.value.code == "NO_FACE"
    with pytest.raises(BiometricError) as e:
        ctx.auth.register("Ann", "ann_1", "a@b.com", [TWO_FACES])
    assert e.value.code == "MULTI_FACE"
    assert ctx.users.by_username("ann_1") is None


def test_register_save_failure_leaves_no_half_account(ctx):
    ctx.store.fail_next_write = True
    with pytest.raises(StorageError):
        ctx.auth.register("Ann", "ann_2", "a@b.com", [face(41)])
    assert ctx.users.by_username("ann_2") is None
    assert not list((ctx.config.data_dir / "biometrics").glob("U-0008*"))


# ---------------------------------------------------------------- UC-02
def test_login_success_starts_session_with_role(ctx):
    r = ctx.auth.verify_sign_in("selina", face(14))
    assert r.ok and r.session.role == "VC" and not r.session.wallet_only
    assert ctx.store.filter("login_attempts", username="selina")[-1]["success"] is True


def test_login_unknown_username_not_counted(ctx):
    with pytest.raises(NotFoundError, match="No account with that username"):
        ctx.auth.start_sign_in("nobody")
    assert ctx.store.read_all("login_attempts") == []


def test_login_no_face_is_not_a_failure(ctx):
    r = ctx.auth.verify_sign_in("alice", NO_FACE)
    assert not r.ok and r.retry_capture
    assert ctx.store.filter("login_attempts", username="alice") == []


def test_three_failures_lock_username_for_5_minutes(ctx):
    clock.set_now(clock.now())
    r1 = ctx.auth.verify_sign_in("alice", face(99))
    r2 = ctx.auth.verify_sign_in("alice", face(98))
    assert "attempt 1 of 3" in r1.message and "attempt 2 of 3" in r2.message
    r3 = ctx.auth.verify_sign_in("alice", face(97))
    assert r3.locked
    with pytest.raises(BiometricError) as e:                  # even the right face is refused now
        ctx.auth.verify_sign_in("alice", face(13))
    assert e.value.code == "LOCKED"
    clock.advance(minutes=5, seconds=1)
    assert ctx.auth.verify_sign_in("alice", face(13)).ok      # lock expired


def test_success_resets_failure_count(ctx):
    ctx.auth.verify_sign_in("alice", face(99))
    ctx.auth.verify_sign_in("alice", face(98))
    assert ctx.auth.verify_sign_in("alice", face(13)).ok
    assert "attempt 1 of 3" in ctx.auth.verify_sign_in("alice", face(97)).message


def test_suspended_account_signs_in_to_wallet_only_mode(ctx):
    r = ctx.auth.verify_sign_in("zakiah", face(16))
    assert r.ok and r.session.wallet_only


def test_missing_template_tells_user_to_contact_su(ctx):
    u = ctx.users.by_username("ibrahim")
    ctx.store.delete("biometrics", lambda r: r["user_ID"] == u["user_ID"])
    with pytest.raises(BiometricError) as e:
        ctx.auth.start_sign_in("ibrahim")
    assert e.value.code == "NO_TEMPLATE" and "Super-User" in e.value.message


def test_new_customer_can_register_then_sign_in(ctx):
    ctx.auth.register("Maya Lin", "maya", "maya@example.com", [face(50), face(50)])
    assert ctx.auth.verify_sign_in("maya", face(50)).ok
    assert not ctx.auth.verify_sign_in("maya", face(51)).ok
