"""IBKR connection manager — the bridge to the brokerage."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ib_async import IB, Contract, Stock, MarketOrder, LimitOrder, StopOrder, Order

from .config import IBKRConfig
from .market_calendar import requires_outside_rth, can_use_market_orders
from .models import OpenPosition, Direction, PortfolioState

logger = logging.getLogger(__name__)


class IBKRConnection:
    """Manages the persistent connection to Interactive Brokers TWS/Gateway."""

    def __init__(self, config: IBKRConfig):
        self.config = config
        self.ib = IB()
        self._connected = False
        self._account = ""
        self._connect_time: datetime | None = None

    async def connect(self) -> bool:
        """Establish connection to TWS/Gateway."""
        try:
            await self.ib.connectAsync(
                self.config.host,
                self.config.port,
                clientId=self.config.client_id,
                timeout=30,  # 30 second timeout for initial connect
            )
            self._connected = True
            self._connect_time = datetime.now()

            accounts = self.ib.managedAccounts()
            if accounts:
                self._account = accounts[0]
                logger.info("Connected to IBKR. Account: %s", self._account)
            else:
                logger.warning("Connected but no managed accounts found")

            self.ib.disconnectedEvent += self._on_disconnect
            return True

        except Exception as e:
            logger.error("Failed to connect to IBKR: %s", e)
            self._connected = False
            return False

    def _on_disconnect(self):
        logger.warning("IBKR connection lost at %s", datetime.now())
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.ib.isConnected()

    @property
    def account(self) -> str:
        return self._account

    async def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            self._connected = False
            logger.info("Disconnected from IBKR")

    async def reconnect(self, max_retries: int = 3, delay: float = 5.0) -> bool:
        """Attempt to reconnect after a disconnect."""
        for attempt in range(1, max_retries + 1):
            logger.info("Reconnect attempt %d/%d", attempt, max_retries)
            if await self.connect():
                return True
            await asyncio.sleep(delay)
        logger.error("Failed to reconnect after %d attempts", max_retries)
        return False

    # ── Account & Portfolio Queries ──────────────────────────────────
    # NOTE: ib_async sync methods (accountSummary, pnl) use run_until_complete
    # which crashes in an already-running async loop. Use the async versions.

    async def get_account_summary(self) -> dict[str, float]:
        """Get key account metrics using async API."""
        try:
            # Request account summary asynchronously
            await self.ib.reqAccountSummaryAsync()
            # Now read the cached data
            summary = self.ib.accountSummary(self._account)
        except Exception:
            # Fallback: use accountValues which are auto-subscribed on connect
            summary = self.ib.accountValues(self._account)

        result = {}
        for item in summary:
            tag = getattr(item, 'tag', '')
            value = getattr(item, 'value', '')
            if tag in (
                "NetLiquidation", "BuyingPower", "MaintMarginReq",
                "AvailableFunds", "GrossPositionValue",
            ):
                try:
                    result[tag] = float(value)
                except (ValueError, TypeError):
                    pass
        return result

    async def get_positions(self) -> list[OpenPosition]:
        """Get all current open positions."""
        # positions() returns cached data — safe to call in async context
        positions = self.ib.positions(self._account)
        result = []
        for pos in positions:
            if pos.position == 0:
                continue
            direction = Direction.LONG if pos.position > 0 else Direction.SHORT
            result.append(OpenPosition(
                ticker=pos.contract.symbol,
                direction=direction,
                shares=abs(int(pos.position)),
                entry_price=pos.avgCost,
                contract_id=pos.contract.conId,
            ))
        return result

    async def get_portfolio_state(self) -> PortfolioState:
        """Build a complete portfolio state snapshot."""
        summary = await self.get_account_summary()
        positions = await self.get_positions()

        equity = summary.get("NetLiquidation", 0.0)
        buying_power = summary.get("BuyingPower", 0.0)
        margin_req = summary.get("MaintMarginReq", 0.0)
        margin_pct = margin_req / equity if equity > 0 else 0.0

        # Try to get P&L — reqPnL is auto-subscribed on connect
        daily_pnl = 0.0
        unrealized = 0.0
        realized = 0.0
        try:
            pnl_list = self.ib.pnl(self._account)
            if pnl_list:
                pnl = pnl_list if not isinstance(pnl_list, list) else pnl_list[0]
                daily_pnl = pnl.dailyPnL if pnl.dailyPnL else 0.0
                unrealized = pnl.unrealizedPnL if pnl.unrealizedPnL else 0.0
                realized = pnl.realizedPnL if pnl.realizedPnL else 0.0
        except Exception as e:
            logger.debug("P&L not available: %s", e)

        return PortfolioState(
            equity=equity,
            buying_power=buying_power,
            margin_used_pct=margin_pct,
            daily_realized_pnl=realized,
            daily_unrealized_pnl=unrealized,
            daily_pnl=daily_pnl,
            daily_pnl_pct=(daily_pnl / equity * 100) if equity > 0 else 0.0,
            open_positions=positions,
            position_count=len(positions),
        )

    async def get_daily_pnl(self) -> float:
        """Get aggregate daily P&L."""
        try:
            pnl = self.ib.pnl(self._account)
            if pnl:
                p = pnl if not isinstance(pnl, list) else pnl[0]
                return p.dailyPnL if p.dailyPnL else 0.0
        except Exception:
            pass
        return 0.0

    # ── Market Data ──────────────────────────────────────────────────

    def make_stock_contract(self, ticker: str) -> Stock:
        return Stock(ticker, "SMART", "USD")

    async def qualify_contract(self, contract: Contract) -> Contract | None:
        """Validate a contract with IBKR."""
        try:
            qualified = await self.ib.qualifyContractsAsync(contract)
            return qualified[0] if qualified else None
        except Exception as e:
            logger.error("Failed to qualify contract %s: %s", contract.symbol, e)
            return None

    async def get_market_price(self, ticker: str) -> float | None:
        """Get current market price for a ticker."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            return None
        ticker_data = self.ib.reqMktData(qualified, "", False, False)
        await asyncio.sleep(2)  # wait for data
        price = ticker_data.marketPrice()
        self.ib.cancelMktData(qualified)
        return price if price == price else None  # NaN check

    # ── Order Management ─────────────────────────────────────────────

    async def place_bracket_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        limit_price: float,
        take_profit_price: float,
        stop_loss_price: float,
    ) -> list[int]:
        """Place a bracket order (entry + take-profit + stop-loss)."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        bracket = self.ib.bracketOrder(
            action=action,
            quantity=quantity,
            limitPrice=limit_price,
            takeProfitPrice=take_profit_price,
            stopLossPrice=stop_loss_price,
        )

        outside_rth = requires_outside_rth()
        for order in bracket:
            order.outsideRth = outside_rth

        order_ids = []
        for order in bracket:
            trade = self.ib.placeOrder(qualified, order)
            order_ids.append(trade.order.orderId)
            logger.info(
                "Placed %s order for %s: %d shares @ $%.2f (ID: %d)",
                order.orderType, ticker, quantity, limit_price, trade.order.orderId,
            )

        return order_ids

    async def place_market_close(self, ticker: str, action: str, quantity: int) -> int:
        """Emergency close — uses MARKET in RTH, LIMIT at last price in ETH."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        if can_use_market_orders():
            order = MarketOrder(action, quantity)
        else:
            price = await self.get_market_price(ticker)
            if action == "SELL":
                limit = price * 0.95 if price else 0.01
            else:
                limit = price * 1.05 if price else 999999
            order = LimitOrder(action, quantity, limit)
            order.outsideRth = True

        trade = self.ib.placeOrder(qualified, order)
        logger.warning(
            "EMERGENCY %s %s: %d shares (ID: %d)",
            action, ticker, quantity, trade.order.orderId,
        )
        return trade.order.orderId

    async def place_trailing_stop(
        self, ticker: str, action: str, quantity: int, trailing_pct: float
    ) -> int:
        """Place a trailing stop — uses TRAIL LIMIT in ETH, TRAIL in RTH."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        outside_rth = requires_outside_rth()
        if outside_rth:
            # ETH: TRAIL LIMIT (TRAIL not supported outside RTH for equities)
            order = Order(
                action=action,
                orderType="TRAIL LIMIT",
                totalQuantity=quantity,
                trailingPercent=trailing_pct,
                lmtPriceOffset=0.10,  # limit offset from trail price
            )
        else:
            order = Order(
                action=action,
                orderType="TRAIL",
                totalQuantity=quantity,
                trailingPercent=trailing_pct,
            )
        order.outsideRth = outside_rth
        trade = self.ib.placeOrder(qualified, order)
        logger.info(
            "Trailing stop %s %s: %d shares, trail %.1f%%, type=%s (ID: %d)",
            action, ticker, quantity, trailing_pct, order.orderType,
            trade.order.orderId,
        )
        return trade.order.orderId

    async def place_stop_limit(
        self, ticker: str, action: str, quantity: int,
        stop_price: float, limit_price: float,
    ) -> int:
        """Place a stop-limit order (preferred over plain stop)."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        order = Order(
            action=action,
            orderType="STP LMT",
            totalQuantity=quantity,
            auxPrice=stop_price,
            lmtPrice=limit_price,
        )
        order.outsideRth = requires_outside_rth()
        trade = self.ib.placeOrder(qualified, order)
        logger.info(
            "Stop-limit %s %s: %d shares, stop=$%.2f limit=$%.2f (ID: %d)",
            action, ticker, quantity, stop_price, limit_price, trade.order.orderId,
        )
        return trade.order.orderId

    async def place_adaptive_order(
        self, ticker: str, action: str, quantity: int,
        limit_price: float, urgency: str = "Normal",
    ) -> int:
        """Place an Adaptive algo order for better fill quality on large orders."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        from ib_async import TagValue
        order = Order(
            action=action,
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=limit_price,
            algoStrategy="Adaptive",
            algoParams=[TagValue("adaptivePriority", urgency)],
        )
        order.outsideRth = requires_outside_rth()
        trade = self.ib.placeOrder(qualified, order)
        logger.info(
            "Adaptive %s %s: %d shares @ $%.2f, urgency=%s (ID: %d)",
            action, ticker, quantity, limit_price, urgency, trade.order.orderId,
        )
        return trade.order.orderId

    async def place_midprice_order(
        self, ticker: str, action: str, quantity: int, cap_price: float,
    ) -> int:
        """Place a midprice order for price improvement."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        order = Order(
            action=action,
            orderType="MIDPRICE",
            totalQuantity=quantity,
            lmtPrice=cap_price,
        )
        order.outsideRth = requires_outside_rth()
        trade = self.ib.placeOrder(qualified, order)
        logger.info(
            "Midprice %s %s: %d shares, cap=$%.2f (ID: %d)",
            action, ticker, quantity, cap_price, trade.order.orderId,
        )
        return trade.order.orderId

    async def place_moc_order(self, ticker: str, action: str, quantity: int) -> int:
        """Place a Market-on-Close order for end-of-day flatten."""
        contract = self.make_stock_contract(ticker)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Cannot qualify contract for {ticker}")

        order = Order(action=action, orderType="MOC", totalQuantity=quantity)
        trade = self.ib.placeOrder(qualified, order)
        logger.info(
            "MOC %s %s: %d shares (ID: %d)",
            action, ticker, quantity, trade.order.orderId,
        )
        return trade.order.orderId

    async def cancel_order(self, order_id: int):
        """Cancel an open order."""
        for trade in self.ib.openTrades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                logger.info("Cancelled order %d", order_id)
                return
        logger.warning("Order %d not found for cancellation", order_id)

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        trades = self.ib.openTrades()
        return [
            {
                "order_id": t.order.orderId,
                "symbol": t.contract.symbol,
                "action": t.order.action,
                "quantity": t.order.totalQuantity,
                "order_type": t.order.orderType,
                "status": t.orderStatus.status,
            }
            for t in trades
        ]

    async def flatten_all(self):
        """Emergency: close ALL open positions with market orders."""
        positions = await self.get_positions()
        for pos in positions:
            action = "SELL" if pos.direction == Direction.LONG else "BUY"
            try:
                await self.place_market_close(pos.ticker, action, pos.shares)
            except Exception as e:
                logger.error("Failed to flatten %s: %s", pos.ticker, e)
