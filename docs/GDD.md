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

## Economy lever: propination (beer and spirits)
Propination (propinacja) was the magnates' and towns' legal monopoly on brewing, distilling and selling drink;
tenants were obliged to buy from the lord's tavern. In 1795 it was one of the largest incomes of the great families
and a fresh target for Austrian excise. In play:
- Every district has taverns tied to a propination holder (a magnate, the town, a monastery). Taverns are safe-house
  candidates, rumour mills and recruiting grounds; the holder's steward (ekonom), brewer, maltster, distiller and
  cellarman are named NPCs.
- Levers: boycott (the Street), smuggling untaxed spirits from Kazimierz and the docks (Underworld), cutting a
  magnate in on excise fraud (Magnates), preaching temperance (Church), an Austrian excise raid (Austria) as a threat
  the player can trigger or forestall.
- Consequences ripple: a boycotted magnate loses income and either bends toward the movement or hires mercenaries.

## Trade and foreigners
Kraków sat on the Vistula salt and grain route and the overland route from Lwów. Armenian and Greek merchants
carried Ottoman and Persian goods (spices, dyes, silks, carpets, coffee); Hungarian wine came over the Carpathians;
Scots pedlars, German and Italian craftsmen, Flemish printers and French émigrés fleeing the Revolution all lived in
the city. These appear as named traders and tradesmen in the districts and as contacts with foreign courts.

## World simulation (the living city)
Reference points: Hitman's schedules and opportunities, the recent 007's crowd and NPC routines.
- **Clock.** The night mission runs on a world clock (default 1 real second = 1 game minute, from 21:00). Curfew
  bells, the watch's rounds, tavern closing and church hours are clock events.
- **Posts and schedules.** Every named NPC has a loop of posts (stall, tavern bar, church door, tenement door,
  well) with an activity at each (pack up, drink, pray, gossip, sleep). Crowd NPCs draw from a small set of shared
  loops. Movement uses a baked navmesh with avoidance, so crowds flow around obstacles and each other.
- **Storylines.** Scripted sequences attached to NPCs with time or proximity triggers: the smuggler's delivery run,
  the bishop's procession, the informer who shadows the player and reports to the watch, the drunk who is thrown
  out of a propination tavern, the printer smuggling a pamphlet bundle to the salon. They can be watched, used as
  cover, interrupted or exploited (steal the pamphlets, replace the delivery, feed the informer a lie).
- **Interiors.** Reusable sets (tavern, shop, workshop, church nave, salon, flat) placed behind doors; each district
  re-dresses the same kits with its own trades, colours and props until bespoke interiors exist.
- **Districts.** Each district has its own trades, its own propination holder, its own notables, and its own
  watch presence, so the same systems produce different textures of life: jewellers and traders in Kazimierz,
  tanners and brewers in Garbary, porters and salt on the docks, grain and horses in Kleparz, canons in Kanonicza.
- **Reactions.** Crowds react to the watch (step aside), to alarms (scatter, gawk), to the player's disguise and
  reputation (greet, ignore, report). Reputation with each faction changes who will talk and who will inform.

## The countryside (farmland as a faction avenue)
Kraków fed on the villages around it: manor farms (folwarki) of the Church, the university, the town and the
magnates, worked by serfs; free peasant villages under royal (now Austrian) law; mills on the Rudawa and Prądnik.
Kościuszko's Połaniec Proclamation (May 1794) had promised the peasants personal freedom and lower labour dues;
the partition cancelled it. That makes the countryside a live avenue:
- **Faction: the Villages.** Wójts (village headmen), millers, folwark stewards, parish priests as intermediaries.
  Influence gives food during a blockade, hiding places outside the walls, a route for smuggled arms and letters,
  and recruits with scythes.
- **Levers.** Promise the Połaniec terms again (costs magnate trust), pay grain debts, protect a village from
  Austrian requisition, or lean on a steward. Betray them and the Street remembers.
- **Sets.** A farm district outside the map's edge: fields, fences, a cottage, a barn, haystacks, a mill,
  a roadside shrine, a folwark manor house. Missions: a night ride to a mill to move a cache; hiding a fugitive in
  a barn; a requisition raid to stop.
