import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CoinReason, CoinTransaction, RewardOrder, RewardProduct, User
from tests.test_integration import auth, register

pytestmark = pytest.mark.integration
ADDRESS = {
    "full_name": "Test Recipient",
    "phone": "9000000000",
    "address_line1": "123 Test Street",
    "address_line2": None,
    "city": "Bengaluru",
    "state": "Karnataka",
    "postal_code": "560001",
    "country_code": "IN",
}


async def shopper(api, sessions, username="shopper", coins=5000, staff=False):
    headers = auth(await register(api, username))
    identifier = UUID((await api.get("/api/v1/users/me", headers=headers)).json()["data"]["id"])
    async with sessions() as session:
        user = await session.get(User, identifier)
        user.is_staff = staff
        if coins:
            session.add(
                CoinTransaction(
                    user_id=identifier,
                    amount=coins,
                    reason=CoinReason.DAILY_CHECK_IN,
                    event_key="isolated-test-funding",
                    reward_date=datetime.now(UTC).date(),
                )
            )
        await session.commit()
    return headers, identifier


def payload(reward="premium-condom-pack", **changes):
    return {"reward_id": reward, "shipping_address": dict(ADDRESS), **changes}


async def order(api, headers, body=None, key=None):
    return await api.post(
        "/api/v1/coins/redeem",
        headers={**headers, "Idempotency-Key": str(key or uuid4())},
        json=body or payload(),
    )


async def wallet(api, headers):
    return (await api.get("/api/v1/users/me/coins", headers=headers)).json()["data"]


@pytest.mark.parametrize(
    "product,cost,size",
    [
        ("premium-condom-pack", 500, None),
        ("water-based-lubricant", 1000, None),
        ("body-massage-oil", 2000, None),
        ("soft-adjustable-blindfold", 4000, None),
    ],
)
async def test_can_order_each_product_to_indian_address(api, sessions, product, cost, size):
    headers, _ = await shopper(api, sessions)
    response = await order(api, headers, payload(product, size=size))
    assert response.status_code == 201
    receipt = response.json()["data"]
    assert receipt["coins_spent"] == cost and not receipt["replayed"]
    assert receipt["order"]["status"] == "placed" and receipt["order"]["size"] == size
    assert receipt["order"]["shipping_address"]["phone"] == "+919000000000"
    assert receipt["wallet"]["balance"] == 5000 - cost
    assert receipt["wallet"]["total_earned"] == 5000 and receipt["wallet"]["total_spent"] == cost
    assert receipt["wallet"]["total_refunded"] == 0
    identifier = receipt["order"]["id"]
    detail = await api.get(f"/api/v1/users/me/orders/{identifier}", headers=headers)
    assert (
        detail.status_code == 200
        and detail.json()["data"]["shipping_address"]["postal_code"] == "560001"
    )
    assert detail.headers["cache-control"] == "no-store"
    history = (await api.get("/api/v1/users/me/orders", headers=headers)).json()
    assert history["total"] == 1 and "shipping_address" not in history["data"][0]
    ledger = (await api.get("/api/v1/users/me/coins/transactions", headers=headers)).json()["data"]
    debit = next(x for x in ledger if x["reason"] == "redemption")
    assert debit["amount"] == -cost and debit["order_id"] == identifier


async def test_idempotent_retries_charge_once_and_conflicts_do_not_change_address(api, sessions):
    headers, _ = await shopper(api, sessions, coins=500)
    key = uuid4()
    responses = await asyncio.gather(*[order(api, headers, key=key) for _ in range(6)])
    assert sorted(r.status_code for r in responses) == [200] * 5 + [201]
    assert len({r.json()["data"]["order"]["id"] for r in responses}) == 1
    assert sum(r.json()["data"]["coins_spent"] for r in responses) == 500
    changed = payload(shipping_address=ADDRESS | {"city": "Another city"})
    conflict = await order(api, headers, changed, key)
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    )
    assert (await wallet(api, headers))["balance"] == 0


async def test_parallel_distinct_orders_cannot_overdraw(api, sessions):
    headers, _ = await shopper(api, sessions, coins=500)
    responses = await asyncio.gather(order(api, headers), order(api, headers))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert (await wallet(api, headers))["balance"] == 0
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RewardOrder)) == 1


async def test_stock_race_and_refund_restore_inventory_once(api, sessions):
    first, _ = await shopper(api, sessions, "first", coins=500)
    second, _ = await shopper(api, sessions, "second", coins=500)
    async with sessions() as session:
        product = await session.get(RewardProduct, "premium-condom-pack")
        product.stock_quantity = 1
        await session.commit()
    responses = await asyncio.gather(order(api, first), order(api, second))
    assert sorted(r.status_code for r in responses) == [201, 409]
    winner = next(i for i, r in enumerate(responses) if r.status_code == 201)
    headers = [first, second][winner]
    identifier = responses[winner].json()["data"]["order"]["id"]
    cancelled = await asyncio.gather(
        *[
            api.post(f"/api/v1/users/me/orders/{identifier}/cancel", headers=headers)
            for _ in range(4)
        ]
    )
    assert all(r.status_code == 200 for r in cancelled)
    assert sum(r.json()["data"]["coins_refunded"] for r in cancelled) == 500
    w = await wallet(api, headers)
    assert (w["balance"], w["total_earned"], w["total_spent"], w["total_refunded"]) == (
        500,
        500,
        500,
        500,
    )
    async with sessions() as session:
        assert (await session.get(RewardProduct, "premium-condom-pack")).stock_quantity == 1
    retry = await order(
        api, headers, key=UUID(responses[winner].request.headers["Idempotency-Key"])
    )
    assert retry.status_code == 200 and retry.json()["data"]["order"]["status"] == "cancelled"
    assert (await wallet(api, headers))["balance"] == 500


@pytest.mark.parametrize(
    "patch",
    [
        {"country_code": "US"},
        {"postal_code": "012345"},
        {"postal_code": "56000"},
        {"phone": "1234567890"},
        {"full_name": "A"},
        {"address_line1": ""},
        {"city": "X"},
        {"state": ""},
        {"full_name": "Test\nRecipient"},
    ],
)
async def test_invalid_addresses_rejected_before_spending(api, sessions, patch):
    headers, _ = await shopper(api, sessions, coins=500)
    response = await order(api, headers, payload(shipping_address=ADDRESS | patch))
    assert response.status_code == 422 and (await wallet(api, headers))["balance"] == 500
    assert "9000000000" not in response.text and "123 Test Street" not in response.text


@pytest.mark.parametrize(
    "changes",
    [
        {"coin_cost": 1},
        {"amount": 1},
        {"quantity": 2},
        {"status": "shipped"},
        {"user_id": str(uuid4())},
    ],
)
async def test_customer_cannot_supply_price_quantity_status_or_owner(api, sessions, changes):
    headers, _ = await shopper(api, sessions, coins=500)
    response = await order(api, headers, payload(**changes))
    assert response.status_code == 422 and (await wallet(api, headers))["balance"] == 500


async def test_order_requires_idempotency_key_and_rejects_unavailable_sizes(api, sessions):
    headers, _ = await shopper(api, sessions)
    assert (
        await api.post("/api/v1/coins/redeem", headers=headers, json=payload())
    ).status_code == 422
    assert (await order(api, headers, payload(size="M"))).json()["error"]["code"] == "invalid_size"
    assert (await order(api, headers, payload("missing"))).status_code == 404


async def test_catalog_lists_only_requested_rewards_and_rejects_retired_merchandise(api, sessions):
    headers, _ = await shopper(api, sessions)
    async with sessions() as session:
        session.add(
            RewardProduct(
                id="lustcode-stickers",
                name="LustCode Sticker Pack",
                description="Retired merchandise retained for order history",
                coin_cost=500,
                available_sizes=[],
                active=True,
            )
        )
        await session.commit()
    products = (await api.get("/api/v1/coins/rewards")).json()["data"]["rewards"]
    assert [(p["name"], p["coin_cost"], p["available_sizes"]) for p in products] == [
        ("Premium Condom Pack (12 pcs)", 500, []),
        ("Water-Based Lubricant (100ml)", 1000, []),
        ("Body Massage Oil (100ml)", 2000, []),
        ("Soft Adjustable Blindfold", 4000, []),
    ]
    assert (await order(api, headers, payload("lustcode-stickers"))).status_code == 404
    for product in products:
        response = await order(api, headers, payload(product["id"], size="M"))
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_size"
    assert (await wallet(api, headers))["balance"] == 5000


async def test_order_address_is_owned_and_fulfillment_access_requires_staff(api, sessions):
    owner, _ = await shopper(api, sessions, "owner")
    other, _ = await shopper(api, sessions, "other")
    receipt = (await order(api, owner)).json()["data"]
    identifier = receipt["order"]["id"]
    assert (
        await api.get(f"/api/v1/users/me/orders/{identifier}", headers=other)
    ).status_code == 404
    assert (
        await api.post(f"/api/v1/users/me/orders/{identifier}/cancel", headers=other)
    ).status_code == 404
    assert (await api.get("/api/v1/users/me/orders", headers=other)).json()["total"] == 0
    for method, path, body in [
        ("GET", "/admin/orders", None),
        ("GET", f"/admin/orders/{identifier}", None),
        ("PATCH", f"/admin/orders/{identifier}", {"status": "processing"}),
        ("PATCH", "/admin/rewards/premium-condom-pack", {"active": False}),
    ]:
        response = await api.request(method, "/api/v1" + path, headers=other, json=body)
        assert response.status_code == 403 and "9000000000" not in response.text
    assert (await api.get("/api/v1/users/owner")).json()["data"].get("is_staff") is None


async def test_fulfillment_tracking_and_status_transitions(api, sessions):
    owner, _ = await shopper(api, sessions, "owner")
    staff, _ = await shopper(api, sessions, "staff", coins=0, staff=True)
    identifier = (await order(api, owner)).json()["data"]["order"]["id"]
    assert (await api.get(f"/api/v1/admin/orders/{identifier}", headers=staff)).json()["data"][
        "shipping_address"
    ]["full_name"] == ADDRESS["full_name"]
    path = f"/api/v1/admin/orders/{identifier}"
    assert (await api.patch(path, headers=staff, json={"status": "delivered"})).status_code == 409
    assert (await api.patch(path, headers=staff, json={"status": "processing"})).status_code == 200
    assert (
        await api.post(f"/api/v1/users/me/orders/{identifier}/cancel", headers=owner)
    ).status_code == 409
    assert (await api.patch(path, headers=staff, json={"status": "shipped"})).status_code == 422
    shipped = await api.patch(
        path,
        headers=staff,
        json={"status": "shipped", "courier": "Test Courier", "tracking_number": "TEST-12345"},
    )
    assert shipped.status_code == 200 and shipped.json()["data"]["shipped_at"]
    assert (await api.patch(path, headers=staff, json={"status": "cancelled"})).status_code == 409
    assert (await api.patch(path, headers=staff, json={"status": "delivered"})).status_code == 200
    assert (await api.patch(path, headers=staff, json={"status": "processing"})).status_code == 409
    assert (await wallet(api, owner))["balance"] == 4500


async def test_staff_cancellation_refunds_processing_order_once(api, sessions):
    owner, _ = await shopper(api, sessions, "owner", coins=500)
    staff, _ = await shopper(api, sessions, "staff", coins=0, staff=True)
    identifier = (await order(api, owner)).json()["data"]["order"]["id"]
    path = f"/api/v1/admin/orders/{identifier}"
    await api.patch(path, headers=staff, json={"status": "processing"})
    for _ in range(2):
        assert (
            await api.patch(path, headers=staff, json={"status": "cancelled"})
        ).status_code == 200
    assert (await wallet(api, owner))["balance"] == 500
    assert (await wallet(api, owner))["total_refunded"] == 500


async def test_atomic_rollback_preserves_coins_order_and_stock(api, sessions, monkeypatch):
    headers, _ = await shopper(api, sessions, coins=500)
    async with sessions() as session:
        product = await session.get(RewardProduct, "premium-condom-pack")
        product.stock_quantity = 1
        await session.commit()

    async def failure(self):
        raise OperationalError("fixture", {}, Exception("private details"))

    key = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", failure)
        response = await order(api, headers, key=key)
    assert response.status_code == 503
    assert (await wallet(api, headers))["balance"] == 500
    assert (await api.get("/api/v1/users/me/orders", headers=headers)).json()["total"] == 0
    async with sessions() as session:
        assert (await session.get(RewardProduct, "premium-condom-pack")).stock_quantity == 1
    assert (await order(api, headers, key=key)).status_code == 201


async def test_staff_can_pause_catalog_and_adjust_stock_without_price_changes(api, sessions):
    owner, _ = await shopper(api, sessions, "owner")
    staff, _ = await shopper(api, sessions, "staff", coins=0, staff=True)
    path = "/api/v1/admin/rewards/premium-condom-pack"
    assert (await api.patch(path, headers=staff, json={"active": False})).status_code == 200
    assert (await order(api, owner)).json()["error"]["code"] == "product_unavailable"
    assert (
        await api.patch(path, headers=staff, json={"active": True, "stock_quantity": 0})
    ).status_code == 200
    assert (await order(api, owner)).json()["error"]["code"] == "out_of_stock"
    assert (await api.patch(path, headers=staff, json={"stock_quantity": None})).status_code == 200
    assert (await api.patch(path, headers=staff, json={"coin_cost": 1})).status_code == 422
    assert (await order(api, owner)).status_code == 201


async def test_cross_origin_redeem_header_is_allowed(client):
    client._transport.app.state.settings.cors_origins[:] = ["http://localhost:3000"]
    response = await client.options(
        "/api/v1/coins/redeem",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )
    assert response.status_code == 200


async def test_staff_claims_and_profile_updates_cannot_elevate_user(api, sessions, settings):
    headers, identifier = await shopper(api, sessions, coins=0)
    claims = jwt.decode(
        headers["Authorization"].removeprefix("Bearer "), options={"verify_signature": False}
    )
    claims["is_staff"] = True
    forged = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        await api.get("/api/v1/admin/orders", headers={"Authorization": "Bearer " + forged})
    ).status_code == 403
    assert (
        await api.patch(
            "/api/v1/users/me", headers=headers, json={"bio": "fixture", "is_staff": True}
        )
    ).status_code == 422
    async with sessions() as session:
        user = await session.get(User, identifier)
        user.is_staff = True
        await session.commit()
    assert (await api.get("/api/v1/admin/orders", headers=headers)).status_code == 200
    async with sessions() as session:
        user = await session.get(User, identifier)
        user.is_staff = False
        await session.commit()
    assert (await api.get("/api/v1/admin/orders", headers=headers)).status_code == 403


async def test_refund_failure_rolls_back_order_and_balance(api, sessions, monkeypatch):
    headers, _ = await shopper(api, sessions, coins=500)
    receipt = (await order(api, headers)).json()["data"]
    identifier = receipt["order"]["id"]

    async def failure(self):
        raise OperationalError("fixture", {}, Exception("private details"))

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", failure)
        response = await api.post(f"/api/v1/users/me/orders/{identifier}/cancel", headers=headers)
    assert response.status_code == 503 and (await wallet(api, headers))["balance"] == 0
    assert (await api.get(f"/api/v1/users/me/orders/{identifier}", headers=headers)).json()["data"][
        "status"
    ] == "placed"
    assert (
        await api.post(f"/api/v1/users/me/orders/{identifier}/cancel", headers=headers)
    ).status_code == 200
    assert (await wallet(api, headers))["balance"] == 500
