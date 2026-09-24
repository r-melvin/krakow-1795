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
### Macro loop (an open city, day and night)
There is no day menu. The player lives in the city and finds the work by walking it, the way Altaïr works a
district: the clock runs through day and night (the sky and the weather follow it; curfew falls at 22:00 and lifts at
dawn), the city changes with the hour (markets and workshops by day, lanterns, patrols and the red lantern by night),
and missions, favours, rumours and holds are discovered through exploration, conversation and storytelling, not chosen
from a list.
1. **Bureaus.** Each faction keeps a room the player can walk into: the printer's back room, the salon, the sacristy,
   the guild hall, the red lantern, the passage where the urchins trade. The keeper talks: the news, what the faction
   wants, who to see. Rumours are planted by going to the channel (the ballad seller under the arcades, the press, the
   pulpit through a priest, the madam), not from a panel.
2. **Investigation.** A target is unlocked by legwork in the streets (any two or three of): eavesdrop on a bench or at
   a table, pickpocket a letter, corner an informer in an alley and make him talk, do a citizen a favour that earns a
   friend in the crowd, read the bills, watch a patrol, climb a tower or roof (a viewpoint: the district's places of
   interest come onto the map). The journal keeps what was learned; the keeper says when it is enough.
3. **Missions.** Night missions start by being at the place at the hour (the courier passes the Cloth Hall at 23:00;
   the ball opens at 21:00) once the legwork is done; several are open at once and the order is the player's within
   what the arc allows. Day missions exist too (a meeting in a crowd, a theft from an open shop, a rescue from the
   pillory).
4. **Consequences arrive in the world.** Faction reactions, the crackdown, news and new openings show up as bills on
   the walls, talk in the street, a changed patrol, a letter at the safe house, a keeper's greeting, a dawn page in
   the journal. Sleeping at the bed (the safe house) saves and passes time; waiting on a bench passes an hour.
The seven institutions of the occupier remain the spine; taking one still changes the city for good.
5. **Milestones and penalties.** The winter has a calendar (12 January to Candlemas, 2 February 1795) with
   milestones the keepers and the street talk about: an institution before the Commissioner's levy, an invitation
   before the ball, the kingpin before Candlemas. Missing one has teeth: the crackdown jumps, a faction steps back to
   arm's length, a person is arrested or leaves the city with their lever, a bureau is raided and shut for two days,
   the finale gains bodyguards or an ending closes. Every sleep costs a day; the journal shows the calendar and the
   days left.
6. **Safe houses by loyalty.** One per faction, opened by loyalty and lost with it: the printer's garret, the red
   lantern's back room, the salon upstairs, a guild widow's house, the sacristy loft, the magnate's palace, a room at
   the Russian resident's, the Prussian agent's lodging, a corrupt sergeant's room at the police post. Each has a bed
   (sleep, save), a stash, a table where letters arrive, a coat rail with that faction's disguise, and its own kind of
   safety: the post is the last place the watch looks but the informers see who enters, the embassy is
   extraterritorial and Russia bills you for it, the sacristy is locked at night, the brothel never sleeps. A raided
   house is shut for two days. Where you wake sets the morning's news and openings.

### Mission loop (3D stealth / puzzle)
- Vision cones, light/shadow, noise. Suspicion meter per guard (calm → curious → searching → alarm).
- Social stealth: disguises, papers, invitations. Wrong disguise in wrong district = recognition.
- Puzzles: routes through the city (rooftops, cellars, church crypts), locks, ciphers on letters, timing patrols, moving crowds as cover.
- Non-lethal default. Lethal has consequences (crackdown, faction fear).

### Intel, disguise zones and notoriety (docs/STEALTH.md phases E and F)
- **Listening is a verb.** Townsfolk in pairs, guards muttering at their posts and storyline scenes carry hints
  (data/storylines.json and data/npcs.json `hints`, Polish or German with an English gloss). Stand within 4 m for
  5 s and the line is said aloud and kept in the journal ("heard at <place>, <time>"). The hints are true: the
  Corporal really leaves St Mary's post for the Winiarnia at 22:30, the Cloth Hall sentry really walks off for the
  midnight relief (data/zones.json `watch_routines`).
- **Paper on the walls.** Austrian proclamations (curfew, the watch rota, a new levy), the magistrate's lamp order and
  a theatre bill on the notice board and facades (data/bills.json). E reads one into the journal.
- **Watching the watch.** Crouch still, or sit on a bench, with a patrol in view: its round is drawn on the journal's
  Map tab, beside the lanterns seen, the hiding places used, the vendors and the red lantern once found.
- **Clothes are permits.** The Rynek is cut into zones: the salon (Town Hall door and hall), the watch post at St
  Mary's, the church porches, the road to Kazimierz, the open street. The salon cloak passes in the salon and the
  street; an Austrian coat in the post and the street; a cassock at the churches. In the wrong place the watch looks
  harder, goes Curious at once and Searching if you stay. The zone you stand in is shown only on the journal map.
- **Faces are not clothes.** The informer, the Corporal, the innkeeper of the Zajazd and a spy by the stalls know
  your face: a cloak does not fool them, and a townsman who recognises you calls the nearest soldier.
- **Notoriety** (0-100, kept across nights): alarms that reach the Corporal, soldiers beaten in the open, takedowns
  seen. At 30 wanted bills describe you from your origin, sex and coat, and the watch looks further; at 60 the
  patrols walk in pairs. Tearing bills down and changing coats bring it down; it fades by 10 a night.

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

## Look (the painted frame)
The game is drawn as an oil painting with muted tones: a screen-space pass (`assets/shaders/looks/canvas/oil.gdshader`,
`scripts/core/look.gd`) over the finished 3D frame, under every UI layer. Brush-smoothed surfaces (coarse strokes on
flat areas, finer where the image is busy so faces and hands stay readable), saturation cut to about 60 % with warm
lights and cool shadows, lifted blacks like an oil ground showing through, a soft five-band luminance banding for the
cel read, thin broken ink only at strong edges (brick courses and mortar stay paint), a canvas weave and a light
vignette. Lamps pull toward oil-lamp orange, the sodium glow of its day, and bleed a little warmth into the dark
around them. The look gives the prototype's rough edges somewhere to hide and sits with the period; it is a toggle
in Options ("Painted look") and `--look=<name>` swaps in another shader from the same folder for review
(`docs/screenshots/looks/`: painterly, ink_wash, cel, puppet, grime were the rejected candidates).

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

**Street trade.** The Rynek at night keeps its hawkers (data/vendors.json, scripts/city/vendors.gd): an obwarzanek
(ring-bread) woman at the Cloth Hall, a chestnut roaster with a glowing brazier-cart, a hot-beer (grzaniec) seller at
the inn door and a fish barrow up from the Vistula stay all night; a knife grinder, candle and herb women, a ballad
seller and a shoe-black keep pitches until 22:00-23:30; a water carrier, milk woman, firewood seller and a Jewish
pedlar walk short rounds. Each calls period cries in Polish, German or Yiddish (with an English gloss), draws passing
townsfolk to haggle (two customers make a crowd to blend into) and sells to the player for a coin: food restores
health, and every seller has a line of street talk that hints at the night's mission. The ballad seller's sheets are
seditious; she runs when the watch raises the alarm, and her sheet is a future intel item (flag `ballad_sheet`).

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
- **Interiors.** Every door opens on a room that is unmistakably its trade. Rooms share one shell system (walls,
  beamed, smoke-blackened, flat or vaulted ceilings; plank, parquet, flag, brick, tile or earth floors) and are
  dressed per trade: the baker's glowing oven and dough trough, the shoemaker's lasts and boots on pegs, the
  goldsmith's barred vault and strongbox, the apothecary's labelled jars, still and crocodile, the locksmith's key
  boards and forge corner, the tailor's board and dress forms, the cloth merchant's pigeonholes and ell, the cooper's
  cask being raised over a cresset, the chandler's vat and dipping wheel, the beer hall's casks and hatch, the wine
  cellar down its steps, the kawiarnia's urn and newspapers on sticks, the zajazd's ledger and coach doors, the house
  with the red lantern (implied, never explicit), the salon with the Constitution open on its desk, St Mary's with
  pulpit and confessional, three kinds of lodging (garret, burgher's parlour, scholar's room), the smithy, the
  guardroom with the Corporal's Ledger and a barred cell, the synagogue's bimah and ark, the Uniate iconostasis, and
  the finale's kingpin house (secret stair to a river tunnel and boat), bathhouse and warehouse.
  `data/interiors.json` maps each door (tenement portals, square landmarks, outer-city buildings) to a set and
  variant; rooms carry lights (flickering flames), night views through their windows, footstep surfaces on their
  floors, tagged props (`ledger`, `poisonable` decanters, `flammable` bales, the `weapons_rack`) and `Post_<n>`
  markers where the population and campaign put people.
- **Districts.** Each district has its own trades, its own propination holder, its own notables, and its own
  watch presence, so the same systems produce different textures of life: jewellers and traders in Kazimierz,
  tanners and brewers in Garbary, porters and salt on the docks, grain and horses in Kleparz, canons in Kanonicza.
- **Reactions.** Crowds react to the watch (step aside), to alarms (scatter, gawk), to the player's disguise and
  reputation (greet, ignore, report). Reputation with each faction changes who will talk and who will inform.

## Night life and crime

`scripts/city/street_life.gd`, tuned entirely from `data/street_life.json` (lines, timings, probabilities by clock
hour and crackdown). Tone: the period's brutality is shown plainly (violence, death, punishment, poverty, the
occupation) without gratuitous detail; sexual matters stay behind the door (no nudity, no depicted acts).
- **The red lantern** (west row, the door beside the beer hall): two women call out to passers-by and to soldiers,
  one of them coughing; a doorman on a bench, a pimp who collects, customers (Austrian soldiers openly) who go in
  and come out later. The madam sells a room (2 złoty: the lodging-house interior, visibility 0 and guard suspicion
  cleared for 20 s, `Mission.flags.brothel_room`) and gossip (1 złoty each: which officer is upstairs, the watch
  rota, whom the informer reports to). At crackdown 40+ a patrol makes its Visitation once a night.
- **Drunks** (3-5 after 22:00): stagger, sing, relieve themselves against a wall, fall asleep on benches, accost
  the player (a swing only shoves them) and are moved on by the watch.
- **Fights, crime** (never more than two at once): brawls near the taverns with a crowd that hides the player and
  draws the watch; cutpurses in crowds (they can rob the player; one blow and they drop the purse); muggings in
  the dark alleys behind the rows (after 23:00 the player alone in the dark is the mark: pay, fight or run; an
  underworld friend walks free); a burglar at a shutter (`saw_burglar`); a fence at the cellar hatch after midnight.
  High crackdown moves drink and violence off the square into the alleys.
- **Punishment**: prisoners in the pillory and stocks by the Town Hall, jeered at or fed; a flogging at the
  whipping post once a night, drummed and counted in German, with a crowd; a hanged Jacobin on the gallows outside
  the rows.
- **Poverty and occupation**: veteran beggars of Maciejowice, a woman who freezes in a doorway and is carted off
  before dawn, children scavenging behind the stalls, a soup line at St Adalbert's; arrests, a press gang, soldiers
  shaking down a Jewish pedlar or a Uniate priest, firewood requisitioned, the printed Constitution torn down and
  burned, and after the curfew bell a drunk beaten for not going home.
- **Voices**: the madam (wry), doorman (fearful), pimp (vengeful), thug leader (vengeful, stern or cynical), the
  drunk (drunk-philosopher), the man in the pillory (gallows-humour) and the bard (wry) carry a `personality`; the
  player's choices carry a `tone` (joke, blunt, humble, threat, flatter, bribe, appeal) and the answer comes from
  personality x tone: a joke buys a drink from the drunk and a slap from a vengeful thug; a threat cows the doorman
  (a free room) and brings out the pimp's knife. Humour is dry and never at the expense of the flogged or the dead,
  except from the gallows-humour man himself; the sergeant reads sentences flat.
- **The bard** at the kawiarnia trades a verse for a rumour, and was taught by a wandering master called Jaskier.
- **Riot and fire** (finale hooks): `StreetLife.riot(centre, intensity, cause)` turns the townsfolk near it into a
  mob with a ringleader the player can talk down or up; stalls are smashed and, at the height, set alight; the watch
  fires a volley after a minute. `Fire.ignite(pos)` (`scripts/city/fire.gd`) burns and spreads between flammable
  props, draws a bucket line from the wells and leaves them charred; snow and rain slow it.


**The house as a faction seat** (street_life.gd, data/street_life.json `brothel`, campaign.json `people.weronika`).
Mother Weronika (model `brothel_madam`) is the Underworld's leader in the Old Town: shrewd, funny, unsentimental,
sells to anyone, and hates Wilk the river king, who takes a third of her house (the `feuds` entry; it is her
motive for helping in the finale: two favours make her an ally, and on the Kingpin night one of her girls slips
you a vial and a seat at Wilk's cards). Business with her finds her (journal People) and opens: her day meeting
(pillow talk: two watch rumours, Underworld +3), the madam channel for planting rumours, favours (a debtor
frightened, a girl's brother out of the guardhouse, a rival house's lantern smashed; neglect raises Underworld
grievance), her client ledger, and an heir candidacy when the Underworld is strong (influence 35 or loyalty 60).
Inside (int_salon_brothel, the Post markers of data/interiors.json): women and men who work there (a woman doing
her hair, a card game with a soldier client, someone asleep on the settle, the house's man at the stair foot, a
woman by the stove), and the madam at her desk with the ledger when you are inside.
Choices at the door follow `option_allowed`-style gates: company offered by inclination (a woman upstairs, the
young man from Tarnów, a gentleman), a bolted room to hide in for anyone, work "with the tray" for a woman (the
witness inside), talk for anyone. NPCs may voice the period's bigotry; the UI never does.

**Implied, never shown.** Taking the room with company: the door closes, the view fades to black over the
landing, a caption on the black ("A door closes on the landing." / "Below, a fiddle; through the wall, a
laugh."), the house heard muffled through the wall (tools/gen_sfx.py `brothel_*`: an upstairs door and latch, a
parlour fiddle through the floor, a low murmur and a laugh, a card-table slap, an old bed frame, all low-passed at
the source), the clock moves on twenty minutes, and the view fades back with the player on the landing
("Nobody on the stairs looks at anybody."). No animation of the act exists. Clients going up are heard the same
way from the street if you stand close.

**Stealth and the Visitation.** The room still hides you. An officer seen going upstairs becomes a lever. If the
Visitation raid comes while you are in the house: bribe the corporal, go out of the back window over the woodshed
roof into the yard (notoriety +4), or go with them (the watch's capture choice).

### Holds on people
Notables (campaign.json `notables`: invented office-holders; no real person is accused, see docs/HISTORY.md) have
weaknesses (vice, debt, secret, dependent, ambition, fear, faith, greed) revealed by rumours (`reveals`), the
madam's ledger and the keyhole. Holds, with strength 0-3 shown in the journal People tab ("Weak spots", "Your
hold ●●○"), are acquired as day actions and spent on demands.

| Hold | How | Strength | Risk |
|---|---|---|---|
| Bribe | a purse (6 zł, +2 each time) | 1, fades nightly; 2 and stable after three | greed |
| Blackmail | proof from the red lantern: witness 1, ledger 2, testimony 2, keyhole 3, his glove 3 | proof | leaks (loyalty), hired thugs (next night), confession (crackdown) |
| Debt | buy his notes (10 zł or Underworld 25) | 2 | he may flee |
| Ward | take his dependent under your protection (3 zł) | 3 | the Polizei may seize the ward: a rescue lead |
| Fear | a dead dog on his step (Street or Underworld 20) | 2 | crackdown, notoriety; fear may turn to informing |
| Rumour | a whisper about him through the ballad seller | 1 | traced |
| Romance | four meetings over days, gated by inclination; nothing shown | 3 | exposure |
| Removal | he is gone | - | grievance, fear, crackdown; the next night counts as blood |

Demands (need +1 against a proud man, resistance 2+): coin, the informer's name, a rumour from his mouth (untraceable),
a pass for tonight (a post waves you through), a witness silenced, a warrant withdrawn, his vote, tonight's door
left unbarred (a patrol sent the wrong way), and install (his faction's influence +2 each dawn). A demand
consumes, strains (-1) or keeps the hold. Holds can be sold (debts to the Underworld, secrets to the salon), burned
for mercy (loyalty), and pass to an heir. If the Underworld's loyalty falls below 40, Weronika may sell your proof
to its subject. Nights when a hold was used show "blackmail" on the score card.


### Sickness at the wells
In 1795 nobody says cholera (it reached Poland in 1831): the street says the flux (biegunka), the fever (typhus,
carried by the armies) or the plague air (morowe powietrze); the professor's students say "a bad well"; the street
says poison, the strzyga, or the old lie about the Jews. A well goes bad by itself (10% a dawn from night 3, not
at a protected well) or by the player's vial (the kit's poison verb on a well or pump). The night after:
boards and a chalk cross on the lid, a watch guard posted on it (a new sentry the stealth systems see), two
water-carriers selling river water (buy a bucket: Street +1), a physician and a priest with the viaticum, the small
bell tolling; district fear +12, Church influence +3; the rumours "a bad well", "boil it", "the well spat black
water", and the old lie (a counter action like the black dog). A poisoned well also sickens the garrison: St Mary's
post and patrol B are abed for two nights, at the cost of notoriety +10 and Church and Street loyalty -5. The player
can steer the blame onto the garrison (plant "the Austrians poisoned the well": ruin if traced back to a real vial)
or onto the strzyga (fear, and nobody hanged), or protect a well (2 zł: a man on the lid, river water, the leaflet
on boiling; Street +3). The urchins sell which wells are safe.

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


## Tone, period constraints and language

**Tone.** The game does not soften the years it is set in. Occupation, public punishment on the Rynek, poverty,
drink, prostitution, disease and killing cold are shown plainly; sexual content stays implied. Characters voice
the bigotries of their age (against Jews, peasants, foreigners, women outside their station, and anyone whose
desires were then a crime). The game presents these as the world the player moves through, not as views it
shares. A content notice says so before the main menu (`scripts/ui/content_notice.gd`).

**Gender and inclination as gates.** Character creation sets sex and "drawn to" (women / men / both / unspoken,
`GameState.inclination`). Content gates on them through dialogue conditions (`gender:f`, `inclination:men|both`,
`origin:...`, `influence:faction>=n`) and `GameState.option_allowed(req)` for doors and roles. Closed choices stay
visible but greyed with a period reason ("Not for a woman here.", "Not your inclination."). Rules of thumb:
- A woman cannot join the watch, sit in the guild hall, be a priest (she is a nun), or walk the streets alone at
  night without drawing a different kind of attention; she can enter kitchens, sickrooms, convents and the
  women's side of the synagogue, and is searched less at gates.
- A man cannot pass as a nun or enter the women's quarters; a nobleman is admitted to the salon a burgher is not.
- Same-sex desire is a crime under the Austrian code: it is a blackmail lever against the player and against
  NPCs (an officer, a canon, a magnate's son), and also a key to certain circles (the theatre, a bathhouse, a
  private salon) that a straight character cannot use. "Unspoken" satisfies no explicit requirement.
- Jews are confined to Kazimierz after curfew and barred from guild trades; a Kazimierz merchant origin has
  doors closed on the Rynek and open in Kazimierz.

**Language.** Polish, German and Yiddish lines are kept as the people would have said them, always with an
English gloss beneath (speech bubbles show "text\n(gloss)"; JSON lines carry a `gloss` field). Period words
used in the UI carry their meaning in `data/glossary.json`, shown in the journal's Glossary tab.

## Buildings and the winter townscape

All architecture is generated headlessly in `assets/blender/build_assets.py` and placed at runtime: the Rynek by
`scripts/city/greybox_district.gd`, the outer streets and everything past the tenement rows by
`scripts/city/outer_city.gd`. Stylised-realistic, period Kraków c. 1795-1805, deep winter.

**Snow and ice.** Every roof carries a conformal snow blanket (`snow_shell`): the upward faces of the roof are
subdivided, lifted and solidified 5-9 cm thick, thicker on the lee slope, scoured thin at the ridge, drifted up
against chimneys, dormers and parapets, with rounded bare patches and downslope slide strips that show the tiles,
and a lip curling over the eaves. Icicles hang under eaves, cornices, balconies, gutters and fountain bowls; sills,
hoods, copings, finials, pinnacle balls and dome ribs carry thin snow; chimneys and back walls take a frost crust.
The snow texture has wind ripples, crystal grain, cold blue hollows and sparse low-roughness glints.

**Masonry and openings.** Rusticated ground floors, quoins, string courses, keystones and carved mascarons on
portals, Gothic bond brick with glazed headers and old lime-wash, damp tide lines on plinths. Windows sit in real
reveals with frames, mullions, sills with drips and lintels; shutters are louvred or boarded, painted per district
(green, ox-blood, ochre, blue, grey, brown), mostly folded back with a few standing half open. Wrought-iron
balconies on carved consoles, timber courtyard galleries (ganki), iron wall anchors (kotwy), lead downpipes with
hoppers, stove chimneys with pots.

**House types.** Five kamienice for the square (`tenement_a..e`) plus nine for the outer streets: Renaissance attic
house (`ten_renaissance`, `_b`, 9 m), narrow Gothic gable house (`ten_gothic`, `_b`, 6.5 m), Baroque palace front
(`ten_baroque`, 14 m), plastered burgher house with a shop arcade (`ten_burgher`, `_b`, 10 m), half-timbered gable
house (`ten_timber`, 8 m), wooden suburban house (`ten_wooden`, 9 m).

**Water.** A public fountain with lion-mask spouts frozen mid-flow, wells with windlass roofs, a wooden pump-post
with a lever (cast iron pumps come later), stone horse troughs, and open street gutters (rynsztok) in stone channels
carrying dark snow-melt down the outer streets.

**Industry on the outer streets.** Post mill (bare sails, canvas furled), water mill on a raised race of the
Młynówka with an iced undershot wheel, bell foundry with a furnace stack and glowing furnace mouth, open-fronted
forge with hearth glow, anvil and tools, propination brewhouse with a copper kettle and malt-kiln cowl, cooper's
yard, tanners' drying frame. Fires carry `Furnace_n` markers and get a flickering light at runtime.

**Faith.** St Mary's with stained glass (emissive, faintly lit at night) and stone tracery, louvred belfry openings
and a ribbed, snow-capped helm dome; a free-standing campanile with a clock and visible bells; the Town Hall tower
with four real dials and hands (11:50); the Old Synagogue (Gothic hall, Renaissance attic, buttresses) and a
smaller synagogue with a three-tier shingled roof and a women's gallery; a Greek Catholic (Uniate) church with an
onion cupola and three-bar crosses (Orthodox proper had no church in Kraków in 1795); a towerless Protestant prayer
house with a ridge turret; a column shrine (figura) and a pillar kapliczka; a monastery gate and enclosure wall.

**The castle.** Wawel as a low-detail skyline set (hill, curtain wall, Senators' and Sandomierska towers, the
palace roofs, the cathedral towers and the gold Sigismund Chapel dome) far to the south-west, and a near castle
gate with round flanking towers and a lowered drawbridge.

**Justice.** Pillory (pręgierz) in front of the Town Hall; stocks, whipping post with the town drum and gallows are
exported for the street-life scenes.

**Snow in the streets.** Doorways and the main routes are shovelled, as they were: a trodden strip down the
middle of the main streets and across the Rynek (to the church doors, the Town Hall, the Cloth Hall passage, the
stall rows), with ridged banks of thrown snow either side, grey-brown at the foot, and heaps waiting for the cart to
the river. The side lanes, the wall streets, the yards, the churchyard green and the moat edge stay deep (a 15-30 cm
layer that rises and sinks with the night's ground cover) with one single-file track trodden through, and every
walker's footprints cut troughs that fill in again while it snows. Drifts bank up on the lee side of the wind
against the town walls, building walls and yard corners and trail behind stalls, carts and the well; the big ones by
the square hide a crouched player. Deep snow slows everyone (x0.6, x0.85 in the trodden track), muffles footsteps,
and a guard who crosses the player's fresh trail follows it. Drifts sink in a thaw, slump and grey in rain, glaze
under sleet (scripts/city/snow_drifts.gd, data/snow.json, assets/blender/build_snow.py).

**Runtime markers.** Buildings export empties as children of the asset root: `Chimney_<n>` at each flue top,
`Window_<n>` on the sill of each openable ground- and first-floor street window (its Blender -Y, which is
Godot +Z, points out into the street), `Furnace_<n>` at forge, foundry, brewery and cooper fires.

### Weather and seasons

The winter is not one fixed night. Each night the campaign picks a preset from data/weather.json
(`Weather.set_conditions("sleet")`, or `--weather=<preset>` for testing): clear frost, light snow, blizzard,
sleet, a rain thaw, fog, overcast, and the day looks (clear day with no snow, snow day). A preset says what is
falling; the town's state accumulates from it and carries over from night to night in the campaign save
(`weather_state`): snowfall lays fresh powder on the roofs and the square and fills old tracks in; rain and thaw
melt the roof snow (it slides off the eaves in sheets when it goes fast, melt water drips from the eaves), wet the
plaster, wood and tile and pool in the low joints of the setts, rippled by the drops; sleet leaves a grey crust that
crunches underfoot (louder steps); melt water refreezes into icicles in frost, which fall in the sun. Mist lies in the
moat, over the Vistula, in the yards and the churchyard and thickens toward dawn; smoke pools by the watch braziers,
lantern haloes grow in mist, and breath shows in the frost. scripts/city/weather.gd and weather_fx.gd drive it,
with the sky, the moon or the low winter sun (after 06:00 the sun rises and the lanterns fade), fog and exposure.
Weather is a stealth lever: rain masks footsteps (guard hearing x0.6), wind and blizzards muffle further (x0.8),
fresh powder muffles steps and a sleet crust betrays them, and blizzard and fog shorten the guards' far sight,
while a clear frosty night leaves every sound carrying across the square.

## Campaign (seven nights, one winter)

Code: `scripts/mission/campaign.gd` (Mission.campaign), `rumours.gd`, `events.gd`, `mission_runner.gd`,
`scripts/ui/day_panel.gd`, `dawn_panel.gd`. Data: `data/campaign.json`, `rumours.json`, `events.json`,
`missions.json`. State lives in `GameState.campaign` and `Mission.journal` and is saved every dawn with the rest
(save/continue works mid-campaign).

### The arc
Each night takes one institution back from the occupier; a lost night still moves the story on (its `failure`
consequences apply and the next night comes).

| Night | Mission | At stake | Roads (the first counts in the pacing estimate) |
|---|---|---|---|
| 1 | The Printer's Bundle | the press | smuggler, urchins, salon |
| 2 | The Corporal's Ledger | the watch's book | Novak's price, laundress (women), drunkard (men); copy or steal |
| 3 | The Salt Barge | the muskets | the guild's false manifest, the raftsmen's sledge; Rózia's key as a shortcut |
| 4 | The Bishop's Letter | the Church | canon's cassock (men), Bernardine habit (women), staged miracle; the confessional's second door (the Uniate priest's key) |
| 5 | The Magnate's Ball | the Town Hall | servant's livery, invitation, on the banker's arm; then blackmail, poison or win Count Wodzicki |
| 6 | The Pillory | the street | a riot, a quiet key or pick, an omen told by the fortune-teller |
| 7 | The Kingpin | the river (the docks district) | a sandbox: see below |

Each mission's `campaign` block turns its outcome into consequences (loyalty, fear, strength, crackdown, camp flags,
levers, rumours seeded, districts). `variants` react to earlier nights (e.g. the informer sells you to Wilk if you
did not win night 1); conditions like `camp:`, `lever:`, `found:`, `night:` gate choices in every mission.

### The whisper network (the distinctive loop)
Rumours are objects (`data/rumours.json`): subject, truth (true, false, or true only if a condition holds, such
as holding the banker's notes), a spread rate, effects when it takes hold, effects when it is disproved.
- **Carried by people.** A rumour lives in named townsfolk (`carriers`, from `data/npcs.json`) linked in a
  `network` of social groups (the west well, the passage, the church steps, the taverns, the watch, the market).
  At night every unheard rumour in play is placed on its carriers as an overheard line (intel.gd: stand within
  4 m for 5 s); the madam's gossip, the ballad sheet and a flogging seen also count as hearing one.
- **Spread at dawn.** Each carrier passes it to each neighbour with probability spread x channel boost x
  (1 - crackdown/200); reach is the share of the roster that carries it. At 35% it takes hold, once.
- **Planted by you.** From the day panel, through a channel: the ballad seller (cheap, slow, hard to trace),
  Mother Weronika (reaches soldiers first), the printer's press (fast; needs the press), Wit the crier (everyone
  at once; everyone saw who paid), a forged bill (needs a seal). Planted rumours move guards (the raid on
  Kazimierz takes a patrol off the Rynek, the warehouse raid pulls one of Wilk's bodyguards away), set traps for
  enforcers (the informer arrested as a Russian spy), draw people out (the amnesty brings the deserter into the
  square), and shift loyalty and fear.
- **Costs.** A planted rumour can be traced to you (notoriety +12, crackdown +3); a false one that takes hold can
  be disproved, and the channel's faction loses influence.
- **Superstition and religion** are a class of their own (`kind`: omen, miracle, curse, relic, prophecy). They
  spread fastest among the pious and the street, slowest in the salon, and cost Salon influence to plant. A staged
  miracle (the bribed sacristan) that is traced is blasphemy. The black-dog omen of Kazimierz, already running on
  day 1, turns people on the Jews unless you counter it (a day action with the rabbi and the Uniate priest). The
  hejnał breaking off, a relic of St Stanislaus or Kościuszko's sabre, a Marian prophecy, a curse on the
  Commissioner's house: each with its own effects.
- **Leads.** A rumour about a person is a lead: follow it (one a day) and that person is in tonight's world with
  a map mark. The day panel shows rumours with reach, truth as far as you know (`?` until proven or disproved) and
  whether you planted them. The journal keeps them in `Mission.journal.rumours` and the Log ("rumour: ...").

### People to find (levers)
Jan Wróbel the deserter (Garbary tanneries: an Austrian coat), Marianna the laundress (the Corporal's secret, a
basket into the post), Monsieur Orlov the Russian (gold, and strings), Wit the crier (cheap crying), Tadeusz the
printer's apprentice (seals and the press), Herr Lindner the Prussian banker (the Commissioner's debts), Rózia
the fence (keys, a vial), Father Hryhorij the Uniate priest (the confessional's second door), Sergeant Kmita at
Kleparz (the veterans), and Jan Śniadecki the astronomer (moon tables: darker nights). Each is found through a
rumour, gives a lever on talking, and has a day meeting afterwards.

### Days
Two hours a day (three after a won night), spent on: lying low, the Zajazd, alms, the guilds, the salon, a
speech, bribes, a smuggler's parcel, a staged miracle, a curse, holy pictures, meeting a person found, appeasing a
faction, making amends, naming an heir, countering a dangerous omen, or planting a rumour. The passage urchins
(Staś and Kasia) sell news for a coin without costing an hour: the watch's sweep, the talk of the passage,
where a person hides, an unlatched window (one more slip-away), shadowing someone, carrying a message. They lie
now and then (honest 60% plus half your Street influence). At night they sell news to anyone on the nights the
mission does not need them.

### Factions against each other
`relations` in campaign.json: Church and Salon, Guilds and Underworld, Magnates and Street, Church and Underworld,
Guilds and Street, Russia and Prussia as spoilers. Influence gained with one side costs the other side loyalty.
If one side's influence runs more than 30 ahead of its rival, the rival keeps you at arm's length: its influence
gates fail ("They keep you at arm's length") until you make amends. Neglect (no gain for two nights) or a broken
promise raises a faction's grievance; at 60 it sabotages the next night unless appeased: a tipped-off patrol, a
mob you did not call, tolls, a loose tongue with the Polizei, no sanctuary. The day panel lists the pairs that
hurt now.

### Random events
`data/events.json`, at most three a night, each at most once, staged 12-40 m from you: a runaway cart, an arrest,
a stall fire (buckets, or slip past the watch it draws), a candle procession (walk with it, disguised), a tavern
brawl (pick a side), a lost child, snowballing urchins (hire them to pelt a guard), the lamplighter (pay him to
leave a corner dark), a pamphlet drop, a duel in the snow, a drunk soldier's coat, the flogging crowd (with
street_life.gd's flogging scene). Each outcome moves influence, loyalty, crackdown or rumours and appears in the
dawn report.

### The finale: The Kingpin
Wilk the river king owns the Vistula quays. He makes a round of five stations (the warehouse, cards behind the
fishermen's tavern at 21:45, the bathhouse at 22:40, his barges under the cargo hook at 23:30, the riverside
shrine), guarded by two enforcer bodyguards who keep a ring round him (one ahead, one behind looking back), see
through disguises and gain suspicion three times as fast within 8 m. Anyone reaching arm's length without a permit
is frisked: the approach fails, the guards go to Alarm and Wilk holes up in his warehouse. The honest roads are
indirect, built from general verbs, and each leaves a different river behind it:

| Method | How | Consequence |
|---|---|---|
| Poison | Salomea's drop, or Rózia's vial, in his card-table jug or bathhouse kvass | Church uneasy |
| Accident | work the pin out of the cargo hook before 23:30 | guilds relieved; nobody to blame |
| Fire | kick the watchmen's brazier into the warehouse straw while he is inside (or as a distraction) | guilds lose grain; crackdown |
| Riot | turn the raftsmen (Street or Underworld loyalty, the relic, the riot of night 6), the mob drags him out | Street cheers; heavy crackdown; the Underworld splits |
| Guillotine | Citizen Lebrun builds the machine (Street strong, 4 zł); the mob's tribunal uses it, or it scares a bodyguard off | Street ecstatic; Church and Salon appalled; curfew sweep |
| Knife | take a bodyguard's coat at the privy (22:15) and walk up as one of them, or isolate him (raid rumour, the machine) | the river respects it |
| Pistol | Jędrek's pistol, the loud last resort | notoriety +30 |

Then decide who rules the river (Jędrek, his lieutenant, or no king at all) and get out through the Grodzka gate.
The docks district's controller becomes `movement`: one district of eight. The ending (Martial Law, A Candle in
the Window, The Tsar's Friends, The Razor on the River, The Commonwealth Stirs, No More Kings on the River, King
Jędrek) follows loyalties and choices.

### Failure, capture and succession
- **Checkpoints**: the start of the night, every objective done, 20 s in a hiding spot.
- **Caught or beaten** by the watch: a choice, not a fail screen. Slip away to the last checkpoint (once a night,
  more with the copied rota or the urchins' window; notoriety +5, ten minutes pass; the Church's sabotage denies
  it), go quietly to the cells, or restart the night (the pause menu's Restart night also stays).
- **The cells** (a cell under the watch post, far below the map): pay the turnkey (6 zł, 3 with Underworld or
  Guilds standing), be ransomed by a faction (its influence -10, its rivals' grievance +15), or wait until he dozes
  at 03:00 and work the window while he looks away (back into the night, notoriety +10, the watch sees further).
  Bribe and ransom end the night as a failure.
- **Two captures in a row**: a trial next morning: flogging (notoriety cleared, one health tonight) or banishment
  (tonight is lost). A third capture at crackdown 60+ is a hanging.
- **Succession** is a standing choice. Name an heir among the people found (a day action; the nominee's faction
  gains, its rivals notice; a nominee with a scandal is a blackmail target; changing heirs costs trust). If the
  figurehead dies or is taken, the nominee takes the banner; with no nominee, or if the movement loses faith (its
  strongest faction at grievance 80, notoriety 90, two nights lost in a row), the strongest faction imposes its
  protégé (a canon, Pani Zofia, a smuggler, a carter-veteran, a guild master, a magnate's client). While you live,
  loss of faith is a coup: concede, stand firm on eloquence, or step aside. The new figurehead inherits journal,
  people, rumours and levers, 70% influence (100% with the backer), no notoriety, a new origin, sex and
  inclination (content re-gates), and the old one becomes a martyr, prisoner or exile rumour. A succession card
  precedes the next briefing. With no one to take up the banner, the movement ends in an epitaph.

### Voices (personality and tone)
Every named person has a `personality` (wry, gallows-humour, stern, pious, vengeful, cynical-merchant, fearful,
ambitious, tender, drunk-philosopher) and a `temper` (0..1). Player choices carry a `tone` (joke, blunt, humble,
threat, flatter, appeal-to-faith, appeal-to-country, bribe). `campaign.json tones.table` decides: good (the
choice's `on_good` node; the person is charmed and remembers: a free rumour, `charmed:<id>` later), bad (`on_bad`,
or with temper 0.6+ you are thrown out; `grudge:<id>` is remembered), neutral. Nodes may carry `lines_by`
personality. The humour is dry, local and period-plausible (the pillory as the city's coldest seat, the Austrians
as "our guests", the tax on crying), never winking at the player, and never undercutting a death or a flogging
except from a gallows-humour character. The stern and the vengeful have their own eloquence.

### Pacing (measured)
`[smoke] campaign nights=7 est_minutes=<n>` sums, per night by its shortest (smoke) route: travel from the entry
through each required objective's map mark (x1.6 detour, 2.2 m/s), 1.4 min of watching and hiding per required
objective and 1.2 per optional, dialogue at 150 wpm, the briefing at 170 wpm, waits for the clock, two events a
night, a lead person from night 2, and the day panel with its choices. The first mission's three roads count once.

### Historical people
Real people appear as named characters or off-stage presences, with sources and the liberties taken in
`docs/HISTORY.md`: Bishop Feliks Paweł Turski, Jan Śniadecki, Canon Sebastian Sierakowski, Count Stanisław
Wodzicki, Filip Nereusz Lichocki, Hugo Kołłątaj, Tadeusz Kościuszko, Wojciech Bogusławski, Johann Wenzel von
Margelik. Journal entries carry `historical: true`.

### The walkable town (outer_city.gd, data/city_layout.json)

`tools/gen_city_layout.py` writes `data/city_layout.json` (streets, ground patches, placements, placement points,
reachability checks, inspection shots); `scripts/city/outer_city.gd` builds it round the Rynek. Godot metres,
+X east, +Z south; the Rynek (+-45) stays greybox_district.gd's. The carriage lanes of data/npcs.json are streets of
the grid and nothing stands within 4 m of them.

- **Walls**: a ring at x=+-100, z=-100/96 (wall segments, towers every ~32 m, a frozen moat outside with plank
  bridges). Gates: St Florian's (x=10, north) with the Barbican beyond, Slawkowska (x=-68, north), Garbary (west,
  z=0), Mikolajska (east, z=-10), Grodzka (south, x=-12).
- **Old Town**: Szewska, Slawkowska, Florianska, Grodzka, Mikolajska, St Anne's and cross streets on a grid;
  blocks of tenements back to back round courtyards, courtyard walls on the short sides (tall, or low enough to
  vault), sien passages cutting some blocks so a yard is a way through (some are dead ends with a climb out),
  the Maly Rynek east of St Mary's with stall points, the Collegium Maius, the campanile, a monastery enclosure.
- **Outside**: Kleparz market (north, past the Barbican; brewery, windmill, carpenter's yard), Garbary (west;
  tanners, the water mill on the Mlynowka, forge, bell foundry, cooper), the Vistula quays (south-west; granaries,
  wharves, frozen-in salt barges, fish market, the kingpin's warehouse, the bathhouse), the castle gate under
  Wawel (Wawel on the skyline), Kazimierz over the frozen Old Vistula (houses, both synagogues, the Uniate church,
  the kingpin's townhouse on Szeroka), farmland east (fields, farmstead, manor, shrine, gallows by the road).
- **Surfaces** (collision `surface` meta for footsteps, 4 m slabs with parallax): field-stone cobbles on the main
  streets; rougher sunken cobbles with a centre gutter on the wall streets and alleys; flagstone strips at St Mary's
  and St Adalbert's steps, under the Cloth Hall loggias and in front of the Town Hall; frozen packed mud with ruts
  and puddles in the yards; dirt roads with a plank walkway (`planks`) in the suburbs; gravel on the road to Wawel;
  snow everywhere else; drifts banked against house fronts.
- **Gutters** follow the street lines: straight channels, mitred corners at turns, crossing slabs at junctions and
  doorways, drains at the ends; no collision.
- **Navigation**: the town's navmesh is baked in 48 chunks from one parse of the colliders, trimmed with
  border_size so they join the square's region (which now ends exactly at +-45 m); ground level only.
- **Climbing**: `climb_<kind>_<n>` collision bodies from the assets (drainpipes, first-floor sills, balconies,
  gallery decks, ladders, shed roofs, low walls, stairs, perches, the Cloth Hall wall-walk and parapet) and the
  collision of crates, barrels, carts, troughs, stalls, woodpiles and walls join group `climbable` with meta
  `climb_kind` (vault, mantle, ledge, pipe). Tenement roofs have their real roof shape as collision. Perches
  overlook the cafe, the guard post by the Cloth Hall and the brothel door.
- **Tags**: `flammable` and `poisonable` metas on the placed props that burn or hold drink; the warehouse's
  `CargoHook` node carries `rig`/`rig_kind`.

### The dawn score card
Every night is scored (`Campaign.score_night` from `mission_runner.gd score_card()`): times seen (the watch's
`player_spotted`, debounced), alarms and runners reaching the Corporal, blood (kills, knockouts, fights in the
open), noise (shots, fires, mobs), collateral, bodies found, methods (disguise, poison, bribe, rumour, distraction,
superstition, the drains, slipping away) and allies (urchins, Mother Weronika, crowds), game-minutes and coin spent.
Five stars minus alarms (up to 2), being seen often, killing, noise, bodies and slips; a failed night caps at two.
Tiers: 5 Ghost of the Rynek, 4 Quiet hand, 3 Rough trade, 2 The talk of the town, 1 The watch has your description.
The dawn panel shows it above the report with the facts, 3-4 lines on what moved it and one road not taken
(missions.json `route_hints`). A 4-5 star night: notoriety -5, Salon and Church loyalty +1; a 1-2 star night:
crackdown +3, Street loyalty +2. Ratings are kept in `GameState.campaign.scores` and on the journal's Missions
entries (`stars`, `tier`, `score_lines`).

### Below the Rynek: the undercroft
Medieval brick culverts and linked cellars (the interiors agent's `int_undercroft`), reached by street grates
(symbolic door ids in `campaign.json undercroft.entrances`: the well grate, the Cloth Hall grate, the laundry
grate, the river outfall; a missing door falls back to a message). The rumour "the boys go in by the well grate"
starts in the passage. Uses: the drains route on night 3 (up the outfall with the muskets, past no exciseman), a
drain behind Wilk's warehouse on night 7 (come up through the office floor behind the bodyguards, which counts as a
permit) and the river-outfall escape, the cell break-out (down the old well shaft, up the laundry grate), and the
side quest **The Fence's Ledger**: follow the lead to Pan Kuna, the fence below the Rynek, and trade with him (the
Corporal's torn pages), rob him (his ledger: coins and a lever, Underworld loyalty -5), or turn him from Wilk to the
movement, by standing or with the body in his dump alcove as blackmail (both reveal Wilk's habits). Two events fire
only below: a corpse carried to the river and a dog-fight ring. Side quests are lead packages merged into any
night (`campaign.json side_quests`: people, items, talk, texts, optional objectives, effects at dawn).
