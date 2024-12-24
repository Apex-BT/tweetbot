from datetime import datetime
from apexbt.sheets.sheets import save_tweet, save_trade, setup_google_sheets
from apexbt.crypto.crypto import get_crypto_price
from datetime import timedelta
from apexbt.trade.trade import TradeManager
from apexbt.tweet.tweet import TwitterManager
import time

def process_tweets(tweets):
    """Process a list of tweets and write to Google Sheet"""
    sheets = setup_google_sheets()
    tweets_sheet = sheets["tweets"]
    trades_sheet = sheets["trades"]
    pnl_sheet = sheets["pnl"]

    # Create TradeManager instance
    trade_manager = TradeManager(sheets)
    trade_manager.start_monitoring()

    # Process tweets with rate limiting
    for tweet in tweets:
        try:
            ticker, ticker_status = TwitterManager.extract_ticker(tweet.text)
            if not ticker:
                continue

            price_data = None
            if ticker_status == "Single ticker":
                price_data = get_crypto_price(ticker, tweet.created_at, include_historical=False)

                if price_data and price_data.get("tweet_time_price"):
                    trade_data = {
                        "trade_id": f"T{tweet.created_at.strftime('%Y%m%d%H%M%S')}",
                        "ticker": ticker,
                        "entry_price": price_data["tweet_time_price"],
                        "position_size": 100,
                        "direction": "Long",
                        "stop_loss": float(price_data["tweet_time_price"]) * 0.95,
                        "take_profit": float(price_data["tweet_time_price"]) * 1.15,
                        "tweet_id": tweet.id,
                        "notes": "Auto trade based on tweet signal",
                        "timestamp": tweet.created_at
                    }

                    print(f"Opening trade with 100 USDC on {ticker} at {price_data['tweet_time_price']}")

                    time.sleep(1)

                    if trade_manager.add_trade(ticker, float(price_data["tweet_time_price"]), tweet.created_at):
                        save_trade(trades_sheet, trade_data, pnl_sheet)
                        print(f"Opened new trade for {ticker} at {price_data['tweet_time_price']}")
                    else:
                        print(f"Could not open trade for {ticker} - position already exists")
                else:
                    print(f"Could not get historical price for {ticker} at tweet time {tweet.created_at}")

            save_tweet(tweets_sheet, tweet, ticker, ticker_status, price_data)

            # Add rate limiting delay
            time.sleep(1)  # Wait 1 second between tweet processing

        except Exception as e:
            print(f"Error processing tweet: {str(e)}")
            time.sleep(2)  # Wait longer after error
            continue

    return trade_manager

def run_historical_analysis(start_date=None):
    """Run analysis on historical tweets"""
    if start_date is None:
        # Default to 7 days ago if no start date provided
        start_date = datetime.now() - timedelta(days=7)

    print(f"Fetching historical tweets since {start_date}")

    # Initialize Twitter manager and fetch historical tweets
    twitter_manager = TwitterManager()

    if twitter_manager.verify_credentials():
        username = "Vader_AI_"
        historical_tweets = twitter_manager.fetch_historical_tweets(username, start_date)

        if historical_tweets:
            print(f"Found {len(historical_tweets)} tweets. Processing...")
            trade_manager = process_tweets(historical_tweets)

            try:
                # Keep the script running to monitor positions
                while True:
                    time.sleep(10)  # Update every 10 seconds
                    stats = trade_manager.get_current_stats()
                    if stats:
                        print("\nCurrent Positions:")
                        for position in stats:
                            print(f"{position['ticker']}: {position['price_change']} "
                                  f"(Entry: {position['entry_price']}, Current: {position['current_price']})")
                    print("-" * 50)
            except KeyboardInterrupt:
                print("Stopping trade manager...")
                trade_manager.stop_monitoring()
        else:
            print("No tweets found for the specified period.")
    else:
        print("Failed to authenticate with Twitter API")

def run_trade_manager_only():
    """Run only the trade manager to monitor existing positions"""
    sheets = setup_google_sheets()

    # Create TradeManager instance
    trade_manager = TradeManager(sheets)
    trade_manager.start_monitoring()

    try:
        print("Trade manager started. Monitoring existing positions...")
        while True:
            time.sleep(10)  # Update every 10 seconds
            stats = trade_manager.get_current_stats()
            if stats:
                print("\nCurrent Positions:")
                for position in stats:
                    print(f"{position['ticker']}: {position['price_change']} "
                          f"(Entry: {position['entry_price']}, Current: {position['current_price']})")

                # Print totals (last row)
                if len(stats) > 0:
                    totals = stats[-1]
                    print("\nPortfolio Totals:")
                    print(f"Total Invested: ${totals['invested_amount']:.2f}")
                    print(f"Total Current Value: ${totals['current_value']:.2f}")
                    print(f"Total PNL: ${totals['pnl_dollars']:.2f}")
            print("-" * 50)
    except KeyboardInterrupt:
        print("Stopping trade manager...")
        trade_manager.stop_monitoring()

if __name__ == "__main__":

    # Set start date to December 1st, 2024
    # start_date = datetime(2024, 12, 10)
    # run_historical_analysis(start_date)

    # Just run the trade manager
    run_trade_manager_only()
