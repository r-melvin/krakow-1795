# Folklore, superstition and the deniable supernatural in Kraków, winter 1795/96

What the town believes, what it says, and how the game uses it. Companion to `data/folklore.json` (rumours,
chatter, omens, stagings, counters), `data/rumours.json` (`kind`: omen, miracle, curse, relic, prophecy) and
docs/GDD.md ("Superstition and religion", "Tone"). Rule of the house: **the game never confirms the
supernatural.** Every strzyga is a knife, every omen is weather, every ghost is a sentry who wanted a warmer post.
The town believes what it needs to, and the player can feed that need. Where a belief is later than 1795 it is
marked **[later]** and the game should not put it in a townsman's mouth except as a deliberate wink.

## 1. Dating: what a Kraków street knew in 1795

The winter of the Third Partition sits at an odd hinge. The Main School (the university under the Commission of
National Education) had spent twenty years teaching Newton, and its astronomer Jan Śniadecki had met Herschel at
Slough in 1787. Forty years earlier the same city had bought Chmielowski's *Nowe Ateny* (1745-46), an encyclopaedia
that lists the effects of comets and the remedies against upiory with equal confidence. The Jesuit Jan Bohomolec's
*Diabeł w swojej postaci* (1772, part II 1777) had argued at book length that upiory, strzygi and witches were
delusion; it sold because people believed in them. The Habsburgs, whose garrison now sat in Wawel, had their own
history here: the 1730s vampire panics were Habsburg affairs (Arnold Paole at Medvegia, 1732, reported by the army
surgeon Flückinger), and in 1755 Maria Theresa, on Gerard van Swieten's report, forbade the exhuming and staking of
the dead in her lands and reserved such matters to the civil power. **Kraków in 1795 is therefore a city where the
staking of a corpse is against the occupier's law, believed in by the occupier's own Moravian and Bohemian
conscripts, sneered at by the professors, half-believed by the market, and quietly monetised by the parish.** That
is the design space.

The sources behind this note, in rough order of usefulness (see section 9 for full citations): Kolberg's
*Krakowskie* (recorded 1860s-70s in the villages round the city: later than 1795 but the fullest record of the same
population's grandparents' beliefs); Kitowicz's *Opis obyczajów* (written in the 1780s: customs of the mid-century);
Chmielowski and Bohomolec (period voices for and against); the chronicle tradition (Kadłubek, Długosz, Bielski) for
the city legends; period travellers (Coxe 1784, Kausch 1793, Schulz 1795-96) for what a foreigner was told;
Trachtenberg for Ashkenazi belief; the Polish anti-revenant burials for what people actually did to corpses.

## 2. The walking dead and the night-pressers

**Strzyga / strzygoń.** From Latin *strix* through Old Polish; the word is in 15th- and 16th-century Polish. A person
born with two souls (the tells: two rows of teeth, born with teeth, a caul, a birthmark, a seventh child). Baptism
takes only one soul; when the body dies the second stays, and the corpse rises at night to strangle and drink blood,
starting with kin. In the Kraków country Kolberg's informants use *strzygoń* for the male revenant and *strzyga* for
the female. Remedies: rebury face down, an aspen stake, decapitation with the head between the feet, burn the
heart, a sickle across the throat, poppy seed in the coffin (the dead must count it, one seed a year). The
Witcher's striga (a cursed princess lifted by a night in her tomb) is Sapkowski, 1980s **[later]**; one line of the
bard's may wink at it, nobody else's.

**Upiór / upir / wąpierz.** The revenant proper, the word borrowed from Ruthenian into Polish by the 17th century
(*wąpierz* is the older western form; both were current). Chmielowski gives the type: the dead man who returns to
his house, sits at the table, calls his wife, and whose grave when opened shows a red face and fresh blood. The
Habsburg troops call him *upír* (Czech) and their families in Moravia and Silesia had had "magia posthuma" trials into
the 1750s. The unshriven, suicides, the excommunicate, the drunkard who died cursing, and anyone buried without the
rites are the candidates: which is why the Church's refusal of consecrated ground creates the very fear its Masses
then relieve. A parish priest in 1795 would deny upiory in the pulpit and sell a Mass for the soul at the door.

**What was actually done to corpses (archaeology).** Polish cemeteries have produced dozens of "deviant" burials
of the 16th-18th centuries: at Drawsko (Greater Poland) sickles laid across the throat or belly and stones under the
chin; at Gliwice (Silesia) decapitated bodies with the head between the legs; at Pień near Bydgoszcz (excavated
2022) a young woman with a sickle across her neck and a padlock on her toe; face-down burials from the early Middle
Ages (Kałdus) onward. Ethnographers add: cutting the sinews behind the knee or heel so the corpse cannot walk,
nailing the shroud or coat to the coffin, a coin or salt in the mouth, aspen or hawthorn pegs, burial at a
crossroads. Every staging in `folklore.json` is one of these, done to a fresh body instead of an exhumed one. None
requires belief in the player: only in whoever finds the body.

**Topielec / utopiec.** The drowned who did not get their rites become the river's own: a small grey man, or the
drowned man himself, who pulls swimmers and drunks under, stands on the ice in fog, and sings under bridges. The
Vistula raftsmen (*flisacy*; the Zwierzyniec brotherhood of *włóczkowie* who also keep the Lajkonik) had the rule
recorded of fishermen across the Slavic north: **do not pull a drowning man out, or the water will take you in his
place.** In the game, a body that goes into the moat, the drains or the river is "the topielec's" by morning, and
the informer sunk by Wilk's men (events.json `corpse_carried`) sings under the Stradom bridge.

**Zmora / mara.** Not a dead thing but a living one: a person (often a woman, the seventh daughter, or a child
baptised with a slip of the tongue) whose soul leaves her at night and sits on a sleeper's chest until he cannot
breathe. The words are in 16th-century dictionaries; the beliefs are Kolberg's. Remedies: sleep on the belly, a knife
or an axe under the bed, invite her to breakfast (she must come, and you know her). Sentries who wake gasping are a
gift to the whisper network: "the mora sits on the Bohemians at the Town Hall post."

**Południca.** The noon-woman of the harvest fields, who twists the necks of reapers who work through midday. Purely
a summer being; in January she is a joke ("even the południca has gone indoors"). Listed so nobody uses her in
the snow.

**Boginka / mamuna and the odmieniec.** Wild women of the riverbanks and marshes who steal an unchurched mother's
child from the cradle and leave their own: the *odmieniec* or *podciepek*, the changeling, big-headed, always hungry,
never thriving. Protections recorded by Kolberg: a red ribbon, a knife or needle in the swaddling, a candle kept lit
until baptism, the mother never left alone before her churching (*wywód*). The test for a changeling is the one
thing in this note the game must handle soberly: the child was laid on the dunghill and beaten with a birch so the
boginka would come for it. A tenement changeling rumour in `folklore.json` puts a real child at risk; the counter
exists and the dawn report says what happened if nobody took it.

## 3. Weather-makers, house-things and the small evil

**Płanetnik / chmurnik.** The cloud-herd, strongest in Lesser Poland and the Podhale: a man taken up into the
storm-cloud (sometimes a drowned man, sometimes a living peasant who vanishes before hail) who drives the weather.
Villagers left flour and eggs on the fence for him and could, it was said, hire one to send hail on a neighbour.
A blizzard on the night the player needs the watch blinded is the płanetnik's, and "somebody paid him" is a
rumour with a name in it (Herr Stolle, the Prussian, pays peasants in flour).

**Licho.** The evil one, one-eyed in the east, nameless in the west: the thing in proverbs (*licho nie śpi*, the
evil one does not sleep; *cicho, bo licho*) rather than in tales. A Kraków townsman says *licho* the way an
Englishman says "sod's law". Useful for chatter, not for rumours.

**Skrzat, ubożę, latawiec, chowaniec.** The Polish house-spirit is not the Russian *domowik* (the word is
Ruthenian; a Kraków burgher would not use it). Fifteenth-century Kraków sermon literature already scolds people
who leave crumbs on a Thursday for the *ubożę*; the *skrzat* is the same thing in the west. The *latawiec* is a
spirit hatched from an egg carried under the armpit for nine days (witch-trial evidence of the 17th century) that
brings its keeper grain or money and is seen as a fiery streak across the sky: **a meteor is a latawiec carrying
someone's fortune home**, and a bright one is "the dragon flying". The printer's skrzat who "only sets Polish" is
the game's affectionate version.

## 4. The city's own legends

**Krak and the Wawel dragon.** Kadłubek (c.1200) has the *holophagus* under the hill killed by Krak's sons with
hides stuffed with sulphur; Długosz (15th c.) gives the deed to Krak himself; the 16th-century chronicle tradition
(Bielski) adds the shoemaker Skuba and the sheep. All three were in print and in the mouths of Kraków schoolboys in
1795. The Smocza Jama itself had been a tavern of low repute in the 17th and 18th centuries; the Austrians would
wall it up within a generation. So "the dragon's cave" in 1795 means a drinking den under the Austrian barracks:
the rumour that he has woken and "eats only Austrians" (rumours.json `dragon_wawel`) is already the children's.
Krak's mound (Kopiec Krakusa) across the river in Podgórze, Austrian since 1772, has the Rękawka fair on Easter
Tuesday (outside the campaign).

**Wanda.** Kadłubek: Krak's daughter refuses the German prince (Rytygier in later tellings), who kills himself for
shame; she lives and dies a virgin queen. Długosz has her throw herself into the Vistula in thanks for the victory.
Her mound stands at Mogiła by the Cistercians. The rhyme *Wanda, co nie chciała Niemca* ("Wanda, who would not have
a German") is 19th-century in that form **[later]**, but the refusal of the German is the 13th-century core, and
in a city that has just been handed to a German-speaking emperor it says itself. An early thaw at Mogiła means
Wanda is turning in her mound.

**Pan Twardowski.** The Kraków sorcerer of King Sigismund Augustus's court (1550s) who sold his soul on condition
the devil could take it only in Rome, and was caught at an inn called Rzym. The bargain, the black mirror (kept at
Węgrów) and the raising of the dead Queen Barbara for the grieving king at Wawel are in 17th-century print. The
ending in which he escapes to the moon and sits there to this day is attested in 19th-century recordings (Kolberg;
Kraszewski's novel 1840) **[uncertain before 1800]**; Mickiewicz's ballad *Pani Twardowska* (1822) is **[later]**.
"Twardowski's school" is a cave in the Krzemionki quarries in Podgórze, on the Austrian side of the river since
1772. For the game: a burgher pointing at the moon and saying "Twardowski's up there, and he's still not signed
for them" is a plausible joke; treat it as a wink, not a fact of 1795.

**The ghost of Wawel.** Not a White Lady (that is Kórnik). In 1795 the Wawel ghost is Queen Barbara Radziwiłłówna,
raised by Twardowski in the black mirror; the belief that the kings in the crypt stir when the Kingdom is in danger
is patriotic folklore of the partition century, plausible in 1795 and everywhere by 1830. The Austrians turned the
castle into barracks and a hospital from 1796. Sentries in the royal apartments who ask to be moved are the
rumour; the cause is the cold.

**Skałka and St Stanislaus.** Bishop Stanislaus was killed at Skałka in 1079 on King Bolesław's order and, by the
13th-century *Vita* (Wincenty of Kielcza), cut in pieces that grew back together under the eagles' guard. The
*Vita* draws the moral out loud: **as the martyr's body grew together, so the divided Kingdom would be one again.**
This is the single most useful piece of authentic 1795 folklore in the game: a 500-year-old prophecy about a
dismembered Poland reuniting, preached in Kraków every May, in the winter the Kingdom was dismembered for the
third time. It cannot be disproved and the Church cannot disown it. The pool at Skałka, the procession from Wawel
on the Sunday after 8 May, the relic in the silver coffin: all real and outside the window; the prophecy is not.

**The Black Madonna.** Częstochowa's icon (the 1655 siege; Jan Kazimierz's Lwów oath of 1656 naming her Queen of
Poland; the Bar Confederates' hymn) is the devotion of the century; the holy cards of `day_actions.holy_cards`
already put her on one side and the Third of May on the other. Kraków has its own Madonnas (the Piasek Carmelites'
"Our Lady of the Sand"; the St Mary's altar), and Queen Jadwiga's crucifix in Wawel cathedral, said to have spoken
to her, is a 15th-century devotion. Weeping and turning icons are the miracle type the campaign already stages.

**The hejnał and the Tatar arrow.** The tower trumpeter is documented from 1392 and the tune does break off
mid-phrase, unexplained. The story that it breaks where a Tatar arrow took the trumpeter's throat in 1241 has no
record before the 20th century and was fixed by Eric P. Kelly's *The Trumpeter of Krakow* (1928) **[later]**.
`rumours.json` `hejnal_sign` currently says "jak za Tatarów"; recommend the campaign agent reword it to "as it
always does, and did not finish" or let the bard be the one who "explains" it.

**St Mary's two towers.** The knife hanging in the Sukiennice passage is real and old (a Magdeburg-law warning
to thieves); the tale of the two builder brothers, the taller tower and the murder, is first written down in the 19th
century (Grabowski's circle) **[later as a tale; the knife was there]**. A porter may point at the knife; nobody
tells the brothers' story.

**The Lajkonik.** The Zwierzyniec raftsmen's hobby-horse rider who beats the crowd with his mace on the Thursday
after Corpus Christi; paid for by the Norbertine convent in accounts from 1738. The Tatar-raid origin story is
19th-century **[later]**. Out of season for the campaign, but the raftsmen who carry him are the same men who land
the salt barge, and "the Lajkonik will beat the Austrians out of the square in June" is their kind of promise.

**Bells.** Kraków's bells were rung *na chmury*, against storm clouds, a practice the synods regulated and never
stopped; the Zygmunt bell (1520) rings for coronations, deaths and disasters, and its ringing in January for no
announced reason would be read as one. Bells were also requisitioned by governments for gun-metal; "the Austrians
mean to melt Zygmunt" is a rumour the town would believe instantly. The lovers' custom of touching Zygmunt's
clapper is **[later]**.

## 5. The sky and the seasons

**Comets.** Chmielowski, following every almanac since Ptolemy: comets mean war, pestilence, a hard winter and the
death of princes. In 1795 the town had all four, and a king: Stanisław August signed his abdication at Grodno on 25
November 1795. Caroline Herschel found a comet on 7 November 1795 (the one later named for Encke), a telescope object
nobody in Kraków saw; the game's comet from campaign night 3 is the alternate-history flex. Śniadecki, who knew
Herschel personally, is the built-in sceptic: a comet is a body on an orbit and he can compute the night it sets
for the last time. The street's reply is that it came, and the crown went.

**Meteors and fireballs.** A shooting star is a soul leaving (cross yourself), or a latawiec carrying money to a
sorcerer's chimney, or "the dragon flying" if it is bright enough to throw shadows. On 13 December 1795 a stone
fell out of the sky at Wold Cottage in Yorkshire and the Royal Society had to admit stones did that; the professor
knows this, the market does not. A fireball is the strongest single omen event the sky can produce in-game.

**Halo.** The 22-degree ring round the moon (sky.json `halo22`, cirrus and fog looks): *księżyc w lisiej czapie*
("the moon in a fox cap") means frost or snow coming, in every almanac; a full ring means a burial or a war
within the month, in Kolberg's villages. Both are said in the same breath. The game reads it as "a ring for a
burial", and the whisper network supplies the name.

**Blood rain, red snow, a red dawn.** Długosz and the chronicles record rains of blood as portents; Chmielowski
repeats them; a red dawn over the Rynek in frost is a thing the sky shader does anyway. "Red snow on the square,
as before the Swedes" is a market woman's line. (Saharan dust is the modern explanation; nobody in 1795 needs it.)

**The three days of darkness.** A Catholic prophecy of the 19th century (Anna Maria Taigi, d. 1837; Marie-Julie
Jahenny, 1870s) **[later]**. In 1795 the reference is scriptural: the darkness over Egypt (Exodus 10) and at the
Crucifixion. Three nights of fog on the Rynek are "Egypt's dark" from a pulpit and "the Austrians' luck" from a
smuggler. Do not put "three days of darkness" as a prophecy in anyone's mouth.

**Thunder in January.** Winter thunder is rare on the upper Vistula and was universally an omen (of a hard year,
of war, of a great man's death); the bells were rung against it. sky.json has a `storm` look with lightning; if the
weather agent ever schedules it in the campaign it should be an omen event, not background.

**Wigilia (24 December).** Kitowicz describes the Christmas Eve customs of the mid-century (hay under the cloth,
the wafer, the first star, an even number at table or someone dies before the year is out); Kolberg adds that at
midnight the cattle speak, and that a man who hides in the byre to listen hears his own death. The campaign's
seven nights fall after Christmas (the Third Partition treaty is late October; the Austrian commissioner arrives in
spring); the ox that spoke on Wigilia is therefore hearsay in January: "the ox in the Kleparz stable said they would
be gone by Easter". The empty place laid for the wanderer is a 19th-century formalisation **[later]**; the wafer,
hay and star are not.

**Twelfth Night (6 January, a Wednesday in 1796).** Chalk blessed at Mass and the initials of the three Kings
written over the door (K+M+B), star-carollers (*kolędnicy*) with the turoń (a horned, snapping beast on a pole),
and the *Herody*, the Herod play performed by students and apprentices, which Kitowicz describes with the Jews'
part played for laughs and the devil carrying Herod off. The chalk is still on every door in the campaign's window,
which is what makes rubbing it off a staging: a door whose Kings have been wiped is a house that has been given up.

**Candlemas, Matki Boskiej Gromnicznej (2 February 1796, a Tuesday).** The *gromnica*, the thunder-candle, is
blessed that day and kept for life: lit in the window against storm and lightning, put in the hands of the dying,
its smoke used to draw a cross on the beam. Our Lady of the Thunder Candle walks the winter fields and keeps the
wolves off the villages; the wolves come to the gate on her night. The proverb: *Gromnica, zimy połowica*
(Candlemas, winter's half). The painting of her with the wolf at her feet is Stachiewicz, 1890s **[later]**; the
belief is older. In a garrison town where the infantry wear white: "the wolves this year have white coats". Three
days later, **St Agatha (5 February)**, bread and salt were blessed against fire and thrown into a blaze to stop
it: a real hook for the fire system, a wholly deniable one.

**Plague.** Kraków's last great plague was 1707-10 (the Northern War); *morowe powietrze*, the pestilential air, is
what the old people remember being told about. The plague as a tall maiden in white waving a red kerchief from a
roof (the *morowa dziewica*) is in the chronicle tradition and Kolberg. Cholera reached Poland in 1831 **[later]**:
never say cholera. The winter disease of 1795 is typhus (*gorączka gnilna*, "putrid fever") in barracks and
prisons, and an Austrian garrison burying its dead at night on Wawel is the Maiden on the roof.

**Kołtun (plica polonica).** The matted "Polish plait" that half the peasantry wore and would not cut, believing
the disease would go inward and kill; the Main School's doctors were campaigning against it and the Silesian
physician Kausch (1793) wrote it up as the type of Polish superstition. Period-perfect flavour for a knife grinder's
or barber's line.

## 6. Salt, garlic, aspen: the apotropaic kit

Salt (Wieliczka's, taxed by the new excise: the `salt_tax` rumour is already running) on the threshold and in the
mouth of the dead; garlic and blessed herbs at the window and, for the dead, in the mouth; aspen (*osika*, the tree
that trembles because Judas hanged on it) for the stake; hawthorn as second choice; poppy seed in the coffin; a coin
for the dead (the *obol*, under the tongue or in the hand); a sickle or knife across the throat; the body face down
"so it digs the other way"; the sinews cut at heel or knee; the shroud nailed; burial at a crossroads or outside
the wall for those the priest refuses. Iron against everything (the knife under the pillow). The gromnica and
Epiphany chalk are the Church's own apotropaics, which is why using them in a staging is sacrilege if it is traced.
All the vendor items proposed in `folklore.json` (`items`) are groszy: salt from the fish seller, garlic and poppy
from the herb woman, chalk from the candle seller, an aspen peg from the firewood man.

## 7. Kazimierz

The Jewish town has its own night. **Dybbuk**: the clinging spirit of a sinner that enters a living person and
speaks through them; possession accounts from 16th-century Safed, the word in Ashkenazi use by the 17th century,
exorcism by a *ba'al shem* with a minyan and shofar. In 1795 a Kazimierz family would sooner consult a ba'al shem
than tell a Christian. **The golem**: the clay man of Rabbi Loew of Prague is a 19th-century literary creation
**[later]**; in 1795 the golem a Kazimierz tailor knows is Rabbi Elijah Ba'al Shem of Chełm's (d. 1583), attested by
Christoph Arnold in 1674 and by Jacob Emden in the 18th century: a servant that grew too big and had to be unmade,
and crushed its maker when it fell. **Reb Eizik Reb Yekeles**: Kraków's own tale, told of Izaak Jakubowicz, who built
the Izaak synagogue (1644): he dreamed of treasure under the Prague bridge, walked there, and was told by the guard
of the guard's own dream of treasure under a Kraków Jew's stove; he went home and dug it up. (The "treasure is at
home" type; recorded in the 19th century, attached to a 17th-century man.) **Shedim** live in bathhouses, privies and
ruins (Talmudic, and household caution in Ashkenaz: do not bathe alone at night). **Lilith** takes the newborn: the
childbed amulet (*kimpet-tsetl*) with the three angels' names on the wall and the door. **The Angel of Death**
(*malekh-hamoves*): when someone dies the water in the house's vessels is poured out because he has washed his
sword in it (Sefer Hasidim); a dangerously sick child is given a new name (*shinui ha-shem*, Talmudic) so that the
Angel's list no longer matches. **The mezuzot are checked** when misfortune runs. The "black wedding" of orphans in
the cemetery to end an epidemic is chiefly 19th-century **[later]**.

And the thing that is not folklore but its shadow: **the blood libel.** Sandomierz's trials of 1698 and 1710-13 and
de Prevot's paintings in its cathedral were within living memory's reach; Cardinal Ganganelli's report of 1759 had
found the accusation baseless, and the Enlightenment elite despised it; the market did not. A body with garlic in
its mouth found within a hundred paces of Kazimierz's gate will be blamed on the Jews by somebody before it is
blamed on a strzygoń. `folklore.json` `counters.blood_slander` is the game's handling of it: never plantable, always
costly, always stoppable, and written into the dawn report and the endings if it was not stopped.

## 8. Six voices

- **The parish priest** (personality pious or wry): "There are no strzygonie. There are souls without a Mass." He
  denies the revenant and offers the remedy; he will bless a cellar door for a crowd and preach against *zabobon*
  the Sunday after. He fears the Bishop more than the dead. Bohomolec is his authority if he has read anything.
- **The professor** (Śniadecki; stern or wry): comets have orbits, corpses do not walk, the peasantry needs schools
  and the Austrians need to leave. He will print against superstition if given the press, and he knows the 1755
  Habsburg decree well enough to shame the commandant with it. He is the town's disprover: every staging's
  `sceptic.professor` line is his.
- **The market woman** (wry, cynical-merchant, fearful): knows the whole kit (salt, garlic, the seventh daughter,
  the caul), believes about half of it, sells the rest, and is the first to name a Jew and the first to feed a
  changeling. Her lines are the network's fastest channel.
- **The raftsman** (gallows-humour, stern): topielce, the rule about not saving the drowning, the singing under the
  bridge, St Barbara, the Lajkonik in June. He has sunk men himself and speaks of the river as an employer.
- **The soldier** (Austrian; fearful or drunk-philosopher): a Moravian or Bohemian conscript who believes in the
  upír more than any Kraków burgher, misses the Rauhnächte at home, has heard the sentries at Wawel complain, and
  will not go down the well grate. His corporal is Tyrolean and thinks the whole province is possessed. German
  lines with glosses; the occasional Czech word.
- **The Jewish tailor** (Kazimierz; wry, tender): dybbuks are for the Hasidim, shedim are in the bathhouse, the
  mezuzah wants checking, his sister changed her boy's name and the boy lived, and the only monster he has ever
  seen on Szeroka wore boots. He knows exactly what a body found near the gate means for his street and says so,
  once, plainly.

## 9. Sources

Period (before or at 1795):
- Wincenty Kadłubek, *Chronica Polonorum* (c. 1190-1208): Krak, the dragon, Wanda.
- Wincenty of Kielcza, *Vita maior sancti Stanislai* (c. 1260): the body grown together and the Kingdom's reunion.
- Jan Długosz, *Annales* (15th c.): Wanda's drowning, prodigies, blood rain; Marcin/Joachim Bielski, *Kronika*
  (1551; 1597): the shoemaker and the dragon.
- Benedykt Chmielowski, *Nowe Ateny* (Lwów 1745-46): comets, upiory, remedies; the period's popular encyclopaedia.
- Augustin Calmet, *Dissertations sur les apparitions... et sur les revenans et vampires* (1746), read in Poland.
- Gerard van Swieten, *Remarques sur le vampyrisme* (1755) and Maria Theresa's decree of 1755 on posthumous magic;
  Johann Flückinger, *Visum et Repertum* (1732), the Paole report.
- Jan Bohomolec SJ, *Diabeł w swojej postaci* (Warsaw 1772; part II 1777): the Polish Enlightenment against upiory.
- Jędrzej Kitowicz, *Opis obyczajów za panowania Augusta III* (written 1780s; printed 1840-41): Wigilia, Herody,
  processions, the customs of the mid-century.
- William Coxe, *Travels into Poland, Russia, Sweden and Denmark* (1784); Johann Joseph Kausch, *Nachrichten über
  Polen* (1793: kołtun and "Polish superstitions" by a physician); Friedrich Schulz, *Reise eines Liefländers*
  (1795-96): what travellers were told in the 1790s.
- Talmud (Berakhot 62a on bathhouse demons; Rosh Hashanah 16b on changing the name); *Sefer Hasidim* (13th c.);
  Christoph Arnold (1674) and Jacob Emden, *Megillat Sefer* (18th c.) on the Chełm golem; Cardinal Ganganelli's
  report on the blood libel (1759).

Later collections of older material (cite, but date what they record):
- Oskar Kolberg, *Lud. Jego zwyczaje...*, ser. 5-8 *Krakowskie* (1871-75): the fullest record; strzygoń, topielec,
  zmora, boginki, płanetnik, halo lore, Wigilia, gromnica.
- Łukasz Gołębiowski, *Lud polski, jego zwyczaje, zabobony* (1830); Ambroży Grabowski, *Kraków i jego okolice*
  (1822) and later editions: the city legends as first written down.
- Hugo Kołłątaj's letter to Jan Maj (1802), the first programme for collecting Polish folk custom, written from
  prison by the game's absent patron.
- Kazimierz Moszyński, *Kultura ludowa Słowian*, II/1 (1934): synthesis; anti-revenant practices including cut
  sinews and face-down burial.
- Joshua Trachtenberg, *Jewish Magic and Superstition* (1939); Gershom Scholem, "The Idea of the Golem" (1960).
- Archaeology: Drawsko (Gregoricka et al., *PLoS ONE* 2014), Gliwice (2013 excavation reports), Pień (Poliński,
  2022 season), Kałdus (Chudziak).

Marked later, for the avoidance of doubt: the Tatar arrow of the hejnał (1928), the two-brothers tale of St
Mary's towers (19th c.), the Lajkonik's Tatar origin (19th c.), Twardowski on the moon (recorded 19th c.),
Mickiewicz's ballad (1822), the Prague golem of Rabbi Loew (19th c.), the three days of darkness (19th c.), cholera
(1831), the wolf at Our Lady's feet (1890s), the empty Wigilia chair (19th c.), the Witcher's striga (1986).
