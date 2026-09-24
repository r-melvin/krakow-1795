# Historical people in Kraków 1795

The game is historical fiction. The people listed here really lived. Their situations in the winter of 1795/96
are drawn from the sources given for each. Everything they *do* in the game (letters, missions, conversations)
is invented unless it says otherwise. No quotation in the game is attributed to a real person as their own words.
Names used in `data/campaign.json` (`historical`, `leaders`), `data/missions.json` and `data/rumours.json`.

Sources used for checking, cited again per person:
- [W] Constantin von Wurzbach, *Biographisches Lexikon des Kaiserthums Oesterreich*, vol. 16 (Vienna, 1867),
  entry "Margelik, Johann Wenzel Freiherr" (public domain; transcribed on de.wikisource.org).
- [O] *Encyklopedia Powszechna* (S. Orgelbrand, Warsaw, 1859–1868), entries for the persons named (public domain).
- [L] Filip Lichocki, *Pamiętnik Filipa Lichockiego prezydenta miasta Krakowa z roku 1794* (memoir, published
  Kraków, 19th century; Silesian Digital Library copy).
- [Wod] Stanisław Wodzicki, *Wspomnienia z przeszłości od roku 1768 do roku 1840* (Kraków, 1873; public domain).
- Modern works used only to check dates (not public domain): the Polish Biographical Dictionary (*Polski Słownik
  Biograficzny*); P. Kopeć, "Hugo Kołłątaj, a State Prisoner in Olomouc and Josefov in 1794–1802", *Poznańskie
  Studia Slawistyczne*; the Archdiocese of Kraków's list of bishops; the Jagiellonian University observatory's
  history pages; the English and Polish Wikipedia articles cited in the development log.

## Faction leaders

Model ids are `hist_<id>` (built by the character pipeline); until they exist the fallback models in
`data/campaign.json leaders` are used. We did not work from any particular portrait, so the descriptions are of
the period type, not likenesses.

| id | Person | Born | Leads | Real or fictional |
|---|---|---|---|---|
| turski | Bishop Feliks Paweł Turski | 1729 | Church | real |
| sniadecki | Jan Śniadecki | 1756 | Salon & intelligentsia (Kołłątaj the absent patron) | real |
| wodzicki | Count Stanisław Wodzicki | 1764 | Magnates | real |
| lichocki | Filip Nereusz Lichocki | 1749 | Guilds & burghers | real |
| kmita | Sergeant Kmita | c.1745 | Street | fictional stand-in (no documented Kościuszko NCO in Kraków could be pinned down) |
| jedrek | Jędrek the Smuggler | c.1760 | Underworld (under the kingpin Wilk, also fictional) | fictional |
| margelik | Johann Wenzel von Margelik | c.1750 | Austria | real |
| orlov | Monsieur Orlov | c.1755 | Russia | fictional |
| lindner | Herr Lindner | c.1750 | Prussia | fictional (the real Warsaw banker Piotr Fergusson Tepper went bankrupt in 1793 and died in 1794) |

### Feliks Paweł Turski (1729–1800): Church
Bishop of Kraków from 1790 until his death on 31 March 1800. Before that he was bishop of Chełm (from 1765) and
of Łuck (from 1771). He was the last to hold the title of Duke of Siewierz. [O; Archdiocese of Kraków list]
- *Portrait (type):* sixty-six in 1795. An elderly prelate, heavy, a little stooped, with grey hair under a red
  zucchetto. He wears a violet cassock, a lace rochet, a red mozzetta, a pectoral cross and the ring, and walks
  with a cane.
- *In game:* the bishop of the procession on the Rynek, and the man confronted in *The Bishop's Letter*.
- *Liberties:* the letter to Vienna is fiction, and it is drafted in his name by the fictional Canon Wolski. His
  fear for the Church's lands under the new Austrian rule is plausible, but no such letter is known.

### Jan Śniadecki (1756–1830): Salon and intelligentsia
Mathematician and astronomer. The Commission of National Education appointed him professor of higher mathematics
and astronomy at the Main School of the Crown in Kraków in 1781. He made astronomical observations in Kraków
between 1788 and 1803, and later directed the observatory at Vilnius and was rector of the university there. [O;
Jagiellonian University observatory history]
- *Portrait (type):* thirty-nine. A lean scholar with his own dark hair, lightly powdered and tied back, and a
  sharp, clean-shaven face. He wears a sober dark coat and a white stock, has ink on his cuffs, and holds his
  spectacles in his hand.
- *In game:* a person to find on Jagiellońska by the Collegium Maius. He gives moon tables (darker nights) and
  lectures students.
- *Liberties:* his conversation and his help to the movement are fiction.

### Hugo Kołłątaj (1750–1812): the absent patron
Co-author of the Constitution of 3 May 1791 and a leader of the 1794 rising. The Austrians captured him in
December 1794, and he was a state prisoner at Olomouc and Josefstadt (Josefov) until 1802. [O; Kopeć]
- *In game:* off-stage only. His letter from prison is a rumour and a pamphlet. The letter is fiction; his
  imprisonment is not.

### Count Stanisław Wodzicki (1764–1843): Magnates
A noble of Lesser Poland who fought in the Kościuszko Rising and much later became the first president of the
Senate of the Free City of Kraków (1815–1831). He was also a botanist and a writer of memoirs. [Wod; O]
- *Portrait (type):* thirty-one. A tall, upright young officer-noble, clean-shaven with short dark hair. At the
  masquerade he wears a French coat; otherwise a kontusz with a sash and a karabela sabre.
- *In game:* the magnates' voice at *The Magnate's Ball*, who can be won over.
- *Liberties:* we do not know that he was in Kraków that winter, or at any such ball. His patriotism in 1794 is
  documented; his dialogue is not.

### Filip Nereusz Lichocki (1749–1806): Guilds and burghers
A lawyer from a Kraków merchant family and city syndic from 1776. He was president (mayor) of Kraków from 4 March
1794, under the settlement of the Grodno Sejm and on behalf of the Targowica party, and was removed after
Kościuszko's arrival in April 1794. He was president again from 1798 to 1802. His memoir of 1794 survives. [L; O]
- *Portrait (type):* forty-six. A stout burgher-lawyer in a powdered bag wig, clean-shaven, with a round face.
  He wears a sober brown coat, a jabot and silver buckles, and the chain of office on formal days.
- *In game:* the guilds' leader, cautious and leaning towards whoever keeps order. Named in the leaders data;
  his scenes are fiction.

### Johann Wenzel von Margelik (c.1750–?): Austria
A Habsburg official, made a baron in 1785, and from 21 March 1796 the first commissioner (Einrichtungshofkommissär)
for the newly annexed West Galicia. Kraków became that province's capital in 1797. [W]
- *Portrait (type):* a senior civil servant of about forty-five, in a powdered wig and a dark official coat with
  an order's star, carrying a cane.
- *In game:* off-stage. Baron von Hauer, "his man in Kraków until spring", is fictional.

### Sebastian Sierakowski (1743–1824)
A Jesuit until the order was suppressed in 1773, then a canon of Wawel cathedral. He made a restoration plan for
Wawel castle for King Stanisław August's visit in 1787, and was later rector of the Kraków Main School
(1809–1814). [O; PSB]
- *In game:* the canon on St Mary's steps who lends a cassock in *The Bishop's Letter*. That scene is fiction.

### Tadeusz Kościuszko (1746–1817)
Wounded and captured by the Russians at Maciejowice in October 1794 and held in St Petersburg until Paul I
released him in 1796. [O]
- *In game:* a rumour and a relic. The rumour that he has escaped is false, as it would have been in the winter
  of 1795/96. The sabre rumour is true only as far as Sergeant Kmita's own sabre goes.

### Wojciech Bogusławski (1757–1829)
Actor and director, "father of the Polish theatre". His opera *Cud mniemany, czyli Krakowiacy i Górale*, with
music by Jan Stefani, had its premiere in Warsaw on 1 March 1794. After the rising he took his company to Lwów,
where he ran the theatre until 1799. [O; Encyklopedia teatru polskiego]
- *In game:* a false rumour that his players are coming to Kraków.

## Fictional characters of note
Wilk the river king, Jędrek, Baron von Hauer, Lieutenant von Arnim, Canon Wolski, Pani Zofia, Monsieur Orlov,
Herr Lindner, Rózia, Marianna, Private Novak, Jan Wróbel, Tadeusz the apprentice, Father Hryhorij, Sergeant Kmita
and his grandson Józef, Old Salomea, Citizen Lebrun, and the townsfolk of the Rynek are invented.
