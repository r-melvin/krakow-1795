# Genre review: tropes, gaps and what is ours

Written against GDD.md, STEALTH.md, the README and `data/`. Sources are cited by title. Fit: **Y** fits 1795,
**~** fits with a period skin, **N** does not.

## 1. Trope inventory

### Detection and feedback
| Trope (source) | Have? | Fit | Add or improve here |
|---|---|---|---|
| Light gem / light meter (Thief, Splinter Cell) | Yes: sampled light, visibility arc (STEALTH A, G) | Y | Keep. Tint the arc's dot blue on a moonlit night so the moon reads as a threat. |
| Surface noise (Thief) | Yes: six surfaces | Y | Add ice (fresh-frozen gutters, 1.4) and slush after a thaw. |
| Staged alert with Evasion/Caution (Metal Gear Solid) | Yes: watch.gd | Y | Build the Caution barricades (known limit): two sawhorse props per side street. |
| Last-known-position ghost (Splinter Cell: Conviction) | Yes | Y | Keep. |
| Footprints in snow (Metal Gear Solid, Shadow Moses) | No | Y | The strongest winter trope we lack: see Proposal 5. |
| Enemies adapt to your habits across missions (Metal Gear Solid V) | No | Y | Austrian orders at dawn answer your method: many rooftop escapes, next night a sentry on the Cloth Hall parapet. |
| Missing-colleague checks | No: only bodies are found | Y | A patrol whose partner is stashed calls his name, then goes Searching after 20 s. |

### Traversal and vantage
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Viewpoint that reveals the map (Assassin's Creed) | Perches only | ~ | Climbing a tower (the campanile, the Barbican) records every patrol in view at once, a "survey" instead of synchronising. |
| Rope arrow / grapple (Thief, Syndicate) | No | ~ | A knotted chimney-sweep's rope: fix it on a `ledge` climbable to make one custom vertical route per night. |
| Shadow teleport (Aragami), Blink (Dishonored) | No | N | Stay grounded; the through-passage (*sień*) and roofs already give routes. |
| Hide in grass / drop from above (Sekiro, Ghost of Tsushima) | Traversal, hang | Y | A takedown dropped from a gallery (*ganek*) or a snowdrift pushed off a roof onto a sentry. |

### Disguise and social space
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Disguise as zone permit, enforcers (Hitman WoA) | Yes (STEALTH F) | Y | Add the servant zone (kitchens, yards) the design names but zones.json lacks. |
| Suspicious *acts*, not only places (Hitman) | Partial | Y | A table of illegal acts in stealth.json (climbing, lock-picking, carrying a musket, running after curfew) that make a guard Curious even in a permitted zone. |
| Crowd blend, benches (Assassin's Creed) | Yes | Y | Blend in queues too: the soup line, the flogging crowd, the procession. |
| Kidnap/escort through crowds (Syndicate) | No | Y | Walk a prisoner, arm in arm and "drunk", through the square: night 6 variant. |
| Papers checks (Papers, Please) | A bark only | Y | See Proposal 2. |

### Tools and non-lethal
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Water arrow / douse light (Thief) | Yes: lamps | Y | A snowball that douses a lamp at range; the urchins already throw them (events.json). |
| Sleep/cosh, tie-up and gag (Commandos, MGS) | Cosh; guards wake | Y | A cord from the kit: a tied guard stays down until found. |
| Sling and light as tools (A Plague Tale) | Stones, torch | Y | Keep; fine. |
| Flash-bang | "Magnesium" flash | **N** | Magnesium was isolated in 1808. Re-skin as a Bengal light (saltpetre, sulphur, realgar), which fireworkers made in the period; change the blurb in stealth.json. |
| Non-lethal default with consequences (Dishonored "chaos") | Yes: crackdown, stars | Y | Show the chaos on the streets: more requisition and arrest scenes per crackdown step (street_life.json already scales them). |

### Information and planning
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Overheard conversations, opportunities (Hitman "Mission Stories") | Yes: hints, storylines | Y | Keep hints true; mark lies in the Whisper Network, not in overhearing. |
| Planning screen: loadout, entry point (Hitman, Desperados III) | No: fixed `night_start` kit | Y | See table stakes 1. |
| Time as the investigation budget (Pentiment) | Yes: day hours | Y | Make leads decay: a person unfollowed for two days leaves the city. |
| Deduction from evidence (Return of the Obra Dinn, AC Unity murder mysteries) | No | Y | Identify the informer's paymaster from three clues; confirm guesses in batches (Obra Dinn) so guessing is punished. |
| Tells on hidden targets (Hitman Freelancer suspects) | No | Y | The kingpin's decoys: two men dress as Wilk; tells (a limp, the kvass) come from rumours. |
| Secrets and hooks (Crusader Kings III) | Blackmail levers | Y | Make a secret an inventory object with holders who can leak it (Proposal 3). |

### Consequence and reactivity
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Wanted posters, bribe the herald (Assassin's Creed II) | Bills, tearing | Y | Bribe the bill-poster (a street_life `poster` NPC) to lose tonight's bills. |
| The press reports your deeds (Suzerain, Deus Ex newspapers) | Dawn report | Y | A one-page *Gazeta Krakowska* at dawn: the Austrian version and, if you hold the press, yours. |
| World state flips (Dishonored, Syndicate gang war) | Districts, docks flip | Y | Show control in the street: flags, graffiti, who drinks where. |

### Mission structure and replay
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Sandbox assassination, many methods (Hitman) | Yes: the Kingpin | Y | Give night 5 the same shape (three kills and a non-kill). |
| Challenges and replay (Hitman, Blacklist playstyle scores) | Stars, "Another road" | Y | Replay a won night from the journal with its challenge list. |
| One-shot targets that never return (Hitman Elusive Targets) | Leads | Y | A lead that appears for one night only and is gone if ignored. |
| Difficulty that adds constraints (Thief: Expert no-kill objectives) | No | Y | Three difficulties that add objectives, not health: see table stakes 6. |
| Character switching (Commandos, Shadow Tactics) | Succession only | ~ | Proposal 4. |

### Narrative framing
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Skills as inner voices (Disco Elysium) | Personality × tone | ~ | Origins as a second voice: one period line per origin on key choices ("A Racławice man doesn't bow"). |
| Typeface by class and literacy (Pentiment) | No | Y | Four fonts in ui_theme.gd: court German chancery, burgher cursive, peasant hand, printed. Letters and bills use them. |
| Occupation bureaucracy (Papers, Please) | Bills, curfew | Y | Rules that change each night via proclamation bills. |
| Hub between missions | Day panel | Y | Keep it abstract; do not build a walkable hub. |

### UI conventions
| Trope | Have? | Fit | Add or improve here |
|---|---|---|---|
| Vision cones on the ground (Commandos, Shadow Tactics) | Yes, fading | Y | Keep. |
| Sound rings (Mark of the Ninja) | Yes | Y | Keep. |
| X-ray "instinct" view (Hitman, Styx amber vision) | No | ~ | Not a see-through mode: a held "watch" posture that marks the last guard looked at on the minimap for 10 s. |
| Pause-and-queue "showdown" (Desperados III) | No | N | Real-time only. |

## 2. Table stakes, ranked by how much the prototype suffers without them

1. **Planning before the night.** Players expect to choose kit and entry. Day panel gets a "Kit and door" step:
   pick five items from what the factions gave you and one of two or three entry points per mission
   (`missions.json stealth.entries`). `day_panel.gd`, `kit.gd`, `mission_runner.gd`. 2 days.
2. **Suspicious acts.** Without them the disguise is a pass for anything. `stealth.json illegal_acts` read by
   `guard.gd` perception; `verbs.gd`/`traversal.gd` raise the flag. 1.5 days.
3. **Enforcers you can handle.** Bribe, frighten (tone table), frame (rumour) or remove an enforcer; known limit.
   `npc.gd`, `dialogue.gd`, `campaign.json tones`. 1.5 days.
4. **Tie-up and missing guards.** Bodies are the genre's main tension. Cord item in `kit.gd`; `watch.gd` tracks
   pairs and roll-calls at the relief. 1 day.
5. **Save mid-night.** Checkpoints exist but journal and notoriety are only safe at dawn. Save the checkpoint
   state to `save.json` in `game_state.gd`. 1 day.
6. **Difficulty by constraint.** Townsman / Conspirator / Kościuszko's man: the last adds "no blood", "no alarm",
   fewer slip-aways; plus accessibility (cone always shown, slower suspicion). `options_panel.gd`, `stealth.json`. 1 day.
7. **Night replay with challenges.** Journal button: replay a won night; challenges per mission in
   `missions.json challenges`, scored in the dawn panel. 1.5 days.
8. **Caution you can feel.** Barricades, closed gates, and `phases.caution_minutes` raised to 10. `watch.gd`,
   `greybox_district.gd`. 0.5 day.
9. **Navmesh patrols.** Straight-line legs through props break trust in cones. `guard.gd`. 0.5 day.
10. **Anachronism pass.** The magnesium flash; audit kit blurbs and bills. `stealth.json`. 1 hour.

## 3. What is new here, sharpened

**The Whisper Network as the planning layer.** *Pitch:* you do not plan a route, you plan what the city will
believe by the time you walk it. *Loop:* hear by night, plant by day, watch it spread at dawn, walk into the world it made.
*First 15 minutes:* on night 1 the player plants one rumour and sees a named patrol leave the square because of it.
*Risks:* dawn dice feel random; the network is invisible. *Deepen:* (a) a network sheet in the journal drawing the
seven groups as a parchment web, carriers lit as they learn; (b) a planted rumour mutates one step per group (the
bard adds a verse, the watch adds a name), so a lie gains detail; (c) the salon table: at the ball, speaking at one
table seeds a rumour that reaches the next table in minutes, and you must be elsewhere when it arrives.

**Identity gating as stealth.** *Pitch:* who you are is the widest disguise and the one you cannot take off.
*Loop:* the origin, sex, inclination and faith open doors, close others and set how the watch looks at you.
*First 15:* night 1 offers each character a road the others cannot take, greyed with the period reason.
*Risks:* reading as punishment; content failing to gate. *Deepen:* (a) the watch's gaze by identity, a woman
alone after curfew is stopped differently, a Jew on the Rynek after the bell is trespassing; (b) passing: borrowed
identity for a night at a price, tested by enforcers (Proposal 2); (c) circles only some can enter (the theatre, the
bathhouse, the women's gallery) that each hold one unique intel source per night.

**Succession as permadeath with continuity.** *Pitch:* the movement is the character. *Loop:* name an heir,
risk the figurehead, lose them, go on with a new face and 70% of the city. *First 15:* the day panel asks for an heir
on day 1, before any risk is felt. *Risks:* players reload rather than accept it; the heir feels generic.
*Deepen:* (a) the heir is present at night as an ally figure you can see and endanger; (b) the fallen figurehead's
fate becomes a rumour you can plant as martyrdom; (c) Proposal 4.

**The city as informant.** *Pitch:* everyone sells what they saw, to you and to them. *Loop:* urchins, vendors,
the bard and the madam trade news both ways; your standing sets who lies. *First 15:* an urchin sells you a patrol
time, then you watch him sell your description to the watch. *Risks:* too many sellers, noise. *Deepen:* (a) a
two-way ledger per informant: what they told you, what they told the Austrians; (b) buying silence; (c) planting
false news on an informant you know sells to the watch.

**Rumour-driven guards.** *Pitch:* the watch walks where the city's talk sends it. *Loop:* rumours reroute patrols,
pull bodyguards, arrest informers. *First 15:* the Kazimierz raid rumour empties a post the player saw full.
*Risks:* too indirect to read. *Deepen:* (a) a bark when a guard is moved by a rumour ("Nach Kazimierz, sofort!");
(b) guards gossip among themselves (Proposal 1); (c) a rumour can put a guard on edge (sight up) not only away.

**Punishment as crowd.** *Pitch:* the city's cruelty is cover, and the crowd's mood is a weapon. *Loop:* floggings
and the pillory gather crowds you blend into, and what the crowd feels (jeers or weeps) feeds rumours and riots.
*First 15:* the night 1 flogging crowd is the safest place on the square. *Risks:* spectacle as playground; tone.
*Deepen:* (a) the crowd's mood as a hidden value that a planted line tips; (b) feeding the pilloried man as a Street
action seen by all; (c) the executioner's assistant as an informant.

**Weather as accumulating variable.** *Pitch:* the winter keeps score. *Loop:* snow cover, wetness and fog build
over nights and change noise, sight and tracks. *First 15:* fresh snow shows the player's own footprints.
*Risks:* invisible numbers. *Deepen:* Proposal 5, plus ice on gutters and Śniadecki's moon tables as a forecast.

## 4. Five innovation proposals

**1. The Composite.** *Fantasy:* the Austrians build your face from scraps, and you can poison the scraps.
*Mechanics:* every witness (guard, enforcer, informant) stores the traits they saw: coat, height, sex, a limp, a
voice. At dawn the watch merges them into the wanted bill; guards gossip, and a trait spreads along the `watch`
network like a rumour. A false trait planted with an informant ("a red sash, a Russian accent") enters the bill;
guards then stop the wrong men. *Uses:* bills.json `wanted`, intel.gd notoriety, rumours.gd network, enforcers.
*First mission:* night 2: the Corporal's Ledger holds the witness statements; copy it and rewrite one line.
*Cost:* 4 days (witness memory in `guard.gd`/`npc.gd`, merge in `intel.gd`, bill text in `bills.json`).

**2. Borrowed Names.** *Fantasy:* under the Habsburg census every house has a number and every soul a line
(Tantner, *Ordnung der Häuser, Beschreibung der Seelen*); live in someone else's line. *Mechanics:* identities are
items: a name, a house number, a trade, a parish. Checkpoints ask two questions whose answers you learn by
overhearing the real person or reading the register; a wrong answer is Curious. A rumour about that name (dead,
arrested, gone to Lwów) burns it. Forging a new one needs the clerk (day action) and a seal. *Uses:* zones.gd
checkpoints, the `kazimierz_gate`, rumours, the veteran's "no papers" weakness, `bribe_clerk`.
*First mission:* night 3, the Salt Barge: pass the quay gate as a raftsman whose real owner drinks at the Zajazd.
*Cost:* 4 days (`zones.gd`, `dialogue.gd`, new `data/identities.json`, a register interior prop).

**3. The Court of the Rynek.** *Fantasy:* every loud act needs a culprit, and the city chooses one.
*Mechanics:* an alarm or death creates a "deed" object; at dawn stories compete for it (yours, the Austrians',
each faction's). The culprit the city believes suffers the crackdown: frame the Russians and Orlov's men are
arrested; let the Jews be blamed and the black-dog omen turns to a pogrom. Planting blame costs the channel's trace.
*Uses:* rumours.gd reach, factions' rivalry and grievance, the dawn report, crackdown.
*First mission:* night 6: after the riot, three stories for one dead soldier.
*Cost:* 3 days (`rumours.gd` deed type, `campaign.gd` resolution, `dawn_panel.gd`).

**4. The Second Candle.** *Fantasy:* when you fall, the heir picks up the night where it stands.
*Mechanics:* the named heir is placed in the district each night (safe house or task). Captured or killed, control
passes live to the heir, who starts with their own kit and knowledge; freeing the figurehead from the cells becomes
an optional objective. Both can survive; the movement then has two faces and the rivals know it.
*Uses:* succession, the cells, safe_house.gd, origins (content re-gates live).
*First mission:* night 4, the Bishop's Letter: a woman heir in a Bernardine habit continues where the male
figurehead in a cassock was taken.
*Cost:* 5 days (`player.gd` swap, `mission_runner.gd`, `campaign.gd` succession, heir placement in `missions.json`).

**5. The Thaw Remembers.** *Fantasy:* the snow keeps your secrets until spring does not.
*Mechanics:* footprints in snow (MGS) that guards follow, erased by new snowfall; bodies and caches stashed in
drifts are hidden until a thaw night, when they surface in public and become deeds (Proposal 3) and witness traits
(Proposal 1). Stashing in a drift is free and silent; it is a debt paid in the weather.
*Uses:* weather.gd `snow_cover`/`wetness`, hiding_spot.gd, campaign weather per night, guard search.
*First mission:* night 2 in light snow, with the night 4 thaw bringing the downed guard back.
*Cost:* 3 days (decal trail in `player.gd`, `guard.gd` track-follow, drift stash, `campaign.gd` surfacing).

## 5. Next pass, in priority order

| # | Item | Owner files | Accept when |
|---|---|---|---|
| 1 | Suspicious acts | `data/stealth.json`, `guard.gd`, `traversal.gd`, `verbs.gd` | Climbing or picking a lock in view of a guard in a permitted zone makes him Curious; smoke line `illegal_act ok`. |
| 2 | Tie-up, missing partners | `kit.gd`, `watch.gd` | A tied guard never wakes; a partner whose pair is missing searches within 20 s. |
| 3 | Enforcer verbs | `npc.gd`, `dialogue.gd`, `campaign.json` | Each enforcer can be bribed, frightened or framed; each removes the red cone for the night. |
| 4 | Planning step | `day_panel.gd`, `kit.gd`, `missions.json` | Five items and one of ≥2 entries chosen per night; no new HUD. |
| 5 | Footprints in snow | `player.gd`, `guard.gd`, `weather.gd` | Prints persist 5 game-min at `snow_cover` > 0.5; a guard seeing them walks them. |
| 6 | The Composite | `guard.gd`, `intel.gd`, `bills.json` | The bill lists only traits actually seen; a planted false trait appears on it. |
| 7 | Bengal light, anachronism pass | `stealth.json` | No item predates its period; blurbs read in the house voice. |
| 8 | Caution barricades, patrol navmesh | `watch.gd`, `greybox_district.gd`, `guard.gd` | Barricades on two side streets in Caution; no patrol clips a stall. |
| 9 | Mid-night save | `game_state.gd`, `mission.gd` | Quit at a checkpoint and continue with notoriety and journal intact. |
| 10 | Typefaces by class | `ui_theme.gd`, `bills.json`, `dialogue.gd` | Bills, letters and speakers use one of four hands, with a legible-font option. |
