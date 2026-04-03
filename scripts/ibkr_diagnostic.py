"""IBKR Gateway diagnostic — test connectivity step by step."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()

HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "4002"))


async def run_diagnostics():
    print(f"=== IBKR Gateway Diagnostic ===")
    print(f"Target: {HOST}:{PORT}")
    print()

    # Step 1: TCP socket check
    print("[1] TCP Socket Check...")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        print("    OK TCP port is OPEN")
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
        print(f"    FAIL TCP FAILED: {e}")
        print("    → Is IB Gateway running? Check the application.")
        return

    # Step 2: ib_async connection (multiple clientIds)
    print()
    print("[2] IB API Connection (trying clientIds 1, 10, 99)...")
    from ib_async import IB

    for client_id in [1, 10, 99]:
        ib = IB()
        try:
            print(f"    Trying clientId={client_id}, timeout=60s...")
            await ib.connectAsync(HOST, PORT, clientId=client_id, timeout=60)
            print(f"    OK Connected with clientId={client_id}!")

            # Step 3: Account info
            accounts = ib.managedAccounts()
            print(f"    OK Managed accounts: {accounts}")

            # Step 4: Account values
            if accounts:
                acct = accounts[0]
                print(f"    OK Account: {acct}")

                # Try positions (cached, always works)
                positions = ib.positions()
                print(f"    OK Open positions: {len(positions)}")

                # Try account values
                try:
                    await ib.reqAccountSummaryAsync()
                    summary = ib.accountSummary()
                    for item in summary:
                        if item.tag == "NetLiquidation":
                            print(f"    OK Equity: ${float(item.value):,.2f}")
                        elif item.tag == "BuyingPower":
                            print(f"    OK Buying Power: ${float(item.value):,.2f}")
                except Exception as e:
                    print(f"    WARN Account summary failed: {e}")
                    print("    (This may be normal on holidays)")

                # Try contract qualification
                print()
                print("[3] Contract Qualification...")
                from ib_async import Stock
                for ticker in ["LITE", "ASML", "MU", "APP"]:
                    try:
                        contract = Stock(ticker, "SMART", "USD")
                        qualified = await ib.qualifyContractsAsync(contract)
                        if qualified:
                            print(f"    OK {ticker}: conId={qualified[0].conId}")
                        else:
                            print(f"    FAIL {ticker}: qualification returned empty")
                    except Exception as e:
                        print(f"    FAIL {ticker}: {e}")

            ib.disconnect()
            print()
            print("=== DIAGNOSTIC COMPLETE — CONNECTION SUCCESSFUL ===")
            return

        except asyncio.TimeoutError:
            print(f"    FAIL Timeout with clientId={client_id}")
            try:
                ib.disconnect()
            except Exception:
                pass
        except Exception as e:
            print(f"    FAIL Error with clientId={client_id}: {e}")
            try:
                ib.disconnect()
            except Exception:
                pass

    print()
    print("=== ALL CONNECTION ATTEMPTS FAILED ===")
    print("Possible causes:")
    print("  1. Today is Good Friday — Gateway API may not respond on holidays")
    print("  2. 'Enable ActiveX and Socket Clients' is not checked in Gateway config")
    print("  3. 'Read-Only API' is checked — uncheck it")
    print("  4. Trusted IP doesn't include 127.0.0.1")
    print("  5. Another application is using the same clientId")
    print("  6. Gateway needs a restart")
    print()
    print("Try: Restart IB Gateway, verify API settings, and run this again.")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
