ApeXBT V0.1 - BASE CHAIN
FEEL FREE TO ADD YOUR COMMENTS / MAKE SUGGESTIONS

Description: Create a trading BOT that follows AiXBT and carries out trades automatically based on its tweets and mentions.

Objective: Outperform Ethereum on monthly basis.

Process:

Follow VaderAI - https://x.com/Vader_AI_
Monitor tweets
When a ticker is mentioned analyse that ticker and buy with 5% of the USDC balance
Before checking, BOT must check no current balance of this ticker
Contract must be more than 2 days old
Liquidity greater than $250k
If there are multiple tokens with same name, purchase the one with greater liquidity
If multiple tokens mentioned in the same tweet, ignore tweet
Track price changes hourly
Selling the token
If price increases 100%, sell initial purchase amount hold rest
If price decreases 50%, sell full amount
Further details in section Portfolio Management

Portfolio Management: The BOT needs to be actively monitoring the portfolio and rebalancing it to maximise returns.

Note below strategies:
The BOT must not hold more than 25 tokens at any given time excluding USDC
Actively monitor token performances and rebalance as and when required
Once the 5 tokens have been purchased, monitor prices of the tokens from purchase date+time of the last token, and sell the token that has the worst performance over the last 14 day period into USDC - key - FROM PURCHASE TIME
If 26th token is mentioned, evaluate performance of all 5 tokens for last 7 days and sell the worst performing token - IRRESPECTIVE OF PURCHASE DATE+TIME
If any token has had 100% performance and initial capital is out - that token has GRADUATED and does not count as one of the 5 tokens and we hold

Routing Trades: Route all trades via Uniswap. Trades must be GAS optimised but TX should not fail - do this by monitoring GAS fees and use 10% higher GAS.

Database format: https://docs.google.com/spreadsheets/d/1AlizAkY2Vc1rUfpS_XRAMJkjv2A_thjhr5Q-GBoSFbU/edit?usp=sharing


API’s:

Dexscreener : https://docs.dexscreener.com/api/reference
Use for verifying token age
Use for verifying token liquidity

Uniswap : https://docs.uniswap.org/contracts/v2/reference/API/overview
Executing trades


—---------------------------

ApeXBT V0.2 - BASE CHAIN

All of the above stays the same but we monitor 2 agents.

AiXBT and VaderAI https://x.com/Vader_AI_

Deploy 10% to AiXBT tokens, max limit to 5 tokens.

Deploy 1% to Vader tokens, max limit to 10 tokens.

Would prefer to do this right away if possible after some initial testing because AiXBT is mentioning too many coins on different networks.


—-------------------

Important Links

https://www.cookie.fun/
