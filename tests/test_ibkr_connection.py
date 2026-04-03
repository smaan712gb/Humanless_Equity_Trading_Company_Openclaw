"""Integration test — verify IBKR Gateway connectivity.
Requires IB Gateway running on the configured port.
Skip if not available.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from tools.config import IBKRConfig
from tools.connection import IBKRConnection

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))


async def _can_connect() -> bool:
    """Quick check if IB Gateway is reachable."""
    import asyncio
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(IBKR_HOST, IBKR_PORT), timeout=3
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        return False


@pytest.fixture
async def ibkr():
    conn = IBKRConnection(IBKRConfig(host=IBKR_HOST, port=IBKR_PORT, client_id=99))
    yield conn
    await conn.disconnect()


@pytest.mark.asyncio
async def test_ibkr_connection(ibkr):
    """Test basic connection to IB Gateway."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    connected = await ibkr.connect()
    assert connected is True
    assert ibkr.is_connected is True
    assert ibkr.account != ""
    print(f"Connected to IBKR. Account: {ibkr.account}")


@pytest.mark.asyncio
async def test_ibkr_account_summary(ibkr):
    """Test account summary retrieval."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    await ibkr.connect()
    summary = await ibkr.get_account_summary()

    assert "NetLiquidation" in summary
    equity = summary["NetLiquidation"]
    assert equity > 0
    print(f"Account equity: ${equity:,.2f}")

    if "BuyingPower" in summary:
        bp = summary["BuyingPower"]
        print(f"Buying power: ${bp:,.2f}")


@pytest.mark.asyncio
async def test_ibkr_positions(ibkr):
    """Test position retrieval (may be empty on paper account)."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    await ibkr.connect()
    positions = await ibkr.get_positions()

    # Positions may be empty — that's fine
    assert isinstance(positions, list)
    print(f"Open positions: {len(positions)}")
    for p in positions:
        print(f"  {p.ticker}: {p.direction.value} {p.shares}sh @ ${p.entry_price:.2f}")


@pytest.mark.asyncio
async def test_ibkr_portfolio_state(ibkr):
    """Test full portfolio state snapshot."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    await ibkr.connect()
    state = await ibkr.get_portfolio_state()

    assert state.equity > 0
    assert isinstance(state.open_positions, list)
    print(f"Portfolio: equity=${state.equity:,.2f} positions={state.position_count} "
          f"margin={state.margin_used_pct:.1%} P&L=${state.daily_pnl:,.2f}")


@pytest.mark.asyncio
async def test_ibkr_contract_qualification(ibkr):
    """Test that we can qualify stock contracts."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    await ibkr.connect()

    # Test core watchlist tickers
    for ticker in ["LITE", "ASML", "MU", "APP"]:
        contract = ibkr.make_stock_contract(ticker)
        qualified = await ibkr.qualify_contract(contract)
        assert qualified is not None, f"Failed to qualify {ticker}"
        print(f"  {ticker}: conId={qualified.conId} exchange={qualified.exchange}")


@pytest.mark.asyncio
async def test_ibkr_disconnect_reconnect(ibkr):
    """Test disconnect and reconnect cycle."""
    if not await _can_connect():
        pytest.skip(f"IB Gateway not running on {IBKR_HOST}:{IBKR_PORT}")

    await ibkr.connect()
    assert ibkr.is_connected

    await ibkr.disconnect()
    assert not ibkr.is_connected

    reconnected = await ibkr.reconnect(max_retries=2, delay=1.0)
    assert reconnected is True
    assert ibkr.is_connected
