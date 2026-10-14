# Battle Desk — design notes (Problem 8)

The board is a back-office desk I'd actually want to sit at. The model is Fortnite's lobby and match HUD: the tickets are loot, the agents are a squad, the payments are supply drops, and a resolved ticket gets a Victory Royale. Everything is drawn in HTML and CSS. No images, no generated art, no external fonts.

## Layout

A three-column desk under a HUD bar, with a sky behind it:

- **HUD (top).** The Campus Customs logo, the **desk day** chip (2026-08-31, the shop's today), the model chip (`gpt-5.6-luna · 5-agent squad`), the **checking bank**, the **approver** name box, and **Back to lobby** (reset).
- **Left: Tickets ("loot pool").** Each ticket is a loot card colored by rarity: customer order = Rare blue, rent notice = Epic purple, price override = Legendary gold. Every card shows the requester, the type, a plain status badge (Open / Agents working / Needs your approval / Resolved) and how many approvals are waiting. A small CSS coffee mug with steam sits under the cards, because it's a desk.
- **Center: the match.** A big ticket hero banner with the facts pulled from the database (product, size, qty, linked invoice or lease) and the **Drop in** button that runs the team. Under it: the delegation path, the five-agent squad, **Supply Drops** (approvals), **Drafts**, and the **Match Summary**.
- **Right: Live feed.** A kill-feed-style stream of every agent event, newest on top: tasks, delegations, tool calls with their arguments, tool results, reports, human clicks.

## How agents read differently

- Every agent is a **CSS-drawn Fortnite-style character** with its own color and rarity stripe: Boss = Jonesy with a headset (Legendary), Inventory = Peely the banana (Uncommon green), Accounting = Midas in gold (Epic), Facilities = a hard-hat Constructor (Rare blue), Customer Service = the Supply Llama (Mythic).
- Each card shows **what the agent is doing right now** ("Using check_inventory", "Waiting on Accounting", "Reported back"), a **speech bubble** with its latest words or final report, and a **hotbar** of the MCP tools it used plus who it delegated to. I wanted it to look like an inventory bar.
- The agent that's working right now **lifts up and glows**, and its avatar bobs. Agents who weren't needed on a ticket are **benched**: dimmed and desaturated, with "Benched for this ticket". That makes it obvious when the boss didn't send everyone out.
- In the live feed, every line has a colored edge in that agent's color, and delegations are highlighted in gold, so you can follow the chain at a glance.

## How tickets get resolved

1. Pick a loot card and hit **🪂 Drop in · run agent team**. The bus has launched and the squad starts streaming events.
2. When agents prepare a payment or purchase, it lands in **Supply Drops** as a crate on a parachute that floats until someone acts. The status pill turns gold: **Needs your approval**.
3. The human types their name in **Approver** and clicks **✔ Approve & pay** or **Decline**. If the pay tool refuses (vendor still blocked, not enough cash), a red toast says exactly why and nothing moves.
4. When nothing's left pending, the ticket flips to **Resolved** and a **#1 VICTORY ROYALE** banner pops in. The Match Summary shows the boss's outcome, who it called first and why, and one line per agent.
5. Customer replies sit as a **yellow sticky note stamped NOT SENT**, because the draft stays on the board.
6. A **storm chip** on the ticket shows urgency in Fortnite terms: "In the storm" for the overdue invoice 501, "Storm closing" for rent due in 2 days, "Safe zone" once it's paid.

## How cash shows up

- The **gold bank** in the HUD always shows the live checking balance from `cash_accounts` (via `/api/cash`), with a spinning coin. When approvals are pending, it also shows how much cash is waiting on them, so I can see what's promised before I click.
- Clicking the bank opens the **ledger**: every payment with kind, reference, amount, date, and who approved it. "Cash only goes out" is right in the header, because this homework has no revenue.
- Every approval toast says the new balance ("Paid $840.00 — checking now $2,560.00").

## Why — the creative choices

- **Fortnite is a shared language for "who's doing what, right now."** A kill feed, a squad bar, and supply drops are already great at showing many actors at once. That's exactly the multi-agent problem: five agents talking and calling tools is hard to follow in a log, and easy to follow as a squad.
- **Benched vs. active** makes the most important thing on this assignment visible: did the boss bring in only the agents the ticket needed?
- **Supply drops for approvals** make the human step feel like a moment, not a hidden button. Money can't move until someone actually opens the crate.
- **Victory Royale** gives the work a finish line. Closing tickets should feel good.
- **The desk touches** (the mug, the sticky-note drafts, the plain-English badges under the Fortnite flavor) keep it a place you'd actually work. You get the fun, but the facts are always written plainly next to it.
