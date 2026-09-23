# Kraków 1795 — Game Design Document (v0.1)

## One-line pitch
Third-person stealth / intrigue / puzzle game. Kraków, 1795, after the Third Partition. Player is the figurehead of a movement to seize the city and relight a reformed Commonwealth. Many roads to power; the character you start as decides which are open, which are cheap, and which are nearly impossible.

## Pillars
1. **Every path is a system, not a script.** Church, underworld, salons, street, guild. Each is a live faction with influence, resources, and its own agenda. The player composes them.
2. **Stealth is social as well as physical.** Sneaking past a patrol matters, but so does not being recognised at a salon, or moving a letter through a checkpoint.
3. **Concede to win.** Losses are expected. Giving a district to a rival, taking a compromise deal, or letting a friend hang can be the correct move.
4. **The city is the board.** Kraków districts are territory. Control is contested by the player and by Austria, Russia, Prussia, and local powers.

## Setting notes (alternate history flex points)
- Kraków fell to Austria in the Third Partition (Oct 1795). Play begins winter 1795/96.
- Kościuszko Uprising (1794) failed one year earlier; veterans, arms caches, and grudges remain.
- Austrian garrison in Wawel. Russian and Prussian agents active. Habsburg bureaucracy replacing Polish law.
- Alternate-history lever: the player's success may reshape what "reform" means (Constitution of 3 May restored, a republic, a new elective monarchy, a burgher-led commonwealth, etc.). Endings branch on which factions carried you.

## Player origins (starting character)
Each origin sets: starting influence per faction, starting skills, starting contacts, a personal goal, and a personal weakness that rivals can exploit.

| Origin | Strong paths | Weak paths | Weakness |
|---|---|---|---|
| Szlachcic (noble) | Politics, Salon, Church (moderate) | Underworld, Street | Estate can be seized; family hostages |
| Bohemian artist | Salon, Street (radicals), Printers | Church, Politics | Reputation scandal; drink/debt |
| Peasant / veteran | Street, Underworld (moderate) | Salon, Politics, Church | No papers; easily conscripted or hanged |
| Merchant / guild burgher | Guilds, Underworld (smuggling), Politics (moderate) | Church, Street radicals | Ledgers can be audited; goods seized |
| Priest / cleric | Church, Street (moderate) | Underworld, Salon radicals | Bishop can silence you; excommunication |
| Jewish merchant (Kazimierz) | Underworld (moderate), Guilds, Finance | Church, Politics | Legal restrictions; pogrom risk as rival lever |

## Factions
**External powers (antagonists, sometimes tools):**
- Austria (occupier). Garrison, police, courts, tax. Strongest hard power.
- Russia. Spies, bribes, wants Austria weak. Will fund you then betray you.
- Prussia. Trade leverage, wants Kraków trade routes. Bankers.

**Local powers (playable levers):**
- Church (Bishop, parish priests, monasteries). Legitimacy, crowds, sanctuary, money.
- Salon / Intelligentsia (nobles, artists, printers, Enlightenment clubs). Ideas, propaganda, foreign sympathy.
- Underworld (smugglers, thieves, fences, Vistula boatmen). Weapons, routes, muscle, intel.
- Street (workers, students, Kościuszko veterans). Crowds, protests, sit-ins, riots.
- Guilds / Burghers (town council remnants, merchants). Money, supply, strike power.
- Magnates (great families). Armed retainers, land, foreign courts. Fickle.

Each faction: `influence` (player's sway, 0–100), `loyalty` (to player vs. to occupiers), `strength` (raw power in city), `agenda` (what they want), `fear` (how much they fear Austria).

## City map (districts as territory)
Old Town (Rynek), Wawel (garrison), Kazimierz, Stradom, Kleparz, Kanonicza/Church quarter, Vistula docks, Garbary (tanners/workers). Each district: controlling faction, unrest, watch presence, safe houses.

## Core loops
### Macro loop (day / night turn)
1. **Day**: manage. Read letters, make deals, allocate agents, set faction moves. Time-limited (action points).
2. **Night**: play. Third-person mission in a district. Stealth, infiltration, sabotage, meeting, rescue, theft, assassination (optional/consequential).
3. **Dawn**: resolve. Faction reactions, Austrian crackdown level, news spreads, new opportunities and threats.

### Mission loop (3D stealth / puzzle)
- Vision cones, light/shadow, noise. Suspicion meter per guard (calm → curious → searching → alarm).
- Social stealth: disguises, papers, invitations. Wrong disguise in wrong district = recognition.
- Puzzles: routes through the city (rooftops, cellars, church crypts), locks, ciphers on letters, timing patrols, moving crowds as cover.
- Non-lethal default. Lethal has consequences (crackdown, faction fear).

### Intrigue loop
- Rival agents run their own plots against you. Detected via intel (underworld, salon gossip, church confessions).
- Deals: every faction wants something. Concessions are tracked and come due.
- Betrayal is a mechanic: you can betray, and be betrayed, with reputation cost.

## Win / lose
- Win: control ≥ N districts + one legitimacy source + Austrian garrison neutralised (siege, defection, negotiated withdrawal) → ending branch by coalition.
- Lose: player captured/killed, crackdown reaches max (city under martial law, movement crushed), or player's figurehead status collapses (all factions below threshold).

## Prototype scope (this repo)
**Milestone 0 (now):** greybox district, player controller, guard AI with vision cone + suspicion, origin select affecting starting influence, faction data model, day/night skeleton.
**Milestone 1:** one full mission with objectives, disguises, simple dialogue, faction resolve step.
**Milestone 2:** district map screen, 3 factions fully live, rival agent plots.
**Milestone 3:** Blender asset pass (Rynek, Sukiennice, St Mary's, tenement blocks), audio, save/load.

## Tech
- Engine: Godot 4.7 (GDScript). Forward+ renderer.
- Assets: Blender → glTF 2.0 (.glb) into `assets/models/`. Greybox uses CSG until then.
- Data: factions/origins/districts as JSON in `data/`, loaded at boot.
