# AI Prompt Log — AI for Managers, Homework 5

A log of what I typed into my vibe coder (Claude Code) while working through Homework 5, one problem at a time.

**Format:** one section per problem. Each section has the problem number and title, at least one prompt in my own words, and a follow-up prompt where I needed one. My running MCP server, agent team, board, database updates and output files are the evidence of the finished work.

---

## Problem 1 — Prompt log setup

**Prompt:**

> Start AI for Managers, Homework 5. I've just downloaded the zip and unzipped it, so I should have data/campus_customs.db. That file is the original shop database. The tools will update the database as tickets get resolved, so make a copy called data/campus_customs_new.db and point my MCP server and backend at that working copy. Keep campus_customs.db untouched so I can reset whenever I want to restart resolving tickets.
>
> The rules of this shop are:
>
> * desk.date_today is today for the shop. Use it to decide what is overdue.
> * Vendor lead times come from the vendors table.
> * A vendor will not ship a new product while they still have an unpaid open invoice.
> * Human approval is required for any payment.
> * When a payment is made, update the relevant tables.
> * If there's not enough cash, I pay personally — the pay tool must refuse.
> * No negative balances. Cash only goes out; we didn't model revenue.
> * Reset the database to the original values before a full run.
> * Never email customers or call real vendors. The draft stays on the board.
> * Use my Portkey API key and only gpt-5.6-luna for every agent.
>
> First, create AI_prompts.md at the start of the assignment and keep it updated as I work. It's a log of what I type into the vibe coder.

**Follow-up prompt:**

> There needs to be one section for each problem, with:
>
> * the problem number and title
> * at least one prompt in my own words
> * a follow-up prompt if I needed one
>
> I'll work one problem at a time. My code, database updates and output files are the evidence, so I don't need any extra proof in the log.

---

## Problem 2 — Understand the database, make the working copy, start the harness

**Prompt:**

> Starting with problem 2, open data/campus_customs.db and look through every table and its fields, then copy the original file to data/campus_customs_new.db. Later problems update that working copy, never the original.
>
> Study the three open tickets to see how they link to the other tables. Then start output/harness.md: for each table, list the file, its fields, and one short line on why the table matters for the agents. I'll keep growing this harness file in later problems.

**Follow-up prompt:**

> Make the original database read-only so nothing can write to it by accident, and give me a small reset script that copies the original back over the working copy. In the harness, spell out the path for each ticket — 101 goes ticket → inventory → invoice 501 → vendor, 102 goes ticket → lease 1 → cash, 103 goes ticket → inventory → pricing.

---

## Problem 3 — Build the MCP server with three ticket tools

**Prompt:**

> For problem 3, build the MCP server. Write it in MCP_server/ using FastMCP, and have it talk to data/campus_customs_new.db. I don't need to connect or run it in this problem. Every agent in this homework will use tools from this MCP server, so I'll add more tools later. For now, write three tools I know I'll need for the tickets in the database. Keep the names clear. Never invent data — only use what's in the database.
>
> In output/harness.md, list each of the three MCP tools. For each one, say which table it reads, which ticket it helps unlock (101, 102, 103), and one sentence on why that tool is the right one for that ticket. Vague lines like "reads inventory" score low, so tie each tool to its ticket. Then add a short MCP_server/readme.md that explains what the MCP server is for, which database file it uses, and the three tools it has.

**Follow-up prompt:**

> Make the date math use desk.date_today, not the real clock — get_invoice should say how many days overdue invoice 501 is and get_lease should say how many days until rent is due. And make the server refuse to open the original campus_customs.db even if someone points it there.

---

## Problem 4 — Connect the MCP server to the vibe coder and test each tool

**Prompt:**

> For problem 4, add the MCP server to the vibe coder so it can call the tools. Save the connection JSON in .mcp.json at the project root. With the vibe coder connected, test each of the three MCP tools and save the evidence in output/mcp_smoke.json. For every tool, include the prompt I asked (or the tool name) and the tool output, and the output has to match the values in data/campus_customs_new.db.

**Follow-up prompt:**

> Don't just paste the output — for each tool, also run the matching SQL against campus_customs_new.db and put the database values next to the tool values with a matches true/false, so anyone grading can see they line up. Use paths relative to the project in .mcp.json so it works for anyone who clones the repo.

---

## Problem 5 — The agent team and the growing MCP server

**Prompt:**

> Now problem 5: build the Campus Customs agent team with PydanticAI — boss, inventory, accounting, facilities and customer service — with prompts, models and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in backend/prompts, one file per agent. Put data types in backend/models.py and the agent files under backend/. The layout can vary as long as the five roles are clear.
>
> Use my Portkey API key and only gpt-5.6-luna for every agent. Write each prompt in my own words with the shop rules the agent needs — detailed prompts that cover the agent's whole job and scope, not short generic ones.
>
> Add any tools the agents need to the MCP server so they can work the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db — don't invent a second shop-tool layer that bypasses MCP.
>
> Wire the agents so they append to output/audit_trail.json as they run. For each agent-loop step, record enough to audit later. Don't wipe it each run.
>
> In output/harness.md, list each agent and each MCP tool, including the new ones, with which table each tool uses. Add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. Update MCP_server/readme.md so the tool list matches.

**Follow-up prompt:**

> The agents should only ever *prepare* a payment or purchase. Put the actual pay tool behind a human click — no agent should have it in its tool list, and it should refuse if cash is short, if the vendor still has an open invoice, or if the approver is an agent name. The dollar amounts should come from the invoice, lease or unit cost, never from the model. Give each agent only the tools for its role, and stop delegation loops: no delegating to yourself or back up the chain, and cap delegations per ticket.

**Follow-up prompt:**

> I ran ticket 101 as a test and the customer draft told Tauhid about our $840 printer invoice and the $8 reprint cost — customers should never see our costs, bills or cash. It also called the hoodie a "Navy Bulldog Hoodie," which isn't the real name. Fix customer service so it uses the product name from the database and keeps the back office out of the draft. Also the boss's summary left out accounting because accounting was called by inventory, not by the boss — make the boss credit every agent that worked on the ticket. Then reset the database.

---

## Problem 6 — Write down the expected plan: output/desk_tickets.html

**Prompt:**

> Before I wire the backend, write down what I expect the team to do on each open ticket. Build output/desk_tickets.html, a page I can double-click, with one tab per ticket plus empty Cash and Reflections tabs for later problems. On each ticket tab, fill in only an Expected section and leave room for an Actual section that I'll fill after I run the agents. For each ticket's expected section, in my own words:
>
> * who the boss should call first and why
> * all the agent delegations I expect — not the boss calling everyone
> * which MCP tools I expect that run to use
>
> Plans that send every specialist on every ticket score low. I'll compare this plan to what actually happens when the agents resolve the three tickets.

**Follow-up prompt:**

> Put the cash I expect on each ticket in the expected section too, so I can check the money later: 101 should be $840 for invoice 501 and then $8 for the tee reprint, 102 should be $2,400 rent, and 103 should move no cash because a quote isn't a purchase. Also say which agents I expect to stay benched on each ticket.

---

## Problem 7 — FastAPI backend routes

**Prompt:**

> For problem 7, my React dashboard needs a backend it can call. In backend/main.py, use FastAPI and add routes that:
>
> * return the three tickets and whether each is open or resolved
> * take a ticket ID and run the agent team on that ticket
> * return recent agent events — what each agent said and which tools they used — so the board can refresh
> * approve a payment or purchase after a human clicks approve (agents only prepare the payment; this route is the one that actually changes the cash)
> * return the current checking balance from cash_accounts
> * reset the database to the original values for a fresh run
>
> Then from the backend/ folder, start the server with `uvicorn main:app --reload --port 8000` so the backend runs on my localhost and the frontend can call these routes. In output/harness.md, list each route on one line with what it does.

**Follow-up prompt:**

> The backend should read shop data through the MCP server too, not straight from SQLite — same rule as the agents. Run the agent team in the background so the board can poll events while it runs, and after a reset, only show events from after the reset so the board starts clean.

---

## Problem 8 — The React dashboard and output/design.md

**Prompt:**

> For problem 8, build the frontend dashboard in frontend/ with React, Vite and TypeScript. It should call the routes from problem 7. At minimum, the board should:
>
> * list all three tickets
> * let me pick one ticket and start the agent team on it
> * show each agent and what they're saying or doing while the ticket runs
> * mark a ticket resolved when the run finishes
> * show a short summary of what each agent did on the ticket
> * let a human approve a payment or purchase when asked
> * show the checking balance
>
> Make it look good and make it really creative — this is a real desk people would want to sit at and put things on. Keep it Fortnite-themed with characters and visuals built in HTML/CSS, no generated images. The frontend talks to the backend on localhost, and the backend has to allow the Vite page origin so the browser can call the routes. I'll start the board with `npm run dev`. Then write output/design.md explaining what I chose for the layout, how the agents read differently, how tickets get resolved, how cash shows up, and why — including the creative choices that make it feel special and fun to use.

**Follow-up prompt:**

> A few fixes: the status pill turns into a blank white box while agents are working, the "2 approvals" flag covers the status badge on the ticket card, and when I switch tickets the Drop-in button stays disabled until the page catches up. Also make it obvious which agents were benched on a ticket, so you can see the boss didn't send everyone.

---

## Problem 9 — Full run: reset, resolve all three tickets, record what happened

**Prompt:**

> For problem 9, before testing the agents on a full run over the three tickets, reset data/campus_customs_new.db so I start clean.
>
> 1. Note the starting checking balance.
> 2. Run all three tickets on the board until each one is resolved.
> 3. In output/desk_tickets.html, fill the Actual section on each ticket tab from this run: which agents worked, what they delegated, and which tools they used.
> 4. Keep the Expected section so I can compare the two.
> 5. On the Cash tab, itemize the money starting from checking: the starting balance for each ticket, how much cash changed when it resolved and why, and the ending balance — which must match cash_accounts in the working database. Wrong cash math loses points even if the board shows every ticket resolved.
> 6. Save output/resolved_tickets.json with, for each ticket: ID, final status, a short outcome, what each agent contributed, and any human approvals.
> 7. Make output/resolved_board.html, a page I can double-click, with a screenshot of my React board for each resolved ticket.
> 8. Append the real runs to output/audit_trail.json.
> 9. Finish output/harness.md so it covers the tables, MCP tools, the five agents, API routes, the dashboard and the safety rules.

**Follow-up prompt:**

> Run 101 and 102 first and stop so I can approve the supply drops myself on the board — invoice 501 first, then the tee reprint, then rent. Run 103 only after invoice 501 is paid so Bulldog Print Co can ship again. Then pull the actual numbers straight from the audit trail and the database for the Actual sections and the Cash tab, and double-check the ending balance against cash_accounts.

---

## Problem 10 — Reflections

**Prompt:**

> Finally, open output/desk_tickets.html and fill in the Reflections tab. Answer in my own voice and be detailed and thorough about how I'd evaluate the agents' performance on each ticket and why. For each ticket:
>
> * How did the actual run compare to the expected plan I wrote earlier?
> * What would have been simpler as one agent with tools, and why?
> * Describe three new problems campers/customers might bring that this agent team could solve with the tools I built.
> * Describe three new problems they might bring that the team could NOT solve with the tools I built, and explain the tools and agents I'd need to solve them.
>
> Tie every answer to this app and the three tickets I ran. Use the ticket tabs and the Cash tab on the same page as evidence. Make it thoughtful, thorough and human — this is my reflection section.

**Follow-up prompt:**

> Point to specific evidence in each answer — the actual delegation chain, the tools that were called, the dollar amounts on the Cash tab — instead of general statements. And be honest where the team was overkill, like the rent ticket, where one agent with the lease and payment tools would have been enough.

---

## Problem 11 — Publish the final submission to GitHub

**Prompt:**

> The final submission has to be public on GitHub. Set the hw-5 folder up as a git repo with a README that explains how to set up the .venv, run the MCP server, start the backend with uvicorn and the board with npm run dev, and reset the database. Keep my .env, the .venv and node_modules out of the repo, and never commit my Portkey key. Then push it to my public repo.

**Follow-up prompt:**

> Before pushing, search the whole repo for my API key and for any model name other than gpt-5.6-luna, so nothing leaks and no other model shows up in my code.
